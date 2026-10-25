"""Regressions of the review of 24 October 2026, area A (docs/acceptance/REVIEW-2026-10-24.md).

A1 the predictor id binds the whole bundle content; A2 ``trusted_roots`` is a collection of
paths; A3 a capture reports the packages of the bundle it names; A4 the calibration ledger
keys a use on the rows, not on the partition's name; then the minor library findings. Every
bundle and study lives in ``tmp_path``; the data are synthetic.
"""
from __future__ import annotations

import importlib.util
import json
import math
import pickle
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from hypotrail_runtime import (canonical, capture_predictor, check_parity, fit_predictor,
                               load_predictor, read_evidence_binding, validate_data_contract,
                               validate_recipe, verify_bundle, write_evidence_binding)
from hypotrail_runtime.contracts import FrozenDict
from hypotrail_runtime.errors import ContractError
from hypotrail_runtime.predictor import (BOUND_CONTEXT, BOUND_PARITY, environment_lock,
                                         frame_from_document)
from mlkit.contracts import context as cx
from mlkit.contracts.testing_packager import SyntheticPackager

import docs_v1

SCOPE = {'role': 'development_fit', 'dataset_id': 'synthetic', 'membership_sha256': 'b' * 64,
         'protocol_id': None}
FP = 'c' * 64


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


def _fitted(seed=0, contract=None):
    return fit_predictor(docs_v1.recipe(), contract or docs_v1.contract(), _frame(200, seed),
                         SCOPE)


def _context(revision=3):
    return cx.build(method='predictor.fit', activity_id='predictor.capture', study_id='s',
                    expected_revision=revision, code_fingerprint=FP)


def _capture(dest, *, context=None, packager=None, seed=0, **kw):
    return capture_predictor(_fitted(seed), context, _frame(30, 1, with_target=False),
                             Path(dest), packager, code_fingerprint=FP, **kw)


def _rewrite(root, mutate):
    path = Path(root) / 'predictor_bundle.json'
    doc = json.loads(path.read_bytes())
    mutate(doc)
    path.write_bytes(canonical.dumps(doc) + b'\n')


def _refresh(root, rel):
    """What an attacker does: recompute the bundle document's entry of ``rel``."""
    root = Path(root)

    def mutate(doc):
        for e in doc['files']:
            if e['relative_path'] == rel:
                e['size_bytes'] = (root / rel).stat().st_size
                e['sha256'] = canonical.file_sha256(root / rel)
        if rel in doc['parity']['sha256s']:
            doc['parity']['sha256s'][rel] = canonical.file_sha256(root / rel)
    _rewrite(root, mutate)


def _refused(fn, *args, code='artifact_integrity_failed', **kw):
    with pytest.raises(ContractError) as e:
        fn(*args, **kw)
    assert e.value.code == code, e.value.to_dict()
    return e.value


@pytest.fixture(scope='module')
def made(tmp_path_factory):
    root = tmp_path_factory.mktemp('made')
    _capture(root / 'plain')
    _capture(root / 'with_context', context=_context())
    _capture(root / 'packaged', packager=SyntheticPackager())
    return root


@pytest.fixture
def bundle(made, tmp_path):
    def copy(name='plain'):
        dest = tmp_path / 'trusted' / name
        shutil.copytree(made / name, dest)
        return dest
    return copy


def _all_refused(b):
    _refused(verify_bundle, b)
    _refused(load_predictor, b, trusted_roots=[b.parent])


# --- A1: the predictor id binds the bundle content -------------------------------------------

def test_manifest_binds_the_parity_and_the_context(bundle):
    b = bundle('with_context')
    desc = verify_bundle(b)
    ext = desc.manifest.extensions
    assert ext[BOUND_PARITY] == desc.bundle.parity.model_dump(mode='json')
    assert ext[BOUND_CONTEXT] == {'relative_path': 'computation_context.json',
                                  'sha256': canonical.file_sha256(b /
                                                                  'computation_context.json')}
    assert verify_bundle(bundle('plain')).manifest.extensions[BOUND_CONTEXT] is None
    p = load_predictor(b, trusted_roots=[b.parent])
    assert check_parity(p).status == 'ok'


def test_swapped_payload_with_rewritten_bundle_document_is_refused(bundle):
    b = bundle()
    other = _fitted(seed=99)
    (b / 'payload/model.pkl').write_bytes(pickle.dumps(other.pipeline, protocol=5))
    _refresh(b, 'payload/model.pkl')
    _all_refused(b)


