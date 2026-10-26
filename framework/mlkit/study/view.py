"""The single view model of a study (``hypotrail.view/1``, plan §9 bis).

``build(study_dir)`` returns one JSON-serialisable dict. ``hypotrail status`` prints
it, and every renderer consumes it rather than raw state: the HTML report, the
generated notebook, and a future webview. Its keys are frozen by
``framework/tests/study/test_contract_freeze.py`` and documented in
``docs/specs/CLI-CONTRACT.md``.

The view is deterministic for a given study content: it contains no clock reading,
so two renders of one revision see the same view.

Read-only (it uses :mod:`mlkit.study.read` only) and free of pandas, numpy, and
scikit-learn at import and at build time, with one exception (round 5, review E, R5E-2):
outside a read-only process, when the study holds a current predictor capture and the next
action would open the final test, the capture is loaded as the confirmation loads it
(:mod:`mlkit.study.capture_check`), which imports the runtime; nothing is written.
"""
from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Mapping

from . import audience
from . import currency
from . import launch
from . import partition
from . import governance, read
from . import criterion as criterion_mod
from . import junior
from . import assurance
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
             'trials',
             # v0.3 (WP-F1, ADR 0007): the candidate and the variants compared fold by fold
             # (one-standard-error rule, selection optimism, advice to stop), and the
             # engine's shortlist of model families; ``null`` in a study without variants.
             'model_selection', 'model_families', 'assurance',
             # reliability roadmap J2: one derived evaluator, never persisted.
             'requirements', 'completion', 'claim_eligibility', 'presentation',
             # L3 (owner session 2026-10-26, R4; D4 A, D4b): the case's statements in both
             # languages from its translation sidecar (``l10n.case_texts``), or ``null``.
             'case_texts')
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
                          'reason_given', 'adoption_question',
                          # L3 (owner session 2026-10-26, R4): the confirmed proposal's
                          # restatement in the study language (``state.label_of``; the
                          # English ``restatement`` when the agent gave none in it).
                          'label')
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
                    # Review 2026-10-24 round 2: rows left out for a delayed label.
                    'delayed_labels_excluded',
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


