"""WP-B1 integrated with WP-B2 (confirmation modes) and WP-B3 (cases, duplicate groups,
``share:p`` rules).

* folds never divide a group of identical records (``duplicates: {policy: group}``),
  stratified or temporal;
* a ``share:p`` rule keeps its share on the out-of-fold policy evaluation and on the final
  test, and the gain points are computed on the out-of-fold predictions;
* ``model_variant`` and ``final_test`` fall back to the generic restatement concept in the
  training mode, and no standing delegation (express included) covers them;
* Online Shoppers (stratified grouped folds, a share rule) and Bank Marketing full (temporal
  folds on the file order) run end to end: cross-validation, the variant, the opening.

Studies live in temporary directories; the committed cases are only read.
"""
from __future__ import annotations

import json

import numpy as np
import pytest

from mlkit.study import activities as act, case as c, concepts, data as dt, policy, registry
from mlkit.study import state as st, store as sto

import flowkit as fk
from flowkit import Flow

SHOPPERS = fk.REPO / 'use-cases' / 'online-shoppers'
BANK_FULL = fk.REPO / 'use-cases' / 'bank-marketing-full'
OPEN_WORDS = 'Yes, I open the sealed final test now, because the model and the rule are fixed'
STANDING = "for questions I can't answer, use your recommended default"


def _propose(flow, decision, value, restatement):
    return flow.call('decide', 'propose', decision, '--value-json', json.dumps(value),
                     '--restatement', restatement, '--rationale', 'It fits the scenario.',
                     '--request-id', flow.rid(), '--expected-revision', flow.rev(),
                     '--study', flow.study)['result']['proposal_id']


def _confirm(flow, pid, words, *extra, expect=0):
    return flow.call('decide', 'confirm', pid, '--user-words', words, *extra, '--request-id',
                     flow.rid(), '--expected-revision', flow.rev(), '--study', flow.study,
                     expect=expect)


def _mode(flow, mode, words=None):
    extra = ('--user-words', words) if words is not None else ()
    return flow.call('mode', 'set', mode, *extra, '--request-id', flow.rid(),
                     '--expected-revision', flow.rev(), '--study', flow.study)


def _open(flow):
    """Confirm the opening; the partition's opening record."""
    value = st.b1_default_value(flow.state(), 'final_test')
    pid = _propose(flow, 'final_test', value, 'You open the sealed final test once, for the '
                                              'chosen configuration.')
    result = _confirm(flow, pid, OPEN_WORDS)['result']
    assert result['opening']['status'] == 'promoted', result['opening']
    record = flow.state()['partition']['opening']
    assert record['result_id'] == result['opening']['result_id']
    return record


def _values(flow, slot):
    store = sto.StudyStore(flow.study)
    return registry.get(store, flow.state()['current'][slot])['output']['values']


def _folds(flow):
    store = sto.StudyStore(flow.study)
    return act.fold_assignment(store, flow.state()['current']['split'])


# --- fold assignment with groups (pure) ------------------------------------------------------

def test_temporal_folds_move_a_divided_group_to_the_fold_of_its_earliest_row():
    order = np.arange(10)
    groups = ['a', 'b', 'c', 'd', 'e', 'b', 'g', 'h', 'i', 'j']     # 'b' at positions 1 and 5
    plain = act.assign_folds(10, 2, order=order)
    assert plain.tolist() == [1] * 5 + [2] * 5                       # 'b' would straddle
    grouped = act.assign_folds(10, 2, order=order, groups=groups)
    assert grouped.tolist() == [1] * 6 + [2] * 4                     # its copy moves to fold 1
    # The earliest is by time order, not by position.
    reverse = act.assign_folds(10, 2, order=order[::-1], groups=groups)
    assert reverse[1] == reverse[5] == 1 and reverse.tolist().count(1) == 6


def test_stratified_folds_keep_a_group_in_one_fold():
    rng = np.random.default_rng(3)
    groups = [f'g{i // 3}' for i in range(300)]                    # triples of copies
    strata = [int(g[1:]) % 4 == 0 for g in groups]                   # a group shares its stratum
    fold = act.assign_folds(300, 5, seed=int(rng.integers(1000)), strata=strata, groups=groups)
    by_group = {}
    for g, f in zip(groups, fold):
        by_group.setdefault(g, set()).add(int(f))
    assert all(len(f) == 1 for f in by_group.values())
    assert sorted(set(fold.tolist())) == [1, 2, 3, 4, 5]


# --- share rules on out-of-fold predictions and on the final test ------------------------------

def test_a_share_rule_is_a_share_on_any_rows():
    from mlkit.study import records as rec
    assert rec.share_of('share:0.1') == 0.1 and rec.share_of('share:0.1@fit.variant') == 0.1
    assert rec.share_of('capacity:10') is None and rec.capacity_of('share:0.1') is None
    assert rec.capacity_share('share:0.25', 999) == 0.25
    assert rec.capacity_share('capacity:25', 1000) == 0.025
    assert rec.capacity_share('threshold:0.3', 1000) is None


