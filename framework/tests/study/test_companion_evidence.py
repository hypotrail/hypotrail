"""WP-E2: ``hypotrail evidence`` (CLI-CONTRACT-COMPANION §5, C5) on the Bank and Auto MPG
walkthroughs, and ``dependencies.effects_for_mutation``.

Studies are built in temporary folders, in process through ``cli.run``; the committed
cases are only read. The contract keys are checked by ``test_contract_companion_e2.py``;
these tests check the acceptance of CC §5: the ledger equals ``exposure_summary``, the
impacts of a feature-set change, no figure for a stale result, and a regression study
without the vocabulary of a decision rule.
"""
from __future__ import annotations

import copy
import json
import re

import pytest

import companion_contract as cc
import flowkit as fk
from mlkit.study import cli, dependencies, read, records as rec

AUTO = fk.REPO / 'use-cases' / 'auto-mpg'
# Spec INV-12: the vocabulary of a decision rule, whole words, case-insensitive.
RULE_VOCABULARY = re.compile(r'\b(threshold|capacity|precision|recall|positive class|policy|'
                             r'calling rule|selected)\b', re.IGNORECASE)


def evidence(study, *args):
    outcome = cli.run(['evidence', *map(str, args), '--study', str(study)])
    assert outcome.exit_code == 0, outcome.payload
    return outcome.payload


def bank_flow(study):
    flow = fk.Flow(study, fk.BANK, prefix='bk')
    flow.init()
    flow.pauses()
    for activity in ('split', 'eda.target_rate', 'eda.special_values', 'fit.baseline',
                     'fit.logistic'):
        flow.run(activity)
    flow.run('eda.rate_by', '--column', 'job')
    flow.run('policy.evaluate', '--rule', 'threshold:0.3')
    flow.decide('policy', 'threshold:0.3')
    flow.call('render', '--study', study)
    return flow


def auto_flow(study):
    flow = fk.Flow(study, AUTO, prefix='am')
    flow.init()
    flow.decide('prediction_time', 'when the technical characteristics of a new model are fixed')
    flow.decide('feature_availability', fk.availability(AUTO, acceleration='uncertain_excluded'))
    flow.decide('split', {'method': 'ordinal_cutoff', 'column': 'model_year', 'cutoff': 79})
    flow.model_decisions()          # WP-A4: success criterion and default preprocessing
    for activity in ('split', 'eda.target_summary', 'eda.special_values', 'fit.baseline',
                     'fit.linear', 'evaluate.regression'):
        flow.run(activity)
    flow.run('eda.mean_by', '--column', 'model_year')
    flow.decide('model_choice', 'fit.linear')
    flow.call('render', '--study', study)
    return flow


@pytest.fixture(scope='module')
def bank(tmp_path_factory):
    return bank_flow(tmp_path_factory.mktemp('ev-bank') / 'study')


@pytest.fixture(scope='module')
def auto(tmp_path_factory):
    return auto_flow(tmp_path_factory.mktemp('ev-auto') / 'study')


def _by_slot(payload):
    return {r['slot']: r for r in payload['results'] if r['promoted']}


def test_bank_ledger_has_six_rows_equal_to_the_exposure_summary(bank):
    p = evidence(bank.study)
    ledger = p['exposure']['ledger']
    # ADR 0006: init inspects the development rows and seals the final test (sixth row).
    assert [(r['purpose'], r['partition']) for r in ledger] == [
        ('structural_inspection', 'development'), ('train_eda', 'train'), ('train_fit', 'train'),
        ('validation_model_evaluation', 'validation'),
        ('validation_policy_selection', 'validation'), ('sealed', 'final_test')]
    assert ledger[5]['rows'] == read.open(bank.study).state['partition']['final_test']['n_rows']
    summary = read.open(bank.study).exposure_summary()
    assert p['exposure']['summary'] == summary
    for row in ledger:
        assert row['rows'] == summary['by_partition'][row['partition']][row['purpose']]
    assert sum(r['records'] for r in ledger) == summary['records'] == len(p['exposure']['records'])
    assert all('row_keys' not in r for r in p['exposure']['records'])
    assert p['exposure']['prior_exposure'] == read.open(bank.study).state['prior_exposure']
    by_split = _by_slot(p)['split']['values']['partitions']
    assert ledger[1]['rows'] == by_split['train']['n_rows']
    assert ledger[3]['rows'] == by_split['validation']['n_rows']


