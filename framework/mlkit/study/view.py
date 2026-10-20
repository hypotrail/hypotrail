"""The single view model of a study (``hypotrail.view/1``, plan §9 bis).

``build(study_dir)`` returns one JSON-serialisable dict. ``hypotrail status`` prints
it, and every renderer consumes it rather than raw state: the HTML report, the
generated notebook, and a future webview. Its keys are frozen by
``framework/tests/study/test_contract_freeze.py`` and documented in
``docs/specs/CLI-CONTRACT.md``.

The view is deterministic for a given study content: it contains no clock reading,
so two renders of one revision see the same view.

Read-only (it uses :mod:`mlkit.study.read` only) and free of pandas, numpy, and
scikit-learn at import and at build time.
"""
from __future__ import annotations

import copy
import re
from pathlib import Path

from . import audience
from . import currency
from . import launch
from . import partition
from . import governance, read
from . import records as rec
from . import state as st
from . import texts
from .case import EPISTEMIC_STATUSES
from .errors import StudyError

SCHEMA = 'hypotrail.view/1'
VIEW_KEYS = ('schema', 'study', 'revision', 'updated', 'case', 'dataset', 'plan',
             'current_step', 'next_action', 'open_proposals', 'decisions', 'facts',
             'structure', 'results', 'stale', 'invalidations', 'executions', 'artifacts',
             'exposure', 'not_yet_defensible', 'settings', 'task',
             # Post-v0.1 (P2): the junior's conditions and holds, verbatim.
             'notes',
             # v0.2a (ADR 0006): the sealed final test, or ``status: absent``.
             'final_test',
             # v0.2a (WP-A1, R7): the engine's Python and the commands that open the
             # notebooks with it.
             'deliverables',
             # ADR 0005 (v0.2a): the confirmation mode and the study language.
             'mode', 'language',
             # v0.2a (WP-A4): the success criterion against the current evaluation, and the
             # ledger of explorations that read the target.
             'criterion', 'eda_looks',
             # v0.2b (WP-B3, R6): the teaching scenario's defaults from the case
             # (``{capacity_share: {value, status, source}}``), or ``null``.
             'scenario_defaults',
             # v0.2b (WP-B1): the number of model configurations evaluated so far.
             'trials')
NOTE_VIEW_KEYS = ('note_id', 'decision_id', 'kind', 'user_words', 'status', 'revision',
                  'resolution')
DECISION_VIEW_KEYS = ('decision_id', 'status', 'value', 'proposal_id', 'depends_on',
                      'revision', 'reason', 'confirmation', 'open_proposals',
                      # v0.2a (WP-A1): per-feature basis of a feature availability value.
                      'feature_basis')
CONFIRMATION_VIEW_KEYS = ('user_words', 'channel', 'actor', 'restatement', 'proposal_id',
                          'revision', 'time', 'authenticated', 'basis', 'delegation_scope',
                          # ADR 0005 (R3): the point the agent raised, kept by the junior.
                          'agent_concern',
                          # v0.2b (WP-B2): the mode in force when the words were accepted
                          # (``null`` for a confirmation recorded before v0.2b).
                          'mode',
                          # WP-A9 (H3): the words_contradict_value warnings kept with the
                          # agent's concern (``[]`` when none).
                          'warnings',
                          # v0.3 (WP-B, R27): for a trade-off in the junior's words, whether
                          # they gave a reason (``null`` otherwise); whether the words answer
                          # the closed adoption question (``false`` when not recorded).
                          'reason_given', 'adoption_question')
PROPOSAL_VIEW_KEYS = ('proposal_id', 'decision_id', 'value', 'restatement', 'rationale',
                      'revision', 'created',
                      # ADR 0005: the restatement per language (``null`` when none was
                      # given), and ``label``, the restatement in the study language. Before
                      # ``origin``, which stays the last key (decision CI.6).
                      'labels', 'label',
                      # Advanced companion (C9, decision CI.6): the stored origin, ``null``
                      # for a proposal recorded before C9. The report reads it.
                      'origin')
RESULT_VIEW_KEYS = ('slot', 'result_id', 'activity', 'current', 'stale_reason', 'partition',
                    'n_rows', 'values', 'blobs', 'params', 'inputs', 'code_fingerprint',
                    'environment', 'execution_id', 'exposure_id', 'started_revision',
                    'integrity')
ARTIFACT_PLACEHOLDER = {'manifest': None, 'status': 'not_rendered', 'items': {}}

SUMMARY_SCHEMA = 'hypotrail.summary/1'
SUMMARY_KEYS = ('goal', 'current_step', 'plan', 'next_action', 'open_proposals', 'decisions',
                'results', 'artifacts', 'executions', 'not_yet_defensible',
                # Post-v0.1 (P2): the junior's conditions and holds, verbatim.
                'notes',
                # Post-v0.1 fixes (D5): the open holds grouped by decision.
                'holds',
                # v0.2a (ADR 0006): the sealed final test, or ``status: absent``; before
                # ``recap``, which stays the last key of the summary.
                'final_test',
                # v0.2a (WP-A4): the success criterion and the count of target looks.
                'criterion', 'eda_looks',
                # Post-v0.1 (T8, F5): the five-line resume recap, generated from state.
                'recap',
                # v0.2a (WP-A1): who the recap is written for, and its junior variant.
                'recap_audience', 'recap_junior',
                # v0.2a (WP-A7, companion requests): the confirmation mode (ADR 0005) and the
                # commands that open the notebooks (the view's ``deliverables``), so a
                # surface needs no full view for them.
                'mode', 'deliverables',
                # v0.2b (WP-B1): the trial count.
                'trials',
                # v0.2b (WP-B6a, companion request): the teaching scenario's defaults, as
                # values only (``{capacity_share: 0.1}``), or ``null``.
                'scenario_defaults',
                # v0.3 (WP-E2, R21): the study language (ADR 0005), which the panel's
                # language setting `auto` follows.
                'language')
SUMMARY_NOTE_KEYS = ('note_id', 'decision_id', 'status', 'user_words', 'resolution_words')
SUMMARY_HOLD_KEYS = ('decision_id', 'status', 'notes')
# The limits that matter first when a chat resumes; the others are named, not quoted.
SUMMARY_PRIORITY = ('sources_changed', 'interrupted_executions', 'open_holds',
                    # v0.2b (WP-B1): the final test no longer measures what the study holds.
                    'changed_after_final_test', 'final_test_opening_interrupted',
                    # v0.2a (WP-A4): an adopting verdict against the success criterion.
                    'verdict_contradicts_criterion',
                    # B6c (H4): keeping the baseline against a criterion met on the final test.
                    'verdict_keeps_baseline_against_criterion',
                    # Post-v0.1 fixes (D2): the conclusion no longer describes the study.
                    'conclusion_outdated', 'result_integrity',
                    'adopted_rule_not_evaluated',
                    'capacity_exceeds_validation', 'small_validation_partition',
                    'code_changed', 'stale_results',
                    # D6: an inconclusive conclusion without a policy or a model choice.
                    'inconclusive_without_choice',
                    'delegated_decisions', 'unconfirmed_decisions',
                    'uncertain_features_included', 'high_cardinality_grouping',
                    'validation_is_not_independent', 'final_test_sealed')
SUMMARY_TOP = 5


# v0.2a (WP-A1): the basis of each feature's availability status. A feature named in the
# junior's words or in the restatement they answered was discussed; any other feature kept
# the status the proposal carried without being discussed, and is never shown as the
# junior's own decision. WP-A9 (H3): an undiscussed status is ``default_from_case`` only
# when the case states that very status; when the case states none (``unknown``) or another
# one, the status was the assistant's proposal (``proposed_not_discussed``). Derived at
# view time from the stored confirmation and the case, so a study written before v0.2a
# reads the same way.
DISCUSSED, DEFAULT_FROM_CASE = 'discussed', 'default_from_case'
PROPOSED_NOT_DISCUSSED = 'proposed_not_discussed'
FEATURE_BASES = (DISCUSSED, DEFAULT_FROM_CASE, PROPOSED_NOT_DISCUSSED)


def mentions(name: str, text: str) -> bool:
    """Whether ``text`` names the variable ``name`` as a word (case-insensitive; an
    underscore may be written as a space or a hyphen)."""
    if not name or not text:
        return False
    parts = [re.escape(p) for p in str(name).split('_') if p]
    pattern = r'(?<![\w])' + r'[ _-]?'.join(parts) + r'(?![\w])'
    return re.search(pattern, str(text), re.IGNORECASE) is not None


def feature_basis(value, confirmation, case_statuses: dict | None = None) -> dict | None:
    """``{feature: discussed | default_from_case | proposed_not_discussed}`` of a confirmed
    availability value, or None (no value or no confirmation). ``case_statuses`` maps a
    feature to the availability the case states (``unknown`` when it states none); without
    it, an undiscussed feature reads ``default_from_case`` (as before WP-A9)."""
    if not isinstance(value, dict) or not isinstance(confirmation, dict):
        return None
    words = ' '.join(str(confirmation.get(k) or '') for k in ('user_words', 'restatement'))
    out = {}
    for f in sorted(value):
        if mentions(f, words):
            out[f] = DISCUSSED
        elif case_statuses is None or case_statuses.get(f) == value[f]:
            out[f] = DEFAULT_FROM_CASE
        else:
            out[f] = PROPOSED_NOT_DISCUSSED
    return out


def case_availability(state: dict) -> dict | None:
    """``{feature: the availability value the case states}``, or None when the case file
    cannot be read."""
    from . import case as c
    try:
        doc = c.case_of(state).document
    except (c.CaseError, OSError):
        return None
    return {v['name']: (v.get('availability') or {}).get('value') or 'unknown'
            for v in doc['variables'] if v.get('role') == 'feature'}


CASE_UNCERTAIN_VALUES = ('uncertain', 'unknown')


def case_uncertain_marked_available(state: dict) -> list[str]:
    """B6c (M1): features the case calls uncertain (or whose availability it does not
    document) that the confirmed availability decision marks ``available_at_prediction``."""
    fa = state['decisions'].get('feature_availability') or {}
    value = fa.get('value')
    if fa.get('status') not in ('confirmed', 'reconfirm_required') or not isinstance(value, dict):
        return []
    statuses = case_availability(state) or {}
    return sorted(f for f, v in value.items() if v == 'available_at_prediction'
                  and statuses.get(f) in CASE_UNCERTAIN_VALUES)


