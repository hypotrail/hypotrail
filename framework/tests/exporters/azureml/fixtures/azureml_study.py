"""Synthetic study material for the Azure ML export tests (private to the tests).

It builds, in a temporary folder, what chantier A's ``read_export_source`` would return
for an Auto MPG-like regression study: a whitespace-separated source file without header
and with ``?`` for a missing horsepower, its data contract, the selected linear recipe, a
five-fold development plan with a disjoint final test, the confirmed decisions, current
result references and, optionally, a predictor bundle captured by the real
``hypotrail_runtime`` (workstream A; the test double was removed at integration). Nothing here reads ``use-cases/`` or a
real study. The final test rows are in the source file (as in a real study) but never in
the development plan's partitions.
"""
from __future__ import annotations

import copy
import hashlib
import json
import random
from pathlib import Path

N_ROWS = 60
N_FINAL = 12
FEATURES = ['cylinders', 'displacement', 'horsepower', 'weight', 'origin']
REVISION = 7


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_source(folder: Path, seed: int = 20261023) -> Path:
    rng = random.Random(seed)
    lines = []
    for i in range(N_ROWS):
        cylinders = rng.choice([4, 6, 8])
        displacement = round(60 + cylinders * 30 + rng.uniform(-20, 20), 1)
        horsepower = '?' if i % 17 == 5 else f'{round(40 + displacement * 0.4 + rng.uniform(-8, 8), 1)}'
        weight = int(round(1500 + displacement * 6 + rng.uniform(-150, 150)))
        origin = rng.choice([1, 2, 3])
        mpg = round(48 - 0.006 * weight - 0.5 * cylinders + 1.5 * (origin - 1)
                    + rng.uniform(-2, 2), 1)
        lines.append(f'{mpg}   {cylinders}   {displacement}   {horsepower}   {weight}.   '
                     f'{origin}\t"car {i % 23}"')
    path = folder / 'cars.data'
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return path


def data_contract(source: Path) -> dict:
    """A ``hypotrail.data_contract/1`` in the runtime's vocabulary (the engine derives the
    same shape from a case with ``mlkit.contracts.recipe.data_contract_from_case``)."""
    def col(name, physical, semantic, role, nullable=False, allowed=None):
        return {'name': name, 'physical_type': physical, 'semantic_type': semantic,
                'nullable': nullable, 'allowed_values': allowed, 'role': role}
    return _validated('contract', {
        'schema_version': 'hypotrail.data_contract/1',
        'dataset_id': 'synthetic-cars-v1',
        'source_sha256': _sha(source.read_bytes()),
        'format': 'csv',
        'parser': {'encoding': 'utf-8', 'delimiter': 'whitespace', 'header': False,
                   'quotechar': '"', 'na_values': ['?'], 'decimal': '.'},
        'columns': [col('mpg', 'float64', 'numeric', 'target'),
                    col('cylinders', 'int64', 'numeric', 'feature'),
                    col('displacement', 'float64', 'numeric', 'feature'),
                    col('horsepower', 'float64', 'numeric', 'feature', nullable=True),
                    col('weight', 'float64', 'numeric', 'feature'),
                    col('origin', 'int64', 'category', 'feature', allowed=[1, 2, 3]),
                    col('car_name', 'string', 'category', 'auxiliary', nullable=True)],
        'row_identity': {'kind': 'source_position', 'columns': [], 'source_hash_required': True},
        'exclusions': [],
        'inference_policy': {'required_columns': list(FEATURES), 'canonical_order': list(FEATURES),
                             'extra_columns': 'reject', 'conversions': [],
                             'unknown_categories': 'predictor_handles'},
        'extensions': {},
    })


def _validated(kind: str, document: dict) -> dict:
    """The document as the runtime validates and serialises it (defaults made explicit),
    which is what a bundle and ``read_export_source`` carry."""
    import hypotrail_runtime as rt
    model = rt.validate_data_contract(document) if kind == 'contract' \
        else rt.validate_recipe(document)
    return model.model_dump(mode='json')