def test_swapped_payload_and_regenerated_parity_outputs_are_refused(bundle):
    b = bundle()
    other = _fitted(seed=99)
    (b / 'payload/model.pkl').write_bytes(pickle.dumps(other.pipeline, protocol=5))
    _refresh(b, 'payload/model.pkl')
    feats = frame_from_document(json.loads((b / 'parity/features.json').read_bytes()))
    exp = json.loads((b / 'parity/expected_outputs.json').read_bytes())
    exp['values'] = [float(v) for v in other.predict(feats).values]
    (b / 'parity/expected_outputs.json').write_bytes(canonical.dumps(exp) + b'\n')
    _refresh(b, 'parity/expected_outputs.json')
    _all_refused(b)


def test_relaxed_parity_tolerance_is_refused(bundle):
    b = bundle()
    _rewrite(b, lambda d: d['parity'].update(tolerance={'rtol': 1e300, 'atol': 1e300,
                                                        'exact': []}))
    _all_refused(b)


@pytest.mark.parametrize('field', ['origin', 'n_rows'])
def test_other_parity_fields_are_bound(bundle, field):
    b = bundle()
    value = {'origin': 'synthetic', 'n_rows': 1}[field]
    _rewrite(b, lambda d: d['parity'].update({field: value}))
    _refused(verify_bundle, b)


def test_a_different_tolerance_gives_a_different_predictor_id(tmp_path):
    a = _capture(tmp_path / 'a')
    b = _capture(tmp_path / 'b', tolerance={'rtol': 1e-9})
    assert a.predictor_id != b.predictor_id


@pytest.mark.parametrize('which', ['wheel', 'lock'])
def test_wheel_and_lock_digests_of_the_manifest_are_checked(bundle, which):
    b = bundle()
    m = verify_bundle(b).manifest
    rel = m.runtime.wheel_relative_path if which == 'wheel' else \
        m.environment.lock_relative_path
    (b / rel).write_bytes((b / rel).read_bytes() + b'evil-package==6.6.6\n')
    _refresh(b, rel)
    e = _refused(verify_bundle, b)
    assert e.path == rel


def test_removed_computation_context_is_refused(bundle):
    b = bundle('with_context')
    (b / 'computation_context.json').unlink()
    _rewrite(b, lambda d: d.update(files=[f for f in d['files']
                                          if f['relative_path'] != 'computation_context.json']))
    _refused(verify_bundle, b)


def test_edited_computation_context_is_refused(bundle):
    b = bundle('with_context')
    doc = json.loads((b / 'computation_context.json').read_bytes())
    doc['expected_revision'] = 99
    (b / 'computation_context.json').write_bytes(canonical.dumps(doc) + b'\n')
    _refresh(b, 'computation_context.json')
    _refused(verify_bundle, b)


def test_added_and_listed_computation_context_is_refused(bundle):
    b = bundle('plain')
    canonical.write_json(b / 'computation_context.json', _context())

    def mutate(doc):
        doc['files'].append({'relative_path': 'computation_context.json',
                             'size_bytes': (b / 'computation_context.json').stat().st_size,
                             'sha256': canonical.file_sha256(b / 'computation_context.json')})
    _rewrite(b, mutate)
    e = _refused(verify_bundle, b)
    assert e.details['files'] == ['computation_context.json']


def test_unlisted_computation_context_is_refused(bundle):
    b = bundle('plain')
    canonical.write_json(b / 'computation_context.json', _context())
    _refused(verify_bundle, b)


def test_the_context_enters_the_id(tmp_path):
    a = _capture(tmp_path / 'a', context=_context(3))
    b = _capture(tmp_path / 'b', context=_context(4))
    c = _capture(tmp_path / 'c')
    assert len({a.predictor_id, b.predictor_id, c.predictor_id}) == 3


def test_a_bundle_whose_manifest_binds_nothing_more_is_refused(bundle):
    """A manifest without the bindings (as captured before the fix), re-signed: refused."""
    b = bundle()
    m = json.loads((b / 'predictor.json').read_bytes())
    for key in (BOUND_PARITY, BOUND_CONTEXT):
        m['extensions'].pop(key)
    m['predictor_id'] = canonical.artifact_id(m, exclude=('predictor_id',))
    (b / 'predictor.json').write_bytes(canonical.dumps(m) + b'\n')
    _refresh(b, 'predictor.json')
    _rewrite(b, lambda d: d.update(predictor_id=m['predictor_id']))
    e = _refused(verify_bundle, b)
    assert e.path == 'extensions'