def _case_uncertain_limit(state: dict, defensible: list) -> None:
    """B6c (M1): a feature used although the case calls its availability uncertain is a
    limit, whether the decision says ``uncertain_included`` or ``available_at_prediction``;
    ``uncertain_features_included`` lists both, ``case_uncertain`` the second kind."""
    overridden = case_uncertain_marked_available(state)
    if not overridden:
        return
    text = ('The case calls the availability of these features uncertain (or does not '
            'document it), yet they are used as known at prediction time: '
            + ', '.join(overridden) + '. Check that they are known at that moment.')
    item = next((i for i in defensible if i['id'] == 'uncertain_features_included'), None)
    if item is None:
        defensible.append({'id': 'uncertain_features_included', 'features': overridden,
                           'case_uncertain': overridden, 'text': text})
    else:
        item['features'] = sorted(set(item['features']) | set(overridden))
        item['case_uncertain'] = overridden
        item['text'] = f'{item["text"]} {text}'


def _decisions(state: dict) -> dict:
    out = {}
    fa = state['decisions'].get('feature_availability') or {}
    statuses = case_availability(state) if isinstance(fa.get('confirmation'), dict) else None
    for d in st.decision_ids(state):
        dec = state['decisions'][d]
        conf = dec['confirmation']
        out[d] = {'decision_id': d, 'status': dec['status'], 'value': dec['value'],
                  'proposal_id': dec['proposal_id'], 'depends_on': list(dec['depends_on']),
                  'revision': dec['revision'], 'reason': dec['reason'],
                  'confirmation': ({**{k: conf.get(k) for k in CONFIRMATION_VIEW_KEYS},
                                    'basis': st.confirmation_basis(conf),
                                    'warnings': list(conf.get('warnings') or []),
                                    'adoption_question': bool(conf.get('adoption_question'))}
                                   if isinstance(conf, dict) else None),
                  'open_proposals': sorted(p['proposal_id'] for p in st.open_proposals(state)
                                           if p['decision_id'] == d),
                  'feature_basis': (feature_basis(dec['value'], conf, statuses)
                                    if d == 'feature_availability' else None)}
    return out


def _facts(state: dict) -> dict:
    by_status = {s: [] for s in EPISTEMIC_STATUSES}
    for fid in sorted(state['facts']):
        f = state['facts'][fid]
        by_status[f['status']].append({'id': fid, 'value': f['value'], 'source': f['source']})
    return {'by_status': by_status, 'count': len(state['facts'])}


def _results(study: read.Study, state: dict) -> dict:
    out = {}
    for slot in sorted(state['current']):
        rid = state['current'][slot]
        item = {k: None for k in RESULT_VIEW_KEYS}
        currency = study.currency(rid)
        item.update(slot=slot, result_id=rid, current=currency['current'],
                    stale_reason=currency['reason'], integrity='ok')
        try:
            entry = study.result(rid)
        except StudyError as exc:
            item.update(integrity=exc.code, current=False, stale_reason=state['stale'].get(rid))
        else:
            item.update(activity=entry['activity'], partition=entry['partition'],
                        n_rows=entry['n_rows'], values=entry['output']['values'],
                        blobs=entry['blobs'], params=entry['params'], inputs=entry['inputs'],
                        code_fingerprint=entry['code']['fingerprint'],
                        environment=entry['environment'], execution_id=entry['execution_id'],
                        exposure_id=entry['exposure_id'],
                        started_revision=entry['started_revision'])
        out[slot] = item
    return out


def _artifacts(study: read.Study, state: dict) -> dict:
    """The manifest with each artefact's **effective** status (``currency.effective_status``).

    The stored ``status`` only says how the last render went; an artefact written for an
    earlier revision, citing a result that is no longer current, or whose file was deleted
    or changed since (M4), is ``stale`` even if that render succeeded; ``stale_reason`` says
    which (``currency.STALE_REASONS``, or null). The stored value stays visible as
    ``recorded_status``.
    """
    raw = study.artifacts()
    if raw is None:
        return dict(ARTIFACT_PLACEHOLDER, items={})
    if not isinstance(raw, dict) or not isinstance(raw.get('artifacts'), dict):
        return {'manifest': read.ARTIFACTS_FILE, 'status': 'unreadable', 'items': {}}
    items = {}

    def current(rid):
        return study.currency(rid)['current']
    for name, item in raw['artifacts'].items():
        if not isinstance(item, dict):
            continue
        file = currency.file_check(study.study_dir, item)     # M4: the bytes on disk
        items[name] = {**item, 'recorded_status': item.get('status'),
                       'status': currency.effective_status(item, state, current, file),
                       'stale_reason': currency.stale_reason(item, state, current, file),
                       'message': currency.message(name, item, state, current, file)}
        # v0.2a (WP-A1): the message names paths and asks for a render (agent).
        items[name].update(audience.artifact(name, items[name]))
    return {'manifest': read.ARTIFACTS_FILE,
            'status': currency.overall(i['status'] for i in items.values()), 'items': items}


def rid_reason(item: dict, key: str):
    """A key of a result item's derived stale reason (``code_changed``, ...), or None."""
    reason = item.get('stale_reason')
    return reason.get(key) if isinstance(reason, dict) else None


def scenario_defaults(state: dict) -> dict | None:
    """The case's ``scenario_defaults`` (v0.2b, WP-B3), or None: none declared, or the case
    file can no longer be read (``sources_changed`` then says why)."""
    from . import case as c
    try:
        return copy.deepcopy(c.case_of(state).scenario_defaults)
    except (c.CaseError, OSError):
        return None


def _with_default_rule(action: dict, defaults: dict | None) -> dict:
    """WP-A9 (R6): at the policy step of a teaching case (``scenario_defaults
    .capacity_share``), the next action carries the scenario's rule as ``default_value``
    (``share:<p>``), as the preprocessing step carries the engine's default. The agent asks
    the capacity as a share and presents it as the exercise's assumption."""
    share = ((defaults or {}).get('capacity_share') or {}).get('value')
    if share is None or action.get('kind') not in ('propose', 'run') \
            or (action.get('decision') or action.get('step')) != 'policy':
        return action
    return {**action, 'default_value': rec.canonical_rule(f'share:{share}')
            or f'share:{share}'}


def _assumed_capacity(state: dict, defaults: dict | None) -> list[dict]:
    """``capacity_assumed_for_exercise`` (R6) when the adopted policy acts on the share of
    the scored rows the teaching scenario assumes, not on a figure from the team."""
    share = ((defaults or {}).get('capacity_share') or {}).get('value')
    decision = state['decisions'].get('policy') or {}
    rule = decision.get('value')
    if share is None or decision.get('status') not in ('confirmed', 'reconfirm_required') \
            or not isinstance(rule, str):
        return []
    parsed = rec.parse_rule(rule)
    if parsed is None or parsed[0] != 'share' or abs(parsed[1] - float(share)) > 1e-12:
        return []
    pct = audience.share_percent(share)
    return [{'id': 'capacity_assumed_for_exercise', 'rule': rec.canonical_rule(rule),
             'share': share,
             'text': f'Capacity assumed for the exercise: acting on the top {pct} of the '
                     f'scored rows is the teaching scenario\'s assumption, not a figure from a '
                     f'team that does the follow-up. With a real team, ask how many it can '
                     f'handle and evaluate that capacity.'}]


def _adopted_without_evaluation(state: dict, results: dict) -> str | None:
    """The adopted policy rule when no current policy evaluation covers it."""
    if 'policy' not in state['decisions']:
        return None
    decision = state['decisions']['policy']
    rule = decision['value']
    if decision['status'] not in ('confirmed', 'reconfirm_required') or not isinstance(rule, str):
        return None
    item = results.get('policy.evaluation')
    if item and item['current'] and item['integrity'] == 'ok':
        params = item['params'] if isinstance(item['params'], dict) else {}
        rules = params.get('rules') or ([params['rule']] if params.get('rule') else [])
        models = params.get('models') or ['fit.logistic']
        if (rec.policy_rule(rule) or rule) in {rec.canonical_rule(r) or r for r in rules} \
                and rec.policy_model(rule) in models:
            return None
    return rule


# G.12 (post-v0.1): small-data warnings, never refusals. A validation partition with at
# most SMALL_VALIDATION_ROWS rows, or (binary) at most SMALL_VALIDATION_POSITIVES positive
# rows, is named (post-v0.1 fixes, D4: the thresholds are inclusive, so the boundary the
# plan calls small is small); so is a capacity that selects every validation row, and an
# exploration that folds a high-cardinality column into its largest groups and "other".
SMALL_VALIDATION_ROWS = 30
SMALL_VALIDATION_POSITIVES = 5


def _citable(item) -> bool:
    return bool(item) and item['current'] and item['integrity'] == 'ok' \
        and isinstance(item.get('values'), dict)


def small_partition_warning(split_values, binary: bool) -> dict | None:
    """The ``small_validation_partition`` warning of a split result's values, or None
    (G.12; inclusive thresholds since D4). Shared by the view and ``preview policy``."""
    if not isinstance(split_values, dict):
        return None
    part = (split_values.get('partitions') or {}).get('validation') or {}
    n, positives = part.get('n_rows'), part.get('n_positive')
    few_rows = isinstance(n, int) and n <= SMALL_VALIDATION_ROWS
    few_positives = binary and isinstance(positives, int) \
        and positives <= SMALL_VALIDATION_POSITIVES
    if not (few_rows or few_positives):
        return None
    counted = f'{n} rows' + (f', {positives} of them positive' if binary
                             and isinstance(positives, int) else '')
    item = {'id': 'small_validation_partition', 'slots': ['split'], 'n_rows': n,
            'min_rows': SMALL_VALIDATION_ROWS,
            'text': f'The validation partition is small ({counted}): every validation '
                    'figure rests on these rows, its interval is wide, and a '
                    'difference between models on them can be chance.'}
    if binary:
        item.update(n_positive=positives, min_positive=SMALL_VALIDATION_POSITIVES)
    return item


