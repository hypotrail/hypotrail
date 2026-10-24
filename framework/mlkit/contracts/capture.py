"""The ``predictor.capture`` activity and the captured predictor of the final test (spec L-10).

``hypotrail run predictor.capture [--profile base|workshop] [--packager FORMAT]`` captures the
configuration the study chose (the confirmed policy or model choice, the configuration the
final test would open) **before** the final test is opened:

1. the complete predictor (:mod:`hypotrail_runtime`) is fitted on every development row,
   the rows the final evaluation refits on, with the hyperparameter chosen there by the
   engine's inner cross-validation when the model is tuned;
2. its predictions on a bounded set of development rows (features only) are compared with
   the engine's own fit path (:func:`mlkit.study.fit._fit_predict`); a difference beyond
   the declared tolerance refuses the capture (nothing is relaxed);
3. the bundle is written in a staging directory, reloaded and checked for parity, optionally
   packaged by an injected packager (workshop profile: packaging is required), then moved
   atomically to ``.hypotrail/predictors/<predictor_id>/`` (content-addressed: the same
   capture again reuses the verified bundle). The packages are made from the native bundle
   after its id exists, so they are not part of the id: a bundle that holds packages lives
   at ``<predictor_id>+<format>[+<format>...]`` and a capture is reused only from the
   bundle of the same id *and* the same package formats; the result always reports the
   packages of the bundle it names (review A3, 2026-10-24). Before a bundle is added or
   reused, every existing bundle of the same predictor id is verified; an altered one
   refuses the capture. The staging folder is removed whatever the outcome.

Its registry result names the predictor id, the digests and the parity. Once a study holds a
capture, ``final_test.evaluation`` requires a *current* capture of the very configuration it
opens and evaluates the reloaded predictor: it predicts the final-test rows with the
bundle's payload, never with a new fit, and its result names the predictor id. A study
without a capture keeps the historical refit (identities unchanged). After the evaluation is
recorded, an evidence binding (``hypotrail.evidence_binding/1``) is written beside the
bundle; the hashed bundle is never modified.

Requested packaging that cannot run (unknown format, module or extra missing) is refused
when the capture is planned, before any row is read. The workshop profile's packager
``mlflow_pyfunc`` is implemented by workstream B (``mlkit.integrations.mlflow_packaging``);
``synthetic_test`` exists only under ``HYPOTRAIL_TEST_HOOKS=1``.
"""
from __future__ import annotations

import hashlib
import importlib
import importlib.util
import os
import shutil
from pathlib import Path
from typing import Mapping

from hypotrail_runtime import RUNTIME_API_VERSION, __version__ as RUNTIME_VERSION
from hypotrail_runtime.errors import ContractError

from . import errors as cerr

CAPTURE = 'predictor.capture'
PROFILES = ('base', 'workshop')
# format -> (module, factory, argument, backend module that must be importable). The
# workshop packager is workstream B's ``packager_for('atelier')`` (MLflow pyfunc).
PACKAGERS = {'mlflow_pyfunc': ('mlkit.integrations.mlflow_packaging', 'packager_for',
                               'atelier', 'mlflow')}
TEST_PACKAGERS = {'synthetic_test': ('mlkit.contracts.testing_packager', 'packager', None,
                                     None)}
WORKSHOP_PACKAGER = 'mlflow_pyfunc'
PARITY_ROWS = 50
TOLERANCE = {'rtol': 1e-10, 'atol': 1e-12, 'exact': []}
PREDICTORS_DIR = 'predictors'
NOTE = ('The predictor of the chosen configuration, fitted on every development row before the '
        'final test is opened, with its whole preparation; reloaded and compared with the '
        'engine\'s own fit before it is kept. It is not evidence: the final test is.')
LIMITATIONS = (
    'Trusted local serialisation (pickle): the bundle digest proves integrity, not safety; load '
    'it only from a source you control.',
    'Parity rows are development rows (features only): they check reproduction, not '
    'generalisation.',
    'Qualified families: linear and ridge regression, logistic regression. Other families are '
    'refused, never replaced.')


def _refuse(code: str, message: str, **details) -> None:
    raise cerr.to_study_error(ContractError(code, message, details=details,
                                            remediation=details.pop('remediation', '')))


def packager_spec(name: str | None) -> tuple[str, str] | None:
    if name is None:
        return None
    if name in TEST_PACKAGERS and os.environ.get('HYPOTRAIL_TEST_HOOKS') == '1':
        return TEST_PACKAGERS[name]
    if name not in PACKAGERS:
        _refuse('capability_not_supported', f'Unknown packager {name!r}.',
                packager=name, known=sorted(PACKAGERS),
                remediation='Use a known packaging format.')
    return PACKAGERS[name]