def test_check_parity_rereads_the_bound_files(bundle):
    b = bundle()
    p = load_predictor(b, trusted_roots=[b.parent])
    exp = json.loads((b / 'parity/expected_outputs.json').read_bytes())
    exp['values'] = [v + 1 for v in exp['values']]
    (b / 'parity/expected_outputs.json').write_bytes(canonical.dumps(exp) + b'\n')
    _refused(check_parity, p)


def test_capture_extensions_cannot_replace_the_bindings(tmp_path):
    e = _refused(_capture, tmp_path / 'x', code='contract_invalid',
                 extensions={BOUND_PARITY: {}})
    assert e.details['keys'] == [BOUND_PARITY]
    assert not (tmp_path / 'x').exists()


def test_evidence_binding_stays_mutable_outside_the_id(bundle):
    b = bundle()
    pid = verify_bundle(b).predictor_id
    binding = {'schema_version': 'hypotrail.evidence_binding/1', 'predictor_id': pid,
               'final_result_id': 'r-1', 'study_revision': 3, 'decision_refs': ['final_test'],
               'protocol_id': None, 'evaluation_context_id': 'k', 'status': 'evaluated'}
    write_evidence_binding(b, binding)
    write_evidence_binding(b, {**binding, 'status': 'stale'})
    assert read_evidence_binding(b).status == 'stale'
    assert verify_bundle(b).predictor_id == pid
    # Round 5 (R5-A2): the temporary documents are written beside the bundle folder, so
    # nothing is left inside the bundle or beside it; the evidence folder holds the bindings
    # only, and any other file there (a leftover, a note) makes the bundle unverifiable.
    assert not list(b.glob('.*')) and not list(b.parent.glob('.*'))
    assert sorted(p.name for p in (b / 'evidence').iterdir()) == ['binding-1.json',
                                                                   'binding-2.json']
    (b / 'evidence' / '.predictor_bundle.json.tmp').write_bytes(b'{}')
    _refused(verify_bundle, b)


# --- optional packages ---------------------------------------------------------------------

def test_a_declared_package_that_does_not_exist_is_refused(bundle):
    b = bundle()
    _rewrite(b, lambda d: d.update(optional_packages=[{
        'format': 'mlflow_pyfunc', 'artifact_id': 'a' * 64,
        'relative_path': 'packages/mlflow_pyfunc', 'manifest_sha256': 'a' * 64}]))
    _refused(verify_bundle, b)


def test_a_packaged_bundle_verifies_and_an_altered_package_is_refused(bundle):
    b = bundle('packaged')
    desc = verify_bundle(b)
    assert [p.format for p in desc.bundle.optional_packages] == ['synthetic_test']
    (b / 'packages/synthetic_test/model.pkl').write_bytes(b'other')
    _refresh(b, 'packages/synthetic_test/model.pkl')
    e = _refused(verify_bundle, b)
    assert e.path == 'packages/synthetic_test/model.pkl'


def test_a_package_whose_descriptor_names_another_predictor_is_refused(bundle):
    b = bundle('packaged')
    rel = 'packages/synthetic_test.descriptor.json'
    doc = json.loads((b / rel).read_bytes())
    doc['predictor_id'] = 'e' * 64
    (b / rel).write_bytes(canonical.dumps(doc) + b'\n')
    _refresh(b, rel)
    _rewrite(b, lambda d: d['optional_packages'][0].update(
        manifest_sha256=canonical.file_sha256(b / rel)))
    _refused(verify_bundle, b)


def test_package_files_outside_a_declared_package_are_refused(bundle):
    b = bundle('packaged')
    _rewrite(b, lambda d: d.update(optional_packages=[]))
    e = _refused(verify_bundle, b)
    assert 'packages/synthetic_test/model.pkl' in e.details['files']


@pytest.mark.parametrize('fmt', ['../../escape', '../escape', 'a/b', '.hidden', '', 'a.b'])
def test_packager_format_is_checked_before_it_becomes_a_path(tmp_path, fmt):
    class P:
        format = fmt

        def package(self, *a):
            raise AssertionError('never called')

        def verify(self, *a):
            raise AssertionError('never called')
    _refused(_capture, tmp_path / 'x', packager=P(), code='contract_invalid')
    assert not (tmp_path / 'escape').exists() and not (tmp_path.parent / 'escape').exists()
    assert list(tmp_path.iterdir()) == []


# --- A2: trusted roots ---------------------------------------------------------------------

