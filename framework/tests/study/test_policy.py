"""Pure policy evaluation, ties, paired bootstrap, re-policy without refit (plan WP2.4).

Hand-made cases pin the tie rule. The study flows run on Bank and on the synthetic
case. ``test_capacity_change_no_refit`` is the structural answer to trap T6 of the E1
steelman (``docs/research/runs/E1-arm-A-2026-10-18.md``): every arm-A run said "no
retraining" and refitted. Studies live in ``tmp_path``.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from mlkit import decision
from mlkit.study import dependencies as dep, policy, read
from mlkit.study import cmd_preview

import flowkit as fk
from flowkit import Flow


# --- pure evaluation ----------------------------------------------------------------------

Y = [1, 0, 1, 1, 0]
S = [0.9, 0.8, 0.8, 0.8, 0.1]


def test_capacity_inside_a_tie_group_prorates_the_group():
    r = policy.evaluate(Y, S, 'capacity:2')
    assert r['selected'] == 2.0 and r['selection'] == 'expected'
    assert r['tied_at_cut'] == 3
    assert r['cut'] == {'score': 0.8, 'n_tied': 3, 'fraction_selected': pytest.approx(1 / 3)}
    assert r['true_positives'] == pytest.approx(1 + 2 / 3)       # the 0.9 row + 1/3 of two
    assert r['false_positives'] == pytest.approx(1 / 3)
    assert r['precision'] == pytest.approx((5 / 3) / 2)
    assert r['recall'] == pytest.approx((5 / 3) / 3)
    assert r['volume_rate'] == pytest.approx(2 / 5)


def test_capacity_on_a_group_boundary_has_no_tie_at_the_cut():
    r = policy.evaluate(Y, S, 'capacity:4')
    assert (r['selected'], r['true_positives'], r['tied_at_cut']) == (4.0, 3.0, 0)
    assert r['selection'] == 'exact' and r['cut']['score'] is None
    everything = policy.evaluate(Y, S, 'capacity:50')                # k > n selects all
    assert (everything['selected'], everything['recall']) == (5.0, 1.0)


def test_threshold_is_inclusive_and_counts_rows_at_the_threshold():
    r = policy.evaluate(Y, S, 'threshold:0.8')
    assert (r['selected'], r['true_positives'], r['tied_at_cut']) == (4.0, 3.0, 3)
    assert r['selection'] == 'exact'
    assert policy.evaluate(Y, S, 'threshold:0.81')['selected'] == 1.0
    none = policy.evaluate(Y, S, 'threshold:0.95')
    assert none['selected'] == 0.0 and none['precision'] is None and none['recall'] == 0.0


def test_constant_score_capacity_precision_is_the_base_rate():
    y = np.array([1] * 13 + [0] * 87)
    r = policy.evaluate(y, np.full(100, 0.13), 'capacity:10')
    assert r['selected'] == 10.0 and r['tied_at_cut'] == 100
    assert r['precision'] == pytest.approx(0.13, abs=1e-15)


@pytest.mark.parametrize('seed', range(5))
def test_capacity_weights_equal_decision_accept_weights(seed):
    rng = np.random.default_rng(seed)
    s = np.round(rng.random(200), 1)                    # many ties
    for k in (1, 7, 50, 199, 200):
        mine, _ = policy.capacity_weights(s, k)
        theirs = decision.accept_weights(-s, k / len(s))
        assert np.allclose(mine, theirs, atol=1e-12, rtol=0)
        assert mine.sum() == pytest.approx(k, abs=1e-9)


@pytest.mark.parametrize('rule', ['threshold:0', 'threshold:1', 'threshold:0.35', 'capacity:1',
                                  'capacity:100', 'threshold:1.5', 'capacity:0', 'cap:3',
                                  'threshold:x', 'capacity:2.5', 7])
def test_rule_grammar_equals_the_decision_grammar(rule):
    expected = dep.parse_policy(rule)
    if expected is None:
        with pytest.raises(ValueError):
            policy.parse_rule(rule)
    else:
        assert policy.parse_rule(rule) == expected


def test_paired_bootstrap_is_deterministic_and_paired():
    rng = np.random.default_rng(1)
    y = (rng.random(400) < 0.15).astype(int)
    a, b = rng.random(400), rng.random(400) + 0.3 * y
    first = policy.paired_bootstrap(y, {'a': a, 'b': b}, 'capacity:40', 300, 5)
    assert first == policy.paired_bootstrap(y, {'a': a, 'b': b}, 'capacity:40', 300, 5)
    other = policy.paired_bootstrap(y, {'a': a, 'b': b}, 'capacity:40', 300, 6)
    assert other['intervals'] != first['intervals']
    same = policy.paired_bootstrap(y, {'a': a, 'twin': a.copy()}, 'threshold:0.5', 300, 5)
    for m in policy.METRICS:                            # shared resamples: zero difference
        d = same['deltas']['twin'][m]
        assert (d['low'], d['high'], d['point']) == (0.0, 0.0, 0.0)
    assert first['intervals']['a']['volume'] == {'low': 40.0, 'high': 40.0,
                                                 'undefined_replicates': 0}
    lo, hi = first['intervals']['b']['precision']['low'], first['intervals']['b']['precision']['high']
    point = policy.evaluate(y, b, 'capacity:40')['precision']
    assert lo <= point <= hi


def test_bootstrap_reports_undefined_precision_instead_of_nan():
    y = np.array([0, 1] * 50)
    out = policy.paired_bootstrap(y, {'c': np.zeros(100)}, 'threshold:0.5', 50, 1)
    assert out['intervals']['c']['precision'] == {'low': None, 'high': None,
                                                  'undefined_replicates': 50}


# --- study flows ----------------------------------------------------------------------------

@pytest.fixture(scope='module')
def cases(tmp_path_factory):
    return {'bank': fk.BANK,
            'synthetic': fk.make_case(tmp_path_factory.mktemp('synthetic'),
                                      n_rows=4000)['case'].parent}


@pytest.fixture(scope='module')
def prepared(tmp_path_factory, cases):
    return {name: fk.prepare(path, tmp_path_factory.mktemp(name) / 'study', upto='fits')
            for name, path in cases.items()}


@pytest.fixture(params=['bank', 'synthetic'])
def flow(request, tmp_path, prepared, cases):
    f = Flow(fk.clone(prepared[request.param], tmp_path / 'study'), cases[request.param])
    f.name = request.param
    return f


def _fit_footprint(study):
    s = read.open(study)
    fits = [e for e in fk.registry_entries(study) if e['activity'].startswith('fit.')]
    return (sorted(e['result_id'] for e in fits),
            {slot: s.state['current'][slot] for slot in ('fit.baseline', 'fit.logistic')},
            {slot: s.current(slot)['blobs']['predictions'] for slot in ('fit.baseline', 'fit.logistic')},
            [r for r in s.exposure_records() if r['purpose'] == 'train_fit'])


def test_capacity_change_no_refit(flow):
    first = flow.run('policy.evaluate', '--rule', 'threshold:0.5')
    footprint = _fit_footprint(flow.study)
    flow.decide('policy', 'threshold:0.5', words='Yes, call everyone scored at 0.5 or more')
    second = flow.run('policy.evaluate', '--rule', 'capacity:100')
    assert second['status'] == 'promoted' and second['result_id'] != first['result_id']
    assert second['values']['predictions'] == footprint[1]
    flow.decide('policy', 'capacity:100', words='Yes, we can call only 100 people, take the top')
    third = flow.run('policy.evaluate', '--rule', 'capacity:50')
    flow.decide('policy', 'capacity:50', words='Yes, fifty calls is the real budget')
    assert _fit_footprint(flow.study) == footprint       # no fit entry, same predictions
    state = flow.state()
    assert all(state['current'][s] not in state['stale'] for s in ('fit.baseline', 'fit.logistic'))
    mutations = [i['mutation'] for i in state['invalidations']]
    assert mutations[-2:] == ['policy.rule_type', 'policy.parameter']
    assert state['decisions']['policy']['value'] == 'capacity:50'
    assert third['values']['rules']['capacity:50']['models']['fit.logistic']['selected'] == 50.0
    selection = [r for r in fk.exposure_records(flow.study)
                 if r['purpose'] == 'validation_policy_selection']
    assert [r['result_id'] for r in selection] == [first['result_id'], second['result_id'],
                                                   third['result_id']]
    assert all(r['partition'] == 'validation' for r in selection)


def test_a_new_evaluation_keeps_the_adopted_rule(flow):
    """An evaluation replaces the current one in its slot. Evaluating only capacity:100 after
    threshold:0.5 was adopted must not drop the adopted rule's evaluation (S8)."""
    flow.run('policy.evaluate', '--rule', 'threshold:0.5')
    flow.decide('policy', 'threshold:0.5', words='Yes, call everyone scored at 0.5 or more')
    out = flow.run('policy.evaluate', '--rule', 'capacity:100')
    assert out['status'] == 'promoted'
    assert set(out['values']['rules']) == {'capacity:100', 'threshold:0.5'}
    assert read.open(flow.study).current('policy.evaluation')['params']['rules'] == [
        'capacity:100', 'threshold:0.5']
    view = flow.view()
    assert view['decisions']['policy']['status'] == 'confirmed'
    assert 'adopted_rule_not_evaluated' not in {x['id'] for x in view['not_yet_defensible']}
    again = flow.run('policy.evaluate', '--rule', 'capacity:100', '--rule', 'threshold:0.5')
    assert again['status'] == 'already_current'          # same rules, same identity