def require_packager(name: str | None) -> None:
    """Refuse a requested packager that cannot be imported, before anything is read."""
    spec = packager_spec(name)
    if spec is None:
        return
    for module in (spec[0], spec[3]):
        if module is None:
            continue
        try:
            found = importlib.util.find_spec(module) is not None
        except ModuleNotFoundError:
            found = False
        if not found:
            _refuse('optional_dependency_missing',
                    f'The packager {name} is requested but {module} is not installed.',
                    packager=name, module=module,
                    remediation='Install the azureml extra (MLflow), or capture with '
                                '--profile base; the final test stays closed.')


def load_packager(name: str | None):
    spec = packager_spec(name)
    if spec is None:
        return None
    module = importlib.import_module(spec[0])
    factory = getattr(module, spec[1])
    return factory(spec[2]) if spec[2] is not None else factory()


# --- planning (no pandas) ----------------------------------------------------------------------

def _chosen(state: Mapping, case, config: Mapping) -> tuple[dict, dict]:
    from mlkit.study import activities as act, trials
    model = config['model']
    if model in act.CANDIDATE_FITS:
        return act.model_plan(state, case, model)
    if trials.is_variant_slot(model):
        return act.model_plan(state, case, act.VARIANT, index=trials.variant_index(model))
    _refuse('capability_not_supported', 'The chosen model is the constant baseline: there is '
            'no fitted predictor to capture.', model=model,
            remediation='Export the recipe only; the baseline needs no runtime.')


def _evaluation_slot(state: Mapping) -> str:
    from mlkit.study import activities as act, state as st
    return act.REGRESSION_EVALUATION if st.task_of(state) == st.REGRESSION else act.POLICY


def missing(state: Mapping) -> list[dict]:
    """Unmet requirements of a capture (``preconditions`` style)."""
    from mlkit.study import state as st
    out = []
    if not st.has_wp_b1_decisions(state):
        return [{'requirement': 'final_test_decision',
                 'detail': 'This study was created before the final test existed: there is no '
                           'chosen configuration to capture.'}]
    if st.final_test_opened(state):
        out.append({'requirement': 'final_test_sealed',
                    'detail': 'A predictor is captured before the final test is opened; after '
                              'the opening a new fit would be a rebuilt candidate, not the '
                              'evaluated model.'})
    if st.choice_config(state) is None:
        out.append({'requirement': 'decision_confirmed', 'decision': st.choice_decision(state),
                    'detail': 'Confirm the policy (or the model choice) before capturing the '
                              'chosen model.'})
    slot = _evaluation_slot(state)
    if not st.is_current(state, slot):
        out.append({'requirement': 'result_current', 'slot': slot})
    return out


def plan(store, state: Mapping, case, inputs: dict, params: dict, options: Mapping,
         expose) -> None:
    from mlkit.study import activities as act, partition, state as st
    config = st.choice_config(state)
    model_inputs, model_params = _chosen(state, case, config)
    profile = options.get('profile') or 'base'
    packager = options.get('packager')
    if profile == 'workshop' and packager is None:
        packager = WORKSHOP_PACKAGER
    require_packager(packager)
    choice = st.choice_decision(state)
    decision = state['decisions'][choice]
    slot = _evaluation_slot(state)
    model_slot = config['model']
    results = {slot: state['current'][slot]}
    if model_slot in state['current']:
        results[model_slot] = state['current'][model_slot]
    inputs.update(results=results, configuration=dict(config), model_inputs=model_inputs,
                  target=act._target(case),
                  selection_reference={'decision_id': choice,
                                       'revision': int(decision['revision']),
                                       'evidence_ids': [results[slot]]})
    params.update(model=model_slot, model_params=model_params, profile=profile,
                  packager=packager, parity_rows=PARITY_ROWS, tolerance=dict(TOLERANCE),
                  runtime={'distribution': 'hypotrail-runtime', 'version': RUNTIME_VERSION,
                           'api_version': RUNTIME_API_VERSION},
                  role='final_development_refit')
    features = list(model_inputs['features'])
    keys = partition.development_keys(store.read_blob, inputs.get('development'))
    if keys is None:
        from mlkit.study import data as dt
        keys = dt.row_index(case).keys
    expose('train_fit', partition.DEVELOPMENT, keys, features + [case.target_column])


