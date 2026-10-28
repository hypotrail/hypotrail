"""The published JSON Schemas are current, and the conforming and non-conforming fixtures
are judged as expected by the engine's validator (and by ``jsonschema`` when installed).

``fixtures/understanding/export-valid/`` is a generation exported by the simulated
end-to-end flow of these tests (simulated reviewers, synthetic case)."""
from __future__ import annotations

import copy
import json

import pytest

import flowkit as fk
from mlkit.study.understanding import canonical, export as ex, schemas

FIXTURE = fk.TESTS / 'fixtures' / 'understanding' / 'export-valid'


def valid() -> dict:
    return canonical.loads((FIXTURE / ex.JSON_FILE).read_bytes())


def test_committed_schemas_are_current():
    assert schemas.main(['--check']) == 0


def test_valid_fixture_is_complete_and_consistent():
    doc = valid()
    assert ex.validate_review(doc) == []
    assert ex.markdown(doc).encode() == (FIXTURE / ex.MD_FILE).read_bytes()
    assert doc['review_id'] == ex.review_id(ex.approval_projection(doc))
    assert 'simulated_human_decisions' in doc['limitations']


def _mutants():
    out = []
    d = copy.deepcopy(valid())
    d['dimensions'][0]['status'] = 'passed'
    out.append(('unknown status', d))
    d = copy.deepcopy(valid())
    d['dimensions'][0]['human_review_ref'] = None
    out.append(('demonstrated without review', d))
    d = copy.deepcopy(valid())
    d['extra'] = 1
    out.append(('extra field', d))
    d = copy.deepcopy(valid())
    d['assurance'] = 'external_verified'
    out.append(('assurance', d))
    d = copy.deepcopy(valid())
    d['public_source_scope']['entries'][0]['path'] = '../escape.py'
    out.append(('traversal', d))
    d = copy.deepcopy(valid())
    del d['privacy_review']
    out.append(('missing privacy review', d))
    return out


@pytest.mark.parametrize('name, doc', _mutants(), ids=[n for n, _ in _mutants()])
def test_non_conforming_fixtures_are_refused(name, doc):
    assert ex.validate_review(doc), name


def test_jsonschema_agrees_when_available():
    jsonschema = pytest.importorskip('jsonschema')
    from referencing import Registry, Resource
    docs = schemas.render()
    registry = Registry().with_resources(
        [(k, Resource.from_contents(v)) for k, v in docs.items()])
    validator = jsonschema.Draft202012Validator(docs['understanding-review-1.schema.json'],
                                                registry=registry)
    assert not list(validator.iter_errors(json.loads(json.dumps(valid()))))
    for name, doc in _mutants():
        if name == 'traversal':
            continue            # a path rule the verifier applies, not the schema
        assert list(validator.iter_errors(doc)), name
