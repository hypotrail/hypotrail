"""Immutable result registry (plan WP1.3, §3.3)."""
from __future__ import annotations

import json
import sys

import pytest

from mlkit.study import records as rec, registry
from mlkit.study.errors import StudyError
from mlkit.study.store import read_jsonl

CODE = registry.code_fingerprint(['mlkit.study.records'])


def _put(store, activity='split', values=None, inputs=None, params=None, **kw):
    return registry.put(store, activity=activity, params=params or {'seed': 1},
                        inputs=inputs or {'dataset_sha256': 'd' * 64}, code=CODE,
                        values={'n': 3} if values is None else values, **kw)


def test_put_and_get_round_trip_with_recomputed_identity(new_study):
    out = _put(new_study, blobs={'rows': b'L2\nL3\n'}, partition='train', n_rows=2,
               execution_id='e1', started_revision=1)
    assert out['created'] and not out['nondeterministic']
    entry = registry.get(new_study, out['result_id'])
    assert entry['schema'] == rec.RESULT_SCHEMA
    assert entry['input_key'] == out['input_key']
    assert entry['result_id'] == rec.result_id('split', {'seed': 1}, {'dataset_sha256': 'd' * 64},
                                               CODE['fingerprint'], entry['output']['sha256'])
    assert set(entry) == set(rec.RESULT_KEYS)
    assert new_study.read_blob(entry['blobs']['rows']) == b'L2\nL3\n'
    again = _put(new_study, blobs={'rows': b'L2\nL3\n'}, partition='train', n_rows=2)
    assert again['result_id'] == out['result_id'] and again['created'] is False


def test_entry_files_are_immutable_and_tampering_is_an_integrity_error(new_study):
    rid = _put(new_study)['result_id']
    path = new_study.home / 'registry' / f'{rid}.json'
    entry = json.loads(path.read_text())
    entry['output']['values']['n'] = 4
    path.write_text(json.dumps(entry))
    with pytest.raises(StudyError) as err:
        registry.get(new_study, rid)
    assert err.value.code == 'integrity_error'


def test_recomputed_result_id_catches_a_consistent_rewrite(new_study):
    rid = _put(new_study)['result_id']
    path = new_study.home / 'registry' / f'{rid}.json'
    entry = json.loads(path.read_text())
    entry['output']['values']['n'] = 4
    entry['output']['sha256'] = rec.output_sha256(entry['output']['values'], entry['blobs'])
    path.write_text(json.dumps(entry))
    with pytest.raises(StudyError, match='result_id') as err:
        registry.get(new_study, rid)
    assert err.value.code == 'integrity_error'


def test_tampered_or_missing_blob_is_an_integrity_error(new_study):
    out = _put(new_study, blobs={'rows': b'L2\n'})
    sha = registry.get(new_study, out['result_id'])['blobs']['rows']
    blob = new_study.home / 'blobs' / sha
    blob.write_bytes(b'L3\n')
    with pytest.raises(StudyError) as err:
        registry.get(new_study, out['result_id'])
    assert err.value.code == 'integrity_error'
    blob.unlink()
    with pytest.raises(StudyError) as err:
        registry.get(new_study, out['result_id'])
    assert err.value.code == 'integrity_error'


def test_unknown_result_is_refused(new_study):
    with pytest.raises(StudyError) as err:
        registry.get(new_study, 'f' * 64)
    assert err.value.code == 'unknown_result'


def test_same_input_key_with_different_output_flags_nondeterminism(new_study):
    first = _put(new_study, values={'n': 3})
    second = _put(new_study, values={'n': 5})
    assert first['input_key'] == second['input_key']
    assert first['result_id'] != second['result_id']
    assert second['nondeterministic'] and second['same_input_results'] == [first['result_id']]
    assert registry.by_input_key(new_study, first['input_key']) == sorted(
        [first['result_id'], second['result_id']])
    events = [e for e in read_jsonl(new_study.events_path) if e['kind'] == 'nondeterministic_result']
    assert events and events[-1]['others'] == [first['result_id']]


def test_environment_is_outside_identity(new_study):
    a = _put(new_study, env={'python': '3.13.0', 'packages': {'pandas': '2.1'}})
    b = _put(new_study, env={'python': '3.13.9', 'packages': {'pandas': '9.9'}})
    assert a['result_id'] == b['result_id'] and not b['nondeterministic']
    entry = registry.get(new_study, a['result_id'])
    assert entry['environment']['python'] == '3.13.0'   # first write wins; never rewritten
    assert set(registry.environment()) >= {'python', 'platform', 'packages'}


def test_code_fingerprint_covers_only_the_activity_modules(tmp_path, monkeypatch):
    pkg = tmp_path / 'fp_probe'
    pkg.mkdir()
    (pkg / '__init__.py').write_text('')
    (pkg / 'mine.py').write_text('X = 1\n')
    (pkg / 'other.py').write_text('Y = 1\n')
    monkeypatch.syspath_prepend(str(tmp_path))
    before = registry.code_fingerprint(['fp_probe.mine'])
    (pkg / 'other.py').write_text('Y = 2\n')
    assert registry.code_fingerprint(['fp_probe.mine']) == before
    (pkg / 'mine.py').write_text('X = 2\n')
    after = registry.code_fingerprint(['fp_probe.mine'])
    assert after['fingerprint'] != before['fingerprint']
    assert set(after['modules']) == {'fp_probe.mine'}
    assert 'fp_probe.mine' not in sys.modules    # located and read, never imported
    with pytest.raises(StudyError):
        registry.code_fingerprint([])


def test_lineage_and_is_current(new_study):
    split = _put(new_study, activity='split')['result_id']
    fit = _put(new_study, activity='fit.logistic', inputs={'results': {'split': split}})['result_id']
    policy = _put(new_study, activity='policy.evaluation',
                  inputs={'results': {'model': fit, 'split': split}})['result_id']
    assert registry.lineage(new_study, policy) == [fit, split]
    assert registry.lineage(new_study, split) == []
    state = new_study.load_state()
    assert not registry.is_current(state, fit)
    state['current'] = {'split': split, 'fit.logistic': fit}
    assert registry.is_current(state, fit)
    state['stale'][fit] = {'reason': 'x', 'since': 2}
    assert not registry.is_current(state, fit)


def test_put_refuses_malformed_inputs(new_study):
    with pytest.raises(StudyError):
        _put(new_study, inputs={'results': {'split': 3}})
    with pytest.raises(StudyError):
        registry.put(new_study, activity='x', params={}, inputs={},
                     code={'fingerprint': '0' * 64, 'modules': {}}, values={})
    with pytest.raises(ValueError):
        _put(new_study, values={'n': float('nan')})
