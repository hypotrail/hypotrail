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
from pathlib import Path

from . import currency
from . import read
from . import records as rec
from . import state as st
from .case import EPISTEMIC_STATUSES
from .errors import StudyError

SCHEMA = 'hypotrail.view/1'
VIEW_KEYS = ('schema', 'study', 'revision', 'updated', 'case', 'dataset', 'plan',
             'current_step', 'next_action', 'open_proposals', 'decisions', 'facts',
             'structure', 'results', 'stale', 'invalidations', 'executions', 'artifacts',
             'exposure', 'not_yet_defensible', 'settings', 'task',
             # Post-v0.1 (P2): the junior's conditions and holds, verbatim.
             'notes',
             # ADR 0005 (v0.2a): the confirmation mode and the study language.
             'mode', 'language')
NOTE_VIEW_KEYS = ('note_id', 'decision_id', 'kind', 'user_words', 'status', 'revision',
                  'resolution')
DECISION_VIEW_KEYS = ('decision_id', 'status', 'value', 'proposal_id', 'depends_on',
                      'revision', 'reason', 'confirmation', 'open_proposals')
CONFIRMATION_VIEW_KEYS = ('user_words', 'channel', 'actor', 'restatement', 'proposal_id',
                          'revision', 'time', 'authenticated', 'basis', 'delegation_scope',
                          # ADR 0005 (R3): the point the agent raised, kept by the junior.
                          'agent_concern')
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
                # Post-v0.1 (T8, F5): the five-line resume recap, generated from state.
                'recap')
SUMMARY_NOTE_KEYS = ('note_id', 'decision_id', 'status', 'user_words', 'resolution_words')
SUMMARY_HOLD_KEYS = ('decision_id', 'status', 'notes')
# The limits that matter first when a chat resumes; the others are named, not quoted.
SUMMARY_PRIORITY = ('sources_changed', 'interrupted_executions', 'open_holds',
                    # Post-v0.1 fixes (D2): the conclusion no longer describes the study.
                    'conclusion_outdated', 'result_integrity',
                    'adopted_rule_not_evaluated',
                    'capacity_exceeds_validation', 'small_validation_partition',
                    'code_changed', 'stale_results',
                    # D6: an inconclusive conclusion without a policy or a model choice.
                    'inconclusive_without_choice',
                    'delegated_decisions', 'unconfirmed_decisions',
                    'uncertain_features_included', 'high_cardinality_grouping',
                    'validation_is_not_independent')
SUMMARY_TOP = 5


def _decisions(state: dict) -> dict:
    out = {}
    for d in st.decision_ids(state):
        dec = state['decisions'][d]
        conf = dec['confirmation']
        out[d] = {'decision_id': d, 'status': dec['status'], 'value': dec['value'],
                  'proposal_id': dec['proposal_id'], 'depends_on': list(dec['depends_on']),
                  'revision': dec['revision'], 'reason': dec['reason'],
                  'confirmation': ({**{k: conf.get(k) for k in CONFIRMATION_VIEW_KEYS},
                                    'basis': st.confirmation_basis(conf)}
                                   if isinstance(conf, dict) else None),
                  'open_proposals': sorted(p['proposal_id'] for p in st.open_proposals(state)
                                           if p['decision_id'] == d)}
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
    return {'manifest': read.ARTIFACTS_FILE,
            'status': currency.overall(i['status'] for i in items.values()), 'items': items}


def rid_reason(item: dict, key: str):
    """A key of a result item's derived stale reason (``code_changed``, ...), or None."""
    reason = item.get('stale_reason')
    return reason.get(key) if isinstance(reason, dict) else None


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
        if (rec.canonical_rule(rule) or rule) in {rec.canonical_rule(r) or r for r in rules}:
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
                        'reason': dec['reason'], 'open_proposals': dec['open_proposals']}
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
                                  'message': i.get('message')}
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
    defensible = {'top': [{'id': x['id'], 'text': x['text']} for x in ordered[:SUMMARY_TOP]],
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
           'holds': _holds(notes, decisions)}
    out['recap'] = recap(out, view)
    return {k: out[k] for k in SUMMARY_KEYS}


# --- the resume recap (post-v0.1, T8 and F5) ------------------------------------------