def test_an_adopted_rule_without_a_current_evaluation_is_not_yet_defensible():
    from mlkit.study import view as view_model
    state = {'decisions': {'policy': {'status': 'confirmed', 'value': 'capacity:100'}}}
    current = {'current': True, 'integrity': 'ok', 'params': {'rules': ['capacity:100']}}
    assert view_model._adopted_without_evaluation(state, {'policy.evaluation': current}) is None
    other = {**current, 'params': {'rules': ['threshold:0.2']}}
    assert view_model._adopted_without_evaluation(state, {'policy.evaluation': other}) == \
        'capacity:100'
    stale = {**current, 'current': False}
    assert view_model._adopted_without_evaluation(state, {'policy.evaluation': stale}) == \
        'capacity:100'
    assert view_model._adopted_without_evaluation(state, {}) == 'capacity:100'
    proposed = {'decisions': {'policy': {'status': 'proposed', 'value': 'capacity:100'}}}
    assert view_model._adopted_without_evaluation(proposed, {}) is None


def test_policy_evaluation_values_and_ties(flow):
    out = flow.run('policy.evaluate', '--rule', 'capacity:100', '--rule', 'threshold:0.5')
    values = out['values']
    assert read.open(flow.study).current('policy.evaluation')['params']['rules'] == [
        'capacity:100', 'threshold:0.5']
    base = values['rules']['capacity:100']['models']['fit.baseline']
    rate = values['n_positive'] / values['n']
    assert base['precision'] == pytest.approx(rate, rel=1e-12)       # constant prior
    assert base['tied_at_cut'] == values['n'] and base['selected'] == 100.0
    assert base['cut']['fraction_selected'] == pytest.approx(100 / values['n'])
    logistic = values['rules']['capacity:100']['models']['fit.logistic']
    assert logistic['selected'] == 100.0
    delta = values['rules']['capacity:100']['deltas']['fit.logistic']
    assert delta['precision']['point'] == pytest.approx(logistic['precision'] - base['precision'])
    assert values['bootstrap'] == {'replicates': 2000, 'seed': 20261017, 'level': 0.95,
                                   'method': 'paired percentile bootstrap over validation rows'}
    if flow.name == 'bank':
        assert (values['n'], values['n_positive']) == (1357, 156)