@pytest.mark.parametrize('roots', ['/', 'not-the-parent', b'/', Path('/'), 3, [3], [b'/']])
def test_trusted_roots_must_be_a_collection_of_paths(bundle, roots, monkeypatch):
    import pickle as pk
    called = []
    monkeypatch.setattr(pk, 'load', lambda *a, **k: called.append(1))
    b = bundle()
    e = _refused(load_predictor, b, trusted_roots=roots, code='contract_invalid')
    assert e.path == 'trusted_roots'
    assert not called


def test_trusted_roots_as_a_list_or_tuple_of_paths(bundle):
    b = bundle()
    assert load_predictor(b, trusted_roots=[str(b.parent)]).predictor_id
    assert load_predictor(b, trusted_roots=(b.parent,)).predictor_id
    _refused(load_predictor, b, trusted_roots=[b.parent / 'elsewhere'])


# --- A3: the packages a capture reports are those of the bundle it names --------------------

def test_place_keeps_one_bundle_per_package_set_and_reports_what_it_holds(tmp_path):
    from mlkit.contracts import capture
    root = tmp_path / 'predictors'
    root.mkdir()
    ctx = _context()
    base = _capture(root / '.staging-1', context=ctx)
    folder, reused, held = capture._place(root, root / '.staging-1', base)
    assert (folder.name, reused, held) == (base.predictor_id, False, [])
    packaged = _capture(root / '.staging-2', context=ctx, packager=SyntheticPackager())
    assert packaged.predictor_id == base.predictor_id           # packages are not in the id
    folder, reused, held = capture._place(root, root / '.staging-2', packaged)
    assert folder.name == f'{base.predictor_id}+synthetic_test' and not reused
    assert [p.format for p in held] == ['synthetic_test']
    assert [p.format for p in verify_bundle(folder).bundle.optional_packages] == \
        ['synthetic_test']
    assert verify_bundle(root / base.predictor_id).bundle.optional_packages == []
    again = _capture(root / '.staging-3', context=ctx, packager=SyntheticPackager())
    folder, reused, held = capture._place(root, root / '.staging-3', again)
    assert reused and [p.format for p in held] == ['synthetic_test']
    assert (root / '.staging-3').exists()          # the caller removes the staging folder
    # An altered bundle of the same predictor refuses the next capture.
    (root / base.predictor_id / 'recipe.json').write_bytes(b'{}')
    shutil.rmtree(root / '.staging-3')
    again = _capture(root / '.staging-4', context=ctx)
    _refused(capture._place, root, root / '.staging-4', again)


def test_bundle_name():
    from mlkit.contracts.capture import bundle_name
    assert bundle_name('a' * 64, []) == 'a' * 64
    assert bundle_name('a' * 64, ['z', 'b']) == 'a' * 64 + '+b+z'


def test_engine_capture_reports_the_packages_its_bundle_holds(tmp_path, monkeypatch):
    import test_capture_final as tcf
    from mlkit.contracts.export_source import read_export_source
    monkeypatch.setenv('HYPOTRAIL_TEST_HOOKS', '1')
    flow = tcf._chosen(tmp_path)
    v1 = flow.run('predictor.capture')['values']
    v2 = flow.run('predictor.capture', '--packager', 'synthetic_test')['values']
    for v in (v1, v2):
        held = [p.format for p in verify_bundle(tcf._home(flow) / v['bundle'])
                .bundle.optional_packages]
        assert [p['format'] for p in v['packages']] == held
    assert [p['format'] for p in v2['packages']] == ['synthetic_test']
    assert read_export_source(flow.study, flow.rev()).predictor.packages == ['synthetic_test']
    root = tcf._home(flow) / 'predictors'
    assert not [p.name for p in root.iterdir() if p.name.startswith('.')]


def test_refused_capture_leaves_no_staging_folder(tmp_path, monkeypatch):
    import test_capture_final as tcf
    from mlkit.contracts import testing_packager
    monkeypatch.setenv('HYPOTRAIL_TEST_HOOKS', '1')
    monkeypatch.setattr(testing_packager, 'packager',
                        lambda: testing_packager.SyntheticPackager(fail=True))
    flow = tcf._chosen(tmp_path)
    out = flow.run('predictor.capture', '--packager', 'synthetic_test', expect=None)
    assert out['ok'] is False
    root = tcf._home(flow) / 'predictors'
    assert list(root.iterdir()) == []