def test_bank_impact_of_a_feature_set_change(bank):
    p = evidence(bank.study)
    impact = next(i for i in p['impacts'] if i['mutation'] == 'feature_availability.feature_set')
    assert impact['decision_id'] == 'feature_availability' and impact['row'] == 2
    assert impact['change'] == 'a change that alters the set of usable features'
    assert {'fit.logistic', 'policy.evaluation'} <= set(impact['stale_slots'])
    assert 'fit.baseline' in impact['kept_slots'] and 'split' in impact['kept_slots']
    assert not set(impact['stale_slots']) & set(impact['kept_slots'])
    # WP-B1: the variant is the candidate with one change, so it refits too.
    assert impact['refit'] == ['fit.logistic', 'fit.variant'] and impact['reconfirm'] == ['policy']
    # Rows 1 to 6 of the binary table, each for a confirmed decision; WP-A4 adds the
    # preprocessing (row 14) and the success criterion (row 16); WP-B1 the variant (17).
    assert [i['row'] for i in p['impacts']] == [1, 2, 3, 4, 5, 6, 14, 16, 17]
    split = next(i for i in p['impacts'] if i['mutation'] == 'split')
    assert 'fit.baseline' in split['stale_slots'] and split['kept_slots'] == []
    rule = next(i for i in p['impacts'] if i['mutation'] == 'policy.parameter')
    assert rule['stale_slots'] == [] and rule['refit'] == []


def test_effects_for_mutation_is_pure(bank):
    study = read.open(bank.study)
    state = study.state
    before = copy.deepcopy(state)
    eff = dependencies.effects_for_mutation(state, 'feature_availability.feature_set')
    assert state == before
    assert eff['stale_slots'] == ['fit.logistic', 'fit.variant', 'policy.evaluation']
    assert eff['reconfirm'] == ['policy'] and 'fit.baseline' in eff['kept_slots']
    with pytest.raises(Exception) as refused:
        dependencies.effects_for_mutation(state, 'dataset')
    assert getattr(refused.value, 'code', None) == 'invalid_arguments'


def test_bank_lineage_of_the_logistic_fit(bank):
    p = evidence(bank.study)
    rid = read.open(bank.study).state['current']['fit.logistic']
    edges = {(e['from'], e['to'], e['role']) for e in p['lineage']['edges']}
    split = read.open(bank.study).state['current']['split']
    evaluation = read.open(bank.study).state['current']['policy.evaluation']
    assert ('dataset', split, 'rows') in edges and ('decision:split', split, 'split') in edges
    assert ('decision:feature_availability', rid, 'features') in edges
    assert (split, rid, 'split') in edges and (rid, evaluation, 'fit.logistic') in edges
    assert ('decision:policy', evaluation, 'rule') in edges
    assert (rid, 'artifact:report', 'consumed') in edges
    nodes = {n['id']: n for n in p['lineage']['nodes']}
    assert nodes['artifact:report']['status'] == 'ok'
    assert nodes['dataset']['status'] == 'ok' and nodes[rid]['status'] == 'current'
    ids = set(nodes)
    assert all(e['from'] in ids and e['to'] in ids for e in p['lineage']['edges'])


def test_bank_detail_anchors_and_hint(bank):
    rid = read.open(bank.study).state['current']['fit.logistic']
    p = evidence(bank.study, '--result', rid)
    d = p['detail']
    assert d['report_anchor'] == f'r-{rid}' and 'report' in d['consumers']
    assert d['notebook_hint'] == {'path': 'notebooks/study_generated.py', 'search': rid[:8]}
    assert d['code']['modules'] and all(m['matches'] for m in d['code']['modules'].values())
    assert d['exposure']['exposure_id'] == read.open(bank.study).result(rid)['exposure_id']
    assert 'predictions' in d['blobs'] and d['values'] is not None


def test_a_replaced_evaluation_is_listed_without_figures(bank, tmp_path):
    flow = fk.Flow(fk.clone(bank.study, tmp_path / 'study'), fk.BANK, prefix='bkr')
    old = read.open(flow.study).state['current']['policy.evaluation']
    flow.run('policy.evaluate', '--rule', 'capacity:100')
    flow.decide('policy', 'capacity:100')
    p = evidence(flow.study)
    stale = next(r for r in p['results'] if r['result_id'] == old)
    assert stale['current'] is False and stale['values'] is None and stale['headline'] is None
    assert stale['promoted'] is False and stale['slot'] == 'policy.evaluation'
    assert stale['stale_reason'] is not None
    new = _by_slot(p)['policy.evaluation']
    assert new['current'] and new['values'] and new['headline']
    shown = [s for s in new['headline']['segments'] if 'result_id' in s]
    assert shown and all(s['result_id'] == new['result_id'] for s in shown)
    # Promoted entries first, whatever the limit; the stale one is dropped first.
    limited = evidence(flow.study, '--limit', 1)
    assert limited['truncated'] is True and all(r['promoted'] for r in limited['results'])
    assert old not in [r['result_id'] for r in limited['results']]
    # The stale node is in the lineage, with the stale status.
    nodes = {n['id']: n for n in p['lineage']['nodes']}
    assert nodes[old]['status'] == 'stale'