def test_recall_interval_width_is_consistent_with_the_binomial_approximation(flow):
    values = flow.run('policy.evaluate', '--rule', 'threshold:0.5')['values']
    r = values['rules']['threshold:0.5']
    p = r['models']['fit.logistic']['recall']
    interval = r['intervals']['fit.logistic']['recall']
    half = (interval['high'] - interval['low']) / 2
    expected = 1.959964 * math.sqrt(p * (1 - p) / values['n_positive'])
    assert 0.8 < half / expected < 1.25, (half, expected)
    if flow.name == 'bank':
        assert values['n_positive'] == 156


def test_policy_evaluation_needs_both_fits_and_a_rule(tmp_path, cases):
    flow = Flow(fk.prepare(cases['synthetic'], tmp_path / 'study', upto='split'),
                cases['synthetic'], prefix='p')
    flow.run('fit.baseline')
    payload = flow.run('policy.evaluate', '--rule', 'capacity:10', expect=2)
    assert payload['error']['code'] == 'precondition_missing'
    assert {'requirement': 'result_current', 'slot': 'fit.logistic'} in \
        payload['error']['details']['missing']
    flow.run('fit.logistic')
    assert flow.run('policy.evaluate', expect=2)['error']['code'] == 'invalid_arguments'
    assert flow.run('policy.evaluate', '--rule', 'capacity:0',
                    expect=2)['error']['code'] == 'invalid_arguments'


def test_preview_writes_nothing_and_matches_the_recorded_evaluation(flow, monkeypatch):
    before = fk.tree_digest(flow.study)
    monkeypatch.setenv('HYPOTRAIL_READ_ONLY', '1')
    preview = flow.call('preview', 'policy', '--rule', 'capacity:100', '--intervals',
                        '--study', flow.study)
    monkeypatch.delenv('HYPOTRAIL_READ_ONLY')
    assert fk.tree_digest(flow.study) == before
    assert tuple(preview) == cmd_preview.PAYLOAD_KEYS and preview['schema'] == 'hypotrail.preview/1'
    assert preview['recorded'] is False and 'Experiment, not adopted' in preview['note']
    recorded = flow.run('policy.evaluate', '--rule', 'capacity:100')['values']['rules']['capacity:100']
    assert preview['evaluations']['capacity:100'] == recorded['models']
    assert preview['intervals']['capacity:100']['intervals'] == recorded['intervals']
    assert preview['adopted'] == {'status': 'open', 'value': None}
    fast = flow.call('preview', 'policy', '--rule', 'threshold:0.2', '--study', flow.study)
    assert fast['intervals'] is None
    assert flow.call('preview', 'policy', '--rule', 'nope', '--study', flow.study,
                     expect=2)['error']['code'] == 'invalid_arguments'


def test_preview_and_policy_modules_never_write():
    from test_read_view import write_violations
    for module in (policy, cmd_preview):
        source = open(module.__file__, encoding='utf-8').read()
        found = [v for v in write_violations(source) if 'import commands' not in v]
        assert not found, (module.__name__, found)