def _confirmed_label(state: Mapping, conf: Mapping) -> str | None:
    """The restatement a confirmation answered, in the study language (L3): the proposal's
    label in that language when the agent gave one, else the recorded restatement."""
    proposal = (state.get('proposals') or {}).get(conf.get('proposal_id'))
    if not isinstance(proposal, Mapping):
        return conf.get('restatement')
    labels = proposal.get('labels') or {}
    return labels.get(st.language_of(state)) or conf.get('restatement')


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
                                    'adoption_question': bool(conf.get('adoption_question')),
                                    'label': _confirmed_label(state, conf)}
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
        items[name].update(audience.artifact(name, items[name], st.language_of(state)))
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
    lang = view.get('language') or audience.EN
    # L3 (R4, T4; D4 A): the case's statements in the study language when its translation
    # sidecar gives them (``view.case_texts``).
    translated = ((view.get('case_texts') or {}).get('facts') or {}) if lang != audience.EN \
        else {}

    def fact(fact_id):
        item = _fact(view, fact_id)
        french = (translated.get(fact_id) or {}).get(lang) if item else None
        return {**item, 'value': french} if french else item
    pt = view['decisions']['prediction_time']
    if pt['value'] is not None:
        prediction_time = {'value': pt['value'], 'source': 'decision', 'status': pt['status']}
    else:
        item = fact('prediction_time')
        prediction_time = ({'value': item['value'], 'source': 'case', 'status': item['status']}
                           if item else None)
    goal = {'intended_use': fact('intended_use'), 'decision': fact('decision'),
            'observation_unit': fact('observation_unit'),
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
                  'restatement': p.get('label') or p['restatement'],
                  'revision': p['revision']}
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
                           # Compact: null when ``text`` is already written for the junior
                           # (v0.3, WP-C: and in the study language).
                           'junior_text': (x.get('junior_text') or audience.junior_text(x, lang)
                                           if x.get('audience') == audience.AGENT
                                           or (x.get('junior_text') or x['text']) != x['text']
                                           else None)}
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
                      'fit.variant': 'the variant', 'fit.variant:2': 'the second variant',
                      'fit.variant:3': 'the third variant'}
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
    named = audience.MODEL_WORDS.get(slot, 'the variant') if slot != 'fit.logistic' \
        else 'the logistic model'
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
        text = f'{label}: {audience.model_words(value)}'
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
            # v0.3 (WP-C, R18): the metric is named (precision or recall).
            name = 'recall' if value.get('metric') == 'recall_gain' else 'precision'
            text = (f'{label} ({name} gain over the baseline of at least '
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
    v0.3 (WP-C): in the study language (:func:`_recap_junior_fr` for a French study).
    """
    if junior and view.get('language') == audience.FR:
        return _recap_junior_fr(summary_out, view)
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
        named = '; '.join(f'{audience.model_words(slot)} {mae} {errors["unit"]}'
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


# --- the junior recap in French (v0.3, WP-C, R21, R37) ------------------------------------

FR = audience.FR


def _comma(number: str) -> str:
    """A decimal number as French writes it (``12.5`` as ``12,5``)."""
    return ','.join(number.split('.'))


def _pct_fr(value) -> str | None:
    return _comma(f'{100 * value:.1f}') + ' %' if isinstance(value, (int, float)) \
        and not isinstance(value, bool) else None


def _headline_fr(view: dict, summary_out: dict, short: bool) -> dict | None:
    """The French junior text of :func:`_policy_headline` (no result id, the rule in words)."""
    head = _policy_headline(view, summary_out)
    if head is None:
        return None
    item = view['results']['policy.evaluation']
    by_rule = {rec.canonical_rule(r) or r: r for r in (item['values'].get('rules') or {})}
    rule = by_rule.get(head['rule'], head['rule'])
    decision = summary_out['decisions'].get('policy') or {}
    chosen = decision.get('value') if head['adopted'] else next(
        (p['value'] for p in summary_out['open_proposals'] if p['decision_id'] == 'policy'),
        None)
    slot = rec.policy_model(chosen) if isinstance(chosen, str) else 'fit.logistic'
    model = ((item['values']['rules'][rule] or {}).get('models') or {}).get(slot) or {}
    figures = ', '.join(f'{name} {v}' for name, v in (('précision', _pct_fr(model.get('precision'))),
                                                      ('rappel', _pct_fr(model.get('recall'))))
                        if v)
    n = item['values'].get('n')
    where = ("lignes de l'échantillon de développement, hors pli"
             if item['values'].get('evaluation') == 'out_of_fold' else 'lignes du jeu de validation')
    rows = f' sur les {n} {where}' if isinstance(n, int) else f' sur les {where}'
    named = 'la variante' if slot == 'fit.variant' else 'le modèle logistique'
    text = f'{named}{rows} : {figures}' if short else \
        f'{named}, {audience.rule_words(head["rule"], FR)},{rows} : {figures}'
    return {'adopted': head['adopted'], 'text': text}


def _recap_decision_fr(decision_id: str, d: dict, view: dict, summary_out: dict,
                       cv: bool) -> str:
    label = audience.decision_words(decision_id, FR)
    value = d['value']
    if decision_id == 'feature_availability' and isinstance(value, dict):
        parts = []
        excluded = sorted(value.get('not_available', []) + value.get('uncertain_excluded', []))
        doubtful = sorted(value.get('uncertain_included', []))
        if excluded:
            parts.append('exclues : ' + ', '.join(excluded))
        if doubtful:
            parts.append('gardées malgré un doute : ' + ', '.join(doubtful))
        text = f'{label} ({"; ".join(parts) if parts else "toutes les variables gardées"})'
    elif decision_id == 'split' and isinstance(value, dict) and value.get('method') in \
            st.CV_METHODS:
        method = audience.CV_METHOD_WORDS_FR.get(value['method'], _spaced(value['method']))
        text = f'{label} (validation croisée à {value.get("folds")} plis, {method})'
    elif decision_id == 'split' and isinstance(value, dict):
        fraction = value.get('validation_fraction')
        if value.get('method') == 'ordinal_cutoff' and value.get('column') is not None:
            text = (f'{label} (selon {value["column"]}, jeu de validation à partir de '
                    f'{value.get("cutoff")})')
        elif isinstance(fraction, (int, float)) and not isinstance(fraction, bool):
            text = f'{label} (aléatoire, {round(100 * fraction):d} % pour le jeu de validation)'
        else:
            text = label
    elif decision_id == 'model_variant' and isinstance(value, dict):
        text = f'{label} ({audience.variant_words(value, FR)})'
    elif decision_id == 'final_test' and isinstance(value, dict):
        text = (f"l'échantillon de test final, ouvert une fois "
                f'({audience.model_words(value.get("model"), FR)}'
                + (f', {audience.rule_words(value["rule"], FR)})' if value.get('rule') else ')'))
    elif decision_id == 'policy' and isinstance(value, str):
        text = f'{label} : {audience.policy_words(value, FR)}'
        head = _headline_fr(view, summary_out, short=True)
        if head and head['adopted']:
            text += f' ({head["text"]})'
    elif decision_id == 'model_choice' and isinstance(value, str):
        text = f'{label} : {audience.model_words(value, FR)}'
        errors = _regression_errors(view)
        mae = (errors or {}).get('mae', {}).get(value)
        if mae is not None:
            where = 'hors pli' if cv else 'de validation'
            text += f' (MAE {where} {_comma(mae)} {errors["unit"]})'
    elif decision_id == 'conclusion' and isinstance(value, dict):
        text = f'{label} : {audience.verdict_words(value.get("verdict", ""), FR)}'
    elif decision_id == 'success_criterion' and isinstance(value, dict):
        from . import criterion as criterion_words
        words = criterion_words.value_words(value, FR, cv)
        text = f'{label} ({words})' if words else label
    elif decision_id == 'preprocessing' and isinstance(value, dict):
        from . import governance as gov
        text = f'{label} ({"par défaut, rien ne change" if gov.is_default(value) else "modifiée"})'
        if value.get('data_contingent'):
            text += ' [choisie après un regard sur le résultat]'
    else:
        text = label
    notes = []
    if d['basis'] == st.DELEGATED_DEFAULT:
        notes.append("déléguée à l'assistant")
    if d['status'] == 'reconfirm_required':
        notes.append('à confirmer à nouveau')
    return text + (f' [{", ".join(notes)}]' if notes else '')


def _deliverables_line_fr(items: dict) -> str:
    words = {'report': 'le rapport', 'notebook': 'le notebook'}
    unwritten = [words[n] for n in ('report', 'notebook')
                 if n not in items or items[n].get('status') == 'not_rendered']
    behind = sorted(audience.ARTIFACT_WORDS_FR.get(name, name) for name, item in items.items()
                    if item.get('status') not in ('ok', 'not_rendered') and name != 'workbench')
    if not unwritten and not behind:
        return 'le rapport et le notebook sont à jour'
    parts = []
    if behind:
        parts.append(', '.join(behind) + ' pas à jour')
    if unwritten:
        parts.append(' et '.join(unwritten) + ' pas encore écrits' if len(unwritten) > 1
                     else unwritten[0] + ' pas encore écrit')
    return '; '.join(parts)


def _recap_next_fr(summary_out: dict, view: dict) -> str:
    nxt = summary_out['next_action'] or {}
    kind = nxt.get('kind')
    if kind == 'await_user_words':
        proposal = next((p for p in view.get('open_proposals') or []
                         if p['proposal_id'] == nxt.get('proposal_id')), None)
        label = audience.decision_words(nxt.get('decision'), FR)
        said = (proposal or {}).get('label') or ''
        return f'si vous adoptez {label} : « {said} »'
    if kind in ('propose', 'run', 'blocked') and nxt.get('step') != summary_out['current_step']:
        titles = {s['id']: s['title'] for s in summary_out['plan']}
        title = junior.step_text(titles.get(nxt.get('step'), ''), FR) or \
            audience.decision_words(nxt.get('step'), FR)
        return f'{title} : {nxt.get("junior_message", "")}'.strip()
    return str(nxt.get('junior_message') or '').strip() or \
        "plus rien dans le plan ; relisez ce qui n'est pas encore défendable."


def _recap_junior_fr(summary_out: dict, view: dict) -> list[str]:
    """``recap_junior`` of a French study: the five lines of :func:`recap` (``junior``) in
    French. The case's own statements (intended use, the prediction moment it states) and
    the recorded values are quoted as they are written."""
    goal = summary_out['goal']
    use = _fact_value(goal['intended_use'])
    use = f'« {use} »' if use else "non indiqué par le cas"
    pt = goal['prediction_time']
    if pt is None:
        moment = 'pas encore décidé'
    elif pt['source'] == 'decision' and pt['status'] == 'confirmed':
        moment = f'« {pt["value"]} »'
    else:
        moment = f'« {pt["value"]} » (selon le cas, pas encore décidé)'
    cv = texts.scheme_of(view) == texts.CROSS_VALIDATION
    decided = [_recap_decision_fr(d, item, view, summary_out, cv)
               for d, item in summary_out['decisions'].items()
               if item['status'] in ('confirmed', 'reconfirm_required')]
    titles = {s['id']: s['title'] for s in summary_out['plan']}
    nxt = summary_out['next_action'] or {}
    kind = nxt.get('kind')
    if kind in ('await_user_words', 'reconfirm'):
        decision = nxt.get('decision')
        title = junior.step_text(titles.get(decision), FR) if titles.get(decision) \
            else _capital_first(audience.decision_words(decision, FR))
        step = (f'{title}, en attente de votre réponse' if kind == 'await_user_words'
                else f'{title}, en attente de votre nouvelle confirmation')
    elif kind in ('outcome_unknown', 'acknowledge_interruption'):
        named = (f'une exécution de {audience.activity_words(nxt["activity"], FR)}'
                 if nxt.get('activity') else 'une exécution')
        step = f'{named} s\'est arrêtée et son résultat est inconnu, en attente de votre accord'
    elif summary_out['current_step']:
        step = junior.step_text(titles.get(summary_out['current_step'], ''), FR)
    else:
        step = 'toutes les étapes sont faites'
    errors = _regression_errors(view)
    chosen = summary_out['decisions'].get('model_choice') or {}
    if errors and chosen.get('status') not in ('confirmed', 'reconfirm_required'):
        named = '; '.join(f'{audience.model_words(slot, FR)} {_comma(mae)} '
                          f'{errors["unit"]}' for slot, mae in sorted(errors['mae'].items()))
        step += f' (MAE {"hors pli" if cv else "de validation"} : {named})'
    head = _headline_fr(view, summary_out, short=False) \
        if st.task_of(view.get('task')) == st.BINARY else None
    if head and not head['adopted']:
        step += f' (dernière évaluation de la règle : {head["text"]})'
    limits = [x for x in view['not_yet_defensible'] if x['id'] not in RECAP_LIMIT_SKIP
              and x.get('junior') is not False]
    rank = {k: i for i, k in enumerate(SUMMARY_PRIORITY)}
    limits.sort(key=lambda x: rank.get(x['id'], len(SUMMARY_PRIORITY)))
    limit = audience.junior_text(limits[0], FR) if limits else 'aucune enregistrée.'
    following = _recap_next_fr(summary_out, view).rstrip()
    holds = summary_out.get('holds') or []
    if holds:
        said = '; '.join('; '.join(f'« {n["user_words"]} »' for n in h['notes'])
                         + f' ({audience.decision_words(h["decision_id"], FR)})' for h in holds)
        following += ('' if following.endswith(('.', '»', '?')) else '.') + (
            f' En suspens, selon vos mots : {said} ; rien de ce qui est en suspens n\'est '
            'confirmé tant que vous ne le levez pas.')
    lines = [f'Objectif : {use} ; la prédiction est faite {moment}.',
             'Décidé : ' + (' ; '.join(decided) if decided else 'rien pour l\'instant') + '.',
             f'Maintenant : {step} ; {_deliverables_line_fr(summary_out["artifacts"]["items"])}.',
             f'Ensuite : {following}',
             f'Limite : {limit}']
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
    language = st.language_of(state)
    # The state keeps canonical English plan text; surfaces receive localized copies.
    plan = [{**step,
             'title': junior.step_text(step['title'], language),
             'question': junior.step_text(step['question'], language)}
            for step in plan]
    results = _results(study, state)
    defensible = st.not_yet_defensible(state)
    _case_uncertain_limit(state, defensible)
    broken = sorted(s for s, r in results.items()
                    if r['integrity'] != 'ok' and s != 'policy.inspection')
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
                     if s != 'policy.inspection' and r['integrity'] == 'ok'
                     and rid_reason(r, 'code_changed'))
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
    # v0.3 (WP-C, R18): the metric the confirmed criterion names (``criterion.assess``).
    criterion = criterion_mod.assess(partial, lambda r: rec.canonical_rule(r) or r)
    started = {slot: r['started_revision'] for slot, r in results.items()
               if r['integrity'] == 'ok' and r['current']}
    final_test = partition.final_test_status(state, started)
    defensible.extend(_governance_limits(state, criterion, final_test))
    out = {
        'schema': SCHEMA,
        'study': str(study.study_dir),
        'revision': state['revision'],
        'updated': state['updated'],
        'case': dict(state['case']),
        'dataset': dict(state['dataset']),
        'plan': plan,
        'current_step': next((s['id'] for s in plan if s['current']), None),
        # v0.2a (WP-A1): every message for a surface says who it is written for.
        'next_action': _next_action(study, state, audience.next_action(
            _with_default_rule(st.next_action(state, suspected), defaults), language)),
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
        'not_yet_defensible': [audience.limit(x, language) for x in defensible],
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
        **_wp_f1(state, results),
    }
    case = _case_or_none(state) if not sources else None
    # L3 (R4; D4 A, D4b): the case's statements in both languages, read by ``junior.enrich``
    # (the prediction moment in the study language) and the surfaces; moved last below.
    from . import l10n
    out['case_texts'] = l10n.case_texts(state, case.document) if case is not None else None
    out['assurance'] = assurance.describe(state, case)
    if assurance.profile(state) == 'review-v1':
        from . import validity
        derived = validity.evaluate(state, case, results)
        out['requirements'] = derived['requirements']
        out['completion'] = derived['completion']
        out['claim_eligibility'] = derived['claim_eligibility']
    else:
        out['requirements'] = None
        out['completion'] = None
        out['claim_eligibility'] = None
    # v0.3 (WP-C): what the agent relays at this pause (``junior_digest``, ``recommended``,
    # ``question``, ``criterion_options``), in the study language.
    # Owner session 2026-10-26 (L1, R2c): at a free choice, ``choice_options`` lists the
    # values a confirmation would accept now (``feasibility.accepts``).
    from . import feasibility
    junior.enrich(out, state, case, accepts=feasibility.accepts(study, state))
    if out['next_action'].get('kind') == 'done':
        # L7 (D15): what comes after the study, the export offered only when supported.
        from . import after_study
        out['next_action']['after_study'] = after_study.build(out, state, case)
    notice = assurance.scope_notice(case, language)
    if assurance.profile(state) == 'review-v1':
        contract = case.document.get('analysis_contract') if case is not None else None
        if contract and out['next_action'].get('decision') == 'prediction_time':
            out['next_action']['default_value'] = contract['prediction_statement']
            out['next_action']['recommended'] = {
                'value': contract['prediction_statement'],
                'why': ("Ce profil est lié au scénario déclaré ; un autre moment de prédiction "
                        "nécessite un cas révisé et une nouvelle étude."
                        if language == 'fr' else
                        'This profile is bound to the declared scenario; a different '
                        'prediction moment needs a revised case and a new study.')}
    if notice:
        out['next_action']['junior_digest'] += ' ' + notice
        # The existing summary and plan both carry next_action; no second scope model.
    from . import guidance
    out['next_action']['pause'] = guidance.pause(out)
    from . import presentation
    out['presentation'] = presentation.build(out)
    out['case_texts'] = out.pop('case_texts')          # the last key (VIEW_KEYS order)
    return out


def _next_action(study: read.Study, state: Mapping, action: dict | None) -> dict | None:
    """The view's ``next_action``: the state's, completed (:func:`_opening_not_current`,
    :func:`_runnable`), then checked as the engine would execute it (review round 6, area E,
    R6E-1, R6E-2: :func:`mlkit.study.feasibility.checked`): an action the engine would refuse
    is replaced by its first remedy, completed the same way. Never an action the engine
    refuses as given, when it has a remedy."""
    from . import feasibility

    def finish(item: dict | None) -> dict | None:
        return _runnable(study, state, _opening_not_current(study, state, item))
    return feasibility.checked(study, state, finish(action), finish)


def _opening_not_current(study: read.Study, state: Mapping, action: dict | None) -> dict | None:
    """Review round 3 (E3-3): ``next_action`` never recommends opening the final test (a
    ``propose`` of ``final_test``, the junior's words awaited on its proposal, or the ``run``
    of its evaluation before the opening) while a
    result the opening rests on is not current by the rule of ``status``
    (:func:`mlkit.study.opening.not_current`); it is then a ``run`` of the
    first such result, upstream first, with ``not_current`` listing every one and a junior
    message in the study language. The state-derived plan is unchanged."""
    if not action or st.final_test_opened(state) or not (
            (action.get('kind') in ('propose', 'await_user_words', 'reconfirm')
             and action.get('decision') == st.FINAL_TEST)
            or (action.get('kind') == 'run'
                and action.get('activity') == 'final_test.evaluation')):
        return action
    from . import opening
    if study.source_changes():
        return action
    missing = opening.not_current(study, state, capture=True)
    if not missing:
        # Round 5 (review E, R5E-2): a capture current by its fingerprint that the final
        # evaluation could not load (another runtime installed, an altered bundle, another
        # environment) is captured again first; proposing the opening would be refused.
        problem = _capture_unloadable(study, state)
        if problem is None:
            return action
        out = {'kind': 'run', 'step': action.get('step'), 'activity': CAPTURE_SLOT,
               'not_current': [CAPTURE_SLOT],
               'message': ('Run predictor.capture again before opening the final test: the '
                           'captured predictor cannot be loaded as the final evaluation loads it '
                           f'({problem.get("message")}). Running it again recomputes the '
                           'capture of the same choice with what is installed now. The final '
                           'test stays sealed.'),
               'audience': audience.AGENT, 'junior_message': problem['junior_message']}
        return _with_capture_options(study, state, out)
    slots = [m['slot'] for m in missing]
    junior = ' '.join(dict.fromkeys(m['junior_message'] for m in missing
                                    if m.get('junior_message')))
    out = {'kind': 'run', 'step': action.get('step'), 'activity': slots[0],
           'not_current': slots,
           'message': (f'Run {", ".join(slots)} again before opening the final test: by the '
                       'rule of status they are not current (code changed, delayed-label rows, '
                       'or an upstream result not current). The final test stays sealed.'),
           'audience': audience.AGENT, 'junior_message': junior}
    return _with_capture_options(study, state, out) if slots[0] == CAPTURE_SLOT else out


CAPTURE_SLOT = 'predictor.capture'


def capture_options(params: Mapping | None) -> dict:
    """Round 5 (review E, R5E-3): the ``run`` options that reproduce a capture's params
    (``profile`` when not the default, ``packager`` when the profile does not imply it), so a
    re-capture keeps its MLflow package. ``{}`` for a base capture without packager."""
    params = params or {}
    out = {}
    profile, packager = params.get('profile'), params.get('packager')
    if isinstance(profile, str) and profile != 'base':
        out['profile'] = profile
    if isinstance(packager, str) and packager and not (
            profile == 'workshop' and packager == 'mlflow_pyfunc'):
        out['packager'] = packager
    return out


def _with_capture_options(study: read.Study, state: Mapping, action: dict) -> dict:
    """R5E-3: a ``run`` of the capture carries ``options`` (each one a ``--<option>
    <value>``) of the capture it replaces, when that capture had any."""
    rid = state['current'].get(CAPTURE_SLOT)
    if rid is None:
        return action
    try:
        options = capture_options(study.result(rid).get('params'))
    except StudyError:
        return action
    return {**action, 'options': options} if options else action


def _capture_unloadable(study: read.Study, state: Mapping) -> dict | None:
    """R5E-2: the ``capture_loadable`` item of the current capture when the final
    evaluation could not load it (:func:`mlkit.study.capture_check.unloadable`, the check of
    the confirmation and of the reservation; never in a read-only process), else None."""
    from . import capture_check
    return capture_check.unloadable(study, state)


POLICY_RUNS = ('policy.evaluation', 'policy.evaluate')


def _runnable(study: read.Study, state: Mapping, action: dict | None) -> dict | None:
    """Review round 4 (E4-2, E4-3): ``next_action`` never names an action the engine would
    refuse as given.

    * After the opening, the final evaluation is never run again, and the final-test
      diagnostics cannot be computed from a final evaluation that is missing or not current
      (``run diag.final_test`` refuses it, E3-4): the action then says so and names what
      remains (:func:`_final_test_not_recomputable`).
    * Before the opening, a confirmed final test whose opening the reservation would refuse
      because the study now chooses another configuration (``chosen_configuration`` of
      :func:`mlkit.study.preconditions.opening_missing`, read here from state: a study that
      changed its choice before this rule existed) is proposed again on that configuration.
    * A ``run`` of the policy evaluation carries the rules to pass (``rules``, each one a
      ``--rule``) whenever the study knows them: the adopted or proposed rule, the
      scenario's default, the rules of the evaluation it runs again."""
    if not action:
        return action
    kind, activity = action.get('kind'), action.get('activity')
    if kind == 'run' and st.final_test_opened(state) \
            and activity in ('final_test.evaluation', 'diag.final_test'):
        replaced = _final_test_not_recomputable(study, state, action)
        if replaced is not None:
            return replaced
    if kind in ('propose', 'reconfirm', 'await_user_words', 'done') \
            and st.final_test_opened(state):
        # Round 5 (review E, R5E-8): after the opening, a decision proposed while the final
        # evaluation is not current says so too (E4-2 for the runs).
        action = _with_final_test_notice(study, state, action)
    if kind == 'propose' and st.structural_first(state) \
            and action.get('decision') in (st.PREPROCESSING, st.MODEL_VARIANT):
        # Owner session 2026-10-26 (L5, R5, R13; D6, D9): the drafts read the evidence. The
        # preparation is drafted from the target-free results (the screened distributions are
        # run first); the variants add the EBM when the diagnostics flag a pattern.
        from . import drafts
        language = st.language_of(state)
        if action.get('decision') == st.PREPROCESSING:
            run = drafts.distribution_run(study, state, action, language)
            if run is not None:
                return run
            action = drafts.with_preprocessing_draft(study, state, action, language)
        else:
            action = drafts.with_variant_draft(study, state, action, language)
    if kind == 'propose' and action.get('decision') == 'policy':
        # R5E-4: the policy proposal carries the rule to propose (``default_value``).
        default = _policy_default(study, state, action)
        if default is not None:
            action = {**action, 'default_value': default}
    if kind == 'run' and activity == 'final_test.evaluation' \
            and not st.final_test_opened(state):
        from . import opening
        decision = state['decisions'].get(st.FINAL_TEST) or {}
        chosen = st.choice_config(state)
        if decision.get('status') == 'confirmed' and chosen is not None \
                and decision.get('value') != chosen:
            # The reservation's ``chosen_configuration`` (read side, state only).
            missing = [{'requirement': 'chosen_configuration', 'value': decision.get('value'),
                        'chosen': chosen}]
            return {'kind': 'propose', 'step': action.get('step'), 'decision': st.FINAL_TEST,
                    'default_value': chosen,
                    'message': ('The final test was confirmed but not opened, and the study '
                                'now chooses another configuration: propose the final test '
                                'again on the chosen configuration and record the junior\'s own '
                                'words; running final_test.evaluation would be refused. The '
                                'final test stays sealed.'),
                    'audience': audience.AGENT,
                    'junior_message': opening.reservation_message(state, missing)}
    if kind == 'run' and activity in POLICY_RUNS and not action.get('rules'):
        rules = _known_rules(study, state, action)
        if rules:
            action = {**action, 'rules': rules}
    return action


# Round 5 (review E, R5E-4): the rules the engine recommends evaluating when the study names
# none (no proposal, no scenario share, no evaluation yet, no rule fixed by a review-v1
# criterion): the top shares the policy evaluation reports its gain at
# (``mlkit.study.policy.GAIN_SHARES``), and among them the one it proposes, the share the
# development diagnostics apply by default (``mlkit.study.diagnostics.DEFAULT_RULE``). Both
# equalities are tested; this module may not import those numerical modules.
RECOMMENDED_RULES = ('share:0.05', 'share:0.1', 'share:0.2')
RECOMMENDED_RULE = 'share:0.1'


def criterion_rule(state: Mapping) -> str | None:
    """R5E-4: under review-v1, the rule the confirmed success criterion fixes
    (``selection.rule``): the policy must adopt it (``selection_rule_mismatch``). None
    otherwise."""
    if assurance.profile(state) != 'review-v1':
        return None
    decision = state['decisions'].get(st.SUCCESS_CRITERION) or {}
    if decision.get('status') not in ('confirmed', 'reconfirm_required'):
        return None
    value = decision.get('value')
    rule = ((value.get('selection') or {}).get('rule') if isinstance(value, Mapping)
            else None)
    return rec.canonical_rule(rule) if isinstance(rule, str) else None


def _evaluation_params(study: read.Study, state: Mapping) -> dict | None:
    """The params of the current policy evaluation (``rules``, ``models``), or None when
    the slot holds none, it is not current by the state, or its entry cannot be read."""
    rid = state['current'].get('policy.evaluation')
    if rid is None or not st.is_current(state, 'policy.evaluation'):
        return None
    try:
        params = study.result(rid).get('params') or {}
    except StudyError:
        return None
    rules = params.get('rules') if isinstance(params.get('rules'), list) else (
        [params['rule']] if params.get('rule') is not None else [])
    return {'rules': [rec.canonical_rule(r) or str(r) for r in rules],
            'models': [str(m) for m in params.get('models') or [rec.POLICY_CANDIDATE]]}


def _with_chosen_model(state: Mapping, rule: str) -> str:
    """``rule`` applied to the model the study chose (``rule@fit.variant``) when a binary
    study's explicit model choice is a variant; the rule alone otherwise."""
    if st.has_explicit_binary_model_choice(state):
        model = (state['decisions'].get('model_choice') or {}).get('value')
        if isinstance(model, str) and model != rec.POLICY_CANDIDATE \
                and model in rec.POLICY_MODELS:
            return f'{rule}{rec.POLICY_MODEL_SEP}{model}'
    return rule


def _policy_default(study: read.Study, state: Mapping, action: Mapping) -> str | None:
    """R5E-4: the policy value a ``propose policy`` action carries: under review-v1 the
    rule the success criterion fixes; else the scenario's share (the action's default);
    else, among the rules of the current evaluation, :data:`RECOMMENDED_RULE` or the first.
    Applied to the chosen model (:func:`_with_chosen_model`)."""
    rule = criterion_rule(state) or rec.canonical_rule(action.get('default_value'))
    if rule is None:
        evaluated = (_evaluation_params(study, state) or {}).get('rules') or []
        rule = RECOMMENDED_RULE if RECOMMENDED_RULE in evaluated else (
            evaluated[0] if evaluated else None)
    return _with_chosen_model(state, rule) if rule else None


def _unevaluated_policy_proposal(study: read.Study, state: Mapping, action: Mapping
                                 ) -> dict | None:
    """R5E-7: the ``run`` that makes the open policy proposal confirmable, or None when the
    confirmation would accept it: the policy evaluation on its rule (and the rules already
    evaluated) when no current evaluation covers that rule or model, or the fit of its model
    first when that fit is not current. Round 6 (R6E-2): the remedy
    :mod:`mlkit.study.feasibility` names for that refusal, after the confirmation's earlier
    refusals (a hold, a stale proposal) and checked like any run."""
    proposal = state['proposals'].get(action.get('proposal_id')) or {}
    value = proposal.get('value')
    rule, model = rec.policy_rule(value), rec.policy_model(value)
    if rule is None:
        return None
    evaluated = _evaluation_params(study, state)
    if evaluated is not None and rule in evaluated['rules'] and model in evaluated['models']:
        return None
    lang = st.language_of(state)
    fr = lang == audience.FR
    words = audience.rule_words(rule, lang)
    if model != rec.POLICY_CANDIDATE and not st.is_current(state, model):
        activity = model
        junior = (f"Votre proposition de règle (« {words} ») s'applique à "
                  f'{audience.model_words(model, lang)}, dont l\'ajustement n\'est pas à jour : '
                  "il est relancé d'abord, puis la règle est évaluée, avant de vous demander "
                  'si vous l\'adoptez.' if fr else
                  f'Your proposed rule ("{words}") applies to '
                  f'{audience.model_words(model, lang)}, whose fit is not current: it is run '
                  'first, then the rule is evaluated, before you are asked whether you adopt '
                  'it.')
        out = {'kind': 'run', 'step': 'policy', 'activity': activity,
               'proposal_id': action.get('proposal_id')}
    else:
        rules = list(dict.fromkeys([rule] + _known_rules(study, state, action)))
        junior = (f"Votre proposition de règle (« {words} ») n'a pas encore été évaluée sur "
                  "les résultats à jour : l'évaluation de la règle est lancée d'abord, puis "
                  'vous dites si vous l\'adoptez.' if fr else
                  f'Your proposed rule ("{words}") has not been evaluated on the current '
                  'results yet: the policy evaluation runs first, then you say whether you '
                  'adopt it.')
        out = {'kind': 'run', 'step': 'policy', 'activity': 'policy.evaluation',
               'rules': rules, 'proposal_id': action.get('proposal_id')}
    out.update(message=(f'Do not ask for words on proposal {action.get("proposal_id")} yet: '
                        f'the confirmation would refuse it, since no current policy evaluation '
                        f'covers {value}. Run {out["activity"]} first; the proposal stays open.'),
               audience=audience.AGENT, junior_message=junior)
    return out


def _known_rules(study: read.Study, state: Mapping, action: Mapping) -> list[str]:
    """E4-3: the rules a policy evaluation runs on as the study knows them, in this order:
    the rule a review-v1 success criterion fixes (round 5, R5E-4), the policy decision's rule
    (confirmed, to confirm again, or proposed), the rules of the open policy proposals, the
    action's default (the scenario's share), and the rules of the current evaluation (run
    again on what it evaluated); when the study names none, :data:`RECOMMENDED_RULES`."""
    found: list[str] = [criterion_rule(state)]
    decision = state['decisions'].get('policy') or {}
    if decision.get('status') in ('confirmed', 'reconfirm_required', 'proposed'):
        found.append(rec.policy_rule(decision.get('value')))
    for p in sorted(st.open_proposals(state), key=lambda p: (p['revision'], p['proposal_id'])):
        if p.get('decision_id') == 'policy':
            found.append(rec.policy_rule(p.get('value')))
    found.append(rec.canonical_rule(action.get('default_value')))
    rid = state['current'].get('policy.evaluation')
    if rid:
        try:
            params = study.result(rid).get('params') or {}
        except StudyError:
            params = {}
        rules = params.get('rules') if isinstance(params.get('rules'), list) else (
            [params['rule']] if params.get('rule') is not None else [])
        found += [rec.canonical_rule(r) for r in rules]
    return [r for r in dict.fromkeys(found) if r] or list(RECOMMENDED_RULES)


def _final_test_not_recomputable(study: read.Study, state: Mapping, action: Mapping
                                 ) -> dict | None:
    """E4-2: after the opening, the ``run`` the plan names (the final evaluation, or the
    final-test diagnostics on a final evaluation that is missing or not current) would be
    refused: None when it would not (the diagnostics on a current final evaluation).
    Otherwise the next action says that the final test cannot be recomputed and why, and
    names what remains: the conclusion (with the verdicts its rule still allows), or nothing
    when it is confirmed. Never a loop."""
    from . import opening
    final = state['current'].get('final_test.evaluation')
    currency = study.currency(final) if final else None
    if action.get('activity') == 'diag.final_test' and currency and currency['current']:
        return None
    reason = (currency or {}).get('reason') or {}
    lang = st.language_of(state)
    fr = lang == audience.FR
    if final is None:
        why = ("l'ouverture a été interrompue avant que son évaluation soit enregistrée" if fr
               else 'the opening was interrupted before its evaluation was recorded')
    elif reason.get('delayed_labels_included'):
        why = ("elle a été calculée avec des lignes de développement dont l'étiquette "
               "n'était pas encore connue au moment de la décision (des étiquettes tardives)"
               if fr else
               'it was computed with development rows whose label was not known yet at the '
               'decision time (delayed labels)')
    elif reason.get('code_changed'):
        why = ("le code du moteur qui l'a calculée a changé depuis" if fr else
               "the engine's code that computed it changed since")
    elif currency is not None and currency['current']:
        why = ("elle est enregistrée, et le test final ne s'ouvre qu'une fois" if fr else
               'it is recorded, and the final test is opened only once')
    else:
        why = ("elle a été calculée à partir de résultats qui ne sont plus à jour" if fr else
               'it was computed from results that are no longer current')
    conclusion = state['decisions'].get('conclusion') or {}
    verdicts = opening.conclusion_verdicts(state)
    step = next((s for s in st.derive_plan(state) if s['id'] == st.FINAL_TEST), None) or {}
    blocked = [a for a in ('final_test.evaluation', 'diag.final_test')
               if a == action.get('activity') or a in (step.get('missing_results') or [])]
    named = audience.join([audience.verdict_words(v, lang) for v in verdicts], lang)
    if fr:
        head = ("Le test final a été ouvert une fois, et son évaluation ne peut pas être "
                f"recalculée : {why}. Ses diagnostics ne peuvent donc pas être calculés non "
                "plus. Ses chiffres restent dans l'étude comme historique.")
        rest = (f' Ce qui reste possible : conclure l\'étude à partir des preuves de '
                f'développement ({named}), en disant pourquoi ; un nouveau test final, '
                f'indépendant, demande une nouvelle étude.' if conclusion.get('status')
                != 'confirmed' and verdicts else
                " Votre conclusion est enregistrée ; un nouveau test final, indépendant, "
                "demande une nouvelle étude.")
    else:
        head = (f'The final test was opened once, and its evaluation cannot be computed again: '
                f'{why}. Its diagnostics cannot be computed either. Its figures stay in the '
                f'study as history.')
        rest = (f' What remains possible: conclude the study from the development evidence '
                f'({named}), saying why; a new, independent final test needs a new study.'
                if conclusion.get('status') != 'confirmed' and verdicts else
                ' Your conclusion is recorded; a new, independent final test needs a new '
                'study.')
    out = {'not_recomputable': blocked,
           'audience': audience.AGENT, 'junior_message': head + rest}
    agent = (f'Do not run {", ".join(blocked)}: the final test was already opened and its '
             'evaluation cannot be recomputed; the engine refuses it.')
    if conclusion.get('status') != 'confirmed' and verdicts:
        return {'kind': 'propose', 'step': 'conclusion', 'decision': 'conclusion',
                'verdicts': verdicts, **out,
                'message': agent + ' Propose the conclusion (verdicts the engine accepts: '
                           + ', '.join(verdicts) + '), its text citing development evidence '
                           'and saying that the final test cannot be recomputed.'}
    return {'kind': 'done', **out,
            'message': agent + ' Nothing else remains in the plan; a new final test needs a '
                               'new study.'}


def _with_final_test_notice(study: read.Study, state: Mapping, action: dict) -> dict:
    """Round 5 (review E, R5E-8): after the opening, a ``propose``, ``reconfirm``,
    ``await_user_words`` or ``done`` while the final evaluation is missing or not current
    carries the E4-2 notice (:func:`_final_test_not_recomputable`): ``not_recomputable``
    and, first in ``junior_message``, why the final test cannot be computed again and what
    remains; a proposal of the conclusion also carries the verdicts its rule still allows."""
    final = state['current'].get('final_test.evaluation')
    if final is not None and study.currency(final)['current']:
        return action
    notice = _final_test_not_recomputable(study, state, {'activity': 'final_test.evaluation'})
    if notice is None:
        return action
    out = {**action, 'not_recomputable': notice['not_recomputable'],
           'junior_message': ' '.join(t for t in (notice['junior_message'],
                                                   action.get('junior_message')) if t)}
    if action.get('decision') == 'conclusion' and notice.get('verdicts') \
            and 'verdicts' not in action:
        out['verdicts'] = notice['verdicts']
    out['message'] = (f'{action.get("message") or ""} The final test was already opened and '
                      'its evaluation is not current and cannot be recomputed: say so, and cite '
                      'development evidence.').strip()
    return out


def _case_or_none(state: dict):
    from .case import CaseError, case_of
    try:
        return case_of(state)
    except (CaseError, OSError):
        return None


def _wp_f1(state: dict, results: dict) -> dict:
    """v0.3 (WP-F1): ``model_selection`` and ``model_families`` (null before WP-B1)."""
    from . import trials as tr
    from .case import CaseError, case_of
    if not st.has_wp_b1_decisions(state):
        return {'model_selection': None, 'model_families': None}
    task = st.task_of(state)
    try:
        document = case_of(state).document
    except (CaseError, OSError):
        document = None
    diag = results.get(st.DIAG_SLOT[task]) or {}
    values = diag.get('values') if diag.get('integrity') == 'ok' else None
    # Owner session 2026-10-26 (L5, R14, D10): each family in the junior's words, and why no
    # random forest (additive keys ``families[].junior_words``, ``not_offered``).
    from . import drafts
    return {'model_selection': tr.selection(results, state, task),
            'model_families': drafts.with_junior_words(
                tr.shortlist(document, values, task, st.language_of(state),
                             diag.get('result_id')), st.language_of(state))}


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
DIGEST_SUMMARY_KEYS = ('moments', 'pauses', 'last_session', 'digest', 'task', 'currency',
                       # L3 (owner session 2026-10-26, R4; D4b): the junior texts this summary
                       # shows, in both languages (:func:`language_texts`).
                       'texts')
# ``texts.<language>``: where each junior text of the summary is, by its id (L3, D4b).
LANGUAGE_TEXT_KEYS = ('plan', 'moments', 'next_action', 'choice_options', 'limits',
                      'artifacts', 'recap', 'digest', 'goal', 'proposals')
# Review fix H1: ``currency`` is the first CURRENCY_HEX hex characters of a sha256 over the
# canonical JSON of :func:`currency_inputs` (CLI-CONTRACT-COMPANION §1.5).
CURRENCY_HEX = 16
CURRENCY_INPUT_KEYS = ('revision', 'sources', 'artifacts', 'sources_changed', 'alerts',
                       'next_action', 'executions', 'results')
MOMENT_KEYS = ('id', 'title', 'steps')
PAUSE_KEYS = ('pause', 'decisions', 'status', 'confirmed')
LAST_SESSION_KEYS = ('boundary_revision', 'boundary_time', 'gap_minutes')
DIGEST_KEYS = ('since', 'until', 'items', 'truncated', 'counts',
               # v0.3 (WP-J, R35): runs, acknowledgements, renders and exports made outside
               # the chat (the study panel passes webview).
               'channel_actions')
CHANNEL_ACTION_KEYS = ('action', 'channel', 'revision', 'activity', 'time')
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
    criterion or preprocessing step), with the titles in its language (L3)."""
    from . import texts

    data = texts.load('steps')
    overlay = data.get('regression_moments', {}) if task == st.REGRESSION else {}
    order = st.step_ids(state if state is not None else task)
    ids = set(order)
    french = st.language_of(state) == audience.FR if state is not None else False
    # Owner session 2026-10-26 (L5): the steps of a moment in the study's plan order (a
    # structural-first study checks the structure, then the preparation, then the target).
    return [{'id': m['id'], 'title': m.get('title_fr', m['title']) if french else m['title'],
             'steps': sorted((s for s in overlay.get(m['id'], m['steps']) if s in ids),
                             key=order.index)}
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
    """The digest sentences of ``content/digest.yaml`` for one task. ``lang`` French (L3,
    owner session 2026-10-26): the junior sentences of a French study, from the file's ``fr``
    mapping, with the decisions and activities in the junior's French words."""

    def __init__(self, task: str, lang: str = audience.EN):
        from . import texts

        data = texts.load('digest')
        if task == st.REGRESSION:
            data = texts._merge({k: v for k, v in data.items() if k != st.REGRESSION},
                                data.get(st.REGRESSION, {}))
        self.lang = lang
        if lang == audience.FR:
            french = data.get('fr') or {}
            data = {**data, 'templates': french['templates'],
                    'junior_templates': french['templates'], 'causes': french['causes'],
                    'junior_causes': {}, 'effects': french['effects'],
                    'slot_with_column': french['slot_with_column'],
                    'webview': french['webview'], 'activities': {}}
        self.data = data

    def decision(self, decision_id) -> str:
        if self.lang == audience.FR:
            return audience.decision_words(decision_id, self.lang)
        return self.data['decisions'].get(decision_id, ' '.join(str(decision_id).split('_')))

    def slot(self, slot, junior: bool = False) -> str:
        base, sep, column = str(slot).partition(':')
        label = self.data['activities'].get(base) or (
            audience.activity_words(base, self.lang) if junior   # WP-A7: no activity id
            else self.data['activity_fallback'].format(activity=base))
        return self.data['slot_with_column'].format(label=label, column=column) if sep else label

    def join(self, labels) -> str:
        labels = list(labels)
        last = ' et ' if self.lang == audience.FR else ' and '
        return labels[0] if len(labels) == 1 else ', '.join(labels[:-1]) + last + labels[-1]

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
            value = (audience.model_words(value, t.lang) if item['decision_id'] == 'model_choice'
                     else audience.rule_words(value, t.lang))
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
                rules = ('; '.join(audience.rule_words(r, t.lang) for r in item['rules'])
                         if junior else ', '.join(item['rules']))
                main = t.template(f'{kind}_rules', junior, rules=rules, **act)
            elif item['column'] and ':' not in str(item['slot']):
                main = t.template(f'{kind}_column', junior, column=item['column'], **act)
            else:
                main = t.template(kind, junior, **act)
        elif action == _PROMOTE:
            main = t.template('run_late', junior, **act)
        else:
            main = t.template(kind, junior, **act)
        if item.get('channel') == 'webview':
            # v0.3 (WP-J, R35): a run started from the study panel says so.
            main += (' ' + t.data.get('webview', 'You ran it from the study panel.') if junior
                     else ' It was started from the study panel (channel webview).')
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
    # L3 (R4): the junior sentences of a French study are French (``text`` stays English).
    lang = st.language_of(state)
    tj = _Texts(st.task_of(state), lang) if lang == audience.FR else t
    full_by_revision: dict[int, dict] = {}
    for inv in state['invalidations']:
        full_by_revision.setdefault(inv['revision'], inv)
    reserved: dict[str, dict] = {}
    occupant: dict[str, str] = {}
    confirmed_before: set = set()
    stale: set = set()
    counts = dict.fromkeys(DIGEST_COUNT_KEYS, 0)
    items = []
    channel_actions: list[dict] = []
    for record in records:
        revision, action = record['revision'], record.get('action') or ''
        params, result = record.get('params') or {}, record.get('result') or {}
        full = full_by_revision.get(revision)
        listed = since < revision <= study.revision
        run = action.startswith('run.')
        eid = (params.get('execution_id') or result.get('execution_id')) if run else None
        if action == _RESERVE:
            reserved[eid] = {'activity': params.get('activity'),
                             'options': params.get('options') or {},
                             'channel': params.get('channel')}
            if listed:
                counts['runs_started'] += 1
                if params.get('channel'):
                    channel_actions.append({'action': 'run', 'channel': params['channel'],
                                            'revision': revision,
                                            'activity': params.get('activity'),
                                            'time': record.get('time')})
            continue
        if action == 'run.acknowledge' and listed and params.get('channel'):
            channel_actions.append({'action': 'acknowledge', 'channel': params['channel'],
                                    'revision': revision,
                                    'activity': result.get('activity'),
                                    'time': record.get('time')})
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
            # v0.3 (WP-J, R35): the channel the run (or its acknowledgement) came from.
            item['channel'] = (params.get('channel') if action == 'run.acknowledge'
                               else started.get('channel'))
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
        if tj is not t:
            # L3: in a French study the junior's sentence is always given, in French.
            item['junior_text'] = _text(tj, item, again=again, state=state, full=own,
                                        record=record, kept=kept, junior=True)
        if kind in _COUNT_OF_KIND:
            counts[_COUNT_OF_KIND[kind]] += 1
        inv = item['invalidation']
        if inv is not None and (inv['mutation'] not in _QUIET_MUTATIONS or inv['stale_slots']
                                or inv['reconfirm_required']):
            counts['invalidations'] += 1
        items.append(item)
    channel_actions += _channel_events(study, since)
    channel_actions.sort(key=lambda a: (a['revision'], a['time'] or ''))
    return {'since': since, 'until': study.revision, 'items': items[-DIGEST_MAX_ITEMS:],
            'truncated': len(items) > DIGEST_MAX_ITEMS, 'counts': counts,
            'channel_actions': channel_actions[-DIGEST_MAX_ITEMS:]}


