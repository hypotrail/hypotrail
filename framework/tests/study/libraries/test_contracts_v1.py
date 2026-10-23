"""Shared contracts v1: strictness, versions, canonical form, schemas, identity (AC02, AC04).

The expected digests and canonical bytes below are frozen reference vectors: a change of
the serialiser or of a model that moves them is a new contract version, not an edit.
"""
from __future__ import annotations

import json
import subprocess
import sys

import pytest

from hypotrail_runtime import canonical
from hypotrail_runtime.contracts import (DiagnosticResult, MODELS, Tolerance, parse,
                                         validate_data_contract, validate_recipe)
from hypotrail_runtime.errors import CODES, ContractError
from mlkit.contracts import context as cx

import docs_v1

RECIPE_ID = '1996818f11ff94fbc23aad319264285f7ec32315aa546b85b6c8a8daa9330078'
# Updated at integration I1 (parser header and quotechar added before any release).
CONTRACT_ID = 'cb1b66b94aae75e30e2936e045e6b3de1580c7201377795b74edf7894867bb39'
VECTORS = [
    ({'b': 1, 'a': [3, 1, 2]}, b'{"a":[3,1,2],"b":1}',
     'c35614dff4239c844f2aba7b99dcf76087221bf13f20fa1fefbe4a4173a7ad12'),
    ({'é': -0.0, 'z': 1.5, 'a': None, 't': True},
     '{"a":null,"t":true,"z":1.5,"é":0.0}'.encode(),
     '31e67ead9d81772a6d0a2920be1813bbee9b71c4a8644fa69ce9048e909740ba'),
    ({'x': {'k': [{'b': 0.1, 'a': 'ü'}]}}, '{"x":{"k":[{"a":"ü","b":0.1}]}}'.encode(),
     '0d6ca24821c9bb529b3e01ad899b1284433f92b9ce3cfea6bef63a3f1a48ece1'),
    ([1, 1.0, 'a'], b'[1,1.0,"a"]',
     '04d2367f700193c4c24a25f34c15e18481f4c57d79b836efcc7482f503e229ce'),
]


def _refused(fn, document) -> ContractError:
    with pytest.raises(ContractError) as e:
        fn(document)
    assert set(e.value.to_dict()) >= {'code', 'path', 'message', 'remediation', 'details'}
    assert e.value.code in CODES
    return e.value


def _both(fn, document):
    """The same document as a Python mapping and as JSON text: same verdict."""
    outcomes = []
    for form in (document, json.dumps(document)):
        try:
            outcomes.append(('ok', fn(form).digest()))
        except ContractError as exc:
            outcomes.append((exc.code, exc.path))
    assert outcomes[0] == outcomes[1], outcomes
    return outcomes[0]


def test_reference_documents_are_accepted_with_frozen_identities():
    assert validate_recipe(docs_v1.RECIPE).digest() == RECIPE_ID
    assert validate_data_contract(docs_v1.DATA_CONTRACT).digest() == CONTRACT_ID
    assert _both(validate_recipe, docs_v1.RECIPE) == ('ok', RECIPE_ID)


@pytest.mark.parametrize('bad, path', [
    ({'seeds': {'estimator': True}}, 'seeds/estimator'),            # a boolean is not an int
    ({'seeds': {'estimator': '7'}}, 'seeds/estimator'),              # a string is not an int
    ({'seeds': {'estimator': 7.0}}, 'seeds/estimator'),              # a float is not an int
    ({'parameters': {'C': '1'}}, 'parameters/C'),
    ({'parameters': {'C': True}}, 'parameters/C'),
    ({'unexpected': 1}, 'unexpected'),
    ({'task': 'multiclass'}, 'task'),
    ({'extensions': {'note': 1}}, 'extensions/note'),               # not namespaced
    ({'features': []}, 'features'),
])
def test_strict_structure_refuses_ambiguous_values(bad, path):
    code, where = _both(validate_recipe, docs_v1.recipe(**bad))
    assert code == 'contract_invalid'
    assert where.startswith(path.split('/')[0])


def test_non_finite_numbers_are_refused_in_python_and_in_json():
    err = _refused(validate_recipe, docs_v1.recipe(parameters={'C': float('nan')}))
    assert err.code == 'contract_invalid'
    err = _refused(validate_recipe, docs_v1.recipe(extensions={'x.y': [float('inf')]}))
    assert err.code == 'contract_invalid'
    text = json.dumps(docs_v1.RECIPE).replace('"tol": 1e-08', '"tol": NaN')
    assert 'NaN' in text
    assert _refused(validate_recipe, text).code == 'contract_invalid'
    with pytest.raises(ContractError):
        canonical.dumps({'a': float('-inf')})


def test_unknown_major_version_is_refused_before_anything_else():
    err = _refused(validate_recipe, docs_v1.recipe(schema_version='hypotrail.model_recipe/2',
                                                   unexpected=True))
    assert err.code == 'schema_version_unsupported'
    assert err.details['supported'] == ['hypotrail.model_recipe/1']
    assert _refused(validate_recipe,
                    docs_v1.recipe(schema_version='hypotrail.data_contract/1')).code \
        == 'contract_invalid'


