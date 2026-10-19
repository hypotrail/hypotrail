"""Capacity as a share of the scored rows (v0.2b, WP-B3, remark R6).

* the rule grammar ``share:p`` (``0 < p <= 1``, spelled like a threshold) and its
  evaluation as ``capacity:k`` with ``k = floor(p * n + 0.5)``;
* ``policy.gain_points``: the top 5, 10 and 20 % of the scored rows, registered in the
  policy evaluation;
* ``scenario_defaults.capacity_share`` in the case (a ``scenario_assumption`` only), shown
  by the view, and ``capacity_assumed_for_exercise`` when the adopted rule is that share.

Studies live in temporary directories on synthetic cases.
"""
from __future__ import annotations

import sys

import numpy as np
import pytest
import yaml

from mlkit.study import case as c, policy, records as rec

import flowkit as fk
from flowkit import Flow

sys.path.insert(0, str(fk.TESTS / 'fixtures' / 'synthetic'))
from make_case import make_case  # noqa: E402

DEFAULTS = {'capacity_share': {'value': 0.1, 'status': 'scenario_assumption',
                               'source': 'Teaching scenario: the team follows up one row in ten'}}


@pytest.mark.parametrize('raw, canonical', [
    ('share:0.1', 'share:0.1'), ('share:0.10', 'share:0.1'), (' share : 0.05 ', 'share:0.05'),
    ('share:1', 'share:1'), ('share:1.0', 'share:1'),
    ('share:0', None), ('share:1.5', None), ('share:-0.1', None), ('share:1e-1', None),
    ('share:10%', None), ('share:', None),
])
def test_the_share_rule_has_one_spelling(raw, canonical):
    assert rec.canonical_rule(raw) == canonical
    if canonical:
        assert rec.parse_rule(raw) == ('share', float(canonical.split(':')[1]))
        assert policy.parse_rule(raw)[0] == 'share'
    else:
        with pytest.raises(ValueError):
            policy.parse_rule(raw)


@pytest.mark.parametrize('p, n, k', [(0.1, 1000, 100), (0.1, 1005, 101), (0.1, 1004, 100),
                                     (0.05, 10, 1), (0.01, 10, 1), (1, 7, 7), (0.2, 0, 0)])
def test_share_capacity_rounds_half_up_and_selects_at_least_one_row(p, n, k):
    assert policy.share_capacity(p, n) == k


def test_a_share_is_evaluated_as_the_capacity_it_names():
    rng = np.random.default_rng(3)
    y = (rng.random(997) < 0.15).astype(float)
    score = rng.random(997) + 0.3 * y
    share = policy.evaluate(y, score, 'share:0.1')
    capacity = policy.evaluate(y, score, 'capacity:100')
    assert share['capacity'] == 100 and share['kind'] == 'share' and share['parameter'] == 0.1
    for key in ('selected', 'true_positives', 'precision', 'recall', 'tied_at_cut', 'selection'):
        assert share[key] == capacity[key]
    a = policy.paired_bootstrap(y, {'m': score}, 'share:0.1', 50, 1)
    b = policy.paired_bootstrap(y, {'m': score}, 'capacity:100', 50, 1)
    assert a['intervals'] == b['intervals']


def test_gain_points_at_five_ten_and_twenty_percent():
    y = np.array([1] * 10 + [0] * 90, dtype=float)
    score = np.linspace(1, 0, 100)                  # the ten positives score highest
    out = policy.gain_points(y, score)
    assert out['base_rate'] == 0.1 and out['n'] == 100 and out['n_positive'] == 10
    by = {p['rule']: p for p in out['points']}
    assert list(by) == ['share:0.05', 'share:0.1', 'share:0.2']
    assert by['share:0.05']['capacity'] == 5 and by['share:0.05']['precision'] == 1.0
    assert by['share:0.1']['gain_points'] == pytest.approx(90.0)
    assert by['share:0.1']['lift'] == pytest.approx(10.0) and by['share:0.1']['recall'] == 1.0
    assert by['share:0.2']['precision'] == 0.5 and by['share:0.2']['recall'] == 1.0
    flat = policy.gain_points(y, np.zeros(100))     # every row tied: the base rate, pro rata
    assert all(abs(p['gain_points']) < 1e-9 for p in flat['points'])


