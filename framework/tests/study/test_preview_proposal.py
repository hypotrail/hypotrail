"""``preview proposal`` (CLI-CONTRACT-COMPANION §4, C4; WP-E3).

Real cases: the committed Bank case (policy drafts of an evaluated capacity and an
evaluated threshold, and an unevaluated capacity) and the committed Auto MPG case (model
choice drafts of both models). Every proposable draft is proposed on a temporary copy of
the study and must be accepted by ``decide propose`` as written; every draft is clean
under ``check --text``. Studies live in ``tmp_path``.
"""
from __future__ import annotations

import re

import pytest

from mlkit.study import cmd_check, preview_proposal as pp, read

import companion_contract as cc
import flowkit as fk

AUTO = fk.REPO / 'use-cases' / 'auto-mpg'
BANK_RULES = ('capacity:100', 'threshold:0.3')
BINARY_VOCABULARY = re.compile(r'threshold|positive class|precision|recall|capacity', re.I)


@pytest.fixture(scope='module')
def bank(tmp_path_factory):
    study = fk.prepare(fk.BANK, tmp_path_factory.mktemp('bank') / 'study', upto='fits')
    flow = fk.Flow(study, fk.BANK, prefix='b')
    flow.run('policy.evaluate', *[x for r in BANK_RULES for x in ('--rule', r)])
    return flow


@pytest.fixture(scope='module')
def auto(tmp_path_factory):
    flow = fk.Flow(tmp_path_factory.mktemp('auto') / 'study', AUTO, prefix='a')
    flow.init()
    flow.pauses(split=False)
    flow.decide('split', {'method': 'ordinal_cutoff', 'column': 'model_year', 'cutoff': 79})
    flow.model_decisions()          # WP-A4: success criterion and default preprocessing
    for activity in ('split', 'fit.baseline', 'fit.linear', 'evaluate.regression'):
        flow.run(activity)
    return flow


def _draft(flow, decision, value):
    return flow.call('preview', 'proposal', decision, '--value', value, '--study', flow.study)


def _propose_on_a_copy(flow, tmp_path, draft):
    copy = fk.Flow(fk.clone(flow.study, tmp_path / 'copy'), flow.case_dir, prefix='c')
    before = copy.rev()
    return copy.call('decide', 'propose', draft['decision_id'], f'--value={draft["value"]}',
                     f'--restatement={draft["restatement"]}',
                     f'--rationale={draft["rationale"]}', '--request-id', copy.rid(),
                     '--expected-revision', before, '--study', copy.study)


def _clean(flow, text):
    report = cmd_check.run_check(flow.study, text)
    assert report['clean'] and report['findings'] == [], report['findings']
    return report


@pytest.mark.parametrize('rule', BANK_RULES)
def test_bank_drafts_of_evaluated_rules_are_proposable_as_written(bank, rule, tmp_path):
    before = cc.study_tree_digest(bank.study)
    draft = _draft(bank, 'policy', rule)
    assert cc.study_tree_digest(bank.study) == before
    assert tuple(draft) == cc.DRAFT_KEYS and draft['proposable'] is True
    evaluation = read.open(bank.study).current('policy.evaluation')
    assert draft['evidence']['result_id'] == evaluation['result_id']
    assert draft['evidence']['activity'] == 'policy.evaluation'
    values = evaluation['output']['values']
    logistic = values['rules'][rule]['models']['fit.logistic']
    figures = {f['path']: f for f in draft['evidence']['figures']}
    precision = figures[f'rules.{rule}.models.[fit.logistic].precision'
                        if '.' not in rule else
                        f'rules.[{rule}].models.[fit.logistic].precision']
    assert precision['value'] == logistic['precision']
    assert precision['shown'] in draft['restatement']
    assert f'{values["n"]:,}' in draft['restatement']
    assert draft['restatement'].startswith(f'Adopt the rule {rule}: ')
    assert 'optimistic' in draft['restatement']
    assert pp.short_id(evaluation['result_id']) in draft['rationale']
    assert 'recommended default' not in draft['restatement'] + draft['rationale']
    _clean(bank, draft['restatement'])
    _clean(bank, draft['rationale'])
    proposed = _propose_on_a_copy(bank, tmp_path, draft)
    assert proposed['ok'] is True and proposed['result']['status'] == 'open', proposed