def capacity_warning(rules, n) -> dict | None:
    """The ``capacity_exceeds_validation`` warning for ``rules`` on ``n`` validation rows,
    or None (G.12). Shared by the view and ``preview policy`` (D4)."""
    over = []
    for rule in rules or []:
        kind, _, k = str(rule).partition(':')
        if kind == 'capacity' and k.isdigit() and isinstance(n, int) and int(k) >= n:
            over.append(rule)
    if not over:
        return None
    return {'id': 'capacity_exceeds_validation', 'rules': over, 'n_rows': n,
            'text': f'A capacity at least as large as the {n} validation rows '
                    'selects every row: its figures describe selecting everyone, '
                    'not a ranking.'}


def _small_data(state: dict, results: dict) -> list[dict]:
    """The G.12 warnings of ``not_yet_defensible``, from current, verified results."""
    out = []
    binary = st.task_of(state) == st.BINARY
    split = results.get('split')
    if _citable(split):
        item = small_partition_warning(split['values'], binary)
        if item:
            out.append(item)
    evaluation = results.get('policy.evaluation')
    if _citable(evaluation) and isinstance(evaluation.get('params'), dict):
        item = capacity_warning(evaluation['params'].get('rules'),
                                evaluation['values'].get('n'))
        if item:
            out.append(item)
    folded = []
    for slot, item in sorted(results.items()):
        other = item['values'].get('other') if _citable(item) else None
        if isinstance(other, dict):
            folded.append((slot, item['values']))
    if folded:
        named = '; '.join(f'{v.get("column")}: {v.get("n_groups")} groups, the '
                          f'{v.get("max_groups")} largest shown' for _, v in folded)
        out.append({'id': 'high_cardinality_grouping', 'slots': [slot for slot, _ in folded],
                    'text': 'A column with many values is shown by its largest groups, the '
                            f'other values folded into one group ({named}); a rate or a mean '
                            'of the folded group mixes many small groups.'})
    return out


def _compact_value(decision_id: str, value):
    """A decision value for the summary: availability is grouped by status."""
    if decision_id == 'feature_availability' and isinstance(value, dict):
        grouped: dict[str, list[str]] = {}
        for feature, status in sorted(value.items()):
            grouped.setdefault(status, []).append(feature)
        return grouped
    return value


def _fact(view: dict, fact_id: str) -> dict | None:
    for status, items in view['facts']['by_status'].items():
        for f in items:
            if f['id'] == fact_id:
                return {'value': f['value'], 'status': status}
    return None


def _holds(notes: list[dict], decisions: dict) -> list[dict]:
    """The open holds grouped by decision, in plan order (D5): one entry per held decision,
    ``{decision_id, status, notes: [{note_id, user_words}]}`` (``status`` is the decision's),
    so a restated hold is seen next to the one already recorded."""
    out = []
    for d, dec in decisions.items():
        held = [{'note_id': n['note_id'], 'user_words': n['user_words']}
                for n in notes if n['status'] == 'open' and n['decision_id'] == d]
        if held:
            out.append({'decision_id': d, 'status': dec['status'], 'notes': held})
    return out


def summary(view: dict) -> dict:
    """A compact digest of a view (``hypotrail status --summary``, D3).

    It holds what a chat needs to resume and to decide its next move, in a few
    kilobytes: the study goal in the case's words, the position (the plan's step ids,
    titles and statuses), the open proposals with
    their restatement, each decision with its value, status, basis and recorded words,
    the current results by slot, each deliverable with its status and one sentence,
    interrupted and late executions, the first limits of ``not_yet_defensible``, and
    ``recap``, five lines a new chat may quote (:func:`recap`). The full view stays in ``hypotrail status --json``.
    """
    pt = view['decisions']['prediction_time']
    if pt['value'] is not None:
        prediction_time = {'value': pt['value'], 'source': 'decision', 'status': pt['status']}
    else:
        fact = _fact(view, 'prediction_time')
        prediction_time = ({'value': fact['value'], 'source': 'case', 'status': fact['status']}
                           if fact else None)
    goal = {'intended_use': _fact(view, 'intended_use'), 'decision': _fact(view, 'decision'),
            'observation_unit': _fact(view, 'observation_unit'),
            'prediction_time': prediction_time}
    decisions = {}
    for d, dec in view['decisions'].items():
        conf = dec['confirmation']
        decisions[d] = {'status': dec['status'], 'value': _compact_value(d, dec['value']),
                        'basis': conf['basis'] if conf else None,
                        'delegation_scope': conf['delegation_scope'] if conf else None,
                        'user_words': conf['user_words'] if conf else None,
                        'reason': dec['reason'], 'open_proposals': dec['open_proposals'],
                        'feature_basis': _compact_value('feature_availability',
                                                        dec.get('feature_basis'))}
    proposals = [{'proposal_id': p['proposal_id'], 'decision_id': p['decision_id'],
                  'value': _compact_value(p['decision_id'], p['value']),
                  'restatement': p['restatement'], 'revision': p['revision']}
                 for p in view['open_proposals']]
    results = {slot: {'result_id': r['result_id'], 'current': r['current'],
                      'stale_reason': r['stale_reason'], 'integrity': r['integrity']}
               for slot, r in view['results'].items()}
    artifacts = {'status': view['artifacts']['status'],
                 'items': {name: {'status': i.get('status'), 'revision': i.get('revision'),
                                  'last_ok_revision': i.get('last_ok_revision'),
                                  'message': i.get('message'),
                                  'audience': i.get('audience'),
                                  'junior_message': i.get('junior_message')}
                           for name, i in view['artifacts']['items'].items()}}
    executions = {
        'active': sorted(view['executions']['active']),
        'interrupted': [{'execution_id': e, 'activity': r.get('activity'),
                         'reason': r.get('reason')}
                        for e, r in sorted(view['executions']['interrupted'].items())],
        'late': [{'execution_id': e, 'activity': r.get('activity'), 'reason': r.get('reason'),
                  'result_id': r.get('result_id')}
                 for e, r in sorted(view['executions']['late'].items())],
        'suspected_interrupted': [{'execution_id': e, 'activity': r.get('activity'),
                                   'liveness': r.get('liveness'), 'reason': r.get('reason')}
                                  for e, r in sorted(view['executions']['suspected_interrupted']
                                                     .items())]}
    rank = {k: i for i, k in enumerate(SUMMARY_PRIORITY)}
    ordered = sorted(view['not_yet_defensible'],
                     key=lambda x: rank.get(x['id'], len(SUMMARY_PRIORITY)))
    defensible = {'top': [{'id': x['id'], 'text': x['text'],
                           'audience': x.get('audience', audience.JUNIOR),
                           # Compact: null when ``text`` is already written for the junior.
                           'junior_text': (audience.junior_text(x)
                                           if x.get('audience') == audience.AGENT else None)}
                          for x in ordered[:SUMMARY_TOP]],
                  'more': [x['id'] for x in ordered[SUMMARY_TOP:]]}
    plan = [{'id': step['id'], 'title': step['title'], 'status': step['status']}
            for step in view['plan']]
    notes = [{'note_id': n['note_id'], 'decision_id': n['decision_id'], 'status': n['status'],
              'user_words': n['user_words'],
              'resolution_words': (n['resolution'] or {}).get('user_words')}
             for n in view['notes']]
    out = {'goal': goal, 'current_step': view['current_step'], 'plan': plan,
           'next_action': view['next_action'], 'open_proposals': proposals,
           'decisions': decisions, 'results': results, 'artifacts': artifacts,
           'executions': executions, 'not_yet_defensible': defensible, 'notes': notes,
           'holds': _holds(notes, decisions), 'final_test': view['final_test'],
           'criterion': _compact_criterion(view.get('criterion')),
           'eda_looks': ({k: view['eda_looks'][k] for k in ('target_looks', 'results')}
                         if view.get('eda_looks') else None)}
    out['recap'] = recap(out, view)
    out['recap_audience'] = audience.AGENT
    out['recap_junior'] = recap(out, view, junior=True)
    out['mode'] = view.get('mode')
    out['deliverables'] = _compact_deliverables(view.get('deliverables'))
    out['trials'] = ({k: view['trials'][k] for k in SUMMARY_TRIALS_KEYS}
                     if view.get('trials') else None)
    out['scenario_defaults'] = _compact_scenario(view.get('scenario_defaults'))
    out['language'] = view.get('language')
    return {k: out[k] for k in SUMMARY_KEYS}


def _compact_scenario(defaults):
    """WP-B6a: the scenario defaults as ``{name: value}`` (the status is always
    ``scenario_assumption``; the source stays in the full view)."""
    if not isinstance(defaults, dict) or not defaults:
        return None
    return {k: (v or {}).get('value') if isinstance(v, dict) else v
            for k, v in sorted(defaults.items())}


SUMMARY_TRIALS_KEYS = ('count',)


# WP-A7: the summary keeps each launch's argument list only (the full view also has the
# interpreter and the shell form), so the summary stays compact.
SUMMARY_DELIVERABLES_KEYS = ('launch',)
SUMMARY_LAUNCH_KEYS = ('mode', 'path', 'argv')


def _compact_deliverables(deliverables):
    if not isinstance(deliverables, dict):
        return None
    return {'launch': {name: {k: item.get(k) for k in SUMMARY_LAUNCH_KEYS}
                       for name, item in (deliverables.get('launch') or {}).items()}}


SUMMARY_CRITERION_KEYS = ('decision_status', 'value', 'status', 'gain', 'low', 'high',
                          'minimum', 'unit', 'rule', 'result_id', 'contradicts_verdict',
                          # v0.2b (WP-B1): the criterion on the final test.
                          'final_test',
                          # v0.2b (WP-B6a, companion request): the model the criterion reads.
                          'model',
                          # B6c (H4): where the criterion is judged, and its status there.
                          'judged_on', 'judged_status')


def _compact_criterion(criterion):
    if not criterion:
        return None
    return {k: criterion.get(k) for k in SUMMARY_CRITERION_KEYS}


# --- the resume recap (post-v0.1, T8 and F5) ------------------------------------------

