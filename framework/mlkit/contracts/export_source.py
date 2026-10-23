"""``read_export_source(study_path, expected_revision)`` (CONTRAT-COMMUN-v1 §6).

A consistent, read-only reading of one study revision for workstream B, which composes its
deployment snapshot from it and never reads the study's internal tables. It takes no writer
lock, fits nothing, reads no data row and records no exposure: it reads the state snapshot,
registry entries and the bundle manifests. Raw data and final-test labels never appear.

* ``decisions``: confirmed (or to-reconfirm) decisions with their value, revision and basis;
  open proposals and the junior's words are not exported;
* ``results``: the current slots with their currency (a stale result stays listed, marked
  not current: earlier evidence is kept, never presented as current);
* ``predictor``: ``captured`` (a current capture: id, bundle, digests, profile, packages),
  ``stale`` (a capture that no longer describes current state), ``not_captured`` (no capture:
  the recipe can be described but no model is invented), or ``not_applicable`` (a study
  created before the final test existed). ``evidence_status`` is ``evaluated`` only when the
  final evaluation scored that very predictor;
* ``limitations``: what the export cannot claim.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from hypotrail_runtime.contracts import ExportSource, parse
from hypotrail_runtime.errors import ContractError

CAPTURE = 'predictor.capture'
FINAL = 'final_test.evaluation'


def _limitations(predictor: dict, opened: bool) -> list[str]:
    out = ['A development-row parity set checks reproduction, not generalisation.']
    if predictor['status'] == 'not_captured':
        out.append('No predictor was captured: the export can describe the recipe only; no '
                   'model is rebuilt or presented as evaluated.')
    if predictor['status'] == 'stale':
        out.append('The captured predictor no longer describes current state: it is kept as '
                   'history, not as the current model.')
    if not opened:
        out.append('The final test is sealed: no independent evidence exists yet.')
    elif predictor['evidence_status'] != 'evaluated':
        out.append('The final evaluation did not score a captured predictor: a model rebuilt '
                   'for export would be a rebuilt candidate without its verdict.')
    return out


def read_export_source(study_path, expected_revision: int) -> ExportSource:
    from mlkit.study import read, registry, state as st
    from mlkit.study.store import StudyStore
    study = read.open(study_path)
    state = study.state
    if study.revision != expected_revision:
        raise ContractError('stale_revision', f'The study is at revision {study.revision}, not '
                            f'{expected_revision}.', path='expected_revision',
                            remediation='Read status again and export that revision.',
                            details={'revision': study.revision,
                                     'expected_revision': expected_revision})
    store = StudyStore(study_path)
    decisions = []
    for did in st.decision_ids(state):
        d = state['decisions'][did]
        if d['status'] in ('confirmed', 'reconfirm_required') and d['confirmation']:
            decisions.append({'decision_id': did, 'status': d['status'], 'value': d['value'],
                              'revision': int(d['revision'] or 0),
                              'basis': st.confirmation_basis(d['confirmation'])})
    results = []
    for slot, rid in sorted(state['current'].items()):
        currency = study.currency(rid)
        results.append({'slot': slot, 'result_id': rid,
                        'activity': registry.get(store, rid)['activity'],
                        'current': bool(currency['current']), 'reason': currency['reason']})
    opened = st.final_test_opened(state)
    final_rid = state['current'].get(FINAL)
    predictor = {'status': 'not_captured', 'predictor_id': None, 'capture_result_id': None,
                 'bundle_dir': None, 'recipe_sha256': None, 'data_contract_sha256': None,
                 'profile': None, 'packages': [], 'evidence_status': 'unassessed',
                 'final_result_id': final_rid}
    if not st.has_wp_b1_decisions(state):
        predictor['status'] = 'not_applicable'
    capture_rid = state['current'].get(CAPTURE)
    if capture_rid is not None:
        entry = registry.get(store, capture_rid)
        values = entry['output']['values']
        current = study.currency(capture_rid)['current']
        predictor.update(status='captured' if current else 'stale',
                         predictor_id=values['predictor_id'], capture_result_id=capture_rid,
                         bundle_dir=str(Path(store.home) / values['bundle']),
                         recipe_sha256=values['recipe_sha256'],
                         data_contract_sha256=values['data_contract_sha256'],
                         profile=values['profile'],
                         packages=[p['format'] for p in values.get('packages') or []])
        if final_rid is not None:
            final = registry.get(store, final_rid)
            used = (final['inputs'].get('predictor') or {}).get('predictor_id')
            if used == values['predictor_id']:
                predictor['evidence_status'] = 'evaluated' if study.currency(final_rid)[
                    'current'] else 'stale'
    split = state['decisions'].get('split') or {}
    plan = {'split': split.get('value') if split.get('status') == 'confirmed' else None,
            'split_result_id': state['current'].get('split'),
            'configuration': st.choice_config(state)}
    part = state.get('partition') or {}
    final_test = {'status': 'opened' if opened else ('sealed' if part else 'absent'),
                  'n_rows': (part.get('final_test') or {}).get('n_rows'),
                  'final_result_id': final_rid}
    contracts = {}
    if predictor['bundle_dir'] is not None:
        contracts = {'recipe_path': str(Path(predictor['bundle_dir']) / 'recipe.json'),
                     'data_contract_path': str(Path(predictor['bundle_dir']) /
                                               'data_contract.json'),
                     'bundle_manifest_path': str(Path(predictor['bundle_dir']) / 'bundle.json')}
    doc = {'schema_version': 'hypotrail.export_source/1',
           'study_id': hashlib.sha256(str(Path(study_path).resolve()).encode()).hexdigest()[:16],
           'revision': study.revision, 'task': st.task_of(state),
           'case': {'id': state['case']['id'], 'sha256': state['case']['sha256']},
           'dataset_sha256': state['dataset']['sha256'], 'scientific_contracts': contracts,
           'decisions': decisions, 'results': results, 'development_plan': plan,
           'final_test': final_test, 'predictor': predictor,
           'limitations': _limitations(predictor, opened),
           'extensions': {'hypotrail.capabilities': {
               'native_predictor': predictor['status'],
               # The engine reserves no calibration partition (spec L-15): the MAPIE
               # capabilities are not applicable to any study it creates today.
               'risk_control': 'not_applicable: no calibration partition',
               'conformal_intervals': 'not_applicable: no calibration partition',
               'calibrated_export': 'refused: packaging of calibrated objects not qualified'}}}
    return parse(ExportSource, doc)