def test_semantic_rules_are_checked_separately_from_structure():
    for changes, path in [
            ({'target': {'name': 'age', 'unit': None, 'positive_label': 'yes'}}, 'target/name'),
            ({'target': {'name': 'renewed', 'unit': None, 'positive_label': None}},
             'target/positive_label'),
            ({'feature_types': {'age': {'semantic': 'numeric', 'physical': 'float64'}}},
             'feature_types'),
            ({'family': 'forest'}, 'family'),
            ({'parameters': {'alpha': 1.0}}, 'parameters/alpha'),
            ({'task': 'regression'}, 'family')]:
        err = _refused(validate_recipe, docs_v1.recipe(**changes))
        assert err.code == 'contract_invalid'
        assert any(i['path'] == path for i in err.issues), (path, err.issues)
    err = _refused(validate_data_contract, docs_v1.contract(inference_policy={
        **docs_v1.DATA_CONTRACT['inference_policy'],
        'required_columns': ['age', 'branch', 'band', 'renewed']}))
    assert 'never required' in err.issues[0]['message']


def test_canonical_reference_vectors_and_typed_normalisation():
    for value, data, digest in VECTORS:
        assert canonical.dumps(value) == data
        assert canonical.sha256_hex(data) == digest
    assert Tolerance(rtol=1, atol=0, exact=[]).canonical() == \
        b'{"atol":0.0,"exact":[],"rtol":1.0}'           # float fields are floats
    with pytest.raises(ContractError):
        canonical.dumps({1: 'non-string key'})


def test_artifact_id_excludes_its_own_id_and_mutable_binding():
    doc = {'predictor_id': 'x', 'binding': 'y', 'content': [1, 2]}
    a = canonical.artifact_id(doc, exclude=('predictor_id', 'binding'))
    b = canonical.artifact_id({**doc, 'predictor_id': 'other', 'binding': 'z'},
                              exclude=('predictor_id', 'binding'))
    assert a == b == canonical.scientific_id({'content': [1, 2]})


def test_json_schemas_are_generated_and_current():
    proc = subprocess.run([sys.executable, '-m', 'hypotrail_runtime.schemas', '--check'],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    from hypotrail_runtime.schemas.__main__ import render
    assert len(render()) == len(MODELS)
    schema = json.loads(render()['model_recipe-v1.schema.json'])
    assert schema['additionalProperties'] is False


def test_adapter_results_separate_not_computed_from_no_alert():
    base = {'schema_version': 'hypotrail.diagnostic_result/1', 'result_id': 'b' * 64,
            'status': 'failed', 'reason': 'backend_failed: boom', 'context': None,
            'backend': None, 'method': {'name': 'm', 'version': '1', 'parameters': {}},
            'warnings': [], 'artifact_refs': [], 'checks': [], 'alert': None}
    assert parse(DiagnosticResult, base).alert is None
    with pytest.raises(ContractError):
        parse(DiagnosticResult, {**base, 'reason': None})          # not ok states its reason
    check = {'id': 'c', 'family': 'marginal_distribution', 'column_or_pair': ['x'],
             'reference_partition': 'development', 'current_partition': 'monitoring',
             'n_reference': 10, 'n_current': 10, 'statistic_name': 'ks',
             'statistic_value': None, 'p_value': None, 'adjusted_p_value': None,
             'effect_size': None, 'threshold': 0.05, 'comparison': 'lt', 'alert': False,
             'status': 'failed', 'reason': 'boom'}
    with pytest.raises(ContractError):                             # failed never says "no alert"
        parse(DiagnosticResult, {**base, 'checks': [check]})


# --- AC04: identity follows the engines a method calls -------------------------------------

def _context(versions: dict, method='bootstrap.scipy_percentile', **extra):
    return cx.build(method=method, activity_id=extra.pop('activity_id', 'run-1'),
                    study_id='s', expected_revision=3, code_fingerprint='c' * 64,
                    lookup=lambda name: versions.get(name), **extra)


def test_identity_changes_with_a_relevant_backend_version_only():
    base = {'numpy': '2.5.4', 'scipy': '1.18.1', 'pandas': '3.0.6', 'evidently': '0.7.23'}
    ref = cx.computation_id(_context(base))
    assert cx.computation_id(_context({**base, 'scipy': '1.18.2'})) != ref
    assert cx.computation_id(_context({**base, 'numpy': '2.6.0'})) != ref
    # Packages this method does not call, the run id and the audit lock do not matter.
    assert cx.computation_id(_context({**base, 'pandas': '9', 'evidently': '9'})) == ref
    assert cx.computation_id(_context(base, activity_id='run-2',
                                      environment_lock_sha256='e' * 64)) == ref
    # The same version change matters to the method that calls that engine.
    ev = cx.computation_id(_context(base, method='diagnostics.evidently'))
    assert cx.computation_id(_context({**base, 'evidently': '0.7.24'},
                                      method='diagnostics.evidently')) != ev


def test_incomplete_environment_has_no_identity():
    with pytest.raises(ContractError) as e:
        _context({'numpy': '2.5.4'})
    assert e.value.code == 'optional_dependency_missing'
    assert e.value.details['missing'] == ['scipy']