def recipe(family: str = 'linear') -> dict:
    """The engine's linear regression recipe (``mlkit.contracts.recipe.recipe_from_fit``)."""
    types = {f: {'semantic': 'numeric', 'physical': 'float64'} for f in FEATURES}
    types['cylinders'] = {'semantic': 'numeric', 'physical': 'int64'}
    types['origin'] = {'semantic': 'category', 'physical': 'int64'}
    return {
        'schema_version': 'hypotrail.model_recipe/1',
        'task': 'regression', 'family': family, 'parameters': {},
        'features': list(FEATURES), 'feature_types': types,
        'preprocessing': [
            {'operation': 'category_as_text', 'version': 1, 'parameters': {'columns': ['origin']}},
            {'operation': 'special_value_indicator', 'version': 1, 'parameters': {'values': []}},
            {'operation': 'numeric_median_impute_scale', 'version': 1, 'parameters': {}},
            {'operation': 'categorical_mode_impute_onehot', 'version': 1,
             'parameters': {'handle_unknown': 'ignore'}}],
        'target': {'name': 'mpg', 'unit': 'mpg', 'positive_label': None},
        'seeds': {},
        'output_contract': {'kind': 'regression_point', 'columns': ['prediction'],
                            'unit': 'mpg', 'positive_label': None},
        'selection_reference': {'decision_id': 'model_choice', 'revision': 6,
                                'evidence_ids': ['r-cv-linear']},
        'method_contract_version': 'hypotrail.method/1', 'runtime_api_version': '1.0',
        'extensions': {},
    }


def plan() -> dict:
    keys = [f'L{i}' for i in range(1, N_ROWS + 1)]
    final, development = keys[-N_FINAL:], keys[:-N_FINAL]
    folds = [{'id': f'fold_{k + 1}', 'role': f'fold_{k + 1}',
              'row_keys': development[k::5], 'membership_sha256': f'a-{k}',
              'exposure_status': 'out_of_fold_evaluated'} for k in range(5)]
    return {'protocol_id': 'cv5-synthetic', 'partitions': folds + [
        {'id': 'final_test', 'role': 'final_test', 'row_keys': final}],
        'final_test': {'status': 'opened_once', 'n_rows': N_FINAL},
        'n_source_records': N_ROWS}


def typed_development(source: Path, contract: dict):
    """The development rows as typed columns (what an authorised training reads)."""
    import shlex

    import pandas as pd
    names = [c['name'] for c in contract['columns']]
    rows, index = [], []
    keys = {k for p in plan()['partitions'] if p['role'] != 'final_test' for k in p['row_keys']}
    for number, line in enumerate(source.read_text().splitlines(), 1):
        if f'L{number}' in keys:
            values = shlex.split(line)
            rows.append(values)
            index.append(f'L{number}')
    frame = pd.DataFrame(rows, columns=names, index=index)
    frame['horsepower'] = pd.to_numeric(frame['horsepower'].replace('?', None))
    for name in ('mpg', 'displacement', 'weight'):
        frame[name] = frame[name].astype(float)
    for name in ('cylinders', 'origin'):
        frame[name] = frame[name].astype(int)
    return frame


def training_membership(keys) -> str:
    """The engine's ``training_scope.membership_sha256`` of the rows a predictor is fitted
    on: the SHA-256 of the sorted row keys, one per line (the study's row-key blob). The
    export checks it against its development plan (review round 3, B3-1)."""
    return _sha(''.join(k + '\n' for k in sorted(set(keys))).encode('utf-8'))


def capture(runtime, folder: Path, source: Path, contract: dict, the_recipe: dict, *,
            packager=None, role: str = 'final_development_refit') -> Path:
    frame = typed_development(source, contract)
    scope = {'role': role, 'dataset_id': contract['dataset_id'],
             'membership_sha256': training_membership(list(frame.index)),
             'protocol_id': 'cv5-synthetic'}
    fitted = runtime.fit_predictor(the_recipe, contract, frame, scope)
    destination = folder / 'bundle'
    runtime.capture_predictor(fitted, None, frame[FEATURES].head(8), destination,
                              packager=packager, parity_origin='authorized_development',
                              code_fingerprint=_sha(b'test-code'))
    return destination


def bind_evidence(bundle_dir: Path, status: str = 'evaluated') -> None:
    """What the engine writes after the final result (``write_evidence_binding``): a new,
    separate binding version named by the bundle document."""
    import hypotrail_runtime as rt
    predictor_id = rt.verify_bundle(bundle_dir).predictor_id
    rt.write_evidence_binding(bundle_dir, {
        'schema_version': 'hypotrail.evidence_binding/1', 'predictor_id': predictor_id,
        'final_result_id': 'r-final-1', 'study_revision': REVISION,
        'decision_refs': ['final_test', 'model_choice'], 'protocol_id': 'cv5-synthetic',
        'evaluation_context_id': 'ctx-1', 'status': status})


