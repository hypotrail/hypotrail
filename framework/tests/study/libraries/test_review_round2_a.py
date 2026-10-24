"""Regressions of the second review round of 24 October 2026, area A.

A1-R2a the native bundle embedded in a package is the outer predictor, byte for byte (the
runtime's package check, ``ArtifactPackager.verify`` and ``package``); A4-R2 calibration
claims always name their rows and are atomic under a file lock; N1 every missing marker of
a categorical column stays missing in the Evidently adapter; N2 an integer that no float
represents exactly is ``contract_invalid``; N4 MAPIE's rank below 0.5 is at most one rank
above the adapter's rule (conservative, documented). Ported from the reviewer's probes.
Every bundle, study and ledger lives in ``tmp_path``; the data are synthetic.
"""
from __future__ import annotations

import importlib.util
import json
import math
import pickle
import shutil
import threading
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from hypotrail_runtime import (canonical, capture_predictor, fit_predictor, load_predictor,
                               validate_recipe, verify_bundle)
from hypotrail_runtime.errors import ContractError
from hypotrail_runtime.predictor import FittedPredictor

import docs_v1

SCOPE = {'role': 'development_fit', 'dataset_id': 'synthetic', 'membership_sha256': 'b' * 64,
         'protocol_id': None}
FP = 'c' * 64
PKG = 'packages/mlflow_pyfunc'

needs_mlflow = pytest.mark.skipif(importlib.util.find_spec('mlflow') is None,
                                  reason='azureml extra (mlflow)')
needs_mapie = pytest.mark.skipif(importlib.util.find_spec('mapie') is None,
                                 reason='uncertainty extra')


def _frame(n=200, seed=0, with_target=True):
    rng = np.random.default_rng(seed)
    age = rng.normal(40, 10, n)
    age[rng.random(n) < 0.1] = np.nan
    branch = np.where(rng.random(n) < 0.5, 'Alder', 'Brook').astype(object)
    branch[rng.random(n) < 0.05] = None
    band = rng.integers(1, 4, n).astype('int64')
    logit = 0.05 * (np.nan_to_num(age, nan=40) - 40) + (branch == 'Alder') * 0.8 - 0.3 * band
    y = np.where(rng.random(n) < 1 / (1 + np.exp(-logit)), 'yes', 'no')
    out = pd.DataFrame({'age': pd.Series(age, dtype='float64'),
                        'branch': pd.Series(branch, dtype=object),
                        'band': pd.Series(band, dtype='int64')})
    if with_target:
        out['renewed'] = pd.Series(y, dtype=object)
    return out


def _fitted():
    return fit_predictor(docs_v1.recipe(), docs_v1.contract(), _frame(), SCOPE)


def _parity():
    """Parity rows without ``band == 3``: a model changed on that category agrees on them."""
    p = _frame(60, 1, with_target=False)
    return p[p['band'] != 3].reset_index(drop=True)


def _other_model(fitted, delta=5.0):
    """Another model that agrees with ``fitted`` on the parity rows (band=3 never appears)."""
    pipe = pickle.loads(pickle.dumps(fitted.pipeline))
    names = list(pipe[:-1].get_feature_names_out())
    pipe.named_steps['model'].coef_[0, names.index('cat__band_3')] += delta
    return FittedPredictor(recipe=fitted.recipe, data_contract=fitted.data_contract,
                           pipeline=pipe, training_scope=fitted.training_scope,
                           n_train=fitted.n_train)


def _refused(fn, *args, code='artifact_integrity_failed', **kw):
    with pytest.raises(ContractError) as e:
        fn(*args, **kw)
    assert e.value.code == code, e.value.to_dict()
    return e.value


def _inventory(root: Path, prefix: str = '') -> list[dict]:
    out = []
    for path in sorted(p for p in Path(root).rglob('*') if p.is_file()):
        if '__pycache__' in path.relative_to(root).parts:
            continue
        rel = path.relative_to(root).as_posix()
        out.append({'relative_path': f'{prefix}{rel}', 'size_bytes': path.stat().st_size,
                    'sha256': canonical.file_sha256(path)})
    return out


