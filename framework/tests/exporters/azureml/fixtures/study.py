"""Synthetic study material for the Azure ML export tests (private to the tests).

It builds, in a temporary folder, what chantier A's ``read_export_source`` would return
for an Auto MPG-like regression study: a whitespace-separated source file without header
and with ``?`` for a missing horsepower, its data contract, the selected linear recipe, a
five-fold development plan with a disjoint final test, the confirmed decisions, current
result references and, optionally, a captured predictor bundle made by the **test double**
of ``hypotrail_runtime`` (``fixtures/fake_runtime``). Nothing here reads ``use-cases/`` or a
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
    def col(name, physical, semantic, role, nullable=False, allowed=None):
        return {'name': name, 'physical_type': physical, 'semantic_type': semantic,
                'nullable': nullable, 'allowed_values': allowed, 'role': role}
    return {
        'schema_version': 'hypotrail.data_contract/1',
        'dataset_id': 'synthetic-cars-v1',
        'source_sha256': _sha(source.read_bytes()),
        'format': 'delimited_text',
        'parser': {'encoding': 'utf-8', 'delimiter': 'whitespace', 'header': False,
                   'quotechar': '"', 'na_values': ['?']},
        'columns': [col('mpg', 'float64', 'numeric', 'target'),
                    col('cylinders', 'int64', 'numeric', 'feature'),
                    col('displacement', 'float64', 'numeric', 'feature'),
                    col('horsepower', 'float64', 'numeric', 'feature', nullable=True),
                    col('weight', 'float64', 'numeric', 'feature'),
                    col('origin', 'int64', 'categorical', 'feature', allowed=[1, 2, 3]),
                    col('car_name', 'string', 'text', 'auxiliary')],
        'row_identity': {'kind': 'source_position', 'columns': [], 'source_hash_required': True},
        'exclusions': [],
        'inference_policy': {'required_columns': list(FEATURES), 'canonical_order': list(FEATURES),
                             'extra_columns': 'ignored', 'conversions': [],
                             'unknown_categories': 'encoded_as_zero'},
    }


def recipe(family: str = 'linear') -> dict:
    types = {f: {'semantic': 'numeric', 'physical': 'float64'} for f in FEATURES}
    types['cylinders'] = {'semantic': 'numeric', 'physical': 'int64'}
    types['origin'] = {'semantic': 'categorical', 'physical': 'int64'}
    return {
        'schema_version': 'hypotrail.model_recipe/1',
        'task': 'regression', 'family': family, 'parameters': {'fit_intercept': True},
        'features': list(FEATURES), 'feature_types': types,
        'preprocessing': [
            {'operation': 'median_impute', 'version': '1',
             'parameters': {'columns': ['cylinders', 'displacement', 'horsepower', 'weight']}},
            {'operation': 'standardise', 'version': '1',
             'parameters': {'columns': ['cylinders', 'displacement', 'horsepower', 'weight']}},
            {'operation': 'one_hot', 'version': '1',
             'parameters': {'columns': ['origin'], 'unknown': 'ignore'}}],
        'target': {'name': 'mpg', 'unit': 'mpg', 'positive_label': None},
        'seeds': {},
        'output_contract': {'kind': 'regression_point', 'columns': ['prediction'],
                            'unit': 'mpg', 'positive_label': None},
        'selection_reference': {'decision_id': 'model_choice', 'revision': 6,
                                'evidence_ids': ['r-cv-linear']},
        'method_contract_version': '1', 'runtime_api_version': '1',
    }


def plan() -> dict:
    keys = [f'L{i}' for i in range(1, N_ROWS + 1)]
    final, development = keys[-N_FINAL:], keys[:-N_FINAL]
    folds = [{'id': f'fold_{k + 1}', 'role': f'fold_{k + 1}',
              'row_keys': development[k::5], 'membership_sha256': f'a-{k}',
              'exposure_status': 'out_of_fold_evaluated'} for k in range(5)]
    return {'protocol_id': 'cv5-synthetic', 'partitions': folds + [
        {'id': 'final_test', 'role': 'final_test', 'row_keys': final}],
        'final_test': {'status': 'opened_once', 'n_rows': N_FINAL}}


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


def capture(runtime, folder: Path, source: Path, contract: dict, the_recipe: dict, *,
            packager=None, role: str = 'final_development_refit') -> Path:
    frame = typed_development(source, contract)
    scope = {'role': role, 'dataset_id': contract['dataset_id'],
             'membership_sha256': 'dev-membership', 'protocol_id': 'cv5-synthetic'}
    fitted = runtime.fit_predictor(the_recipe, contract, frame, scope)
    destination = folder / 'bundle'
    runtime.capture_predictor(fitted, {'code_fingerprint': 'test'}, frame[FEATURES].head(8),
                              destination, packager=packager)
    return destination


def bind_evidence(bundle_dir: Path, status: str = 'evaluated') -> None:
    """What chantier A writes after the final result: a separate, immutable binding."""
    bundle = json.loads((bundle_dir / 'predictor_bundle.json').read_text())
    manifest = json.loads((bundle_dir / bundle['predictor_manifest_path']).read_text())
    binding = {'predictor_id': manifest['predictor_id'], 'final_result_id': 'r-final-1',
               'study_revision': REVISION, 'decision_refs': ['final_test', 'model_choice'],
               'protocol_id': 'cv5-synthetic', 'evaluation_context_id': 'ctx-1', 'status': status}
    (bundle_dir / 'evidence').mkdir(exist_ok=True)
    (bundle_dir / 'evidence' / 'binding-1.json').write_text(json.dumps(binding, indent=2))
    bundle['evidence_binding_path'] = 'evidence/binding-1.json'
    (bundle_dir / 'predictor_bundle.json').write_text(json.dumps(bundle, indent=2))


def export_source(folder: Path, *, bundle_dir: Path | None, the_recipe: dict | None = None,
                  confirmed: bool = True, current: bool = True, revision: int = REVISION,
                  contract: dict | None = None, source: Path | None = None) -> dict:
    source = source or folder / 'cars.data'
    contract = contract or data_contract(source)
    the_recipe = copy.deepcopy(the_recipe or recipe())
    return {
        'study_id': 'study-synthetic-cars', 'revision': revision,
        'case': {'id': 'synthetic-cars-v1', 'title': 'Synthetic cars'},
        'scientific_contracts': {'model_recipe': the_recipe, 'data_contract': contract},
        'decisions': [{'decision_id': 'model_choice', 'status': 'confirmed' if confirmed
                       else 'proposed', 'value': 'linear'},
                      {'decision_id': 'split', 'status': 'confirmed', 'value': 'cv5'}],
        'results': [{'result_id': 'r-cv-linear', 'activity': 'fit.linear', 'current': current},
                    {'result_id': 'r-final-1', 'activity': 'final.evaluate', 'current': True}],
        'validity': {'selected_result_current': current},
        'development_plan': plan(),
        'predictor': None if bundle_dir is None else {'bundle_dir': str(bundle_dir)},
        'limitations': ['Synthetic data: a test of the export, not of a model.'],
        'metrics': ['mae', 'rmse'],
        'conclusion': {'verdict': 'adopt_model', 'text': 'Synthetic conclusion for tests.'},
    }


def reader_of(source_doc: dict):
    """A ``read_export_source`` test double that serves one revision."""
    def read(study_path, expected_revision):
        doc = copy.deepcopy(source_doc)
        if expected_revision != doc['revision']:
            from mlkit.exporters.azureml.errors import ExportError
            raise ExportError('stale_revision', 'stale', path='expected_revision')
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