def _channel_events(study: read.Study, since: int) -> list[dict]:
    """v0.3 (WP-J, R35): the renders and exports recorded with a channel other than the chat
    (``channel_action`` events of ``events.jsonl``) at revision ``since`` or later: they
    commit no revision, so one made at the revision the agent last read is listed too."""
    import json

    out = []
    home = getattr(study, 'home', None)
    if home is None:
        return out
    path = home / 'events.jsonl'           # store.EVENTS_FILE (the read side imports no writer)
    try:
        lines = path.read_text(encoding='utf-8').splitlines()
    except OSError:
        return out
    for line in lines:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict) or event.get('kind') != 'channel_action':
            continue
        revision = event.get('revision')
        if isinstance(revision, int) and revision >= since:
            out.append({'action': event.get('action'), 'channel': event.get('channel'),
                        'revision': revision, 'activity': None, 'time': event.get('time')})
    return out


def with_digest(study: read.Study, built: dict, summary_out: dict, *,
                since: int | None = None, leases: dict | None = None) -> dict:
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
    start = session['boundary_revision'] if since is None else since
    out.update({'moments': moments(built['task'], state), 'pauses': pauses(state),
                'last_session': session,
                'digest': digest(study, state, since=start),
                'task': built['task'], 'currency': currency_digest(study, built)})
    out['texts'] = language_texts(study, built, out, since=start, leases=leases)
    return out