RECAP_LABELS = ('Goal', 'Decided', 'Now', 'Next', 'Limit')
DECISION_LABELS = {'prediction_time': 'prediction moment',
                   'feature_availability': 'feature availability', 'split': 'split',
                   'policy': 'policy', 'model_choice': 'model choice',
                   'conclusion': 'conclusion'}
# A regression study's model choice (M3), in words: the recap never says "policy".
MODEL_CHOICE_WORDS = {'fit.linear': 'the linear model', 'fit.baseline': 'the mean baseline'}
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
    rule = next((by_rule[rec.canonical_rule(c) or c] for c in candidates
                 if isinstance(c, str) and (rec.canonical_rule(c) or c) in by_rule), None)
    if rule is None:
        return None
    model = ((item['values']['rules'][rule] or {}).get('models') or {}).get(HEADLINE_MODEL) or {}
    precision, recall = _pct(model.get('precision')), _pct(model.get('recall'))
    if precision is None and recall is None:
        return None
    figures = ', '.join(f'{name} {v}' for name, v in (('precision', precision),
                                                      ('recall', recall)) if v)
    n = item['values'].get('n')
    rows = f' on the {n} validation rows' if isinstance(n, int) else ' on the validation rows'
    return {'rule': rule, 'adopted': adopted is not None and (rec.canonical_rule(adopted)
                                                              or adopted) == (
                                                                  rec.canonical_rule(rule) or rule),
            'text': f'the logistic model at {rule}{rows}: {figures}, result '
                    f'{item["result_id"][:RECAP_RID]}'}


def _recap_decision(decision_id: str, d: dict, errors: dict | None = None,
                    headline: dict | None = None) -> str:
    label = DECISION_LABELS[decision_id]
    value = d['value']
    if decision_id == 'feature_availability' and isinstance(value, dict):
        parts = []
        excluded = sorted(value.get('not_available', []) + value.get('uncertain_excluded', []))
        doubtful = sorted(value.get('uncertain_included', []))
        if excluded:
            parts.append('excluded ' + ', '.join(excluded))
        if doubtful:
            parts.append('kept with a doubt ' + ', '.join(doubtful))
        text = f'{label} ({"; ".join(parts) if parts else "every feature kept"})'
    elif decision_id == 'split' and isinstance(value, dict):
        method = _spaced(value.get('method', 'split'))
        fraction = value.get('validation_fraction')
        share = (f', {round(100 * fraction):d}% for validation'
                 if isinstance(fraction, (int, float)) and not isinstance(fraction, bool) else '')
        if value.get('method') == 'ordinal_cutoff' and value.get('column') is not None:
            share = f' on {value["column"]}, validation from {value.get("cutoff")}'
        text = f'{label} ({method}{share})'
    elif decision_id in ('policy',) and isinstance(value, str):
        text = f'{label} {value}'
        if headline and headline['adopted']:
            text += f' ({headline["text"]})'
    elif decision_id == 'model_choice' and isinstance(value, str):
        text = f'{label}: {MODEL_CHOICE_WORDS.get(value, value)}'
        mae = (errors or {}).get('mae', {}).get(value)
        if mae is not None:
            text += (f' (validation MAE {mae} {errors["unit"]}, result '
                     f'{errors["result_id"][:RECAP_RID]})')
    elif decision_id == 'conclusion' and isinstance(value, dict):
        text = f'{label} {_spaced(value.get("verdict", ""))}'.strip()
    else:
        text = label
    notes = []
    if d['basis'] == st.DELEGATED_DEFAULT:
        notes.append('delegated to the assistant')
    if d['status'] == 'reconfirm_required':
        notes.append('to confirm again')
    return text + (f' [{", ".join(notes)}]' if notes else '')


def _recap_next(summary_out: dict, view: dict) -> str:
    nxt = summary_out['next_action']
    kind = nxt.get('kind')
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
        return f'your answer, in your own words, on the {label}: "{restatement}"'
    if kind in ('propose', 'run', 'blocked'):
        if nxt.get('step') == summary_out['current_step']:
            return str(nxt.get('message', '')).strip()
        title = titles.get(nxt.get('step'), nxt.get('step') or 'the next step')
        return f'{title}: {nxt.get("message", "")}'.strip()
    return 'nothing left in the plan; review what is not yet defensible.'