def test_headlines_cite_their_own_result_at_its_precision(bank):
    from mlkit.study import cite
    p = evidence(bank.study)
    for r in p['results']:
        for s in (r['headline'] or {}).get('segments', []):
            if 'result_id' in s:
                assert s['result_id'] == r['result_id']
                assert s['text'] == cite.fmt_number(s['value'], s['format'])
                assert cite.resolve(r['values'], cite.parse_path(s['path'])) == s['value']
            else:
                # Text segments hold no figure, only rule identifiers.
                assert not re.search(r'(?<![\w.:])\d', s['text']), s


def test_eda_catalog_lists_the_columns_run_would_accept(bank, auto):
    binary = {a['activity']: a for a in evidence(bank.study)['eda_catalog']['activities']}
    rate = [c['name'] for c in binary['eda.rate_by']['columns']]
    assert 'job' in rate and 'y' not in rate
    job = next(c for c in binary['eda.rate_by']['columns'] if c['name'] == 'job')
    assert job['slot'] == 'eda.rate_by:job' and cc.is_hex64(job['result_id'])
    assert 'y' in [c['name'] for c in binary['eda.distribution']['columns']]
    assert all(a['runnable'] and a['missing'] == [] for a in binary.values())
    regression = {a['activity']: a for a in evidence(auto.study)['eda_catalog']['activities']}
    assert tuple(regression) == cc.EDA_CATALOG_ACTIVITIES['regression']
    mean_by = {c['name']: c for c in regression['eda.mean_by']['columns']}
    assert mean_by['model_year']['role'] == 'time'
    assert mean_by['model_year']['slot'] == 'eda.mean_by:model_year'


def test_a_study_before_the_split_cannot_run_eda(tmp_path, synthetic_case_dir):
    flow = fk.Flow(tmp_path / 'study', synthetic_case_dir, prefix='e0')
    flow.init()
    p = evidence(flow.study)
    assert p['results'] == [] and p['impacts'] == [] and p['truncated'] is False
    # WP-A9 (M5): the catalog lists the structural quality overview, which reads the
    # development rows and needs no split; every training-row activity waits for it.
    items = {a['activity']: a for a in p['eda_catalog']['activities']}
    assert items['eda.quality']['runnable'] and items['eda.quality']['partition'] == 'development'
    assert all(not a['runnable'] and a['missing'] for a in p['eda_catalog']['activities']
               if a['partition'] == 'train')
    assert [r['purpose'] for r in p['exposure']['ledger']] == ['structural_inspection', 'sealed']


def test_auto_mpg_evidence_holds_no_rule_vocabulary(auto):
    p = evidence(auto.study)
    assert p['task'] == 'regression'
    # WP-A4: 14, 16; WP-B1: 17
    assert [i['row'] for i in p['impacts']] == [1, 2, 3, 4, 13, 14, 16, 17]
    assert 'validation_policy_selection' not in [r['purpose'] for r in p['exposure']['ledger']]
    choice = next(i for i in p['impacts'] if i['mutation'] == 'model_choice')
    assert choice['stale_slots'] == [] and choice['refit'] == []
    rid = read.open(auto.study).state['current']['evaluate.regression']
    detail = evidence(auto.study, '--result', rid)
    for payload in (p, detail):
        found = sorted({m.group(0).lower() for m in RULE_VOCABULARY.finditer(json.dumps(payload))})
        assert found == [], found
    headline = _by_slot(p)['evaluate.regression']['headline']
    assert headline and 'mpg' in ''.join(s['text'] for s in headline['segments'])


def test_an_entry_that_fails_its_check_is_listed_without_failing(bank, tmp_path):
    study = fk.clone(bank.study, tmp_path / 'study')
    rid = read.open(study).state['current']['eda.special_values']
    path = study / '.hypotrail' / 'registry' / f'{rid}.json'
    entry = json.loads(path.read_text())
    entry['output']['values']['n_rows'] = 1     # the output digest no longer covers it
    path.write_text(json.dumps(entry))
    p = evidence(study)
    item = next(r for r in p['results'] if r['result_id'] == rid)
    assert item['integrity'] == 'integrity_error' and item['values'] is None
    assert item['current'] is False and item['headline'] is None


def test_evidence_does_not_record_exposure_or_read_rows(bank, tmp_path):
    study = fk.clone(bank.study, tmp_path / 'study')
    before = fk.tree_digest(study)
    evidence(study)
    evidence(study, '--result', read.open(study).state['current']['split'])
    assert fk.tree_digest(study) == before
    assert len(fk.exposure_records(study)) == read.open(study).exposure_summary()['records']
    assert all(rec.EXPOSURE_SCHEMA == r['schema'] for r in fk.exposure_records(study))
