"""``read_export_source(study_path, expected_revision)`` (CONTRAT-COMMUN-v1 §6).

A consistent, read-only reading of one study revision for workstream B, which composes its
deployment snapshot from it and never reads the study's internal tables. It takes no writer
lock, fits nothing, reads no data row and records no exposure: it reads the state snapshot,
registry entries and the bundle manifests. Raw data and final-test labels never appear.

* ``decisions``: confirmed (or to-reconfirm) decisions with their value, revision and basis;
  open proposals and the junior's words are not exported;
* ``results``: the current slots with their currency (a stale result stays listed, marked
  not current: earlier evidence is kept, never presented as current);
* ``predictor``: ``captured`` (a current capture of the confirmed selection: id, bundle,
  digests, profile, packages), ``stale`` (a capture that no longer describes current state,
  that captured another configuration than the confirmed one, or whose configuration awaits
  re-confirmation in the chat), ``not_captured`` (no capture: the recipe can be described
  but no model is invented), or ``not_applicable`` (a study created before the final test
  existed). A capture is the confirmed selection when its configuration equals the
  configuration confirmed now **and** the engine reports the capture result current (the
  rule the engine itself applies before it opens the final test): re-confirming the same
  choice at a later revision keeps it selected; the raw decision revision is not the
  criterion. ``evidence_status`` is ``evaluated`` only when the final evaluation scored that
  very predictor and it is still the captured selection;
* ``scientific_contracts``: the captured bundle's recipe and data contract only when the
  predictor is ``captured``; otherwise the recipe of the confirmed configuration (never the
  recipe of a superseded capture). Its ``selection`` block states how the capture relates to
  the confirmed selection (``capture``: ``selected``, ``awaiting_reconfirmation``,
  ``superseded``, ``not_current`` or null), with both configurations and the decision's
  status and revision, so the exporter applies the same rule;
* ``study_id``: a stable identity of the study, independent of the folder it is read from:
  the first 16 hex digits of the SHA-256 of the canonical JSON of its creation time, case
  id, dataset SHA-256 and final-test partition seed (the same study copied elsewhere has the
  same id);
* ``development_plan.n_source_records``: the number of records the engine read in the
  source file (development, final test and excluded rows), so a reader of the file can
  check it splits records as the engine did;
* ``limitations``: what the export cannot claim.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from hypotrail_runtime.contracts import ExportSource, parse
from hypotrail_runtime.errors import ContractError

CAPTURE = 'predictor.capture'
FINAL = 'final_test.evaluation'


SELECTED, AWAITING, SUPERSEDED, NOT_CURRENT = ('selected', 'awaiting_reconfirmation',
                                               'superseded', 'not_current')
AWAITING_LIMITATION = ('The model choice awaits re-confirmation in the chat: the captured '
                       'predictor is not exported until the choice is confirmed again. '
                       'Re-confirming the same choice in the chat makes the export possible '
                       'again (the capture and its final evaluation are kept).')


def _limitations(predictor: dict, opened: bool, relation: str | None = None) -> list[str]:
    out = ['A development-row parity set checks reproduction, not generalisation.']
    if predictor['status'] == 'not_captured':
        out.append('No predictor was captured: the export can describe the recipe only; no '
                   'model is rebuilt or presented as evaluated.')
    if predictor['status'] == 'stale':
        if relation == AWAITING:
            # The capture is still the one the final test scored: nothing earlier was
            # evaluated, the choice only has to be confirmed again.
            out.append(AWAITING_LIMITATION)
        elif relation == SUPERSEDED:
            out.append('The captured predictor is not the confirmed selection (another '
                       'configuration was confirmed after the capture): it is not exported as '
                       'the selected model.')
        else:
            out.append('The captured predictor no longer describes current state: it is kept '
                       'as history, not as the current model.')
        if opened and relation != AWAITING:
            out.append('The final test evaluated an earlier predictor: its verdict is not '
                       'inherited by the recipe of the current selection.')
    if not opened:
        out.append('The final test is sealed: no independent evidence exists yet.')
    elif predictor['evidence_status'] != 'evaluated' and relation != AWAITING:
        out.append('The final evaluation did not score a captured predictor: a model rebuilt '
                   'for export would be a rebuilt candidate without its verdict.')
    return out


def _protocol(split: dict) -> str | None:
    value = split.get('value') if split.get('status') == 'confirmed' else None
    if not isinstance(value, dict) or not value.get('method'):
        return None
    method = value['method']
    detail = '-'.join(f'{k}={value[k]}' for k in sorted(value) if k != 'method'
                      and isinstance(value[k], (int, float, str)))
    return f'{method}:{detail}' if detail else method


def _membership(keys: list) -> str:
    return hashlib.sha256('\n'.join(sorted(keys)).encode()).hexdigest()


def _partitions(store, state, results: list) -> list:
    """The development partitions of the current split, by row key (development rows only;
    the final test is named by its status and size, never by its keys)."""
    from mlkit.study import activities as act
    split_rid = state['current'].get('split')
    if split_rid is None or not any(r['slot'] == 'split' and r['current'] for r in results):
        return []
    out = []
    folds = act.fold_assignment(store, split_rid)
    if folds:
        for fold in sorted(set(folds.values())):
            keys = [k for k, f in folds.items() if f == fold]
            out.append({'id': f'fold_{fold}', 'role': f'fold_{fold}', 'row_keys': keys,
                        'membership_sha256': _membership(keys),
                        'exposure_status': 'exposed'})
        return out
    plan = act.evaluation_membership(store, split_rid)
    if plan is not None:
        for i, fold in enumerate(plan.get('folds') or [], start=1):
            keys = list(fold['validation_keys'])
            out.append({'id': f'fold_{i}', 'role': f'fold_{i}', 'row_keys': keys,
                        'membership_sha256': _membership(keys), 'exposure_status': 'exposed'})
        warmup = list(plan.get('unscored_keys') or [])
        if warmup:
            out.append({'id': 'warmup', 'role': 'train', 'row_keys': warmup,
                        'membership_sha256': _membership(warmup),
                        'exposure_status': 'exposed'})
        return out
    keys = act.split_keys(store, split_rid)
    for role in ('train', 'validation'):
        out.append({'id': role, 'role': role, 'row_keys': list(keys[role]),
                    'membership_sha256': _membership(list(keys[role])),
                    'exposure_status': 'exposed'})
    return out


def _contracts(store, state, predictor: dict, limitations: list) -> dict:
    """The recipe and the data contract: those of the captured bundle when there is one;
    otherwise derived from the chosen configuration without any fit (the column types of the
    development rows are read, no value is used), when the model has no tuned
    hyperparameter. A tuned model's value exists only after a fit: no recipe is invented."""
    import json
    if predictor['status'] == 'captured' and predictor['bundle_dir'] is not None:
        from hypotrail_runtime import verify_bundle
        desc = verify_bundle(Path(predictor['bundle_dir']))
        bundle = Path(predictor['bundle_dir'])
        return {'model_recipe': json.loads((bundle / desc.bundle.recipe_path).read_bytes()),
                'data_contract': json.loads((bundle / desc.bundle.data_contract_path)
                                            .read_bytes()),
                'source': 'captured_bundle', 'bundle_dir': str(bundle)}
    from mlkit.study import state as st
    config = st.choice_config(state)
    if config is None:
        limitations.append('No configuration is chosen: no recipe can be described.')
        return {'source': 'none'}
    from mlkit.study import case as c, data as dt, fit, partition
    from . import capture
    from .recipe import data_contract_from_case, recipe_from_fit
    from hypotrail_runtime.errors import ContractError
    case = c.case_of(state)
    try:
        model_inputs, model_params = capture._chosen(state, case, config)
    except Exception:                    # noqa: BLE001 - the baseline: no fitted predictor
        limitations.append('The chosen model is the constant baseline: no recipe.')
        return {'source': 'none'}
    if model_params.get('tuning') and model_params.get('tuned_value') is None:
        limitations.append('The chosen model has a tuned hyperparameter, whose value exists '
                           'only after a fit: capture the predictor to export its recipe.')
        return {'source': 'none'}
    keys = partition.development_keys(store.read_blob, partition.inputs(state))
    if keys is None:
        keys = dt.row_index(case).keys
    frame = fit._ordered(dt.load_development(case, keys).frame)
    choice = st.choice_decision(state)
    decision = state['decisions'][choice]
    slot = capture._evaluation_slot(state)
    try:
        recipe, _ = recipe_from_fit(case, frame, model_inputs, model_params,
                                    selection_reference={
                                        'decision_id': choice,
                                        'revision': int(decision['revision']),
                                        'evidence_ids': [state['current'][slot]]
                                        if slot in state['current'] else []})
        contract = data_contract_from_case(case, frame,
                                           dataset_sha256=state['dataset']['sha256'],
                                           features=list(recipe.features))
    except ContractError as exc:
        limitations.append(f'No recipe: {exc.message}')
        return {'source': 'none'}
    limitations.append('The recipe is described from the chosen configuration; no model was '
                       'captured, so the export carries no evaluated predictor.')
    return {'model_recipe': recipe.model_dump(mode='json'),
            'data_contract': contract.model_dump(mode='json'), 'source': 'configuration'}