def test_final_test_refuses_a_swapped_payload(tmp_path):
    """End to end: the payload replaced and only the bundle document updated; the opening
    is refused with an integrity error and records no final result. Since review round 2
    (area A, F1) the refusal comes before the confirmation commits: the final test stays
    sealed and none of its rows is read."""
    import test_capture_final as tcf
    from mlkit.study import activities as act, read, state as st
    flow = tcf._chosen(tmp_path, 'regression')
    v = flow.run('predictor.capture')['values']
    b = tcf._home(flow) / v['bundle']
    other = pickle.loads((b / 'payload/model.pkl').read_bytes())
    other.named_steps['model'].coef_ = other.named_steps['model'].coef_ * 0.5
    (b / 'payload/model.pkl').write_bytes(pickle.dumps(other, protocol=5))
    _refresh(b, 'payload/model.pkl')
    out = tcf._open(flow, expect=2)
    assert out['error']['code'] == 'precondition_missing'
    item = next(x for x in out['error']['details']['missing']
                if x['requirement'] == 'capture_loadable')
    assert item['contract_code'] == 'artifact_integrity_failed'
    state = read.open(flow.study).state
    assert act.FINAL not in state['current'] and not st.final_test_opened(state)
    assert not (b / 'evidence').exists()                # no evidence binding was written


# --- A4: the calibration ledger keys on the rows -----------------------------------------------

mapie_missing = pytest.mark.skipif(importlib.util.find_spec('mapie') is None,
                                   reason='uncertainty extra')


def _eligibility(name, keys):
    from mlkit.integrations import mapie_uncertainty as mu
    others = {'train': [], 'tuning': [], 'selection': [], 'final_test': []}
    return mu.eligibility({'id': name, 'role': 'calibration', 'keys': list(keys),
                           'reserved_revision': 1, 'frozen_revision': 2},
                          other_partitions=others)


def test_ledger_refuses_the_same_rows_under_another_name(tmp_path):
    """Row keys are mandatory since review A4, round 2: the claims pass them (the
    expectations are unchanged)."""
    from mlkit.integrations import mapie_uncertainty as mu
    ledger = mu.CalibrationLedger(tmp_path / 'l.jsonl')
    a, b = _eligibility('calibration', 'abc'), _eligibility('calibration-bis', 'abc')
    keys = list('abc')
    first = ledger.claim(a['calibration_ref'], {'p': 1}, keys=keys)
    with pytest.raises(ContractError) as e:
        ledger.claim(b['calibration_ref'], {'p': 2}, keys=keys)
    assert e.value.code == 'calibration_not_eligible'
    assert e.value.details['reason'] == 'same_rows'
    # The same procedure on the same rows is a reproduction, whatever the name.
    assert ledger.claim(b['calibration_ref'], {'p': 1}, keys=keys) == first
    assert len(ledger.uses()) == 1


@pytest.mark.parametrize('second', [['c1', 'c2', 'c3'], ['c2', 'c9'], ['c1']])
def test_ledger_refuses_overlapping_rows_when_the_keys_are_given(tmp_path, second):
    from mlkit.integrations import mapie_uncertainty as mu
    ledger = mu.CalibrationLedger(tmp_path / 'l.jsonl')
    first = _eligibility('cal', ['c1', 'c2'])
    ledger.claim(first['calibration_ref'], {'p': 1}, keys=['c1', 'c2'])
    other = _eligibility('cal', second)
    for procedure in ({'p': 1}, {'p': 2}):
        with pytest.raises(ContractError) as e:
            ledger.claim(other['calibration_ref'], procedure, keys=second)
        assert e.value.code == 'calibration_not_eligible'
        assert e.value.details['reason'] == 'overlapping_rows'
    disjoint = _eligibility('cal', ['d1'])
    ledger.claim(disjoint['calibration_ref'], {'p': 3}, keys=['d1'])
    assert len(ledger.uses()) == 2
    assert '"c1"' not in (tmp_path / 'l.jsonl').read_text()        # row keys are digested


def test_ledger_keys_must_be_the_rows_of_the_reference(tmp_path):
    from mlkit.integrations import mapie_uncertainty as mu
    ledger = mu.CalibrationLedger(tmp_path / 'l.jsonl')
    ref = _eligibility('cal', ['c1', 'c2'])['calibration_ref']
    _refused(ledger.claim, ref, {'p': 1}, keys=['c1'], code='contract_invalid')
    _refused(ledger.claim, 'no-membership', {'p': 1}, keys=['c1'], code='contract_invalid')


# --- minor library findings ----------------------------------------------------------------