def matching_capture(store, state: Mapping, case, model_inputs: Mapping,
                     model_params: Mapping, config: Mapping) -> dict | None:
    """The capture the final evaluation must use: None when the study never captured;
    otherwise the current capture of this exact configuration, or a refusal
    (``model_not_captured``)."""
    from mlkit.study import registry, state as st
    rid = state['current'].get(CAPTURE)
    if rid is None:
        return None
    entry = registry.get(store, rid)
    same = (entry['inputs'].get('configuration') == dict(config)
            and entry['inputs'].get('model_inputs') == dict(model_inputs)
            and entry['params'].get('model_params') == dict(model_params))
    if not same or not st.is_current(state, CAPTURE):
        _refuse('model_not_captured', 'The captured predictor does not describe the '
                'configuration the final test would open (or is no longer current).',
                capture=rid, remediation='Run predictor.capture again before opening the '
                                         'final test.')
    values = entry['output']['values']
    return {'result_id': rid, 'predictor_id': values['predictor_id'],
            'bundle': values['bundle'], 'profile': entry['params'].get('profile'),
            'packages': [p['format'] for p in values.get('packages') or []]}


# --- computation ---------------------------------------------------------------------------------

def _membership(inputs: Mapping, keys) -> str:
    development = inputs.get('development')
    if development is not None:
        return development['row_keys']
    return hashlib.sha256('\n'.join(sorted(keys)).encode()).hexdigest()


def _study_id(store) -> str:
    return hashlib.sha256(str(Path(store.study_dir).resolve()).encode()).hexdigest()[:16]


def predictors_root(store) -> Path:
    return Path(store.home) / PREDICTORS_DIR


def compute(store, plan_: Mapping) -> dict:
    try:
        return _compute(store, plan_)
    except ContractError as exc:
        raise cerr.to_study_error(exc) from None


def _compute(store, plan_: Mapping) -> dict:
    import numpy as np
    from hypotrail_runtime import capture_predictor, fit_predictor
    from hypotrail_runtime.predictor import compare
    from mlkit.study import activities as act, fit
    from . import context as cx
    from .recipe import data_contract_from_case, recipe_from_fit
    inputs, params = plan_['inputs'], plan_['params']
    case, dataset = act.load(plan_, store)
    development = fit._ordered(dataset.frame)
    model_inputs, model_params = inputs['model_inputs'], dict(params['model_params'])
    binary = case.task == 'binary'
    recipe, info = recipe_from_fit(case, development, model_inputs, model_params,
                                   selection_reference=inputs['selection_reference'])
    if 'tuning' in info:
        model_params['tuned_value'] = info['tuning']['value']
    features = list(recipe.features)
    contract = data_contract_from_case(case, development, dataset_sha256=plan_['dataset_sha256'],
                                       features=features)
    from mlkit.integrations import pandera_validation
    validation = pandera_validation.validate(contract, development[[
        col.name for col in contract.columns if col.role in ('feature', 'target')]],
        partition='development', authorized=('development',), purpose='training')
    if validation['status'] != 'ok':
        raise ContractError('contract_invalid', 'The development rows do not satisfy the data '
                            'contract the predictor would declare.', path='development',
                            remediation='Read the issues; nothing is corrected silently.',
                            issues=validation['issues'])
    protocol = model_inputs.get('evaluation_protocol')
    scope = {'role': params['role'], 'dataset_id': case.id,
             'membership_sha256': _membership(inputs, list(development.index)),
             'protocol_id': protocol.get('method') if isinstance(protocol, Mapping) else None}
    fitted = fit_predictor(recipe, contract, development, scope)
    parity = development.iloc[:min(int(params['parity_rows']), len(development))]
    engine = fit._fit_predict(case, development, parity, model_inputs, model_params, binary)[0]
    runtime = fitted.predict(parity[features]).values
    engine_parity = compare(np.asarray(engine, dtype=float), runtime, params['tolerance'])
    if engine_parity.status != 'ok':
        raise ContractError('artifact_integrity_failed', 'The complete predictor does not '
                            'reproduce the engine\'s fit of this configuration.',
                            remediation='Report it; the tolerance is never relaxed.',
                            details=engine_parity.model_dump(mode='json'))
    context = cx.build(method='predictor.fit', activity_id=CAPTURE,
                       study_id=_study_id(store), expected_revision=plan_['started_revision'],
                       code_fingerprint=plan_['code']['fingerprint'],
                       protocol_id=scope['protocol_id'],
                       decision_refs=[inputs['selection_reference']['decision_id']],
                       input_refs=[{'id': 'dataset', 'sha256': plan_['dataset_sha256'],
                                    'role': 'source'}],
                       partition_refs=[{'id': 'development',
                                        'membership_sha256': scope['membership_sha256'],
                                        'role': 'development', 'exposure_status': 'exposed'}],
                       backend={'distribution': 'scikit-learn',
                                'version': cx.installed_version('scikit-learn')})
    root = predictors_root(store)
    root.mkdir(parents=True, exist_ok=True)
    staging = root / f'.staging-{plan_.get("execution_id") or os.getpid()}'
    if staging.exists():
        shutil.rmtree(staging)
    try:
        packager = load_packager(params.get('packager'))
        descriptor = capture_predictor(fitted, context, parity[features], staging, packager,
                                       parity_origin='authorized_development',
                                       tolerance=params['tolerance'],
                                       extensions={'hypotrail.engine_parity':
                                                   engine_parity.model_dump(mode='json')})
        final, reused, held = _place(root, staging, descriptor)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    values = {
        'predictor_id': descriptor.predictor_id,
        'bundle': f'{PREDICTORS_DIR}/{final.name}',
        'reused': reused, 'profile': params['profile'],
        'model': params['model'], 'family': recipe.family, 'task': recipe.task,
        'configuration': dict(inputs['configuration']), 'features': features,
        'recipe_sha256': descriptor.manifest.recipe_sha256,
        'data_contract_sha256': descriptor.manifest.data_contract_sha256,
        'training_scope': dict(scope), 'n_train': int(len(development)),
        'output_contract': recipe.output_contract.model_dump(mode='json'),
        'learnt_state': fitted.learnt_state(), 'validation': validation,
        'tuning': info.get('tuning') and {'value': info['tuning']['value']},
        'parity': descriptor.parity.model_dump(mode='json') if descriptor.parity else None,
        'engine_parity': engine_parity.model_dump(mode='json'),
        'packages': [{'format': p.format, 'artifact_id': p.artifact_id} for p in held],
        'runtime': dict(params['runtime']), 'computation_id': cx.computation_id(context),
        'limitations': list(LIMITATIONS), 'note': NOTE}
    return {'values': values, 'blobs': {}, 'partition': 'development',
            'n_rows': int(len(development))}