RECAP_LABELS = ('Goal', 'Decided', 'Now', 'Next', 'Limit')
DECISION_LABELS = {'prediction_time': 'prediction moment',
                   'feature_availability': 'feature availability', 'split': 'split',
                   'policy': 'policy', 'model_choice': 'model choice',
                   'conclusion': 'conclusion',
                   # v0.2a (WP-A4)
                   'success_criterion': 'success criterion', 'preprocessing': 'preprocessing',
                   # v0.2b (WP-B1)
                   'model_variant': 'variant', 'final_test': 'final test'}
# A regression study's model choice (M3), in words: the recap never says "policy".
MODEL_CHOICE_WORDS = {'fit.linear': 'the linear model', 'fit.baseline': 'the mean baseline',
                      'fit.variant': 'the variant'}
# The limit quoted by the recap: the most urgent of ``not_yet_defensible`` that the other
# lines do not already say (unconfirmed decisions are the "Decided" and "Next" lines).
RECAP_LIMIT_SKIP = ('unconfirmed_decisions', 'open_holds', 'conclusion_outdated')


def _spaced(identifier) -> str:
    """``stratified_random`` as "stratified random"."""
    return ' '.join(str(identifier).split('_'))


def _fact_value(item) -> str | None:
    return item.get('value') if isinstance(item, dict) else None


# P3: a regression recap cites the current validation MAE with its result id prefix.
RECAP_RID = 8


def _regression_errors(view: dict) -> dict | None:
    """The validation MAE of each model, as displayed (two decimals), with the unit and the
    result id of the current, verified ``evaluate.regression``; None otherwise."""
    item = view['results'].get('evaluate.regression')
    if not item or not item['current'] or item['integrity'] != 'ok' \
            or not isinstance(item.get('values'), dict):
        return None
    models = item['values'].get('models') or {}
    mae = {slot: f'{m["mae"]:.2f}' for slot, m in models.items()
           if isinstance(m, dict) and isinstance(m.get('mae'), (int, float))}
    unit = item['values'].get('unit') or ''
    return {'mae': mae, 'unit': unit, 'result_id': item['result_id']} if mae else None


# D10: a binary recap cites the headline policy result: the logistic model's precision and
# recall at one evaluated rule, as the report displays them (one decimal, in percent), on the
# validation rows, with the result id prefix.
HEADLINE_MODEL = 'fit.logistic'


def _pct(value) -> str | None:
    return f'{100 * value:.1f}%' if isinstance(value, (int, float)) \
        and not isinstance(value, bool) else None


def _policy_headline(view: dict, summary_out: dict) -> dict | None:
    """The headline of the current, verified ``policy.evaluation`` (D10), or None: the
    adopted rule when it was evaluated, else the rule of the open policy proposal, else the
    first evaluated rule. ``adopted`` says whether it is the confirmed (or to-reconfirm)
    policy."""
    item = view['results'].get('policy.evaluation')
    if not _citable(item):
        return None
    by_rule = {rec.canonical_rule(r) or r: r for r in (item['values'].get('rules') or {})}
    params = item['params'] if isinstance(item.get('params'), dict) else {}
    decision = summary_out['decisions'].get('policy') or {}
    adopted = decision.get('value') if decision.get('status') in (
        'confirmed', 'reconfirm_required') else None
    candidates = [adopted] + [p['value'] for p in summary_out['open_proposals']
                              if p['decision_id'] == 'policy'] + list(params.get('rules') or [])
    found = next(((by_rule[rec.policy_rule(c) or c], c) for c in candidates
                  if isinstance(c, str) and (rec.policy_rule(c) or c) in by_rule), None)
    if found is None:
        return None
    rule, chosen = found
    # WP-B1: the headline names the model the policy applies its rule to.
    slot = rec.policy_model(chosen)
    model = ((item['values']['rules'][rule] or {}).get('models') or {}).get(slot) or {}
    precision, recall = _pct(model.get('precision')), _pct(model.get('recall'))
    if precision is None and recall is None:
        return None
    figures = ', '.join(f'{name} {v}' for name, v in (('precision', precision),
                                                      ('recall', recall)) if v)
    n = item['values'].get('n')
    where = ('out-of-fold development rows' if item['values'].get('evaluation') == 'out_of_fold'
             else 'validation rows')
    rows = f' on the {n} {where}' if isinstance(n, int) else f' on the {where}'
    named = 'the variant' if slot == 'fit.variant' else 'the logistic model'
    return {'rule': rule, 'adopted': adopted is not None and (rec.canonical_policy(adopted)
                                                              or adopted) == (
                                                                  rec.canonical_policy(chosen)
                                                                  or chosen),
            'text': f'{named} at {rule}{rows}: {figures}, result '
                    f'{item["result_id"][:RECAP_RID]}',
            # v0.2a (WP-A1): the junior recap names no result id; WP-A7: nor the rule's
            # token, which it says in words.
            'junior_text': f'{named}, {audience.rule_words(rule)},{rows}: {figures}',
            # WP-A9 (M6): after the rule itself (the Decided line), without repeating it.
            'short_text': f'{named}{rows}: {figures}, result '
                          f'{item["result_id"][:RECAP_RID]}',
            'short_junior_text': f'{named}{rows}: {figures}'}


def _recap_decision(decision_id: str, d: dict, errors: dict | None = None,
                    headline: dict | None = None, junior: bool = False,
                    cv: bool = False) -> str:
    # v0.2a (WP-A7): the junior recap names each decision and its value in words, never a
    # recorded token (a rule, a model slot, a verdict id).
    label = audience.decision_words(decision_id) if junior else DECISION_LABELS[decision_id]
    value = d['value']
    if decision_id == 'feature_availability' and isinstance(value, dict):
        parts = []
        excluded = sorted(value.get('not_available', []) + value.get('uncertain_excluded', []))
        doubtful = sorted(value.get('uncertain_included', []))
        if excluded:
            parts.append('excluded ' + ', '.join(excluded))
        if doubtful:
            parts.append('kept despite a doubt: ' + ', '.join(doubtful))
        text = f'{label} ({"; ".join(parts) if parts else "every feature kept"})'
    elif decision_id == 'split' and isinstance(value, dict) and value.get('method') in \
            st.CV_METHODS:
        # WP-B1: the evaluation scheme.
        method = (audience.CV_METHOD_WORDS.get(value['method'], _spaced(value['method']))
                  if junior else _spaced(value['method']))
        text = f'{label} ({value.get("folds")}-fold cross-validation, {method})'
    elif decision_id == 'model_variant' and isinstance(value, dict):
        text = f'{label} ({audience.variant_words(value)})'
    elif decision_id == 'final_test' and isinstance(value, dict):
        # B6c (Low): "the final test, opened once", never "the opening ... opened".
        opened = 'the final test, opened once' if junior else f'{label} opened'
        text = f'{opened} ({audience.model_words(value.get("model"))}' + (
            f', {audience.rule_words(value["rule"])})' if junior and value.get('rule') else
            f' at {value["rule"]})' if value.get('rule') else ')')
    elif decision_id == 'split' and isinstance(value, dict):
        method = _spaced(value.get('method', 'split'))
        fraction = value.get('validation_fraction')
        share = (f', {round(100 * fraction):d}% for validation'
                 if isinstance(fraction, (int, float)) and not isinstance(fraction, bool) else '')
        if value.get('method') == 'ordinal_cutoff' and value.get('column') is not None:
            share = f' on {value["column"]}, validation from {value.get("cutoff")}'
        text = f'{label} ({method}{share})'
    elif decision_id in ('policy',) and isinstance(value, str):
        text = f'{label}: {audience.policy_words(value)}' if junior else f'{label} {value}'
        if headline and headline['adopted']:
            text += f' ({headline["short_junior_text" if junior else "short_text"]})'
    elif decision_id == 'model_choice' and isinstance(value, str):
        text = f'{label}: {MODEL_CHOICE_WORDS.get(value, value)}'
        mae = (errors or {}).get('mae', {}).get(value)
        if mae is not None:
            where = 'out-of-fold' if cv else 'validation'
            text += (f' ({where} MAE {mae} {errors["unit"]})' if junior else
                     f' ({where} MAE {mae} {errors["unit"]}, result '
                     f'{errors["result_id"][:RECAP_RID]})')
    elif decision_id == 'conclusion' and isinstance(value, dict):
        verdict = value.get('verdict', '')
        text = (f'{label}: {audience.VERDICT_WORDS.get(verdict, _spaced(verdict))}' if junior
                else f'{label} {_spaced(verdict)}'.strip())
    elif decision_id == 'success_criterion' and isinstance(value, dict):
        if 'min_points' in value:
            text = (f'{label} (precision gain over the baseline of at least '
                    f'{value["min_points"]} points)')
        else:
            # B6c (M3): the error the criterion reads, in the study's scheme.
            error = 'out-of-fold error' if cv else 'validation error'
            text = (f'{label} ({error} at least '
                    f'{round(100 * value.get("min_share", 0))}% below the mean baseline)')
    elif decision_id == 'preprocessing' and isinstance(value, dict):
        text = f'{label} ({preprocessing_words(value)})'
        if value.get('data_contingent'):
            text += ' [motivated by a look at the target]'
    else:
        text = label
    notes = []
    if d['basis'] == st.DELEGATED_DEFAULT:
        notes.append('delegated to the assistant')
    if d['status'] == 'reconfirm_required':
        notes.append('to confirm again')
    return text + (f' [{", ".join(notes)}]' if notes else '')


def preprocessing_words(value: dict) -> str:
    """A preprocessing value in words (v0.2a, WP-A4)."""
    from . import governance
    if governance.is_default(value):
        return 'the default: no missing-value indicator, every category kept, no cap, no transform'
    parts = []
    missing = value.get('missing')
    if missing == 'indicator':
        parts.append('missing-value indicators')
    elif isinstance(missing, dict):
        named = sorted(c for c, v in missing.items() if v == 'indicator')
        if named:
            parts.append('missing-value indicators for ' + ', '.join(named))
    if value.get('rare_category_min_rows'):
        parts.append(f'categories with fewer than {value["rare_category_min_rows"]} training '
                     f'rows grouped')
    if value.get('caps'):
        parts.append('caps on ' + ', '.join(sorted(value['caps'])))
    if value.get('log_transform'):
        parts.append('log transform of ' + ', '.join(value['log_transform']))
    return '; '.join(parts) if parts else 'the default'