def _redescribe_mlflow_package(dest: Path) -> None:
    """Re-describe an edited MLflow package consistently everywhere an attacker can write:
    the descriptor inside the package, the one beside it and the bundle document."""
    from mlkit.integrations import mlflow_packaging as mp
    pkg = dest / PKG
    files = [e for e in mp._inventory(pkg) if e['relative_path'] != mp.DESCRIPTOR_FILE]
    inner_doc = json.loads((pkg / mp.DESCRIPTOR_FILE).read_bytes())
    inner_doc['files'] = files
    (pkg / mp.DESCRIPTOR_FILE).write_bytes(json.dumps(inner_doc, indent=2, sort_keys=True)
                                           .encode() + b'\n')
    desc_path = dest / f'{PKG}.descriptor.json'
    desc = json.loads(desc_path.read_bytes())
    desc['files'] = files
    desc_path.write_bytes(canonical.dumps(desc) + b'\n')
    doc = json.loads((dest / 'predictor_bundle.json').read_bytes())
    kept = [e for e in doc['files'] if not e['relative_path'].startswith(PKG + '/')
            and e['relative_path'] != f'{PKG}.descriptor.json']
    new = [{'relative_path': f'{PKG}/{e["relative_path"]}', 'size_bytes': e['size_bytes'],
            'sha256': e['sha256']} for e in mp._inventory(pkg)]
    new.append({'relative_path': f'{PKG}.descriptor.json', 'size_bytes': desc_path.stat().st_size,
                'sha256': canonical.file_sha256(desc_path)})
    doc['files'] = sorted(kept + new, key=lambda e: e['relative_path'])
    doc['optional_packages'][0]['manifest_sha256'] = canonical.file_sha256(desc_path)
    (dest / 'predictor_bundle.json').write_bytes(canonical.dumps(doc) + b'\n')


def _swap_embedded_bundle(package: Path, tmp: Path, fitted) -> str:
    """Replace the native bundle inside ``package`` with a capture of another model that
    agrees on the parity rows; return that other predictor's id."""
    inner = tmp / 'inner'
    capture_predictor(_other_model(fitted), None, _parity(), inner, None, code_fingerprint=FP)
    native = package / 'artifacts' / 'native_bundle'
    shutil.rmtree(native)
    shutil.copytree(inner, native)
    return verify_bundle(inner).predictor_id


# --- A1-R2a: the embedded native bundle is the evaluated predictor ----------------------------

@needs_mlflow
def test_a_package_carrying_another_model_under_the_same_id_is_refused(tmp_path):
    """Reviewer probe: the embedded bundle re-captured with another model that agrees on the
    parity rows, the package re-described consistently. Before the fix the outer bundle
    verified under the same id, the MLflow verify passed and the export said ``packaged``,
    while the pyfunc served the other model."""
    from mlkit.integrations import mlflow_packaging as mp
    f = _fitted()
    dest = tmp_path / 'trusted' / 'b'
    pid = capture_predictor(f, None, _parity(), dest, mp.packager_for('atelier'),
                            code_fingerprint=FP).predictor_id
    honest = mp.ArtifactPackager().verify(dest, dest / PKG)
    assert honest.status == 'passed', honest
    inner_pid = _swap_embedded_bundle(dest / PKG, tmp_path, f)
    _redescribe_mlflow_package(dest)
    assert inner_pid != pid
    e = _refused(verify_bundle, dest)
    assert e.path == f'{PKG}/artifacts/native_bundle'
    assert e.details['found'] == inner_pid
    _refused(load_predictor, dest, trusted_roots=[dest.parent])
    from mlkit.exporters.azureml.artifact import verify_predictor
    from mlkit.exporters.azureml.errors import ExportError
    recipe = json.loads((dest / 'recipe.json').read_bytes())
    contract = json.loads((dest / 'data_contract.json').read_bytes())
    with pytest.raises(ExportError) as err:
        verify_predictor(dest, recipe, contract)
    assert 'artifact_integrity_failed' in (err.value.code,
                                           (err.value.details or {}).get('contract_code'))