# --- WP-B2 modes: the generic concept, never a standing delegation -----------------------------

@pytest.fixture
def chosen(tmp_path):
    """A synthetic binary study with cross-validation, a variant fitted and a policy chosen;
    the final test and the variant decision are left to the test."""
    case_dir = fk.make_case(tmp_path / 'case', task='binary', n_rows=600)['case'].parent
    flow = Flow(tmp_path / 'study', case_dir)
    flow.init()
    flow.decide('prediction_time', 'when the record is created, before the outcome')
    flow.decide('feature_availability', fk.availability(case_dir))
    flow.decide('split', st.b1_default_value(flow.state(), 'split'))
    flow.model_decisions()
    flow.run('split')
    flow.run('fit.baseline')
    flow.run('fit.logistic')
    return flow


def test_new_decisions_have_no_concept_map_and_no_standing_delegation(chosen):
    state = chosen.state()
    for decision, value in (('model_variant', dict(fk.VARIANT)),
                            ('final_test', {'model': 'fit.logistic', 'rule': 'capacity:40'})):
        proposal = {'proposal_id': 'p_1', 'decision_id': decision, 'value': value,
                    'restatement': 'You decide as stated.'}
        assert concepts.concept_map(state, proposal) == [{'concept': 'restatement'}]
        assert decision not in st.STANDING_DELEGATION_DECISIONS
        assert decision not in st.EXPRESS_STANDING_DELEGATION_DECISIONS


def test_training_mode_asks_a_restatement_of_the_variant_and_a_reason_for_the_opening(chosen):
    flow = chosen
    _mode(flow, 'training')
    pid = _propose(flow, 'model_variant', dict(fk.VARIANT),
                   'You compare the candidate with a strongly regularised variant.')
    out = _confirm(flow, pid, 'oui je confirme cela', expect=2)
    assert out['error']['code'] == 'paraphrase_required'
    assert [m['concept'] for m in out['error']['details']['missing']] == ['restatement']
    done = _confirm(flow, pid, 'I compare the candidate with a strongly regularised variant')
    assert done['result']['mode'] == 'training' and done['result']['basis'] == st.RESTATED
    flow.run('fit.variant')
    flow.run('policy.evaluate', '--rule', 'capacity:40')
    flow.decide('policy', 'capacity:40',
                words='I adopt capacity 40 because the desk can make 40 calls')
    value = st.b1_default_value(flow.state(), 'final_test')
    pid = _propose(flow, 'final_test', value,
                   'You open the sealed final test once, for the chosen configuration.')
    rev = flow.rev()
    out = _confirm(flow, pid, 'I open the sealed final test once', expect=2)
    assert out['error']['code'] == 'reason_required' and out['error']['details']['mode'] == \
        'training'
    assert out['error']['details']['decision_id'] == 'final_test'
    assert flow.rev() == rev and flow.state()['partition']['status'] == 'sealed'
    done = _confirm(flow, pid, OPEN_WORDS)
    assert done['result']['mode'] == 'training' and done['result']['opening'] is not None
    assert flow.state()['partition']['status'] == 'opened'


def test_express_never_delegates_the_variant_or_the_opening(chosen):
    flow = chosen
    _mode(flow, 'express', 'on passe en mode express')
    pid = _propose(flow, 'model_variant', dict(fk.VARIANT),
                   'My recommended default: a strongly regularised variant.')
    out = _confirm(flow, pid, STANDING, '--basis', 'delegated_default', '--delegation-scope',
                   'standing', expect=2)
    assert out['error']['details']['reason'] == 'delegation_not_given_at_this_pause'
    assert out['error']['details']['mode'] == 'express'
    assert 'model_variant' not in out['error']['details']['standing_covers']
    _confirm(flow, pid, 'yes, the strongly regularised variant')
    flow.run('fit.variant')
    flow.run('policy.evaluate', '--rule', 'capacity:40')
    flow.decide('policy', 'capacity:40',
                words='I adopt capacity 40 because the desk can make 40 calls')
    value = st.b1_default_value(flow.state(), 'final_test')
    pid = _propose(flow, 'final_test', value,
                   'My recommended default: you open the sealed final test once.')
    for scope in ('standing', 'this_decision'):
        out = _confirm(flow, pid, STANDING, '--basis', 'delegated_default',
                       '--delegation-scope', scope, expect=2)
        assert out['error']['code'] == 'reason_required'
        assert out['error']['details']['mode'] == 'express'
    assert flow.state()['partition']['status'] == 'sealed'
    # Express keeps the guided reason rule for the junior's own words.
    out = _confirm(flow, pid, 'oui je confirme cela', expect=2)
    assert out['error']['code'] == 'reason_required'
    assert _confirm(flow, pid, OPEN_WORDS)['result']['mode'] == 'express'


# --- the v0.2b cases end to end --------------------------------------------------------------