def test_a_feature_outside_required_columns_absent_at_inference_is_contract_invalid():
    c = docs_v1.contract()
    c['inference_policy']['required_columns'] = ['age', 'branch']
    f = _fitted(contract=c)
    e = _refused(f.predict, _frame(10, 1, with_target=False).drop(columns=['band']),
                 code='contract_invalid')
    assert e.issues[0]['kind'] == 'missing_columns' and e.issues[0]['columns'] == ['band']


def _string_dtypes():
    out = ['string[python]']
    try:
        pd.array(['a'], dtype='string[pyarrow]')
        out.append('string[pyarrow]')
    except Exception:          # pyarrow not installed
        pass
    return out


@pytest.mark.parametrize('dtype', _string_dtypes())
def test_pandas_na_in_a_string_feature_predicts_like_a_missing_value(dtype):
    f = _fitted()
    x = _frame(40, 5, with_target=False)
    x['branch'] = pd.Series(['Alder', None] * 20, dtype=object)
    reference = f.predict(x).values
    y = x.copy()
    y['branch'] = pd.array(['Alder', None] * 20, dtype=dtype)
    np.testing.assert_array_equal(f.predict(y).values, reference)
    z = x.copy()
    z['branch'] = pd.Series(['Alder', np.nan] * 20, dtype=object)
    np.testing.assert_array_equal(f.predict(z).values, reference)


def test_capture_with_pandas_na_in_parity_rows(tmp_path):
    parity = _frame(10, 1, with_target=False)
    parity['branch'] = pd.array(['Alder', None] * 5, dtype='string[python]')
    desc = capture_predictor(_fitted(), None, parity, tmp_path / 'b', code_fingerprint=FP)
    doc = json.loads((tmp_path / 'b' / 'parity/features.json').read_bytes())
    branch = next(c for c in doc['columns'] if c['name'] == 'branch')
    assert branch['values'][:2] == ['Alder', None]
    assert desc.parity.status == 'ok'


@pytest.mark.parametrize('rare', [0, 1])
def test_preparation_reads_pandas_na_as_the_engine_reads_nan(rare):
    """``pd.NA`` (a nullable boolean read as text) is prepared exactly as the engine's
    ``NaN`` is, with and without rare-category folding; ``v != v`` on it used to raise."""
    from hypotrail_runtime.preprocess import HypotrailPreparation

    def prepared(values):
        prep = HypotrailPreparation(features=['flag'], text_columns=['flag'],
                                    rare_min_rows=rare)
        return prep.fit(values).transform(values)['flag'].tolist()
    na = prepared(pd.DataFrame({'flag': pd.array([True, None, False, True],
                                                 dtype='boolean')}))
    nan = prepared(pd.DataFrame({'flag': pd.Series([True, np.nan, False, True],
                                                   dtype=object)}))
    assert na == nan and na[0] == 'True'


@pytest.mark.parametrize('value', [{'a': '\ud800'}, {'\udfff': 1}, ['x\ud83d']])
def test_lone_surrogate_is_contract_invalid(value):
    _refused(canonical.dumps, value, code='contract_invalid')


def test_integer_and_float_spellings_of_a_real_parameter_are_one_recipe():
    params = {'solver': 'newton-cholesky', 'tol': 1e-08, 'max_iter': 1000}
    ids = {validate_recipe(form).digest()
           for c in (1, 1.0)
           for doc in (docs_v1.recipe(parameters={**params, 'C': c}),)
           for form in (doc, json.dumps(doc))}
    assert len(ids) == 1
    # The reference recipe already spells C as a float: its frozen id is unchanged.
    assert validate_recipe(docs_v1.RECIPE).parameters['C'] == 1.0
    for bad in ({**params, 'C': True}, {**params, 'max_iter': 1000.0}):
        _refused(validate_recipe, docs_v1.recipe(parameters=bad), code='contract_invalid')


def test_validated_contracts_are_immutable_all_the_way_down():
    r = validate_recipe(docs_v1.RECIPE)
    d0 = r.digest()
    for mutate in (lambda: r.parameters.__setitem__('C', 1e9),
                   lambda: r.features.append('age'),
                   lambda: r.preprocessing[0].parameters['columns'].append('age'),
                   lambda: r.extensions.update({'x.y': 1}),
                   lambda: r.feature_types.pop('age')):
        with pytest.raises(TypeError):
            mutate()
    assert r.digest() == d0
    dumped = r.model_dump(mode='json')
    dumped['features'].append('x')                     # a dump is an ordinary copy
    assert not isinstance(dumped['parameters'], FrozenDict)
    assert r.features == ['age', 'branch', 'band']
    assert pickle.loads(pickle.dumps(r)).digest() == d0
    c = validate_data_contract(docs_v1.DATA_CONTRACT)
    with pytest.raises(TypeError):
        c.columns.append(c.columns[0])


