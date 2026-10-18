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

from pathlib import Path

from . import currency
from . import read
from . import state as st
from .case import EPISTEMIC_STATUSES
from .errors import StudyError

SCHEMA = 'hypotrail.view/1'
VIEW_KEYS = ('schema', 'study', 'revision', 'updated', 'case', 'dataset', 'plan',
             'current_step', 'next_action', 'open_proposals', 'decisions', 'facts',
             'structure', 'results', 'stale', 'invalidations', 'executions', 'artifacts',
             'exposure', 'not_yet_defensible', 'settings')
DECISION_VIEW_KEYS = ('decision_id', 'status', 'value', 'proposal_id', 'depends_on',
                      'revision', 'reason', 'confirmation', 'open_proposals')
CONFIRMATION_VIEW_KEYS = ('user_words', 'channel', 'actor', 'restatement', 'proposal_id',
                          'revision', 'time', 'authenticated', 'basis')
PROPOSAL_VIEW_KEYS = ('proposal_id', 'decision_id', 'value', 'restatement', 'rationale',
                      'revision', 'created')
RESULT_VIEW_KEYS = ('slot', 'result_id', 'activity', 'current', 'stale_reason', 'partition',
                    'n_rows', 'values', 'blobs', 'params', 'inputs', 'code_fingerprint',
                    'environment', 'execution_id', 'exposure_id', 'started_revision',
                    'integrity')
ARTIFACT_PLACEHOLDER = {'manifest': None, 'status': 'not_rendered', 'items': {}}

SUMMARY_SCHEMA = 'hypotrail.summary/1'
SUMMARY_KEYS = ('goal', 'current_step', 'plan', 'next_action', 'open_proposals', 'decisions',
                'results', 'artifacts', 'executions', 'not_yet_defensible')
# The limits that matter first when a chat resumes; the others are named, not quoted.
SUMMARY_PRIORITY = ('interrupted_executions', 'result_integrity', 'adopted_rule_not_evaluated',
                    'code_changed', 'stale_results', 'delegated_decisions', 'unconfirmed_decisions',
                    'uncertain_features_included', 'validation_is_not_independent')
SUMMARY_TOP = 5


def _decisions(state: dict) -> dict:
    out = {}
    for d in st.DECISION_IDS:
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
    earlier revision, or citing a result that is no longer current, is ``stale`` even if
    that render succeeded. The stored value stays visible as ``recorded_status``.
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
        items[name] = {**item, 'recorded_status': item.get('status'),
                       'status': currency.effective_status(item, state, current),
                       'message': currency.message(name, item, state, current)}
    return {'manifest': read.ARTIFACTS_FILE,
            'status': currency.overall(i['status'] for i in items.values()), 'items': items}


def rid_reason(item: dict, key: str):
    """A key of a result item's derived stale reason (``code_changed``, ...), or None."""
    reason = item.get('stale_reason')
    return reason.get(key) if isinstance(reason, dict) else None


def _adopted_without_evaluation(state: dict, results: dict) -> str | None:
    """The adopted policy rule when no current policy evaluation covers it."""
    decision = state['decisions']['policy']
    rule = decision['value']
    if decision['status'] not in ('confirmed', 'reconfirm_required') or not isinstance(rule, str):
        return None
    item = results.get('policy.evaluation')
    if item and item['current'] and item['integrity'] == 'ok':
        params = item['params'] if isinstance(item['params'], dict) else {}
        rules = params.get('rules') or ([params['rule']] if params.get('rule') else [])
        if rule in rules:
            return None
    return rule


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


def summary(view: dict) -> dict:
    """A compact digest of a view (``hypotrail status --summary``, D3).

    It holds what a chat needs to resume and to decide its next move, in a few
    kilobytes: the study goal in the case's words, the position (the plan's step ids,
    titles and statuses), the open proposals with
    their restatement, each decision with its value, status, basis and recorded words,
    the current results by slot, each deliverable with its status and one sentence,
    interrupted and late executions, and the first limits of ``not_yet_defensible``.
    The full view stays in ``hypotrail status --json``.
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
                 for e, r in sorted(view['executions']['late'].items())]}
    rank = {k: i for i, k in enumerate(SUMMARY_PRIORITY)}
    ordered = sorted(view['not_yet_defensible'],
                     key=lambda x: rank.get(x['id'], len(SUMMARY_PRIORITY)))
    defensible = {'top': [{'id': x['id'], 'text': x['text']} for x in ordered[:SUMMARY_TOP]],
                  'more': [x['id'] for x in ordered[SUMMARY_TOP:]]}
    plan = [{'id': step['id'], 'title': step['title'], 'status': step['status']}
            for step in view['plan']]
    out = {'goal': goal, 'current_step': view['current_step'], 'plan': plan,
           'next_action': view['next_action'], 'open_proposals': proposals,
           'decisions': decisions, 'results': results, 'artifacts': artifacts,
           'executions': executions, 'not_yet_defensible': defensible}
    return {k: out[k] for k in SUMMARY_KEYS}


def build(study_dir) -> dict:
    """The view model of the study at ``study_dir`` (or of an open :class:`read.Study`)."""
    study = study_dir if isinstance(study_dir, read.Study) else read.open(Path(study_dir))
    state = study.state
    plan = st.derive_plan(state)
    results = _results(study, state)
    defensible = st.not_yet_defensible(state)
    broken = sorted(s for s, r in results.items() if r['integrity'] != 'ok')
    if broken:
        defensible.append({'id': 'result_integrity', 'slots': broken,
                           'text': 'Some recorded results fail their integrity check and '
                                   'cannot be cited.'})
    changed = sorted(s for s, r in results.items()
                     if r['integrity'] == 'ok' and rid_reason(r, 'code_changed'))
    if changed:
        defensible.append({'id': 'code_changed', 'slots': changed,
                           'text': 'The code of these activities changed after their results '
                                   'were computed; those results, and the ones computed from '
                                   'them, cannot be cited until they are run again.'})
    adopted = _adopted_without_evaluation(state, results)
    if adopted:
        defensible.append({'id': 'adopted_rule_not_evaluated', 'rules': [adopted],
                           'text': f'The adopted policy {adopted} has no current evaluation; '
                                   'its figures cannot be cited until it is evaluated again.'})
    return {
        'schema': SCHEMA,
        'study': str(study.study_dir),
        'revision': state['revision'],
        'updated': state['updated'],
        'case': dict(state['case']),
        'dataset': dict(state['dataset']),
        'plan': plan,
        'current_step': next((s['id'] for s in plan if s['current']), None),
        'next_action': st.next_action(state),
        'open_proposals': [{k: p[k] for k in PROPOSAL_VIEW_KEYS}
                           for p in sorted(st.open_proposals(state),
                                           key=lambda p: (p['revision'], p['proposal_id']))],
        'decisions': _decisions(state),
        'facts': _facts(state),
        'structure': state['structure'],
        'results': results,
        'stale': state['stale'],
        'invalidations': state['invalidations'],
        'executions': state['executions'],
        'artifacts': _artifacts(study, state),
        'exposure': study.exposure_summary(),
        'not_yet_defensible': defensible,
        'settings': state['settings'],
    }