def _entity_groups(case_dir):
    return dt.entity_groups(dt.row_index(c.load_case(case_dir)))


def test_online_shoppers_end_to_end_with_grouped_folds_a_share_and_the_opening(tmp_path):
    flow = Flow(tmp_path / 'study', SHOPPERS, prefix='s')
    flow.init()
    flow.pauses(split=False)
    split = st.b1_default_value(flow.state(), 'split')
    assert split['method'] == 'kfold_stratified'
    flow.decide('split', split)
    flow.model_decisions()
    values = flow.run('split')['values']
    # Identical records never straddle folds.
    assert values['implementation'] == act.GROUPED_FOLDS_IMPLEMENTATION
    assert values['duplicates']['policy'] == 'group'
    assert values['duplicates']['divided_groups'] == 0 and values['duplicates']['n_groups'] > 0
    folds, groups = _folds(flow), _entity_groups(SHOPPERS)
    by_group = {}
    for key, fold in folds.items():
        by_group.setdefault(groups[key], set()).add(fold)
    copies = {g for g in by_group if sum(groups[k] == g for k in folds) > 1}
    assert copies and all(len(by_group[g]) == 1 for g in by_group)
    # The candidate and the variant out of fold, then share rules on every development row.
    flow.run('fit.baseline')
    fit_values = flow.run('fit.logistic')['values']
    assert fit_values['evaluation'] == 'out_of_fold'
    assert fit_values['cross_validation']['folds'] == split['folds']
    flow.variant()
    out = flow.run('policy.evaluate', '--rule', 'share:0.1', '--rule', 'share:0.2')['values']
    n_dev = len(folds)
    assert out['evaluation'] == 'out_of_fold' and out['n'] == n_dev
    for rule, p in (('share:0.1', 0.1), ('share:0.2', 0.2)):
        entry = out['rules'][rule]
        assert entry['capacity_share'] == p
        assert entry['models']['fit.logistic']['capacity'] == policy.share_capacity(p, n_dev)
        assert entry['comparisons']['fit.variant']['reference'] == 'fit.logistic'
    # The gain points are computed on the out-of-fold predictions of every development row.
    gain = out['gain_points']
    assert gain['n'] == n_dev and gain['model'] == 'fit.logistic'
    assert gain['points'][1]['capacity'] == out['rules']['share:0.1']['models'][
        'fit.logistic']['capacity']
    flow.decide('policy', 'share:0.1',
                words='Yes, I adopt this policy as stated, because the budget covers that many')
    opening = _open(flow)
    assert opening['rule'] == 'share:0.1' and opening['model'] == 'fit.logistic'
    final = _values(flow, 'final_test.evaluation')
    n_final = flow.state()['partition']['final_test']['n_rows']
    assert final['n'] == n_final and final['rule_final'] == 'share:0.1'
    assert final['capacity_share'] == 0.1                # the share is kept as it is
    assert final['models']['fit.logistic']['capacity'] == policy.share_capacity(0.1, n_final)
    assert final['refit']['n_rows'] == n_dev
    assert flow.state()['partition']['status'] == 'opened'
    assert flow.call('check', '--study', flow.study)['clean'] is True


def test_bank_full_end_to_end_with_temporal_folds_on_the_file_order(tmp_path):
    flow = Flow(tmp_path / 'study', BANK_FULL, prefix='b')
    flow.init()
    flow.pauses(split=False)
    split = st.b1_default_value(flow.state(), 'split')
    assert split['method'] == 'temporal_folds'
    split['folds'] = 3                             # fewer fits on 37,062 rows; still k-fold
    flow.decide('split', split)
    flow.model_decisions()
    values = flow.run('split')['values']
    assert values['order_column'] == 'line' and values['seed'] is None
    folds = _folds(flow)
    lines = sorted((int(k[1:]), f) for k, f in folds.items())
    assert [f for _, f in lines] == sorted(f for _, f in lines)     # contiguous, in file order
    assert {f for _, f in lines} == {1, 2, 3} and len(lines) == 37062   # WP-B6a: + 893
    flow.run('fit.baseline')
    assert flow.run('fit.logistic')['values']['cross_validation']['method'] == 'temporal_folds'
    flow.variant()
    out = flow.run('policy.evaluate', '--rule', 'capacity:500')['values']
    assert out['evaluation'] == 'out_of_fold' and out['n'] == 37062
    assert out['rules']['capacity:500']['capacity_share'] == 500 / 37062
    assert out['gain_points']['n'] == 37062
    flow.decide('policy', 'capacity:500',
                words='Yes, I adopt that rule because the desk can make that many calls')
    opening = _open(flow)
    assert opening['rule'] == 'capacity:500'
    final = _values(flow, 'final_test.evaluation')
    assert final['n'] == 8149 and final['refit']['n_rows'] == 37062
    k = max(1, int(np.floor(500 / 37062 * 8149 + 0.5)))
    assert final['rule_final'] == f'capacity:{k}'
    assert flow.call('check', '--study', flow.study)['clean'] is True