def _recap_next(summary_out: dict, view: dict, junior: bool = False) -> str:
    nxt = summary_out['next_action']
    kind = nxt.get('kind')
    if junior and kind != 'await_user_words' and nxt.get('audience') == audience.AGENT \
            and nxt.get('junior_message'):
        # v0.2a (WP-A1): an instruction to the agent is never quoted to the junior.
        return str(nxt['junior_message']).strip()
    titles = {s['id']: s['title'] for s in summary_out['plan']}
    if kind in ('outcome_unknown', 'acknowledge_interruption'):
        activity = nxt.get('activity') or 'an activity'
        return (f'a run of {activity} stopped and its outcome is unknown; decide whether to '
                'acknowledge it before anything else.')
    if kind == 'reconfirm':
        return f'confirm the {DECISION_LABELS.get(nxt.get("decision"), "decision")} again.'
    if kind == 'await_user_words':
        proposal = next((p for p in summary_out['open_proposals']
                         if p['proposal_id'] == nxt.get('proposal_id')), None)
        label = DECISION_LABELS.get(nxt.get('decision'), 'decision')
        restatement = proposal['restatement'] if proposal else ''
        return f'whether you adopt the {label}: "{restatement}"'
    if kind in ('propose', 'run', 'blocked'):
        if nxt.get('step') == summary_out['current_step']:
            return str(nxt.get('message', '')).strip()
        title = titles.get(nxt.get('step'), nxt.get('step') or 'the next step')
        return f'{title}: {nxt.get("message", "")}'.strip()
    if kind == 'show_data_card':
        # WP-A9 (M4): step 0 is the first step of the plan, not its end.
        return ('show the junior the data card (hypotrail data): what one row describes, the '
                'columns and their meaning, and five example rows; nothing to confirm. Then '
                'propose the prediction moment.')
    if kind != 'done' and nxt.get('message'):
        return str(nxt['message']).strip()
    return 'nothing left in the plan; review what is not yet defensible.'


def _junior_now(summary_out: dict, titles: dict, step: str) -> str:
    """The ``Now`` line's step for the junior (v0.2a, WP-A7): the step that waits for them.

    An open proposal or a reconfirmation names its decision's step, which may come before
    the engine's current step (a confirmed decision reopened by a new proposal); a run with
    an unknown outcome is named in words. Otherwise the current step, as for the agent."""
    nxt = summary_out['next_action'] or {}
    kind = nxt.get('kind')
    if kind in ('await_user_words', 'reconfirm'):
        decision = nxt.get('decision')
        title = titles.get(decision) or _capital_first(audience.decision_words(decision))
        return (f'{title}, waiting for your answer' if kind == 'await_user_words'
                else f'{title}, waiting for you to confirm it again')
    if kind in ('outcome_unknown', 'acknowledge_interruption'):
        named = (f'a run of {audience.activity_words(nxt["activity"])}' if nxt.get('activity')
                 else 'a run')
        return f'{named} stopped and its outcome is unknown, waiting for your acknowledgement'
    return step


def _capital_first(text: str) -> str:
    return text[:1].upper() + text[1:]


def _mid_sentence(text: str) -> str:
    """``text`` placed mid-sentence: a capital first letter of an ordinary word is lowered
    ("Before the call" -> "before the call"); an acronym or a name in capitals is kept."""
    if len(text) >= 2 and text[0].isupper() and text[1].islower():
        return text[0].lower() + text[1:]
    return text


def _deliverables_line(items: dict) -> str:
    """The deliverables part of the ``Now`` line: what is not up to date, and what has not
    been rendered yet (v0.2a, WP-A1: never "up to date" before a first render)."""
    unwritten = [n for n in ('report', 'notebook')
                 if n not in items or items[n].get('status') == 'not_rendered']
    behind = sorted(name for name, item in items.items()
                    if item.get('status') not in ('ok', 'not_rendered') and name != 'workbench')
    if not unwritten and not behind:
        return 'the report and notebook are up to date'
    parts = []
    if behind:
        parts.append(', '.join(behind) + ' not up to date')
    if unwritten:
        parts.append(' and '.join(unwritten) + ' not rendered yet')
    return '; '.join(parts)


def recap(summary_out: dict, view: dict, junior: bool = False) -> list[str]:
    """Five lines a new chat may quote to resume (post-v0.1, T8 and F5).

    Deterministic, from the summary and the view only, with no revision numbers or ids
    except the result id prefix next to a headline figure (P3, D10):
    1. ``Goal``: the intended use and the prediction moment (decided or from the case);
    2. ``Decided``: each confirmed decision, with the excluded features by name and a
       note when it was delegated or must be confirmed again (a regression study names
       its model choice, "the linear model" or "the mean baseline", where a binary study
       names its policy, with the logistic model's precision and recall at that rule from
       the current policy evaluation, D10);
    3. ``Now``: the current step and the deliverables that are not up to date (before the
       policy is adopted, the latest evaluated rule's precision and recall, D10);
    4. ``Next``: the next decision or action (an open restatement is quoted, so a
       stand-in figure keeps its caveat);
    5. ``Limit``: the most urgent limit of ``not_yet_defensible`` the other lines do not
       already say.

    ``junior`` (v0.2a, WP-A1): the variant written for the junior (``recap_junior``): no
    result id, the junior variant of an agent instruction, and holds in the second person.
    """
    goal = summary_out['goal']
    use = _fact_value(goal['intended_use']) or 'not stated in the case'
    pt = goal['prediction_time']
    if pt is None:
        moment = 'not decided yet'
    elif pt['source'] == 'decision' and pt['status'] == 'confirmed':
        moment = _mid_sentence(str(pt['value']))
    else:
        moment = f'{_mid_sentence(str(pt["value"]))} (from the case, not decided yet)'
    errors = _regression_errors(view)
    headline = _policy_headline(view, summary_out) if st.task_of(view.get('task')) == st.BINARY \
        else None
    cv = texts.scheme_of(view) == texts.CROSS_VALIDATION
    decided = [_recap_decision(d, item, errors, headline, junior, cv)
               for d, item in summary_out['decisions'].items()
               if item['status'] in ('confirmed', 'reconfirm_required')]
    titles = {s['id']: s['title'] for s in summary_out['plan']}
    step = titles.get(summary_out['current_step'], 'every step is done') \
        if summary_out['current_step'] else 'every step is done'
    if junior:
        step = _junior_now(summary_out, titles, step)
    deliverables = _deliverables_line(summary_out['artifacts']['items'])
    chosen = summary_out['decisions'].get('model_choice') or {}
    if errors and chosen.get('status') not in ('confirmed', 'reconfirm_required'):
        # Before the model choice, "Now" gives both validation errors (P3).
        named = '; '.join(f'{MODEL_CHOICE_WORDS.get(slot, slot)} {mae} {errors["unit"]}'
                          for slot, mae in sorted(errors['mae'].items()))
        step += (f' (validation MAE: {named})' if junior else
                 f' (validation MAE: {named}; result {errors["result_id"][:RECAP_RID]})')
    if headline and not headline['adopted']:
        # D10: before a rule is adopted, "Now" gives the latest evaluated figures.
        step += (f' (latest policy evaluation: '
                 f'{headline["junior_text" if junior else "text"]})')
    limits = [x for x in view['not_yet_defensible'] if x['id'] not in RECAP_LIMIT_SKIP
              # v0.3 (WP-A, R34): a limit marked not for the junior stays in the agent's.
              and not (junior and x.get('junior') is False)]
    rank = {k: i for i, k in enumerate(SUMMARY_PRIORITY)}
    limits.sort(key=lambda x: rank.get(x['id'], len(SUMMARY_PRIORITY)))
    if limits:
        limit = audience.junior_text(limits[0]) if junior else limits[0]['text']
    else:
        limit = 'none recorded.'
    nxt = _recap_next(summary_out, view, junior).rstrip()
    holds = summary_out.get('holds') or []
    if holds:
        # P2: a condition the junior stated stays visible in every chat until resolved;
        # D5: the holds of one decision are quoted together.
        said = '; '.join('; '.join(f'"{n["user_words"]}"' for n in h['notes'])
                         + f' (the {DECISION_LABELS.get(h["decision_id"], h["decision_id"])})'
                         for h in holds)
        nxt += ('' if nxt.endswith(('.', '"', '?')) else '.') + (
            f' On hold in your words: {said}; nothing on hold is confirmed until you '
            'resolve it.' if junior else
            f" On hold in the junior's words: {said}; nothing on hold is confirmed until "
            'they resolve it.')
    lines = [f'Goal: {use}; the prediction is made {moment}.',
             'Decided: ' + ('; '.join(decided) if decided else 'nothing yet') + '.',
             f'Now: {step}; {deliverables}.',
             f'Next: {nxt}',
             f'Limit: {limit}']
    # P3: one flat line each (no nested list, no line break), never a revision number.
    return [' '.join(line.split()) for line in lines]


LIVENESS_RUNNING, LIVENESS_UNKNOWN, LIVENESS_NOT_CHECKED = ('running', 'outcome_unknown',
                                                           'not_checked')


def _executions(state: dict, leases: dict | None) -> tuple[dict, dict]:
    """Executions with a per-execution ``liveness`` (F1); the suspected ones apart.

    ``leases`` is a read-only lease probe taken before the state was read
    (``lock.probe_leases``, by ``status``). An active execution whose lease file exists
    and is not held has an unknown outcome: it moves to ``suspected_interrupted``. One
    with no lease entry was reserved after the probe and is running. Without a probe
    (renderers, which must stay deterministic per revision), liveness is ``not_checked``.
    """
    ex = state['executions']
    active, suspected = {}, {}
    for eid, record in sorted(ex['active'].items()):
        if leases is None:
            active[eid] = {**record, 'liveness': LIVENESS_NOT_CHECKED}
        elif leases.get(eid, True):
            active[eid] = {**record, 'liveness': LIVENESS_RUNNING}
        else:
            suspected[eid] = {**record, 'liveness': LIVENESS_UNKNOWN,
                              'reason': 'Recorded as running, but no process holds its lease: '
                                        'it stopped and its outcome is unknown. The next run '
                                        'or acknowledgement records it as interrupted.'}
    out = {'active': active, 'interrupted': ex['interrupted'], 'late': ex['late'],
           'suspected_interrupted': suspected}
    return out, suspected