@needs_mlflow
def test_mlflow_verify_refuses_a_package_whose_embedded_bundle_is_another_model(tmp_path):
    """The packager's own check, on a package outside the bundle (the runtime's bundle check
    does not see it): another embedded predictor is ``artifact_integrity_failed``."""
    from mlkit.integrations import mlflow_packaging as mp
    f = _fitted()
    native = tmp_path / 'native'
    capture_predictor(f, None, _parity(), native, None, code_fingerprint=FP)
    package = tmp_path / 'package'
    mp.ArtifactPackager().package(native, package)
    assert mp.ArtifactPackager().verify(native, package).status == 'passed'
    _swap_embedded_bundle(package, tmp_path, f)
    doc = json.loads((package / mp.DESCRIPTOR_FILE).read_bytes())
    doc['files'] = [e for e in mp._inventory(package) if e['relative_path'] != mp.DESCRIPTOR_FILE]
    (package / mp.DESCRIPTOR_FILE).write_bytes(json.dumps(doc).encode())
    with pytest.raises(mp.PackagingError) as e:
        mp.ArtifactPackager().verify(native, package)
    assert e.value.code == 'artifact_integrity_failed'
    assert 'another predictor' in e.value.message


@needs_mlflow
@pytest.mark.parametrize('edit', ['wrapper', 'mlmodel_path', 'embedded_extra_file'])
def test_mlflow_verify_refuses_a_package_that_would_serve_something_else(tmp_path, edit):
    from mlkit.integrations import mlflow_packaging as mp
    import yaml
    native = tmp_path / 'native'
    capture_predictor(_fitted(), None, _parity(), native, None, code_fingerprint=FP)
    package = tmp_path / 'package'
    mp.ArtifactPackager().package(native, package)
    if edit == 'wrapper':
        (package / mp.WRAPPER_FILE).write_text(mp.WRAPPER_SOURCE + '\n# changed\n')
    elif edit == 'mlmodel_path':
        shutil.copytree(package / 'artifacts' / 'native_bundle', package / 'artifacts' / 'other')
        model = yaml.safe_load((package / 'MLmodel').read_text())
        model['flavors']['python_function']['artifacts']['native_bundle']['path'] = \
            'artifacts/other'
        (package / 'MLmodel').write_text(yaml.safe_dump(model))
    else:
        (package / 'artifacts' / 'native_bundle' / 'notes.txt').write_text('extra')
    doc = json.loads((package / mp.DESCRIPTOR_FILE).read_bytes())
    doc['files'] = [e for e in mp._inventory(package) if e['relative_path'] != mp.DESCRIPTOR_FILE]
    (package / mp.DESCRIPTOR_FILE).write_bytes(json.dumps(doc).encode())
    with pytest.raises(mp.PackagingError) as e:
        mp.ArtifactPackager().verify(native, package)
    assert e.value.code == 'artifact_integrity_failed'