def _validity(contracts: dict, results: list, predictor: dict) -> dict:
    current = {r['result_id']: r['current'] for r in results}
    evidence = ((contracts.get('model_recipe') or {}).get('selection_reference') or {}) \
        .get('evidence_ids') or []
    return {'selected_result_current': bool(evidence) and all(current.get(e) is True
                                                               for e in evidence),
            'artifact_status': predictor['status'],
            'evidence_status': predictor['evidence_status']}


def _case(state) -> dict:
    from mlkit.study import case as c
    try:
        title = c.case_of(state).document.get('title')
    except Exception:                    # noqa: BLE001 - a moved case file: id only
        title = None
    return {'id': state['case']['id'], 'title': title, 'sha256': state['case']['sha256']}


def _conclusion(state) -> dict | None:
    d = (state.get('decisions') or {}).get('conclusion') or {}
    if d.get('status') != 'confirmed':
        return None
    value = d.get('value')
    return {'verdict': value.get('verdict') if isinstance(value, dict) else value,
            'revision': d.get('revision')}


def study_id(state) -> str:
    """A stable identity of the study (see the module docstring), not its folder path. The
    capture's computation context uses the same identity (:mod:`mlkit.contracts.capture`)."""
    import json
    basis = {'created': state.get('created'), 'case_id': (state.get('case') or {}).get('id'),
             'dataset_sha256': (state.get('dataset') or {}).get('sha256'),
             'partition_seed': (state.get('partition') or {}).get('seed')}
    text = json.dumps(basis, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    return hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]