def _texts_of(built: dict, summary_out: dict, lang: str) -> dict:
    """The junior texts of one summary (and the view it was made from), by id."""
    nxt = built.get('next_action') or {}
    return {
        'plan': {s['id']: s['title'] for s in built['plan']},
        'moments': {m['id']: m['title'] for m in summary_out.get('moments') or []},
        'next_action': nxt.get('junior_message'),
        'choice_options': {o['id']: o['label'] for o in nxt.get('choice_options') or []},
        'limits': {x['id']: x.get('junior_text') or x.get('text')
                   for x in built['not_yet_defensible']},
        'artifacts': {name: i.get('junior_message')
                      for name, i in built['artifacts']['items'].items()},
        'recap': list(summary_out.get('recap_junior') or []),
        'digest': {str(i['revision']): i.get('junior_text') or i.get('text')
                   for i in (summary_out.get('digest') or {}).get('items') or []},
        'goal': {k: (v or {}).get('value') for k, v in (summary_out.get('goal') or {}).items()},
        'proposals': {p['proposal_id']: (p.get('labels') or {}).get(lang)
                      for p in built['open_proposals']},
    }


def language_texts(study: read.Study, built: dict, summary_out: dict, *, since: int,
                   leases: dict | None = None) -> dict:
    """``texts`` of ``status --summary --digest`` (L3, owner session 2026-10-26; D4b):
    ``{"en": T, "fr": T}``, where ``T`` gives each junior text of the summary in that language
    by its id (:data:`LANGUAGE_TEXT_KEYS`): the step titles (``plan``), the ``moments``, the
    next action's ``junior_message`` and ``choice_options`` labels, the ``limits``'
    ``junior_text``, the deliverables' ``junior_message`` (``artifacts``), ``recap_junior``
    (``recap``), the digest items' junior sentences by revision (``digest``), the ``goal``,
    and each open proposal's restatement in that language (``proposals``, null when the agent
    gave none in it). The study language's table is read from this summary; the other one
    from the same study read in the other language (no write, no clock), so the study panel
    can follow its own language switch."""
    state = study.state
    lang = built.get('language') or audience.EN
    other = audience.FR if lang == audience.EN else audience.EN
    twin_state = {**state, 'language': other}
    twin = read.Study.at_state(study.study_dir, twin_state)
    twin_built = build(twin, leases=leases)
    twin_summary = summary(twin_built)
    twin_summary['moments'] = moments(twin_built['task'], twin_state)
    twin_summary['digest'] = digest(twin, twin_state, since=since)
    tables = {lang: _texts_of(built, summary_out, lang),
              other: _texts_of(twin_built, twin_summary, other)}
    return {k: tables[k] for k in (audience.EN, audience.FR)}


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