class _EmbeddingPackager:
    """A test packager that embeds a native bundle in its package, as the MLflow packager
    does: the bundle it is given (honest) or another one (``source``)."""
    format = 'embedding_test'

    def __init__(self, source: Path | None = None, declare: str | None = 'native'):
        self.source, self.declare = source, declare

    def package(self, native_bundle_dir, output_dir, parity_spec):
        native = verify_bundle(native_bundle_dir)
        source = self.source or Path(native_bundle_dir)
        shutil.copytree(source, Path(output_dir) / 'native',
                        ignore=shutil.ignore_patterns('packages', 'evidence'))
        doc = {'schema_version': 'hypotrail.package_descriptor/1', 'format': self.format,
               'artifact_id': '0' * 64, 'predictor_id': native.predictor_id,
               'files': _inventory(output_dir), 'signature': {}, 'environment': {},
               'parity_result': {'schema_version': 'hypotrail.parity_result/1', 'status': 'ok',
                                 'n_rows': 1, 'max_abs_diff': 0.0, 'max_rel_diff': None,
                                 'exact_mismatches': 0,
                                 'tolerance': dict(parity_spec['tolerance']), 'reason': None,
                                 'extensions': {}},
               'extensions': {} if self.declare is None
               else {'hypotrail.native_bundle': self.declare}}
        doc['artifact_id'] = canonical.artifact_id(doc, exclude=('artifact_id',))
        return doc

    def verify(self, native_bundle_dir, package_dir, parity_spec):
        return {'schema_version': 'hypotrail.parity_result/1', 'status': 'ok', 'n_rows': 1,
                'max_abs_diff': 0.0, 'max_rel_diff': None, 'exact_mismatches': 0,
                'tolerance': dict(parity_spec['tolerance']), 'reason': None, 'extensions': {}}


def test_an_honest_embedded_bundle_passes_the_runtime_check(tmp_path):
    f = _fitted()
    d = capture_predictor(f, None, _parity(), tmp_path / 'b', _EmbeddingPackager(),
                          code_fingerprint=FP)
    assert verify_bundle(tmp_path / 'b').predictor_id == d.predictor_id
    assert verify_bundle(tmp_path / 'b' / 'packages/embedding_test/native').predictor_id == \
        d.predictor_id


def test_the_runtime_refuses_a_package_embedding_another_predictor(tmp_path):
    f = _fitted()
    other = tmp_path / 'other'
    capture_predictor(_other_model(f), None, _parity(), other, None, code_fingerprint=FP)
    e = _refused(capture_predictor, f, None, _parity(), tmp_path / 'b',
                 _EmbeddingPackager(source=other), code_fingerprint=FP)
    assert 'another predictor' in e.message
    assert not (tmp_path / 'b').exists()


def test_the_runtime_refuses_an_embedded_bundle_with_other_bound_files(tmp_path):
    """Same predictor id, but a bound file of the embedded copy was edited: its own
    verification fails, and the package is refused."""
    f = _fitted()
    same = tmp_path / 'same'
    capture_predictor(f, None, _parity(), same, None, code_fingerprint=FP)
    (same / 'recipe.json').write_bytes(b'{}')
    e = _refused(capture_predictor, f, None, _parity(), tmp_path / 'b',
                 _EmbeddingPackager(source=same), code_fingerprint=FP)
    assert e.details['inner_code'] == 'artifact_integrity_failed'


def test_the_runtime_refuses_a_declared_embedded_bundle_that_is_absent(tmp_path):
    _refused(capture_predictor, _fitted(), None, _parity(), tmp_path / 'b',
             _EmbeddingPackager(declare='elsewhere'), code_fingerprint=FP)