def recap(summary_out: dict, view: dict) -> list[str]:
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
    """
    goal = summary_out['goal']
    use = _fact_value(goal['intended_use']) or 'not stated in the case'
    pt = goal['prediction_time']
    if pt is None:
        moment = 'not decided yet'
    elif pt['source'] == 'decision' and pt['status'] == 'confirmed':
        moment = str(pt['value'])
    else:
        moment = f'{pt["value"]} (from the case, not decided yet)'
    errors = _regression_errors(view)
    headline = _policy_headline(view, summary_out) if st.task_of(view.get('task')) == st.BINARY \
        else None
    decided = [_recap_decision(d, item, errors, headline)
               for d, item in summary_out['decisions'].items()
               if item['status'] in ('confirmed', 'reconfirm_required')]
    titles = {s['id']: s['title'] for s in summary_out['plan']}
    step = titles.get(summary_out['current_step'], 'every step is done') \
        if summary_out['current_step'] else 'every step is done'
    behind = sorted(name for name, item in summary_out['artifacts']['items'].items()
                    if item.get('status') != 'ok' and name != 'workbench')
    deliverables = ('the report and notebook are up to date' if not behind
                    else ', '.join(behind) + ' not up to date')
    chosen = summary_out['decisions'].get('model_choice') or {}
    if errors and chosen.get('status') not in ('confirmed', 'reconfirm_required'):
        # Before the model choice, "Now" gives both validation errors (P3).
        named = '; '.join(f'{MODEL_CHOICE_WORDS.get(slot, slot)} {mae} {errors["unit"]}'
                          for slot, mae in sorted(errors['mae'].items()))
        step += (f' (validation MAE: {named}; result '
                 f'{errors["result_id"][:RECAP_RID]})')
    if headline and not headline['adopted']:
        # D10: before a rule is adopted, "Now" gives the latest evaluated figures.
        step += f' (latest policy evaluation: {headline["text"]})'
    limits = [x for x in view['not_yet_defensible'] if x['id'] not in RECAP_LIMIT_SKIP]
    rank = {k: i for i, k in enumerate(SUMMARY_PRIORITY)}
    limits.sort(key=lambda x: rank.get(x['id'], len(SUMMARY_PRIORITY)))
    limit = limits[0]['text'] if limits else 'none recorded.'
    nxt = _recap_next(summary_out, view).rstrip()
    holds = summary_out.get('holds') or []
    if holds:
        # P2: a condition the junior stated stays visible in every chat until resolved;
        # D5: the holds of one decision are quoted together.
        said = '; '.join('; '.join(f'"{n["user_words"]}"' for n in h['notes'])
                         + f' (the {DECISION_LABELS.get(h["decision_id"], h["decision_id"])})'
                         for h in holds)
        nxt += ('' if nxt.endswith(('.', '"', '?')) else '.') + (
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
    return {
        'schema': SCHEMA,
        'study': str(study.study_dir),
        'revision': state['revision'],
        'updated': state['updated'],
        'case': dict(state['case']),
        'dataset': dict(state['dataset']),
        'plan': plan,
        'current_step': next((s['id'] for s in plan if s['current']), None),
        'next_action': st.next_action(state, suspected),
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
        'not_yet_defensible': defensible,
        'settings': state['settings'],
        'task': st.task_of(state),
        'notes': [{k: n[k] for k in NOTE_VIEW_KEYS} for n in st.notes(state)],
        'mode': st.mode_of(state),
        'language': st.language_of(state),
    }


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
                    'basis', 'delegation_scope', 'superseded', 'invalidation', 'text')
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


def moments(task: str) -> list[dict]:
    """The four moments of the plan (``content/steps.yaml``, ``moments``)."""
    from . import texts

    data = texts.load('steps')
    overlay = data.get('regression_moments', {}) if task == st.REGRESSION else {}
    return [{'id': m['id'], 'title': m['title'], 'steps': list(overlay.get(m['id'], m['steps']))}
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

    def slot(self, slot) -> str:
        base, sep, column = str(slot).partition(':')
        label = self.data['activities'].get(base) or self.data['activity_fallback'].format(
            activity=base)
        return self.data['slot_with_column'].format(label=label, column=column) if sep else label

    @staticmethod
    def join(labels) -> str:
        labels = list(labels)
        return labels[0] if len(labels) == 1 else ', '.join(labels[:-1]) + ' and ' + labels[-1]

    def template(self, name: str, **fields) -> str:
        return self.data['templates'][name].format(**fields)


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


def _effect_sentences(t: _Texts, item: dict, full: dict | None, kept: list[str]) -> list[str]:
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
                slots=t.join(t.slot(s) for s in inv['refit'])))
        elif inv['kept_fits']:
            out.append(t.data['effects']['nothing_refitted'])
        others = [s for s in inv['stale_slots'] if s not in inv['refit']]
        if others:
            out.append(t.data['effects']['stale'].format(slots=t.join(t.slot(s) for s in others)))
    again = inv['reconfirm_required']
    if again:
        causes = t.data['causes']
        if inv['mutation'] == 'result_replaced':
            cause = causes['result_replaced'].format(
                activity=t.slot(item['slot'] or (full or {}).get('decision_id')))
        elif inv['mutation'] == 'hold_added':
            cause = causes['hold_added'].format(decision=t.decision(item['decision_id']))
        else:
            cause = causes['decision'].format(
                decision=t.decision((full or {}).get('decision_id') or item['decision_id']))
        name = 'reconfirm_one' if len(again) == 1 else 'reconfirm_many'
        out.append(t.data['effects'][name].format(
            Decisions=_cap(t.join(t.decision(d) for d in again)), cause=cause))
    return out


def _text(t: _Texts, item: dict, *, again: bool, state: dict, full: dict | None,
          record: dict, kept: list[str]) -> str:
    kind, action = item['kind'], item['action']
    params = record.get('params') or {}
    decision = t.decision(item['decision_id']) if item['decision_id'] else ''
    fields = {'decision': decision, 'Decision': _cap(decision)}
    if kind == 'proposed':
        value = params.get('value')
        # Only a rule identifier or a model slot is quoted: other values are free text.
        identifier = item['decision_id'] in st.CHOICE_DECISION.values() and isinstance(value, str)
        main = (t.template('proposed_value', value=value, **fields) if identifier
                else t.template('proposed', **fields))
        if item['superseded']:
            main += ' ' + t.data['templates']['superseding']
    elif kind == 'confirmed':
        name = ('confirmed_delegated' if item['basis'] == st.DELEGATED_DEFAULT
                else 'confirmed_again' if again else 'confirmed')
        main = t.template(name, channel=item['channel'], **fields)
    elif kind == 'withdrawn':
        main = t.template('withdrawn', **fields)
    elif kind == 'hold_recorded':
        main = t.template('hold_recorded', words=params.get('user_words'), **fields)
    elif action == 'decide.note':
        # ADR 0005 (R3): a correction note is listed as ``other``, not as a hold.
        main = t.template('correction_recorded', words=params.get('user_words'), **fields)
    elif kind == 'hold_resolved':
        note = (state.get('notes') or {}).get(item['note_id']) or {}
        name = 'hold_withdrawn' if action == 'decide.withdraw_note' else 'hold_resolved'
        main = t.template(name, hold=note.get('user_words'), words=params.get('user_words'),
                          **fields)
    elif item['activity'] is not None or item['slot'] is not None:
        activity = t.slot(item['slot'] or item['activity'])
        act = {'activity': activity, 'Activity': _cap(activity)}
        if kind in ('result_added', 'result_replaced'):
            if item['rules']:
                main = t.template(f'{kind}_rules', rules=', '.join(item['rules']), **act)
            elif item['column'] and ':' not in str(item['slot']):
                main = t.template(f'{kind}_column', column=item['column'], **act)
            else:
                main = t.template(kind, **act)
        elif action == _PROMOTE:
            main = t.template('run_late', **act)
        else:
            main = t.template(kind, **act)
    elif action == 'init':
        main = t.template('created')
    else:
        main = t.template('other', action=action)
    return ' '.join([main, *_effect_sentences(t, item, full, kept)])


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
    out.update({'moments': moments(built['task']), 'pauses': pauses(state),
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