CHOICE_DECISIONS = ('model_choice', 'policy')


def _held_config(state) -> dict | None:
    """The configuration the study would choose if every choice decision that awaits
    re-confirmation (``reconfirm_required``, a hold stated after its confirmation) were
    confirmed again with its recorded value; None when none awaits re-confirmation."""
    import copy
    from mlkit.study import state as st
    decisions = state.get('decisions') or {}
    held = [d for d in CHOICE_DECISIONS
            if (decisions.get(d) or {}).get('status') == 'reconfirm_required']
    if not held:
        return None
    view = copy.deepcopy(dict(state))
    for d in held:
        view['decisions'][d]['status'] = 'confirmed'
    return st.choice_config(view)


def _selection_relation(state, entry: dict, current: bool) -> str:
    """How a capture registry entry relates to the selection confirmed now (the engine's own
    rule, :func:`mlkit.contracts.capture.matching_capture` and the final-test
    preconditions): ``selected`` when its configuration equals the confirmed configuration
    and the capture result is current, whatever the revision of the confirmation (the same
    choice confirmed again keeps it); ``awaiting_reconfirmation`` when the choice is on hold
    and confirming it again with its recorded value would select it; ``not_current`` for the
    same configuration whose capture is no longer current; ``superseded`` when another
    configuration (or no configuration) is chosen."""
    from mlkit.study import state as st
    captured = entry['inputs'].get('configuration')
    reference = entry['inputs'].get('selection_reference') or {}
    if reference.get('decision_id') != st.choice_decision(state):
        return SUPERSEDED
    config = st.choice_config(state)
    if config is None:
        held = _held_config(state)
        if held is not None and captured == dict(held):
            return AWAITING if current else NOT_CURRENT
        return SUPERSEDED
    if captured != dict(config):
        return SUPERSEDED
    return SELECTED if current else NOT_CURRENT