def test_bank_threshold_draft_states_the_selected_count(bank):
    draft = _draft(bank, 'policy', 'threshold:0.30')        # canonicalised
    assert draft['value'] == 'threshold:0.3'
    selected = read.open(bank.study).current('policy.evaluation')['output']['values'][
        'rules']['threshold:0.3']['models']['fit.logistic']['selected']
    assert f'selected {round(selected):,} rows' in draft['restatement']


def test_bank_unevaluated_capacity_is_not_proposable(bank):
    draft = _draft(bank, 'policy', 'capacity:150')
    assert draft['proposable'] is False and draft['evidence'] is None
    assert draft['missing'] == [{'requirement': 'evaluated_rule', 'value': 'capacity:150'}]
    assert draft['restatement'] is None and draft['rationale'] is None
    assert draft['supersedes_proposal'] is None and draft['recorded'] is False


@pytest.mark.parametrize('model', ('fit.linear', 'fit.baseline'))
def test_auto_mpg_model_choice_drafts_cite_the_evaluation(auto, model, tmp_path):
    draft = _draft(auto, 'model_choice', model)
    assert draft['proposable'] is True and draft['missing'] == []
    evaluation = read.open(auto.study).current('evaluate.regression')
    values = evaluation['output']['values']
    assert draft['evidence']['result_id'] == evaluation['result_id']
    mae = f'{values["models"]["fit.linear"]["mae"]:.2f}'
    baseline = f'{values["models"]["fit.baseline"]["mae"]:.2f}'
    assert mae in draft['restatement'] and baseline in draft['restatement']
    first = baseline if model == 'fit.baseline' else mae
    assert f'mean absolute error is {first} mpg' in draft['restatement']
    assert not BINARY_VOCABULARY.search(draft['restatement'] + draft['rationale'])
    _clean(auto, draft['restatement'])
    proposed = _propose_on_a_copy(auto, tmp_path, draft)
    assert proposed['ok'] is True, proposed


def test_a_draft_never_crosses_tasks_and_refuses_other_decisions(bank, auto):
    for flow, decision, value in ((bank, 'model_choice', 'fit.linear'),
                                  (auto, 'policy', 'capacity:100')):
        p = flow.call('preview', 'proposal', decision, '--value', value, '--study', flow.study,
                      expect=2)
        assert p['error']['code'] == 'unknown_decision', p
    for flow, decision in ((bank, 'split'), (auto, 'conclusion')):
        p = flow.call('preview', 'proposal', decision, '--value', 'x', '--study', flow.study,
                      expect=2)
        assert p['error']['code'] == 'unsupported_capability', p
        assert p['error']['details']['decisions'] == list(
            pp.DRAFT_DECISIONS[flow.view()['task']])
    p = auto.call('preview', 'proposal', 'model_choice', '--value', 'fit.logistic',
                  '--study', auto.study, expect=2)
    assert p['error']['code'] == 'invalid_value'


def test_a_stale_evaluation_is_not_evidence(bank, tmp_path):
    copy = fk.Flow(fk.clone(bank.study, tmp_path / 'stale'), fk.BANK, prefix='s')
    copy.run('fit.logistic')                 # same identity: still current
    assert _draft(copy, 'policy', 'capacity:100')['proposable'] is True
    p = copy.call('decide', 'propose', 'split', '--value-json',
                  '{"method": "stratified_random", "validation_fraction": 0.25, "seed": 7}',
                  '--restatement', 'You decide the split as stated.', '--rationale', 'Another.',
                  '--request-id', copy.rid(), '--expected-revision', copy.rev(),
                  '--study', copy.study)
    copy.call('decide', 'confirm', p['result']['proposal_id'], '--user-words',
              'Yes, I want the split exactly as you stated it', '--request-id', copy.rid(),
              '--expected-revision', copy.rev(), '--study', copy.study)
    draft = _draft(copy, 'policy', 'capacity:100')
    assert draft['proposable'] is False
    assert draft['missing'] == [{'requirement': 'evaluated_rule', 'value': 'capacity:100'}]


def test_short_id_is_never_all_digits():
    assert pp.short_id('ae80b53f' + '0' * 56) == 'ae80b53f'
    assert pp.short_id('12345678' + 'a' + '0' * 55) == '12345678a'