def test_workshop_capture_tampered_package_refuses_the_final_test(tmp_path):
    """Reviewer probe, engine path: the workshop capture's package re-captured with another
    model (cap bounds on a column, parity rows unchanged) and re-described. Before the fix
    the final test was promoted and the export said ``packaged``; now the bundle is refused
    and the opening fails without a final result."""
    pytest.importorskip('mlflow')
    import test_capture_final as tcf
    from mlkit.study import activities as act, read
    flow = tcf._chosen(tmp_path, 'regression')
    v = flow.run('predictor.capture', '--profile', 'workshop')['values']
    bundle = tcf._home(flow) / v['bundle']
    desc = verify_bundle(bundle)
    pipe = pickle.loads((bundle / desc.manifest.payload_files[0].relative_path).read_bytes())
    from hypotrail_runtime import inference
    from hypotrail_runtime.predictor import frame_from_document
    parity = frame_from_document(json.loads((bundle / desc.bundle.parity.features_path)
                                            .read_bytes()))
    view, _ = inference.check_frame(desc.data_contract, parity, features=list(desc.recipe.features))
    prep = pipe.named_steps['prepare']
    column = [c for c in desc.recipe.features
              if desc.data_contract.column(c).physical_type == 'float64'
              and view[c].notna().sum() > 1][0]
    prep.cap_bounds_ = {**prep.cap_bounds_,
                        column: [float(view[column].min()), float(view[column].max())]}
    other = FittedPredictor(recipe=desc.recipe, data_contract=desc.data_contract, pipeline=pipe,
                            training_scope=desc.manifest.training_scope,
                            n_train=int(desc.manifest.extensions['hypotrail.n_train']))
    inner = tmp_path / 'inner'
    capture_predictor(other, None, view, inner, None, code_fingerprint=FP)
    native = bundle / PKG / 'artifacts' / 'native_bundle'
    shutil.rmtree(native)
    shutil.copytree(inner, native)
    _redescribe_mlflow_package(bundle)
    _refused(verify_bundle, bundle)
    out = tcf._open(flow, expect=None)
    opening = out['result']['opening']
    assert opening['status'] == 'failed'
    assert opening['error']['details']['contract_code'] == 'artifact_integrity_failed'
    assert act.FINAL not in read.open(flow.study).state['current']


# --- A4-R2: claims name their rows and are atomic ----------------------------------------------

def _ref(keys, name='cal'):
    m = canonical.sha256_hex('\n'.join(sorted(set(keys))).encode())
    return f'{name}@{m}'


PROC_A = {'predictor_id': 'a' * 64, 'objective': 'precision'}
PROC_B = {'predictor_id': 'b' * 64, 'objective': 'precision'}


@needs_mapie
def test_a_claim_without_row_keys_is_refused(tmp_path):
    """Reviewer probes: a claim that omitted its keys let a superset of used rows escape
    (first or second claim). Keys are now mandatory."""
    from mlkit.integrations import mapie_uncertainty as mu
    led = mu.CalibrationLedger(tmp_path / 'ledger.jsonl')
    first = [f'r{i}' for i in range(50)]
    with pytest.raises(TypeError):
        led.claim(_ref(first), PROC_A)                          # noqa - no keys argument
    for keys in (None, 'r1', b'r1', []):
        _refused(led.claim, _ref(first), PROC_A, keys=keys, code='contract_invalid')
    assert led.uses() == []


@needs_mapie
def test_ledger_overlapping_superset_also_escapes(tmp_path):
    """Formerly the escape of a superset when either claim omitted its keys; with mandatory
    keys a superset, a subset, a reordering with duplicates and a one-row overlap are all
    recognised."""
    from mlkit.integrations import mapie_uncertainty as mu
    led = mu.CalibrationLedger(tmp_path / 'ledger.jsonl')
    first = [f'r{i}' for i in range(50)]
    use = led.claim(_ref(first), PROC_A, keys=first)
    rev = list(reversed(first)) + first[:5]
    assert led.claim(_ref(rev, 'renamed'), PROC_A, keys=rev) == use      # reproduction
    for keys in (first + ['r99'], first[:10], rev, ['r7', 'x1']):
        e = _refused(led.claim, _ref(keys, 'x'), PROC_B, keys=keys,
                     code='calibration_not_eligible')
        assert e.details['reason'] in ('same_rows', 'overlapping_rows')
    _refused(led.claim, _ref(first + ['r99'], 'x'), PROC_A, keys=first + ['r99'],
             code='calibration_not_eligible')
    assert led.claim(_ref(['z1'], 'z'), PROC_B, keys=['z1'])['procedure_id'] == \
        mu.CalibrationLedger.procedure_id(PROC_B)
    assert len(led.uses()) == 2