def bundle_name(predictor_id: str, formats) -> str:
    """The folder of a bundle under ``predictors/``: its predictor id, plus the formats of
    its optional packages (sorted) when it holds any."""
    formats = sorted(formats)
    return '+'.join([predictor_id, *formats])


def _place(root: Path, staging: Path, descriptor):
    """Move the staged bundle into place, or reuse the verified bundle of the same id and
    package formats. Return ``(folder, reused, packages held by that folder)``."""
    from hypotrail_runtime import verify_bundle
    pid = descriptor.predictor_id
    formats = [p.format for p in descriptor.bundle.optional_packages]
    final = root / bundle_name(pid, formats)
    # Every bundle of this predictor already in the store is verified first: an altered one
    # is reported, never silently shadowed by a new folder.
    for sibling in sorted(root.iterdir()):
        if sibling.name == pid or sibling.name.startswith(pid + '+'):
            existing = verify_bundle(sibling)
            if existing.predictor_id != pid:
                raise ContractError('artifact_integrity_failed', f'{sibling.name} holds '
                                    'another predictor.', path=sibling.name,
                                    remediation='Remove or restore the altered bundle.')
    if final.exists():
        existing = verify_bundle(final)      # a verified identical capture is reused
        held = list(existing.bundle.optional_packages)
        if sorted(p.format for p in held) != sorted(formats):
            raise ContractError('artifact_integrity_failed', f'{final.name} does not hold the '
                                'packages its name declares (packages_differ).',
                                path=final.name, remediation='Remove or restore the bundle.',
                                details={'reason': 'packages_differ',
                                         'held': sorted(p.format for p in held),
                                         'requested': sorted(formats)})
        return final, True, held
    os.replace(staging, final)
    return final, False, list(descriptor.bundle.optional_packages)


def load_for_final(store, predictor: Mapping):
    """The verified, reloaded predictor the final evaluation scores with (its own parity
    rows are checked first)."""
    from hypotrail_runtime import check_parity, load_predictor
    root = predictors_root(store)
    try:
        loaded = load_predictor(Path(store.home) / predictor['bundle'], trusted_roots=[root])
        if loaded.predictor_id != predictor['predictor_id']:
            raise ContractError('artifact_integrity_failed', 'The bundle holds another '
                                'predictor.', remediation='Capture again.')
        parity = check_parity(loaded)
        if parity.status != 'ok':
            raise ContractError('artifact_integrity_failed', 'The reloaded predictor does not '
                                'reproduce its parity rows.', remediation='Capture again.',
                                details=parity.model_dump(mode='json'))
    except ContractError as exc:
        raise cerr.to_study_error(exc) from None
    return loaded, parity


def bind_evidence(store, plan_: Mapping, result_id: str, revision: int) -> None:
    """Write the evidence binding of the evaluated predictor (after the result exists)."""
    from hypotrail_runtime import write_evidence_binding
    predictor = plan_['inputs'].get('predictor')
    if not predictor:
        return
    write_evidence_binding(Path(store.home) / predictor['bundle'], {
        'schema_version': 'hypotrail.evidence_binding/1',
        'predictor_id': predictor['predictor_id'], 'final_result_id': result_id,
        'study_revision': int(revision),
        'decision_refs': ['final_test'], 'protocol_id': None,
        'evaluation_context_id': plan_['input_key'], 'status': 'evaluated'})