def export_source(folder: Path, *, bundle_dir: Path | None, the_recipe: dict | None = None,
                  confirmed: bool = True, current: bool = True, revision: int = REVISION,
                  contract: dict | None = None, source: Path | None = None) -> dict:
    source = source or folder / 'cars.data'
    # Copies: a test may change the document without changing the session's material.
    contract = copy.deepcopy(contract or data_contract(source))
    the_recipe = copy.deepcopy(the_recipe or recipe())
    return {
        'study_id': 'study-synthetic-cars', 'revision': revision,
        'case': {'id': 'synthetic-cars-v1', 'title': 'Synthetic cars'},
        'scientific_contracts': {'model_recipe': the_recipe, 'data_contract': contract},
        # As read_export_source states them: each confirmed decision with the revision of
        # its confirmation (the recipe's selection_reference names the model choice's).
        'decisions': [{'decision_id': 'model_choice', 'status': 'confirmed' if confirmed
                       else 'proposed', 'value': 'linear',
                       'revision': the_recipe['selection_reference']['revision']},
                      {'decision_id': 'split', 'status': 'confirmed', 'value': 'cv5',
                       'revision': 2}],
        'results': [{'result_id': 'r-cv-linear', 'activity': 'fit.linear', 'current': current},
                    {'result_id': 'r-final-1', 'activity': 'final.evaluate', 'current': True}],
        'validity': {'selected_result_current': current},
        'development_plan': plan(),
        # The predictor as read_export_source describes a current capture of the selection
        # that the final test evaluated (the binding beside the bundle can only lower it).
        # It names the predictor id the capture recorded (the export requires the bundle at
        # bundle_dir to be that predictor).
        'predictor': None if bundle_dir is None else {
            'status': 'captured', 'bundle_dir': str(bundle_dir), 'evidence_status': 'evaluated',
            'predictor_id': _bundle_id(bundle_dir),
            'capture_result_id': 'r-capture-1', 'final_result_id': 'r-final-1'},
        'limitations': ['Synthetic data: a test of the export, not of a model.'],
        'metrics': ['mae', 'rmse'],
        'conclusion': {'verdict': 'adopt_model', 'text': 'Synthetic conclusion for tests.'},
    }


def _bundle_id(bundle_dir: Path) -> str | None:
    """The id the capture recorded: the bundle document's, read without verification (the
    tests of an altered bundle alter it after the capture)."""
    try:
        return json.loads((Path(bundle_dir) / 'predictor_bundle.json').read_text())['predictor_id']
    except (OSError, ValueError, KeyError):
        return None


def reader_of(source_doc: dict):
    """A ``read_export_source`` test double that serves one revision and, for another one,
    raises what the real reader raises: ``hypotrail_runtime``'s ``ContractError``."""
    def read(study_path, expected_revision):
        doc = copy.deepcopy(source_doc)
        if expected_revision != doc['revision']:
            from hypotrail_runtime.errors import ContractError
            raise ContractError('stale_revision', f'The study is at revision {doc["revision"]}, '
                                f'not {expected_revision}.', path='expected_revision',
                                remediation='Read status again and export that revision.',
                                details={'revision': doc['revision'],
                                         'expected_revision': expected_revision})
        return doc
    return read


def profile(folder: Path, **changes) -> Path:
    document = {
        'schema_version': 'hypotrail.azure_target/1',
        'subscription_id': '00000000-0000-4000-8000-000000000000',
        'resource_group': 'rg-atelier', 'workspace': 'ws-atelier', 'compute': 'cpu-atelier',
        'data_asset': {'name': 'synthetic-cars-development', 'version': '1'},
        'environment': {'name': 'hypotrail-py313', 'version': '1',
                        'base_image': 'mcr.microsoft.com/azureml/openmpi4.1.0-ubuntu22.04:20250601.v1'},
        'identity': {'mode': 'user_identity'},
    }
    for key, value in changes.items():
        if value is None:
            document.pop(key, None)
        else:
            document[key] = value
    path = folder / 'atelier.yaml'
    import yaml
    path.write_text(yaml.safe_dump(document, sort_keys=True))
    return path