def build(study_dir, *, leases: dict | None = None) -> dict:
    """The view model of the study at ``study_dir`` (or of an open :class:`read.Study`).

    ``leases``: a read-only lease probe taken *before* the study was opened
    (``{execution_id: held}``); ``status`` passes one so a dead execution is never shown
    as running (F1). Renderers pass none and stay deterministic per revision.
    """
    study = study_dir if isinstance(study_dir, read.Study) else read.open(Path(study_dir))
    state = study.state
    executions, suspected = _executions(state, leases)
    plan = st.derive_plan(state)
    results = _results(study, state)
    defensible = st.not_yet_defensible(state)
    _case_uncertain_limit(state, defensible)
    broken = sorted(s for s, r in results.items() if r['integrity'] != 'ok')
    if broken:
        defensible.append({'id': 'result_integrity', 'slots': broken,
                           'text': 'Some recorded results fail their integrity check and '
                                   'cannot be cited.'})
    sources = study.source_changes()
    if sources:
        defensible.append({'id': 'sources_changed', 'changes': sources,
                           'text': 'The case or dataset file changed since the study started: '
                                   'no result describes the current bytes, and every decision, '
                                   'run and render is refused. Start a new study on the new data.'})
    changed = sorted(s for s, r in results.items()
                     if r['integrity'] == 'ok' and rid_reason(r, 'code_changed'))
    if changed:
        defensible.append({'id': 'code_changed', 'slots': changed,
                           'text': 'The code of these activities changed after their results '
                                   'were computed; those results, and the ones computed from '
                                   'them, cannot be cited until they are run again.'})
    if suspected:
        item = next((x for x in defensible if x['id'] == 'interrupted_executions'), None)
        if item is None:
            defensible.append({'id': 'interrupted_executions', 'executions': sorted(suspected),
                               'text': 'An execution has an unknown outcome.'})
        else:
            item['executions'] = sorted(set(item['executions']) | set(suspected))
    adopted = _adopted_without_evaluation(state, results)
    if adopted:
        defensible.append({'id': 'adopted_rule_not_evaluated', 'rules': [adopted],
                           'text': f'The adopted policy {adopted} has no current evaluation; '
                                   'its figures cannot be cited until it is evaluated again.'})
    defensible.extend(_small_data(state, results))
    defaults = scenario_defaults(state)
    defensible.extend(_assumed_capacity(state, defaults))
    partial = {'decisions': _decisions(state), 'task': st.task_of(state), 'results': results,
               'open_proposals': [p for p in st.open_proposals(state)]}
    criterion = governance.assess(partial, lambda r: rec.canonical_rule(r) or r)
    started = {slot: r['started_revision'] for slot, r in results.items()
               if r['integrity'] == 'ok' and r['current']}
    final_test = partition.final_test_status(state, started)
    defensible.extend(_governance_limits(state, criterion, final_test))
    return {
        'schema': SCHEMA,
        'study': str(study.study_dir),
        'revision': state['revision'],
        'updated': state['updated'],
        'case': dict(state['case']),
        'dataset': dict(state['dataset']),
        'plan': plan,
        'current_step': next((s['id'] for s in plan if s['current']), None),
        # v0.2a (WP-A1): every message for a surface says who it is written for.
        'next_action': audience.next_action(_with_default_rule(st.next_action(state, suspected),
                                                               defaults)),
        'open_proposals': [_proposal_view(p, st.language_of(state))
                           for p in sorted(st.open_proposals(state),
                                           key=lambda p: (p['revision'], p['proposal_id']))],
        'decisions': _decisions(state),
        'facts': _facts(state),
        'structure': state['structure'],
        'results': results,
        'stale': state['stale'],
        'invalidations': state['invalidations'],
        'executions': executions,
        'artifacts': _artifacts(study, state),
        'exposure': study.exposure_summary(),
        'not_yet_defensible': [audience.limit(x) for x in defensible],
        'settings': state['settings'],
        'task': st.task_of(state),
        'notes': [{k: n[k] for k in NOTE_VIEW_KEYS} for n in st.notes(state)],
        'final_test': final_test,
        'deliverables': launch.deliverables(study.study_dir),
        'mode': st.mode_of(state),
        'language': st.language_of(state),
        'criterion': criterion,
        'eda_looks': governance.ledger(study.exposure_records(), _target_column(state)),
        'scenario_defaults': defaults,
        'trials': trials(study.exposure_records()),
    }


# WP-B1: the activities whose runs are model configurations (the baseline is not a trial),
# and the purposes of their fitting reads.
TRIAL_ACTIVITIES = ('fit.logistic', 'fit.linear', 'fit.variant')
TRIAL_PURPOSES = ('train_fit', 'cross_validated_fit')
TRIALS_KEYS = ('count', 'results', 'note')


def trials(records) -> dict:
    """How many model configurations the study evaluated so far (WP-B1): the distinct
    results of the candidate and variant fits in the exposure ledger (a rerun with the same
    inputs is the same result; an interrupted fit counts by its execution). A disclosure, like
    the count of target looks: the more configurations compared on the same rows, the more
    the best of them may owe to chance."""
    seen: list[str] = []
    for r in records:
        if r.get('activity') not in TRIAL_ACTIVITIES or r.get('purpose') not in TRIAL_PURPOSES:
            continue
        key = r.get('result_id') or r.get('execution_id')
        if key and key not in seen:
            seen.append(key)
    return {'count': len(seen), 'results': seen,
            'note': 'Each candidate or variant configuration fitted is a trial. Choosing the '
                    'best of several trials on the same rows makes its figures slightly '
                    'optimistic; the final test, opened once, is not affected.'}


def _target_column(state: dict) -> str | None:
    """The target column of the study's case, or None when the case file cannot be read
    (``sources_changed`` already says so)."""
    from .case import CaseError, case_of
    try:
        return case_of(state).target_column
    except (CaseError, OSError):
        return None


def _governance_limits(state: dict, criterion: dict | None,
                       final_test: dict | None = None) -> list[dict]:
    """v0.2a (WP-A4) limits: a verdict that adopts against the success criterion, and a
    preprocessing motivated by a look at the target. v0.2b (WP-B1): the final test still
    sealed (every figure is development evidence), an opening whose evaluation was never
    recorded, and changes made after the final test was opened."""
    out = []
    final_test = final_test or {}
    if final_test.get('status') == 'sealed' and st.has_wp_b1_decisions(state):
        out.append({'id': 'final_test_sealed',
                    'text': 'The final test is still sealed: every figure so far is development '
                            'evidence, measured on rows used to explore, fit, and choose.'})
    opening = final_test.get('opening') or {}
    if final_test.get('status') == 'opened' and not opening.get('result_id'):
        out.append({'id': 'final_test_opening_interrupted',
                    'text': 'The final test was opened but its evaluation was not recorded: it '
                            'cannot be opened again, so the study has no final evidence.'})
    if final_test.get('post_final_test'):
        out.append({'id': 'changed_after_final_test',
                    'changed': list(final_test.get('changed_after') or []),
                    'text': 'Something changed after the final test was opened ('
                            + ', '.join(final_test.get('changed_after') or []) + '): the final '
                            'test no longer measures what the study now holds, and it is no '
                            'longer independent evidence for it.'})
    if criterion and criterion.get('contradicts_verdict'):
        judged = criterion.get('judged_status') or criterion['status']
        on_final = criterion.get('judged_on') == 'final_test'
        why = ('the gain does not reach the minimum fixed before the models'
               if judged == 'not_met' else
               'the paired interval of the gain includes 0')
        where = ' on the final test' if on_final else ''
        out.append({'id': 'verdict_contradicts_criterion', 'decisions': ['conclusion'],
                    'status': judged,
                    'text': f'The conclusion adopts while the success criterion fixed before '
                            f'the models is not met{where}: {why}.'})
    if governance.keeps_against_met(criterion):
        # B6c (H4): keeping the baseline against a criterion met on the final test.
        out.append({'id': 'verdict_keeps_baseline_against_criterion',
                    'decisions': ['conclusion'], 'status': 'met',
                    'text': 'The conclusion keeps the baseline although the success criterion '
                            'fixed before the models is met on the final test: say why (a '
                            'cost, a risk, or a limit the criterion does not capture), or '
                            'reconsider the verdict.'})
    pre = (state['decisions'].get('preprocessing') or {})
    value = pre.get('value')
    if pre.get('status') in ('confirmed', 'reconfirm_required') and isinstance(value, dict) \
            and value.get('data_contingent'):
        out.append({'id': 'data_contingent_preprocessing', 'decisions': ['preprocessing'],
                    'results': list(value.get('motivated_by') or []),
                    'text': ('The preparation of the variables was chosen after looking at '
                             'the outcome on the development rows, so the out-of-fold figures '
                             'may be slightly optimistic.' if st.uses_cross_validation(state)
                             else 'The preparation of the variables was chosen after looking '
                                  'at the outcome on training rows, so the validation figures '
                                  'may be slightly optimistic.')})
    return out


def _proposal_view(p: dict, language: str) -> dict:
    out = {}
    for k in PROPOSAL_VIEW_KEYS:
        if k in ('origin', 'labels'):
            out[k] = copy.deepcopy(p.get(k))
        elif k == 'label':
            out[k] = st.label_of(p, language)
        else:
            out[k] = p[k]
    return out


# --- the digest of the advanced companion (CLI-CONTRACT-COMPANION §1, C1) -------------

# ``status --summary --digest`` appends these keys after ``recap``, in this order.
DIGEST_SUMMARY_KEYS = ('moments', 'pauses', 'last_session', 'digest', 'task', 'currency')
# Review fix H1: ``currency`` is the first CURRENCY_HEX hex characters of a sha256 over the
# canonical JSON of :func:`currency_inputs` (CLI-CONTRACT-COMPANION §1.5).
CURRENCY_HEX = 16
CURRENCY_INPUT_KEYS = ('revision', 'sources', 'artifacts', 'sources_changed', 'alerts',
                       'next_action', 'executions', 'results')
