"""The v0.2b cases (WP-B3): Online Shoppers (advanced since v0.3) and Bank Marketing full file;
the generation check also covers the v0.3 discovery case, Hotel booking demand.

* each committed ``case.yaml`` is what its ``build_case.py`` generates, and the committed
  data pass the integrity checks against the figures UCI publishes (``--verify``);
* each case validates and is supported; ``init`` seals the expected final test
  (stratified with whole duplicate groups for Online Shoppers, the last 20 % of the lines
  for Bank full); the data card reads each;
* Online Shoppers runs end to end to the policy evaluation (share rules, gain points, the
  PageValues legitimacy question) and the adopted default share is a named limit.

Studies live in temporary directories; the committed cases are only read.
"""
from __future__ import annotations

import importlib.util
import json

import pytest

from mlkit.study import case as c, data, partition

import flowkit as fk
from flowkit import Flow

SHOPPERS = fk.REPO / 'use-cases' / 'online-shoppers'
BANK_FULL = fk.REPO / 'use-cases' / 'bank-marketing-full'
# v0.3 (WP-G): the discovery case, built the same way (its own tests: test_v03_hotel_case.py)
HOTEL = fk.REPO / 'use-cases' / 'hotel-booking'


def _builder(case_dir):
    spec = importlib.util.spec_from_file_location(f'build_{case_dir.name}',
                                                  case_dir / 'build_case.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('case_dir', [HOTEL, SHOPPERS, BANK_FULL], ids=lambda p: p.name)
def test_the_committed_case_is_generated_and_the_data_verify(case_dir, capsys):
    builder = _builder(case_dir)
    assert builder.main(['--check']) == 0, capsys.readouterr().out
    assert builder.main(['--verify']) == 0, capsys.readouterr().out
    case = c.load_case(case_dir)
    assert c.require_supported(case) is case
    assert case.scenario_defaults['capacity_share'] == {
        'value': 0.1, 'status': 'scenario_assumption',
        'source': case.scenario_defaults['capacity_share']['source']}
    facts = {f['id']: f for f in case.document['facts']}
    for fact in ('data_rows_columns', 'data_class_counts', 'data_mirror'):
        assert facts[fact]['status'] == 'observed'
        assert case.dataset['sha256'] in json.dumps(case.document['provenance']) \
            or fact != 'data_mirror'
    # every variable has a group and a French label
    for v in case.document['variables']:
        assert v.get('group') and (v.get('labels') or {}).get('fr'), v['name']


def test_online_shoppers_states_what_is_not_verified():
    case = c.load_case(SHOPPERS)
    assert case.task == 'binary' and case.order is None and case.duplicates_policy == 'group'
    statuses = {v['status'] for v in case.document['variables']}
    assert statuses == {'scenario_assumption'}                    # nothing claimed as sourced
    page_values = case.variables['PageValues']
    assert page_values['availability']['value'] == 'uncertain'
    assert page_values['availability']['status'] != 'documented_fact'
    assert 'first question' in page_values['availability']['source']
    index = data.row_index(case)
    summary = data.duplicate_summary(case, index)
    assert summary['n_extra_rows'] == case.document['structure']['duplicates']['value'] == 125
    labels = data.load_dataset(case).frame['Revenue'].astype(str).value_counts().to_dict()
    assert labels == {'False': 10422, 'True': 1908}


def test_bank_full_is_ordered_by_line_and_contains_bank(tmp_path):
    case = c.load_case(BANK_FULL)
    assert case.order == {'by': 'line', 'direction': 'ascending', 'status': 'documented_fact',
                          'source': case.order['source']}
    assert case.order['source'].startswith('data/bank-names.txt:31')
    sample = c.load_case(fk.BANK)
    assert [v['name'] for v in case.document['variables']] == sample.column_names
    assert case.document['variables'] == sample.document['variables']
    flow = Flow(tmp_path / 'study', BANK_FULL)
    init = flow.init()
    final = init['final_test']
    # WP-B6a (review M2): the latest 9,042 lines less the 893 of them that are bank.csv
    # records (already exposed by the tutorial and any Bank study): 8,149 sealed rows.
    prior = set(c.prior_exposed_keys(case))
    assert len(prior) == 4521
    tail = [f'L{n}' for n in range(45212 - 9042 + 1, 45213)]           # the latest lines
    assert sum(k in prior for k in tail) == 893
    assert final['method'] == 'temporal' and final['rows'] == 8149
    assert final['excluded_prior_exposed'] == 893
    assert final['development_rows'] == 37062 and final['schema_check'] == 'pass'
    keys = fk.partition_keys(flow.study, 'final_test')
    assert keys == [k for k in tail if k not in prior]
    assert not prior & set(keys)                       # no bank.csv record is sealed
    assert prior <= set(fk.partition_keys(flow.study, 'development'))
    record = flow.state()['partition']['prior_exposed']
    assert record == {'path': 'data/prior-exposed-rows.txt',
                      'sha256': case.prior_exposed_rows['sha256'], 'declared_rows': 4521,
                      'excluded_rows': 893}
    card = flow.call('data', '--study', flow.study)
    assert card['development']['rows'] == 37062
    assert card['development']['duplicates']['n_groups'] == 0
    assert flow.view()['scenario_defaults']['capacity_share']['value'] == 0.1


@pytest.fixture(scope='module')
def shoppers(tmp_path_factory):
    """Online Shoppers to the policy evaluation, availability as the case states it
    (uncertain features included: a test choice, not a recommendation)."""
    flow = Flow(tmp_path_factory.mktemp('shop') / 'study', SHOPPERS, prefix='s')
    init = flow.init()
    out = {'init': init, 'card': flow.call('data', '--study', flow.study),
           'quality': flow.run('eda.quality')['values']}
    flow.pauses()
    out['split'] = flow.run('split')['values']
    out['signal'] = flow.run('eda.single_feature_signal')['values']
    flow.run('fit.baseline')
    out['fit'] = flow.run('fit.logistic')['values']
    out['policy'] = flow.run('policy.evaluate', '--rule', 'share:0.1', '--rule',
                             'share:0.2')['values']
    return flow, out


def test_online_shoppers_init_and_data_card(shoppers):
    flow, out = shoppers
    final = out['init']['final_test']
    assert final['method'] == 'stratified' and final['schema_check'] == 'pass'
    assert final['rows'] + final['development_rows'] == 12330
    groups = data.entity_groups(data.row_index(c.load_case(SHOPPERS)))
    dev = fk.partition_keys(flow.study, 'development')
    sealed = fk.partition_keys(flow.study, 'final_test')
    assert not {groups[k] for k in dev} & {groups[k] for k in sealed}
    record = flow.state()['partition']
    assert record['groups']['policy'] == 'group' and record['groups']['n_groups'] == 76
    card = out['card']
    assert card['development']['rows'] == final['development_rows']
    assert card['development']['duplicates']['policy'] == 'group'
    assert [g['group'] for g in card['groups']][-1] == 'Outcome'
    assert card['rows']['columns'][0] == 'Revenue'
    assert out['quality']['duplicates']['records']['n_groups'] \
        == card['development']['duplicates']['n_groups']
    assert set(partition.final_test_status(flow.state())) >= {'status', 'rows'}


def test_online_shoppers_runs_to_the_policy_with_gain_points(shoppers):
    flow, out = shoppers
    assert out['split']['duplicates']['divided_groups'] == 0
    flagged = [q['feature'] for q in out['signal']['questions']]
    assert flagged == ['PageValues']                       # the legitimacy question
    top = out['signal']['signals'][0]
    assert top['feature'] == 'PageValues' and top['score'] > 0.8
    auc = out['fit']['validation']['roc_auc']
    assert 0.85 < auc < 0.95
    gain = out['policy']['gain_points']
    assert [p['rule'] for p in gain['points']] == ['share:0.05', 'share:0.1', 'share:0.2']
    ten = gain['points'][1]
    entry = out['policy']['rules']['share:0.1']['models']['fit.logistic']
    assert ten['capacity'] == entry['capacity'] == round(0.1 * out['policy']['n'])
    assert ten['gain_points'] > 30 and ten['lift'] > 3


def test_adopting_the_default_share_names_the_exercise_assumption(shoppers, tmp_path):
    flow, _ = shoppers
    clone = Flow(fk.clone(flow.study, tmp_path / 'study'), SHOPPERS, prefix='a')
    clone.decide('policy', 'share:0.1',
                 words='Yes, I adopt this policy as stated, because the budget covers that many')
    ids = [x['id'] for x in clone.view()['not_yet_defensible']]
    assert 'capacity_assumed_for_exercise' in ids
    render = clone.call('render', '--study', clone.study)
    assert render['status'] == 'ok'
    report = (clone.study / 'reports' / 'study.html').read_text(encoding='utf-8')
    assert 'Select the 10% highest-scored rows' in report
    check = clone.call('check', '--study', clone.study)
    assert check['clean'] is True, check['findings']
