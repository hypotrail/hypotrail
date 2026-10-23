"""Units of the export: canonical JSON (contract §1), projection, profile, transfer."""
from __future__ import annotations

import math

import pytest

from mlkit.exporters.azureml import canonical as cj, profile as pf, projection, transfer
from mlkit.exporters.azureml.errors import ExportError


@pytest.mark.parametrize(('value', 'expected'), [
    ({'b': 1, 'a': [3, 1]}, b'{"a":[3,1],"b":1}'),
    ({'x': -0.0}, b'{"x":0.0}'),
    ({'x': 1.0, 'y': 1}, b'{"x":1.0,"y":1}'),
    ({'t': True, 'n': None}, b'{"n":null,"t":true}'),
    ({'é': 'ü'}, '{"é":"ü"}'.encode()),
])
def test_canonical_vectors(value, expected):
    assert cj.canonical_bytes(value) == expected


@pytest.mark.parametrize('bad', [{'x': math.nan}, {'x': math.inf}, {1: 'a'}, {'x': object()}])
def test_canonical_refuses_non_json(bad):
    with pytest.raises(cj.CanonicalError):
        cj.canonical_bytes(bad)


def test_a_boolean_is_not_an_integer():
    assert cj.canonical_sha256({'x': True}) != cj.canonical_sha256({'x': 1})
    assert projection.differences({'x': 1}, {'x': True}) == ['x']
    assert projection.differences({'x': 1}, {'x': 1.0}) == ['x']


def test_strict_loads_refuses_nan():
    with pytest.raises(cj.CanonicalError):
        cj.loads_strict('{"x": NaN}')


def test_the_config_shape_refuses_unknown_keys_and_targets():
    with pytest.raises(projection.ProjectionError):
        projection.check_shape({'surprise': 1})
    with pytest.raises(projection.ProjectionError):
        projection.check_shape({'components': {'training': {'model': {'params': {
            '_target_': 'os.system'}}}}})
    projection.check_shape({'components': {'training': {'model': {'params': {'alpha': 1}}}}})


def _profile(**changes):
    doc = {'schema_version': pf.SCHEMA,
           'subscription_id': '00000000-0000-4000-8000-000000000000',
           'resource_group': 'rg', 'workspace': 'ws', 'compute': 'cpu',
           'data_asset': {'name': 'dev', 'version': '1'},
           'environment': {'name': 'env', 'version': '2',
                           'base_image': 'mcr.microsoft.com/azureml/base:20250601.v1'},
           'identity': {'mode': 'user_identity'}}
    doc.update(changes)
    return doc


def test_a_complete_profile_is_configured():
    normal, missing = pf.validate(_profile())
    assert missing == [] and normal['ci']['cloud_enabled'] is False


def test_no_profile_is_a_draft_with_every_field_missing():
    _, missing = pf.validate(None)
    assert missing == list(pf.REQUIRED)


def test_a_partial_profile_lists_what_is_missing():
    doc = _profile()
    del doc['compute']
    doc['environment'] = {'name': 'env'}
    _, missing = pf.validate(doc)
    assert missing == ['compute', 'environment.version', 'environment.base_image']


@pytest.mark.parametrize(('changes', 'path'), [
    ({'client_secret': 'x'}, 'client_secret'),
    ({'workspace_password': 'x'}, 'workspace_password'),
    ({'resource_group': 'DefaultEndpointsProtocol=https;AccountKey=abc'}, 'resource_group'),
    ({'surprise': 1}, 'surprise'),
    ({'subscription_id': 'not-a-guid'}, 'subscription_id'),
    ({'data_asset': {'name': 'dev', 'version': 'latest'}}, 'data_asset.version'),
    ({'environment': {'name': 'e', 'version': '1', 'base_image': 'mcr.microsoft.com/x:latest'}},
     'environment.base_image'),
    ({'identity': {'mode': 'password'}}, 'identity.mode'),
])
def test_a_malformed_or_secret_profile_is_refused(changes, path):
    with pytest.raises(ExportError) as error:
        pf.validate(_profile(**changes))
    assert error.value.code == 'contract_invalid'
    assert error.value.details['path'] == path


def test_an_unknown_profile_version_is_refused():
    with pytest.raises(ExportError) as error:
        pf.validate({'schema_version': 'hypotrail.azure_target/2'})
    assert error.value.code == 'schema_version_unsupported'


def test_transfer_applies_amlignore(tmp_path):
    (tmp_path / '.amlignore').write_text('data/\n*.key\n**/__pycache__/\n!keep.key\n')
    for rel in ('src/a.py', 'src/__pycache__/a.pyc', 'data/x.csv', 'b.key', 'keep.key', 'README.md'):
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('x')
    assert transfer.transferable(tmp_path) == ['.amlignore', 'README.md', 'keep.key', 'src/a.py']