@needs_mapie
def test_a_recorded_use_without_row_digests_blocks_every_other_membership(tmp_path):
    from mlkit.integrations import mapie_uncertainty as mu
    path = tmp_path / 'ledger.jsonl'
    rows = ['r1', 'r2']
    legacy = {'schema': mu.LEDGER_SCHEMA, 'calibration_ref': _ref(rows),
              'membership_sha256': mu.CalibrationLedger.membership(_ref(rows)),
              'procedure_id': mu.CalibrationLedger.procedure_id(PROC_A), 'procedure': PROC_A}
    path.write_text(canonical.dumps(legacy).decode() + '\n')
    led = mu.CalibrationLedger(path)
    assert led.claim(_ref(rows), PROC_A, keys=rows) == legacy           # reproduction
    e = _refused(led.claim, _ref(['q9']), PROC_B, keys=['q9'], code='calibration_not_eligible')
    assert e.details['reason'] == 'recorded_rows_unknown'


@needs_mapie
def test_two_concurrent_claims_never_both_bind(tmp_path, monkeypatch):
    """Two claims of different procedures on the same rows, interleaved: the second reads
    the ledger only after the first has appended (file lock), so exactly one binds."""
    from mlkit.integrations import mapie_uncertainty as mu
    path = tmp_path / 'ledger.jsonl'
    rows = [f'r{i}' for i in range(20)]
    original = mu.CalibrationLedger.uses
    reading = threading.Event()

    def slow_uses(self):
        out = original(self)
        reading.set()
        time.sleep(0.3)               # the window in which an unlocked claim interleaves
        return out
    monkeypatch.setattr(mu.CalibrationLedger, 'uses', slow_uses)
    outcomes = {}

    def claim(name, procedure):
        try:
            mu.CalibrationLedger(path).claim(_ref(rows), procedure, keys=rows)
            outcomes[name] = 'bound'
        except ContractError as e:
            outcomes[name] = e.code
    first = threading.Thread(target=claim, args=('a', PROC_A))
    first.start()
    assert reading.wait(5)
    second = threading.Thread(target=claim, args=('b', PROC_B))
    second.start()
    first.join(10)
    second.join(10)
    assert sorted(outcomes.values()) == ['bound', 'calibration_not_eligible'], outcomes
    assert outcomes['a'] == 'bound'
    assert len(original(mu.CalibrationLedger(path))) == 1


# --- N4: MAPIE's rank below 0.5 (observation, behaviour unchanged) ------------------------------

def _oracle_rank(n, level):
    rank = math.ceil((n + 1) * level - 1e-12)
    return None if rank > n else rank


@needs_mapie
@pytest.mark.parametrize('level', [0.1, 0.3, 0.5, 0.8, 0.9, 0.95, 0.975, 0.99])
def test_conformal_quantile_against_the_rank_oracle_on_every_small_n(level):
    """At 0.5 and above (and at 0.1) the half-width is the residual of rank ⌈(n+1)·level⌉
    for every n from 1 to 69. At 0.3, MAPIE sometimes takes the next rank up (its 1 − α is
    0.30000000000000004): the half-width is then the next residual, never a smaller one, and
    never more than one rank above (documented in the module docstring, N4)."""
    from mlkit.integrations import mapie_uncertainty as mu
    rng = np.random.default_rng(3)
    bad, above = [], 0
    for n in range(1, 70):
        X = rng.normal(size=(n, 1))
        y = 2 * X[:, 0] + rng.normal(size=n)
        res = np.sort(np.abs(y - 2 * X[:, 0]))
        cal = {'eligible': True, 'reasons': [], 'calibration_ref': 'c@' + 'a' * 64,
               'n_rows': n}
        out = mu.split_conformal(lambda Z: 2 * np.asarray(Z)[:, 0], X, y, np.zeros((2, 1)),
                                 confidence_level=level, predictor_id=None, calibration=cal)
        rank = _oracle_rank(n, level)
        if rank is None:
            if out.status != 'insufficient_data':
                bad.append((n, 'expected insufficient', out.status))
            continue
        if out.status != 'ok':
            bad.append((n, out.status, out.reason))
            continue
        half = out.interval_bounds[0].high
        allowed = [float(res[rank - 1])]
        if level < 0.5 and rank < n:
            allowed.append(float(res[rank]))          # one rank higher, conservative
        hits = [math.isclose(half, a, rel_tol=1e-12, abs_tol=1e-12) for a in allowed]
        if not any(hits):
            bad.append((n, half, allowed, out.extensions.get('hypotrail.quantile')))
        elif not hits[0]:
            above += 1
    assert not bad, bad
    if level >= 0.5 or level == 0.1:
        assert above == 0