MOMENT_KEYS = ('id', 'title', 'steps')
PAUSE_KEYS = ('pause', 'decisions', 'status', 'confirmed')
LAST_SESSION_KEYS = ('boundary_revision', 'boundary_time', 'gap_minutes')
DIGEST_KEYS = ('since', 'until', 'items', 'truncated', 'counts')
DIGEST_ITEM_KEYS = ('revision', 'time', 'action', 'kind', 'decision_id', 'proposal_id', 'note_id',
                    'activity', 'slot', 'result_id', 'execution_id', 'rules', 'column', 'channel',
                    'basis', 'delegation_scope', 'superseded', 'invalidation', 'text',
                    # v0.2a (WP-A7, CLI-CONTRACT §3.3): who ``text`` is written for, and its
                    # junior variant (null when ``text`` is already written for the junior).
                    'audience', 'junior_text')
DIGEST_KINDS = ('proposed', 'confirmed', 'withdrawn', 'hold_recorded', 'hold_resolved',
                'result_added', 'result_replaced', 'run_failed', 'run_interrupted',
                'interruption_acknowledged', 'other')
DIGEST_INVALIDATION_KEYS = ('mutation', 'row', 'stale_slots', 'reconfirm_required', 'refit',
                            'kept_fits')
DIGEST_COUNT_KEYS = ('proposed', 'confirmed', 'withdrawn', 'holds_recorded', 'holds_resolved',
                     'results_added', 'results_replaced', 'runs_started', 'runs_failed',
                     'invalidations')
# The gap that separates two working sessions: the default of ``session-report
# --gap-minutes``. Recorded commit times are compared with each other, never with the clock.
SESSION_GAP_MINUTES = 20
# The digest lists the newest items only (``truncated`` says older ones were dropped).
DIGEST_MAX_ITEMS = 50
# Invalidations recorded only when they invalidate something (``dependencies``).
_QUIET_MUTATIONS = ('first_confirmation', 'unchanged_value', 'result_replaced', 'hold_added')
_RESERVE, _PROMOTE = 'run.reserve', 'run.promote'
_KIND_OF_ACTION = {'decide.propose': 'proposed', 'decide.confirm': 'confirmed',
                   'decide.withdraw': 'withdrawn', 'decide.note': 'hold_recorded',
                   'decide.resolve_note': 'hold_resolved', 'decide.withdraw_note': 'hold_resolved',
                   'run.fail': 'run_failed', 'run.recover': 'run_interrupted',
                   'run.acknowledge': 'interruption_acknowledged'}
_COUNT_OF_KIND = {'proposed': 'proposed', 'confirmed': 'confirmed', 'withdrawn': 'withdrawn',
                  'hold_recorded': 'holds_recorded', 'hold_resolved': 'holds_resolved',
                  'result_added': 'results_added', 'result_replaced': 'results_replaced',
                  'run_failed': 'runs_failed'}


def moments(task: str, state: dict | None = None) -> list[dict]:
    """The four moments of the plan (``content/steps.yaml``, ``moments``). With ``state``,
    only the steps of that study are listed (a study created before WP-A4 has no success
    criterion or preprocessing step)."""
    from . import texts

    data = texts.load('steps')
    overlay = data.get('regression_moments', {}) if task == st.REGRESSION else {}
    ids = set(st.step_ids(state if state is not None else task))
    return [{'id': m['id'], 'title': m['title'],
             'steps': [s for s in overlay.get(m['id'], m['steps']) if s in ids]}
            for m in data['moments']]


def pause_decisions(state) -> dict[int, list[str]]:
    """``{pause: [decision ids]}`` from the plan's steps (as ``session-report``)."""
    out: dict[int, list[str]] = {}
    for step in st.steps(state):
        if step.get('pause') and step.get('decision'):
            out.setdefault(step['pause'], []).append(step['decision'])
    return dict(sorted(out.items()))


def pauses(state: dict) -> list[dict]:
    """Each pause with its decisions; ``closed`` when every one of them is confirmed."""
    out = []
    for number, ids in pause_decisions(state).items():
        confirmed = [d for d in ids if state['decisions'][d]['status'] == 'confirmed']
        out.append({'pause': number, 'decisions': list(ids),
                    'status': 'closed' if len(confirmed) == len(ids) else 'open',
                    'confirmed': confirmed})
    return out


def _time(text):
    import datetime as dt

    try:
        return dt.datetime.fromisoformat(str(text))
    except (TypeError, ValueError):
        return None