@pytest.mark.parametrize('value, path', [
    ({'capacity_share': {'value': 0.1, 'status': 'documented_fact', 'source': 'x'}},
     'scenario_defaults.capacity_share.status'),
    ({'capacity_share': {'value': 0, 'status': 'scenario_assumption', 'source': 'x'}},
     'scenario_defaults.capacity_share.value'),
    ({'capacity_share': {'value': 1.5, 'status': 'scenario_assumption', 'source': 'x'}},
     'scenario_defaults.capacity_share.value'),
    ({'budget': 3}, 'scenario_defaults.budget'),
    ({}, 'scenario_defaults'),
])
def test_scenario_defaults_are_validated(tmp_path, value, path):
    doc = yaml.safe_load(make_case(tmp_path / 'case', n_rows=200)['case'].read_text())
    doc['scenario_defaults'] = value
    assert path in {p['path'] for p in c.validate(doc)}


@pytest.fixture(scope='module')
def share_study(tmp_path_factory):
    root = tmp_path_factory.mktemp('share')
    paths = make_case(root / 'case', n_rows=2000, seed=11)
    doc = yaml.safe_load(paths['case'].read_text())
    doc['scenario_defaults'] = DEFAULTS
    paths['case'].write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True))
    flow = Flow(root / 'study', paths['case'].parent)
    flow.init()
    flow.pauses()
    flow.run('split')
    flow.run('fit.baseline')
    flow.run('fit.logistic')
    evaluation = flow.run('policy.evaluate', '--rule', 'share:0.10', '--rule', 'share:0.2')
    return flow, evaluation


def test_the_policy_evaluation_registers_gain_points_and_share_rules(share_study):
    flow, evaluation = share_study
    values = evaluation['values']
    assert set(values['rules']) == {'share:0.1', 'share:0.2'}
    n = values['n']
    entry = values['rules']['share:0.1']['models']['fit.logistic']
    assert entry['capacity'] == policy.share_capacity(0.1, n)
    gain = values['gain_points']
    assert gain['model'] == 'fit.logistic' and gain['n'] == n
    assert [p['share'] for p in gain['points']] == [0.05, 0.1, 0.2]
    ten = gain['points'][1]
    assert ten['precision'] == pytest.approx(entry['precision'])
    assert ten['gain_points'] == pytest.approx(100 * (entry['precision'] - gain['base_rate']))


def test_the_view_shows_the_default_and_the_assumed_capacity_is_a_limit(share_study, tmp_path):
    flow, _ = share_study
    view = flow.view()
    assert view['scenario_defaults'] == DEFAULTS
    assert 'capacity_assumed_for_exercise' not in [x['id'] for x in view['not_yet_defensible']]
    clone = Flow(fk.clone(flow.study, tmp_path / 'study'), flow.case_dir, prefix='k')
    clone.decide('policy', 'share:0.1',
                 words='Yes, I adopt this policy as stated, because the team can follow up that many')
    limits = {x['id']: x for x in clone.view()['not_yet_defensible']}
    item = limits['capacity_assumed_for_exercise']
    assert item['rule'] == 'share:0.1' and item['share'] == 0.1
    assert item['audience'] == 'junior' and 'top 10%' in item['text']
    summary = clone.call('status', '--summary', '--study', clone.study)
    listed = [x['id'] for x in summary['not_yet_defensible']['top']] \
        + summary['not_yet_defensible']['more']
    assert 'capacity_assumed_for_exercise' in listed


def test_another_share_is_not_the_exercise_assumption(share_study, tmp_path):
    flow, _ = share_study
    clone = Flow(fk.clone(flow.study, tmp_path / 'study'), flow.case_dir, prefix='j')
    clone.decide('policy', 'share:0.2',
                 words='Yes, I adopt this policy as stated, because our team said it can call that many')
    ids = [x['id'] for x in clone.view()['not_yet_defensible']]
    assert 'capacity_assumed_for_exercise' not in ids


def test_a_case_without_defaults_shows_none(tmp_path):
    flow = Flow(tmp_path / 'study', fk.BANK)
    flow.init()
    assert flow.view()['scenario_defaults'] is None