def test_lock_header_names_the_platform_as_the_manifest_does():
    import platform
    lines = environment_lock().decode().splitlines()
    assert lines[1] == f'# platform {sys.platform}-{platform.machine()}'


def test_bootstrap_with_an_undefined_point_estimate_is_not_ok():
    from mlkit.integrations import scipy_bootstrap as sb
    calls = {'n': 0}

    def ev(yy, pp):
        calls['n'] += 1
        return {'point': None} if calls['n'] <= 2 else \
            {'point': float(np.mean(np.abs(np.asarray(yy) - np.asarray(pp))))}
    out = sb.paired_bootstrap([0.0, 1.0, 2.0], {'a': [0.0] * 3, 'b': [1.0] * 3}, ev,
                              replicates=50, seed=0)
    assert out['status'] == 'insufficient_data'
    assert out['delta'] == {'point': None, 'low': None, 'high': None}
    assert out['uncertainty']['eligible'] is False
    assert out['intervals'] == {'a': {'low': None, 'high': None},
                                'b': {'low': None, 'high': None}}


# --- MAPIE ------------------------------------------------------------------------------------

ELIGIBLE = {'eligible': True, 'reasons': [], 'calibration_ref': 'cal@x', 'n_rows': 3}


def _linear(X):
    return 2 * np.asarray(X)[:, 0]


@mapie_missing
@pytest.mark.parametrize('n,level', [(19, .95), (9, .9), (99, .99), (20, .95), (29, .8)])
def test_conformal_rank_at_most_n_gives_the_finite_sample_quantile(n, level):
    from mlkit.integrations import mapie_uncertainty as mu
    rng = np.random.default_rng(n)
    X = rng.normal(size=(n, 1))
    y = 2 * X[:, 0] + rng.standard_t(3, size=n)
    r = mu.split_conformal(_linear, X, y, X[:3], confidence_level=level, predictor_id=None,
                           calibration=ELIGIBLE)
    k = math.ceil(round((n + 1) * level, 9))
    assert r.status == 'ok', r.reason
    half = np.sort(np.abs(y - _linear(X)))[k - 1]
    assert {round(b.high - b.low, 9) for b in r.interval_bounds} == {round(2 * half, 9)}
    boundary = mu._mapie_refuses(n, level)
    assert r.extensions['hypotrail.quantile'] == ('adapter_rank_rule' if boundary else 'mapie')
    assert bool(r.warnings) == boundary


@mapie_missing
def test_conformal_rank_beyond_n_is_insufficient_data():
    from mlkit.integrations import mapie_uncertainty as mu
    X = np.arange(18.0).reshape(-1, 1)
    r = mu.split_conformal(_linear, X, 2 * X[:, 0] + 1, X[:3], confidence_level=.95,
                           predictor_id=None, calibration=ELIGIBLE)
    assert r.status == 'insufficient_data'


@mapie_missing
@pytest.mark.parametrize('module', ['mapie.regression', 'mapie.risk_control'])
def test_missing_mapie_submodule_is_optional_dependency_missing(monkeypatch, module):
    from mlkit.integrations import mapie_uncertainty as mu
    monkeypatch.setitem(sys.modules, module, None)
    X = np.arange(30.0).reshape(-1, 1)
    with pytest.raises(ContractError) as e:
        if module == 'mapie.regression':
            mu.split_conformal(_linear, X, 2 * X[:, 0], X[:3], confidence_level=.8,
                               predictor_id=None, calibration=ELIGIBLE)
        else:
            mu.control_precision(np.linspace(0, 1, 30), np.arange(30) % 2, thresholds=[.5],
                                 target_precision=.5, confidence_level=.9, predictor_id=None,
                                 calibration=ELIGIBLE)
    assert e.value.code == 'optional_dependency_missing'


# --- Evidently --------------------------------------------------------------------------------

evidently_missing = pytest.mark.skipif(importlib.util.find_spec('evidently') is None,
                                       reason='diagnostics extra')


@evidently_missing
def test_integer_categories_with_a_missing_value_are_the_same_categories():
    from mlkit.integrations import evidently_diagnostics as ed
    rng = np.random.default_rng(0)
    ref = pd.DataFrame({'band': rng.integers(1, 4, 300)})
    cur = rng.integers(1, 4, 300).astype(float)
    cur[0] = np.nan
    out = ed.run(ed.demonstration_profile({'band': 'categorical'}), ref,
                 pd.DataFrame({'band': cur}), reference_partition='d', current_partition='d',
                 authorized=('d',))['result']
    checks = {c.id: c for c in out.checks}
    assert checks['unknown_categories:band'].statistic_value == 0.0
    assert checks['unknown_categories:band'].alert is False
    assert checks['chisquare:band'].status == 'ok' and checks['chisquare:band'].alert is False