# --- N1: missing markers of a categorical column ----------------------------------------------

@pytest.mark.parametrize('dtype', ['string', 'object', 'Int64'])
def test_pd_na_in_a_categorical_column_is_missing_not_a_category(dtype):
    """Reviewer probe: pd.NA in a ``string``/``object`` categorical column became the text
    '<NA>' (missing-share alert lost, false unknown-category alert)."""
    pytest.importorskip('evidently')
    from mlkit.integrations import evidently_diagnostics as ed
    rng = np.random.default_rng(0)
    ref = pd.DataFrame({'c': pd.Series(rng.choice([1, 2, 3], 400), dtype='Int64')})
    cur = pd.DataFrame({'c': pd.Series(rng.choice([1, 2, 3], 400), dtype='Int64')})
    cur.loc[:99, 'c'] = pd.NA                       # 25 % missing
    ref['c'], cur['c'] = ref['c'].astype(dtype), cur['c'].astype(dtype)
    assert cur['c'].isna().mean() == 0.25
    out = ed.run(ed.demonstration_profile({'c': 'categorical'}), ref, cur,
                 reference_partition='development', current_partition='development',
                 authorized=('development',))
    checks = {c['id']: c for c in out['result'].model_dump(mode='json')['checks']}
    assert checks['missing_share:c']['alert'] is True
    assert checks['missing_share:c']['statistic_value'] == pytest.approx(0.25)
    assert checks['unknown_categories:c']['alert'] is False
    assert checks['unknown_categories:c']['statistic_value'] == 0.0
    assert checks['unknown_categories:c']['n_current'] == 300


def test_category_text_reads_every_missing_marker_as_missing():
    from mlkit.integrations import evidently_diagnostics as ed
    s = pd.Series(['a', None, np.nan, pd.NA, pd.NaT, 1.0, 2.5, 'b'], dtype=object)
    out = ed._category_text(s)
    assert out.isna().tolist() == [False, True, True, True, True, False, False, False]
    assert out.dropna().tolist() == ['a', '1', '2.5', 'b']


# --- N2: integers a float does not represent exactly -------------------------------------------

@pytest.mark.parametrize('value', [10 ** 400, 2 ** 53 + 1, 2 ** 60 + 1, 10 ** 5000],
                         ids=['1e400', '2^53+1', '2^60+1', '1e5000'])
@pytest.mark.parametrize('form', ['object', 'bytes'])
def test_an_integer_no_float_represents_is_contract_invalid(value, form):
    d = docs_v1.recipe()
    d['parameters'] = {**d['parameters'], 'C': value}
    if form == 'bytes':
        if value.bit_length() > 10_000:
            pytest.skip('beyond the JSON reader integer-digit limit (refused as not JSON)')
        d = json.dumps(d).encode()
    e = _refused(validate_recipe, d, code='contract_invalid')
    assert e.path in ('parameters/C', 'parameters')


@pytest.mark.parametrize('form', ['object', 'bytes'])
def test_an_exact_integer_is_still_read_as_its_float(form):
    for value in (1, 2 ** 53, 10 ** 20):
        d = docs_v1.recipe()
        d['parameters'] = {**d['parameters'], 'C': value}
        r = validate_recipe(d if form == 'object' else json.dumps(d).encode())
        assert r.parameters['C'] == float(value) and type(r.parameters['C']) is float
