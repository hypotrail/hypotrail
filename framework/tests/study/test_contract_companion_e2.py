# Contract tests of the advanced companion, WP-E2 part (C5, C6, C7, C10 locations). Written
# by WP-0. WP-E2 removes the ``E2`` markers of this file only, and deletes
# ``test_wp0_stubs_refuse_until_e2``, whose stubs it replaces. Nothing else changes here
# without the integrator (docs/plans/COMPANION-ADVANCED-PLAN.md §2.1).
"""CLI-CONTRACT-COMPANION C5 (``evidence``), C6 (``explain``), C7 (``export handoff``),
and the ``location`` of C10 (``check`` findings), with R1 and R3.

The ``E2``-marked tests are strict ``xfail``: they fail until WP-E2 lands.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import companion_contract as cc
import flowkit as fk
from mlkit.study import read


@pytest.fixture(scope='module')
def binary(tmp_path_factory, synthetic_case_dir):
    return cc.binary_study(synthetic_case_dir, tmp_path_factory.mktemp('cc-e2') / 'study')


@pytest.fixture
def clone(binary, tmp_path):
    return fk.Flow(fk.clone(binary.study, tmp_path / 'study'), binary.case_dir, prefix='k')


def _rid(study, slot):
    return read.open(study).state['current'][slot]


# --- C5 ------------------------------------------------------------------------------------

def test_c5_evidence_keys(binary):
    code, p = cc.run('evidence', '--study', binary.study)
    assert code == 0, p
    assert tuple(p) == cc.EVIDENCE_KEYS and p['schema'] == cc.EVIDENCE_SCHEMA
    assert p['task'] == 'binary' and p['truncated'] is False and p['detail'] is None
    promoted = [r for r in p['results'] if r['promoted']]
    assert promoted and p['results'][:len(promoted)] == promoted
    for r in p['results']:
        assert tuple(r) == cc.EVIDENCE_RESULT_KEYS and cc.is_hex64(r['result_id'])
        if not (r['current'] and r['integrity'] == 'ok'):
            assert r['values'] is None and r['headline'] is None
        for segment in (r['headline'] or {}).get('segments', []):
            assert tuple(segment) in (cc.SEGMENT_KEYS, cc.CITED_SEGMENT_KEYS)
    assert tuple(p['lineage']) == cc.LINEAGE_KEYS
    for node in p['lineage']['nodes']:
        assert tuple(node) == cc.LINEAGE_NODE_KEYS
        assert node['kind'] in cc.LINEAGE_NODE_KINDS and node['status'] in cc.LINEAGE_NODE_STATUSES
    for edge in p['lineage']['edges']:
        assert tuple(edge) == cc.LINEAGE_EDGE_KEYS
    assert tuple(p['exposure']) == cc.EXPOSURE_KEYS
    assert p['exposure']['summary'] == read.open(binary.study).exposure_summary()
    for record in p['exposure']['records']:
        assert tuple(record) == cc.EXPOSURE_RECORD_VIEW_KEYS
    purposes = [row['purpose'] for row in p['exposure']['ledger']]
    assert purposes[0] == 'structural_inspection' and 'train_eda' in purposes
    for row in p['exposure']['ledger']:
        assert tuple(row) == cc.LEDGER_KEYS
    for impact in p['impacts']:
        assert tuple(impact) == cc.IMPACT_KEYS
    assert tuple(p['eda_catalog']) == cc.EDA_CATALOG_KEYS
    catalog = p['eda_catalog']['activities']
    assert tuple(a['activity'] for a in catalog) == cc.EDA_CATALOG_ACTIVITIES['binary']
    for item in catalog:
        assert tuple(item) == cc.EDA_CATALOG_ITEM_KEYS
        for column in item['columns']:
            assert tuple(column) == cc.EDA_CATALOG_COLUMN_KEYS
    per_column = {a['activity']: a for a in catalog if a['per_column']}
    assert set(per_column) == {'eda.rate_by', 'eda.distribution'}
    assert cc.NUMERIC_COLUMN in [c['name'] for c in per_column['eda.distribution']['columns']]
    assert tuple(p['sources']) == cc.SOURCES_KEYS
    assert all(tuple(p['sources'][k]) == cc.SOURCE_KEYS for k in cc.SOURCES_KEYS)


def test_c5_detail_limit_and_refusals(binary):
    rid = _rid(binary.study, 'fit.logistic')
    code, p = cc.run('evidence', '--result', rid, '--limit', 1, '--study', binary.study)
    assert code == 0, p
    assert tuple(p['detail']) == cc.DETAIL_KEYS and p['detail']['result_id'] == rid
    assert tuple(p['detail']['code']) == cc.DETAIL_CODE_KEYS
    hint = p['detail']['notebook_hint']
    assert hint is None or (tuple(hint) == cc.NOTEBOOK_HINT_KEYS and hint['search'] == rid[:8])
    assert p['detail']['report_anchor'] in (None, f'r-{rid}')
    promoted = sum(1 for r in p['results'] if r['promoted'])
    assert len(p['results']) == promoted     # promoted entries come first, whatever the limit
    for bad in ('0', '-3'):
        code, p = cc.run('evidence', '--limit', bad, '--study', binary.study)
        assert code == 2 and cc.refusal(p)[0] == 'invalid_arguments', p
    code, p = cc.run('evidence', '--result', 'f' * 64, '--study', binary.study)
    assert code == 2 and cc.refusal(p)[0] == 'unknown_result', p


# --- C6 ------------------------------------------------------------------------------------

def test_c6_explain_keys(binary):
    code, p = cc.run('explain', '--study', binary.study)
    assert code == 0, p
    assert tuple(p) == cc.EXPLAIN_KEYS and p['schema'] == cc.EXPLAIN_SCHEMA
    terms = {t['id']: t for t in p['terms']}
    for t in p['terms']:
        assert tuple(t) == cc.EXPLAIN_TERM_KEYS and t['example_status'] in cc.EXAMPLE_STATUSES
        if t['example_status'] != 'shown':
            assert t['example'] is None
    base = terms['base_rate']
    assert base['example_status'] == 'shown'
    cited = [s for s in base['example']['segments'] if 'result_id' in s]
    assert cited and cited[0]['result_id'] == _rid(binary.study, 'eda.target_rate')
    for step, texts in p['steps'].items():
        assert tuple(texts) == cc.EXPLAIN_STEP_KEYS, step
    for q in p['predictions']:
        assert tuple(q) == cc.EXPLAIN_PREDICTION_KEYS
        assert 2 <= len(q['choices']) <= 4 and 'not_sure' in [c['id'] for c in q['choices']]
        assert all(tuple(c) == cc.EXPLAIN_CHOICE_KEYS for c in q['choices'])
        assert q['available'] is (q['reveal'] is not None)
    code, one = cc.run('explain', '--term', 'base_rate', '--study', binary.study)
    assert code == 0 and [t['id'] for t in one['terms']] == ['base_rate'], one
    code, bad = cc.run('explain', '--term', 'no_such_term', '--study', binary.study)
    assert code == 2 and cc.refusal(bad)[0] == 'invalid_arguments' and 'terms' in cc.refusal(bad)[1]


# --- R1, R3 (C5, C6) -----------------------------------------------------------------------

def test_e2_reads_are_read_only_and_import_no_heavy_module(binary, tmp_path):
    study = fk.clone(binary.study, tmp_path / 'ro study')
    for argv in (('evidence',), ('evidence', '--result', _rid(study, 'fit.logistic')),
                 ('explain',)):
        code, payload = cc.r1_read_only(study, *argv)
        assert code == 0 and payload['ok'] is True, (argv, payload)
        assert cc.r3_imported(study, *argv) == [], argv


# --- C7 ------------------------------------------------------------------------------------

def test_c7_export_handoff(clone, tmp_path):
    before = cc.study_tree_digest(clone.study)
    out = tmp_path / 'packs' / 'first'
    code, p = cc.run('export', 'handoff', '--out', out, '--study', clone.study)
    assert code in (0, 3), p
    assert tuple(p) == cc.EXPORT_KEYS and p['schema'] == cc.EXPORT_SCHEMA and p['kind'] == 'handoff'
    assert Path(p['out']) == out
    assert all(tuple(f) == cc.EXPORT_FILE_KEYS for f in p['files'])
    names = {f['path'] for f in p['files']}
    assert {'handoff.md', 'handoff.json'} <= names <= set(cc.EXPORT_FILES)
    assert (out / 'SHA256SUMS').is_file()
    assert ('study.html' in names) is p['included_report'] and (code == 3) is (
        not p['included_report'])
    assert set(p['warnings']) <= set(cc.EXPORT_WARNINGS)
    handoff = json.loads((out / 'handoff.json').read_text(encoding='utf-8'))
    assert tuple(handoff) == cc.HANDOFF_KEYS and handoff['schema'] == cc.HANDOFF_SCHEMA
    for item in handoff['results_cited']:
        assert tuple(item) == cc.HANDOFF_CITED_KEYS
    assert cc.study_tree_digest(clone.study) == before
    second = tmp_path / 'packs' / 'second'
    code2, _ = cc.run('export', 'handoff', '--out', second, '--study', clone.study)
    assert code2 == code
    assert {f.name: f.read_bytes() for f in out.iterdir()} == {
        f.name: f.read_bytes() for f in second.iterdir()}


def test_c7_export_refusals(clone, tmp_path):
    code, p = cc.run('export', 'handoff', '--out', clone.study / '.hypotrail' / 'pack',
                     '--study', clone.study)
    assert code == 2 and cc.refusal(p)[0] == 'invalid_arguments', p
    assert cc.refusal(p)[1].get('field') == 'out'
    busy = tmp_path / 'busy'
    busy.mkdir()
    (busy / 'keep.txt').write_text('mine')
    code, p = cc.run('export', 'handoff', '--out', busy, '--study', clone.study)
    assert code == 2 and cc.refusal(p)[0] == 'export_target_exists', p
    assert cc.refusal(p)[1].get('path') == str(busy)
    assert (busy / 'keep.txt').read_text() == 'mine'
    code, p = fk.hyp('export', 'handoff', '--out', tmp_path / 'ro', '--study', clone.study,
                     cwd=tmp_path, extra_env={'HYPOTRAIL_READ_ONLY': '1'})
    assert code == 2 and cc.refusal(p)[0] == 'read_only', p
    assert not (tmp_path / 'ro').exists()


# --- C10 locations -------------------------------------------------------------------------

def test_c10_check_findings_carry_a_location(clone):
    note = clone.study / 'note.md'
    note.write_text('A first line.\nThe model reaches 97.3% here.\n', encoding='utf-8')
    code, p = cc.run('check', '--text', note, '--study', clone.study)
    assert p['findings'], p
    for finding in p['findings']:
        assert tuple(finding['location']) == cc.CHECK_LOCATION_KEYS
    location = p['findings'][0]['location']
    assert location['path'] == 'note.md' and location['line'] == 2 and location['anchor'] is None
