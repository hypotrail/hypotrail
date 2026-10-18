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
                          'revision', 'time', 'authenticated')
PROPOSAL_VIEW_KEYS = ('proposal_id', 'decision_id', 'value', 'restatement', 'rationale',
                      'revision', 'created')
RESULT_VIEW_KEYS = ('slot', 'result_id', 'activity', 'current', 'stale_reason', 'partition',
                    'n_rows', 'values', 'blobs', 'params', 'inputs', 'code_fingerprint',
                    'environment', 'execution_id', 'exposure_id', 'started_revision',
                    'integrity')
ARTIFACT_PLACEHOLDER = {'manifest': None, 'status': 'not_rendered', 'items': {}}


def _decisions(state: dict) -> dict:
    out = {}
    for d in st.DECISION_IDS:
        dec = state['decisions'][d]
        conf = dec['confirmation']
        out[d] = {'decision_id': d, 'status': dec['status'], 'value': dec['value'],
                  'proposal_id': dec['proposal_id'], 'depends_on': list(dec['depends_on']),
                  'revision': dec['revision'], 'reason': dec['reason'],
                  'confirmation': ({k: conf.get(k) for k in CONFIRMATION_VIEW_KEYS}
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
        item.update(slot=slot, result_id=rid, current=st.is_current(state, slot),
                    stale_reason=state['stale'].get(rid), integrity='ok')
        try:
            entry = study.result(rid)
        except StudyError as exc:
            item.update(integrity=exc.code, current=False)
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


def _artifacts(study: read.Study) -> dict:
    manifest = study.artifacts()
    if manifest is None:
        return dict(ARTIFACT_PLACEHOLDER, items={})
    items = manifest.get('artifacts', manifest.get('items', {})) if isinstance(manifest, dict) else {}
    return {'manifest': read.ARTIFACTS_FILE, 'status': manifest.get('status', 'present')
            if isinstance(manifest, dict) else 'unreadable', 'items': items}


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
        'artifacts': _artifacts(study),
        'exposure': study.exposure_summary(),
        'not_yet_defensible': defensible,
        'settings': state['settings'],
    }