def last_session(records: list[dict]) -> dict:
    """The last revision before the latest gap of more than :data:`SESSION_GAP_MINUTES`
    between two consecutive commit times, with that gap in whole minutes; revision 1 and
    a null gap when the study was worked on in one session."""
    first = next((r for r in records if r.get('revision') == 1), records[0] if records else None)
    out = {'boundary_revision': 1, 'boundary_time': first.get('time') if first else None,
           'gap_minutes': None}
    for a, b in zip(records, records[1:]):
        ta, tb = _time(a.get('time')), _time(b.get('time'))
        if ta is None or tb is None:
            continue
        seconds = (tb - ta).total_seconds()
        if seconds > SESSION_GAP_MINUTES * 60:
            out = {'boundary_revision': a['revision'], 'boundary_time': a.get('time'),
                   'gap_minutes': int(seconds // 60)}
    return out


class _Texts:
    """The digest sentences of ``content/digest.yaml`` for one task."""

    def __init__(self, task: str):
        from . import texts

        data = texts.load('digest')
        if task == st.REGRESSION:
            data = texts._merge({k: v for k, v in data.items() if k != st.REGRESSION},
                                data.get(st.REGRESSION, {}))
        self.data = data

    def decision(self, decision_id) -> str:
        return self.data['decisions'].get(decision_id, ' '.join(str(decision_id).split('_')))

    def slot(self, slot, junior: bool = False) -> str:
        base, sep, column = str(slot).partition(':')
        label = self.data['activities'].get(base) or (
            audience.activity_words(base) if junior   # WP-A7: no activity id for the junior
            else self.data['activity_fallback'].format(activity=base))
        return self.data['slot_with_column'].format(label=label, column=column) if sep else label

    @staticmethod
    def join(labels) -> str:
        labels = list(labels)
        return labels[0] if len(labels) == 1 else ', '.join(labels[:-1]) + ' and ' + labels[-1]

    def template(self, name: str, junior: bool = False, **fields) -> str:
        own = self.data.get('junior_templates', {}).get(name) if junior else None
        return (own or self.data['templates'][name]).format(**fields)

    def cause(self, name: str, junior: bool = False, **fields) -> str:
        own = self.data.get('junior_causes', {}).get(name) if junior else None
        return (own or self.data['causes'][name]).format(**fields)


def _cap(text: str) -> str:
    return text[:1].upper() + text[1:]


def _invalidation(result: dict, full: dict | None, kept_fits: list[str]) -> dict | None:
    """The digest's invalidation of a record: the record's own (a confirmation, a
    replacement) or the one ``state['invalidations']`` holds for its revision.
    ``kept_fits`` are the fit slots current before the record; those it made stale are
    dropped."""
    own = result.get('invalidation')
    base = own if isinstance(own, dict) else full
    if base is None:
        return None
    effects = (full or {}).get('effects') or {}
    stale_slots = list(base.get('stale_slots') or [])
    return {'mutation': base.get('mutation'), 'row': base.get('row'), 'stale_slots': stale_slots,
            'reconfirm_required': list(base.get('reconfirm_required') or []),
            'refit': list(effects.get('refit') or []),
            'kept_fits': [s for s in kept_fits if s not in stale_slots]}


def _effect_sentences(t: _Texts, item: dict, full: dict | None, kept: list[str],
                      junior: bool = False) -> list[str]:
    inv = item['invalidation']
    if inv is None:
        # A replaced result that invalidated nothing (a re-evaluated policy): say that the
        # models were kept when there were current fits.
        replaced = item['kind'] == 'result_replaced' and not str(item['slot']).startswith('fit.')
        return [t.data['effects']['nothing_refitted']] if replaced and kept else []
    out = []
    if inv['mutation'] not in ('first_confirmation', 'unchanged_value', 'hold_added'):
        if inv['refit']:
            out.append(t.data['effects']['refit'].format(
                slots=t.join(t.slot(s, junior) for s in inv['refit'])))
        elif inv['kept_fits']:
            out.append(t.data['effects']['nothing_refitted'])
        others = [s for s in inv['stale_slots'] if s not in inv['refit']]
        if others:
            out.append(t.data['effects']['stale'].format(
                slots=t.join(t.slot(s, junior) for s in others)))
    again = inv['reconfirm_required']
    if again:
        if inv['mutation'] == 'result_replaced':
            cause = t.cause('result_replaced', junior, activity=t.slot(
                item['slot'] or (full or {}).get('decision_id'), junior))
        elif inv['mutation'] == 'hold_added':
            cause = t.cause('hold_added', junior, decision=t.decision(item['decision_id']))
        else:
            cause = t.cause('decision', junior, decision=t.decision(
                (full or {}).get('decision_id') or item['decision_id']))
        name = 'reconfirm_one' if len(again) == 1 else 'reconfirm_many'
        out.append(t.data['effects'][name].format(
            Decisions=_cap(t.join(t.decision(d) for d in again)), cause=cause))
    return out


def _text(t: _Texts, item: dict, *, again: bool, state: dict, full: dict | None,
          record: dict, kept: list[str], junior: bool = False) -> str:
    """The digest sentence of ``item``; ``junior`` (WP-A7) its variant for the junior: the
    second person, a rule or a model in words, no channel and no activity id."""
    kind, action = item['kind'], item['action']
    params = record.get('params') or {}
    decision = t.decision(item['decision_id']) if item['decision_id'] else ''
    fields = {'decision': decision, 'Decision': _cap(decision)}

    def template(name, **more):
        return t.template(name, junior, **fields, **more)

    if kind == 'proposed':
        value = params.get('value')
        # Only a rule identifier or a model slot is quoted: other values are free text.
        identifier = item['decision_id'] in st.CHOICE_DECISION.values() and isinstance(value, str)
        if identifier and junior:
            value = (audience.model_words(value) if item['decision_id'] == 'model_choice'
                     else audience.rule_words(value))
        main = template('proposed_value', value=value) if identifier else template('proposed')
        if item['superseded']:
            main += ' ' + t.data['templates']['superseding']
    elif kind == 'confirmed':
        name = ('confirmed_delegated' if item['basis'] == st.DELEGATED_DEFAULT
                else 'confirmed_again' if again else 'confirmed')
        main = template(name, channel=item['channel'])
    elif kind == 'withdrawn':
        main = template('withdrawn')
    elif kind == 'hold_recorded':
        main = template('hold_recorded', words=params.get('user_words'))
    elif action == 'decide.note':
        # ADR 0005 (R3): a correction note is listed as ``other``, not as a hold.
        main = template('correction_recorded', words=params.get('user_words'))
    elif kind == 'hold_resolved':
        note = (state.get('notes') or {}).get(item['note_id']) or {}
        name = 'hold_withdrawn' if action == 'decide.withdraw_note' else 'hold_resolved'
        main = template(name, hold=note.get('user_words'), words=params.get('user_words'))
    elif item['activity'] is not None or item['slot'] is not None:
        activity = t.slot(item['slot'] or item['activity'], junior)
        act = {'activity': activity, 'Activity': _cap(activity)}
        if kind in ('result_added', 'result_replaced'):
            if item['rules']:
                rules = ('; '.join(audience.rule_words(r) for r in item['rules']) if junior
                         else ', '.join(item['rules']))
                main = t.template(f'{kind}_rules', junior, rules=rules, **act)
            elif item['column'] and ':' not in str(item['slot']):
                main = t.template(f'{kind}_column', junior, column=item['column'], **act)
            else:
                main = t.template(kind, junior, **act)
        elif action == _PROMOTE:
            main = t.template('run_late', junior, **act)
        else:
            main = t.template(kind, junior, **act)
    elif action == 'init':
        main = template('created')
    else:
        main = template('other', action=action)
    return ' '.join([main, *_effect_sentences(t, item, full, kept, junior)])


def digest(study: read.Study, state: dict, *, since: int) -> dict:
    """The revision records after ``since`` as digest items (CLI-CONTRACT-COMPANION §1.4).

    Every record is read in order, from the first one, to know which slots were already
    filled (``result_replaced``), which fits were current (``kept_fits``), what each
    execution was started with (``rules``, ``column``), and whether a decision was
    confirmed before (a reconfirmation). Only the records after ``since`` are listed.
    """
    records = study.revisions(0)
    t = _Texts(st.task_of(state))
    full_by_revision: dict[int, dict] = {}
    for inv in state['invalidations']:
        full_by_revision.setdefault(inv['revision'], inv)
    reserved: dict[str, dict] = {}
    occupant: dict[str, str] = {}
    confirmed_before: set = set()
    stale: set = set()
    counts = dict.fromkeys(DIGEST_COUNT_KEYS, 0)
    items = []
    for record in records:
        revision, action = record['revision'], record.get('action') or ''
        params, result = record.get('params') or {}, record.get('result') or {}
        full = full_by_revision.get(revision)
        listed = since < revision <= study.revision
        run = action.startswith('run.')
        eid = (params.get('execution_id') or result.get('execution_id')) if run else None
        if action == _RESERVE:
            reserved[eid] = {'activity': params.get('activity'),
                             'options': params.get('options') or {}}
            if listed:
                counts['runs_started'] += 1
            continue
        kept = [s for s in sorted(occupant) if s.startswith('fit.') and occupant[s] not in stale]
        kind = _KIND_OF_ACTION.get(action, 'other')
        if action == 'decide.note' and result.get('kind') == st.CORRECTION:
            kind = 'other'                       # ADR 0005: a correction is not a hold
        promoted = action == _PROMOTE and result.get('status') == 'promoted'
        if promoted:
            kind = 'result_replaced' if result.get('slot') in occupant else 'result_added'
        again = False
        if kind == 'confirmed':
            again = result.get('decision_id') in confirmed_before
            confirmed_before.add(result.get('decision_id'))
        started = reserved.get(eid) or {}
        options = started.get('options') or {}
        item = dict.fromkeys(DIGEST_ITEM_KEYS)
        item.update(revision=revision, time=record.get('time'), action=action, kind=kind)
        if run:
            item.update(activity=result.get('activity') or started.get('activity'),
                        slot=result.get('slot'), result_id=result.get('result_id'),
                        execution_id=eid,
                        rules=list(options['rules']) if options.get('rules') else None,
                        column=options.get('column'))
        else:
            item.update(decision_id=result.get('decision_id') or params.get('decision_id'),
                        proposal_id=result.get('proposal_id') or params.get('proposal_id'),
                        note_id=result.get('note_id') or params.get('note_id'))
        if kind == 'proposed':
            item['superseded'] = list(result.get('superseded') or [])
        if kind == 'confirmed':
            item.update(channel=result.get('channel') or params.get('channel') or 'chat',
                        basis=result.get('basis') or params.get('basis') or st.EXPLICIT,
                        delegation_scope=result.get('delegation_scope',
                                                    params.get('delegation_scope')))
        own = full if kind in ('confirmed', 'hold_recorded', 'hold_resolved') or promoted \
            else None
        item['invalidation'] = _invalidation(result, own, kept)
        if promoted:
            occupant[result['slot']] = result['result_id']
            stale.discard(result['result_id'])
        if full is not None:
            stale.update(full.get('stale_results') or [])
        elif isinstance(result.get('invalidation'), dict):
            stale.update(result['invalidation'].get('stale_results') or [])
        if not listed:
            continue
        item['text'] = _text(t, item, again=again, state=state, full=own, record=record,
                             kept=kept)
        junior = _text(t, item, again=again, state=state, full=own, record=record, kept=kept,
                       junior=True)
        # WP-A7: ``junior_text`` only when the sentence differs (the summary stays compact).
        item['audience'] = audience.JUNIOR if junior == item['text'] else audience.AGENT
        item['junior_text'] = None if junior == item['text'] else junior
        if kind in _COUNT_OF_KIND:
            counts[_COUNT_OF_KIND[kind]] += 1
        inv = item['invalidation']
        if inv is not None and (inv['mutation'] not in _QUIET_MUTATIONS or inv['stale_slots']
                                or inv['reconfirm_required']):
            counts['invalidations'] += 1
        items.append(item)
    return {'since': since, 'until': study.revision, 'items': items[-DIGEST_MAX_ITEMS:],
            'truncated': len(items) > DIGEST_MAX_ITEMS, 'counts': counts}


def with_digest(study: read.Study, built: dict, summary_out: dict, *,
                since: int | None = None) -> dict:
    """``summary_out`` with the keys of ``--digest`` (CLI-CONTRACT-COMPANION §1, C1).

    It appends :data:`DIGEST_SUMMARY_KEYS` after ``recap`` and adds ``origin`` (C9, null
    for a proposal recorded before C9) as the last key of each open proposal. ``since``
    is ``--since``: the digest then starts after it instead of at the last session's
    boundary. Deterministic for a study content: no clock is read.
    """
    if since is not None and not 0 <= since <= study.revision:
        raise StudyError('invalid_arguments',
                         f'--since must be between 0 and the current revision '
                         f'({study.revision}).',
                         details={'since': since, 'revision': study.revision})
    state = study.state
    session = last_session(study.revisions(0))
    out = dict(summary_out)
    out['open_proposals'] = [{**p, 'origin': (state['proposals'].get(p['proposal_id']) or {})
                              .get('origin')} for p in summary_out['open_proposals']]
    out.update({'moments': moments(built['task'], state), 'pauses': pauses(state),
                'last_session': session,
                'digest': digest(study, state, since=session['boundary_revision']
                                 if since is None else since),
                'task': built['task'], 'currency': currency_digest(study, built)})
    return out


def currency_inputs(study: read.Study, built: dict) -> dict:
    """What ``currency`` digests (CLI-CONTRACT-COMPANION §1.5): everything a client shows
    that can change **without** a new revision, plus the revision itself.

    * ``sources``: the sha256 of the case and dataset files as they are now (the recorded one
      when they match), so an edited dataset changes it;
    * ``artifacts``: per deliverable, its effective status, ``stale_reason``, and for the
      generated ones the hash of the file on disk (``currency.file_fingerprint``; null when
      missing), so a render, a deleted file, or an edited one changes it. The workbench is
      the junior's free space: only its status counts;
    * ``sources_changed`` and ``alerts`` (the ids of ``not_yet_defensible``, in order),
      ``next_action`` (its kind), ``executions`` (the interrupted, suspected, and late ids);
    * ``results``: per promoted slot, ``[result_id, current, integrity]``, the registry's
      current set with the derived currency (a code change makes a result not current).

    It reads the files the view read already (and the generated deliverables' bytes); it
    reads no clock and no absolute path, so it is equal for equal study content."""
    changed = {c['label']: c['actual_sha256'] for c in study.source_changes()}
    sources = {label: changed.get(label, built[label]['sha256'])
               for label in ('case', 'dataset')}
    artifacts = {}
    for name, item in sorted(built['artifacts']['items'].items()):
        artifacts[name] = {'status': item.get('status'),
                           'stale_reason': item.get('stale_reason'),
                           'file': None if item.get('generated') is False
                           else currency.file_fingerprint(study.study_dir, item)}
    ex = built['executions']
    ids = [x['id'] for x in built['not_yet_defensible']]
    return {'revision': built['revision'], 'sources': sources,
            'artifacts': {'status': built['artifacts']['status'], 'items': artifacts},
            'sources_changed': 'sources_changed' in ids, 'alerts': ids,
            'next_action': (built['next_action'] or {}).get('kind'),
            'executions': {k: sorted(ex[k]) for k in ('interrupted', 'suspected_interrupted',
                                                      'late')},
            'results': {slot: [r['result_id'], r['current'], r['integrity']]
                        for slot, r in sorted(built['results'].items())}}


def currency_digest(study: read.Study, built: dict) -> str:
    """The ``currency`` of ``status --summary --digest`` (review fix H1)."""
    import hashlib
    import json

    inputs = currency_inputs(study, built)
    text = json.dumps({k: inputs[k] for k in CURRENCY_INPUT_KEYS}, sort_keys=True,
                      separators=(',', ':'), ensure_ascii=True)
    return hashlib.sha256(text.encode('utf-8')).hexdigest()[:CURRENCY_HEX]