def _profile_doc(**column):
    doc = {'schema_version': 'hypotrail.diagnostic_profile/1', 'name': 'x', 'version': 1,
           'columns': {'a': {'kind': 'numerical', 'method': 'ks', 'statistic': 'p_value',
                             'threshold': 0.05, 'comparison': 'lt', 'min_observations': 30,
                             **column}},
           'missing_share_threshold': 0.05, 'unknown_category_share_threshold': 0.05,
           'multiple_testing': 'holm', 'demonstration_thresholds': True}
    return doc


@pytest.mark.parametrize('change', [
    {'threshold': '0.05'}, {'min_observations': '30'}, {'comparison': 'ge'},
    {'comparison': 'gt'},
    {'method': 'wasserstein', 'statistic': 'distance', 'comparison': 'lt'},
    {'method': 'psi', 'statistic': 'distance', 'comparison': 'le'}])
def test_profile_is_strict_and_refuses_an_inverted_alert(change):
    from mlkit.integrations import evidently_diagnostics as ed
    _refused(ed.profile_of, _profile_doc(**change), code='contract_invalid')


def test_profile_top_level_values_are_strict():
    from mlkit.integrations import evidently_diagnostics as ed
    for key, value in (('version', '1'), ('demonstration_thresholds', 'yes'),
                       ('missing_share_threshold', '0.05')):
        _refused(ed.profile_of, {**_profile_doc(), key: value}, code='contract_invalid')
    ok = ed.profile_of(_profile_doc(method='wasserstein', statistic='distance',
                                    comparison='ge'))
    assert ok.columns['a'].comparison == 'ge'
    assert ed.demonstration_profile({'a': 'numerical'}, relationships=[('a', 'b')])


@evidently_missing
def test_empty_profile_says_it_checked_nothing():
    from mlkit.integrations import evidently_diagnostics as ed
    doc = {**_profile_doc(), 'columns': {}}
    r = ed.run(ed.profile_of(doc), pd.DataFrame(), pd.DataFrame(), reference_partition='d',
               current_partition='d', authorized=('d',))['result']
    assert r.status == 'failed' and r.checks == []
    assert r.reason == 'the profile declares no check: nothing was computed'


@evidently_missing
def test_a_profile_column_absent_from_a_population_is_contract_invalid():
    from mlkit.integrations import evidently_diagnostics as ed
    p = ed.demonstration_profile({'a': 'numerical'})
    e = _refused(ed.run, p, pd.DataFrame({'a': np.arange(50.0)}),
                 pd.DataFrame({'b': np.arange(50.0)}), reference_partition='d',
                 current_partition='d', authorized=('d',), code='contract_invalid')
    assert e.details['columns'] == ['a'] and e.path == 'current/columns'


# --- Pandera ---------------------------------------------------------------------------------

def test_pandera_honours_a_declared_conversion_like_the_runtime():
    from hypotrail_runtime import inference
    from mlkit.integrations import pandera_validation as pv
    c = docs_v1.contract()
    c['inference_policy']['conversions'] = [{'column': 'age', 'source': 'int64',
                                             'target': 'float64', 'rule': 'int_to_float'}]
    contract = validate_data_contract(c)
    x = _frame(20, 1, with_target=False)
    x['age'] = 40
    inference.check_frame(contract, x, features=['age', 'branch', 'band'])
    assert pv.validate(contract, x, partition='d', authorized=('d',))['status'] == 'ok'
    # An undeclared type is still refused by both.
    x['band'] = x['band'].astype('float64')
    with pytest.raises(ContractError):
        inference.check_frame(contract, x, features=['age', 'branch', 'band'])
    assert pv.validate(contract, x, partition='d', authorized=('d',))['status'] == 'failed'
    # Without the declaration, the int64 column is refused by both.
    y = _frame(20, 1, with_target=False).assign(age=40)
    with pytest.raises(ContractError):
        inference.check_frame(validate_data_contract(docs_v1.contract()), y,
                              features=['age', 'branch', 'band'])
    assert pv.validate(docs_v1.contract(), y, partition='d',
                       authorized=('d',))['status'] == 'failed'