def _selection_block(state, capture_rid, entry, relation) -> dict:
    """``scientific_contracts.selection``: what the exporter needs to apply the same rule."""
    from mlkit.study import state as st
    choice = st.choice_decision(state)
    decision = (state.get('decisions') or {}).get(choice) or {}
    statuses = [(state['decisions'].get(d) or {}).get('status') for d in CHOICE_DECISIONS
                if d in (state.get('decisions') or {})]
    status = 'reconfirm_required' if 'reconfirm_required' in statuses \
        else decision.get('status')
    config = st.choice_config(state)
    return {'decision_id': choice, 'decision_status': status,
            'decision_revision': decision.get('revision'),
            'confirmed_configuration': None if config is None else dict(config),
            'capture_result_id': capture_rid,
            'capture_configuration': None if entry is None
            else entry['inputs'].get('configuration'),
            'capture': relation,
            'rule': 'the capture is the confirmed selection when its configuration equals '
                    'the confirmed configuration and the capture result is current'}


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
    relation, entry = None, None
    if capture_rid is not None:
        entry = registry.get(store, capture_rid)
        values = entry['output']['values']
        current = bool(study.currency(capture_rid)['current'])
        relation = _selection_relation(state, entry, current)
        predictor.update(status='captured' if relation == SELECTED else 'stale',
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
                evaluated = (predictor['status'] == 'captured'
                             and study.currency(final_rid)['current'])
                predictor['evidence_status'] = 'evaluated' if evaluated else 'stale'
    split = state['decisions'].get('split') or {}
    part = state.get('partition') or {}
    final_test = {'status': 'opened' if opened else ('sealed' if part else 'absent'),
                  'n_rows': (part.get('final_test') or {}).get('n_rows'),
                  'final_result_id': final_rid}
    plan = {'split': split.get('value') if split.get('status') == 'confirmed' else None,
            'split_result_id': state['current'].get('split'),
            'configuration': st.choice_config(state),
            'protocol_id': _protocol(split),
            'partitions': _partitions(store, state, results),
            'final_test': {'status': final_test['status'], 'n_rows': final_test['n_rows']},
            'n_source_records': part.get('n_rows')}
    limitations = _limitations(predictor, opened, relation)
    contracts = _contracts(store, state, predictor, limitations)
    contracts['selection'] = _selection_block(state, capture_rid, entry, relation)
    doc = {'schema_version': 'hypotrail.export_source/1',
           'study_id': study_id(state),
           'revision': study.revision, 'task': st.task_of(state),
           'case': _case(state),
           'dataset_sha256': state['dataset']['sha256'], 'scientific_contracts': contracts,
           'decisions': decisions, 'results': results, 'development_plan': plan,
           'final_test': final_test, 'predictor': predictor,
           'limitations': limitations,
           'validity': _validity(contracts, results, predictor),
           'metrics': ['mae', 'rmse'] if st.task_of(state) == st.REGRESSION
           else ['precision', 'recall', 'roc_auc', 'average_precision'],
           'conclusion': _conclusion(state),
           'extensions': {'hypotrail.capabilities': {
               'native_predictor': predictor['status'],
               # The engine reserves no calibration partition (spec L-15): the MAPIE
               # capabilities are not applicable to any study it creates today.
               'risk_control': 'not_applicable: no calibration partition',
               'conformal_intervals': 'not_applicable: no calibration partition',
               'calibrated_export': 'refused: packaging of calibrated objects not qualified'}}}
    return parse(ExportSource, doc)
