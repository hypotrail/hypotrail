"""``preview effects`` (CLI-CONTRACT-COMPANION §3, C3) on the Bank and Auto MPG walkthroughs.

Every confirmation of both walkthroughs is preceded by ``preview effects`` at the same
revision, and the test asserts that the preview equals the confirmation's
``result.invalidation`` (``commands.confirmation_plan`` is the one implementation of
both). The flows run in process through ``cli.run``, the code path of the CLI; R1 (a
read-only tree, a real process) is checked on the previews that matter.
"""
from __future__ import annotations

import json

import pytest

import companion_contract as cc
import flowkit as fk
from mlkit.study import commands as cmd, read

AUTO = fk.REPO / 'use-cases' / 'auto-mpg'
CONCLUSION_TEXT = ('The comparison was made on validation rows that were used to choose, so it '
                   'is optimistic and is not a forecast.')


class Previewing(fk.Flow):
    """A flow whose every confirmation is preceded by ``preview effects``."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.previews: list[dict] = []

    def propose(self, decision, value, restatement=None):
        out = self.call('decide', 'propose', decision, '--value-json', json.dumps(value),
                        '--restatement', restatement or f'You decide the {decision} as stated.',
                        '--rationale', 'It fits the scenario.', '--request-id', self.rid(),
                        '--expected-revision', self.rev(), '--study', self.study)
        return out['result']['proposal_id']

    def preview(self, pid) -> dict:
        return self.call('preview', 'effects', pid, '--study', self.study)

    def confirm(self, pid, words=None) -> dict:
        decision = read.open(self.study).state['proposals'][pid]['decision_id']
        preview = self.preview(pid)
        assert preview['blocked'] == [], preview['blocked']
        out = self.call('decide', 'confirm', pid, '--user-words',
                        words or f'Yes, I want the {decision} exactly as you stated it',
                        '--request-id', self.rid(), '--expected-revision', preview['revision'],
                        '--study', self.study, expect=None)
        assert out['ok'] is True, out
        invalidation = out['result']['invalidation']
        assert {k: preview[k] for k in cc.PREVIEW_EQUALS_INVALIDATION} == {
            k: invalidation[k] for k in cc.PREVIEW_EQUALS_INVALIDATION}, (preview, invalidation)
        self.previews.append(preview)
        return out

    def decide(self, decision, value, words=None):
        return self.confirm(self.propose(decision, value), words)


@pytest.fixture(scope='module')
def bank(tmp_path_factory):
    """The Bank walkthrough up to an adopted threshold, every confirmation previewed."""
    flow = Previewing(tmp_path_factory.mktemp('bank') / 'study', fk.BANK, prefix='b')
    flow.init()
    first = flow.propose('prediction_time', 'before the first contact of the campaign')
    preview = flow.preview(first)
    assert preview['previous'] is None and preview['mutation'] == 'first_confirmation'
    assert preview['kept_slots'] == [] and preview['refit'] == []
    flow.confirm(first)
    flow.decide('feature_availability', fk.availability(
        fk.BANK, duration='not_available', day='not_available', month='not_available',
        campaign='not_available', contact='uncertain_included'))
    flow.decide('split', fk.SPLIT)
    for activity in ('split', 'eda.target_rate', 'eda.special_values'):
        flow.run(activity)
    flow.run('eda.rate_by', '--column', 'job')
    flow.run('fit.baseline')
    flow.run('fit.logistic')
    flow.run('policy.evaluate', '--rule', 'threshold:0.2')
    flow.decide('policy', 'threshold:0.2')
    return flow


def test_bank_policy_change_keeps_both_fits(bank, tmp_path):
    flow = Previewing(fk.clone(bank.study, tmp_path / 'study'), fk.BANK, prefix='c')
    flow.run('policy.evaluate', '--rule', 'capacity:100')
    pid = flow.propose('policy', 'capacity:100')
    code, p = cc.r1_read_only(flow.study, 'preview', 'effects', pid)
    assert code == 0 and tuple(p) == cc.PREVIEW_EFFECTS_KEYS, p
    assert p['mutation'] in ('policy.parameter', 'policy.rule_type') and p['refit'] == []
    assert {'fit.baseline', 'fit.logistic'} <= set(p['kept_slots'])
    assert p['reconfirm_required'] == [] and p['blocked'] == []
    assert tuple(p['previous']) == cc.PREVIEW_EFFECTS_PREVIOUS_KEYS
    assert p['previous']['value'] == 'threshold:0.2' and p['previous']['channel'] == 'chat'
    # the confirmed threshold proposal is the one the confirmation marks superseded
    assert p['supersedes_proposal'] == p['previous']['proposal_id']
    flow.confirm(pid, 'Yes: our desk can make 100 calls, take the top 100.')
    state = read.open(flow.study).state
    assert state['proposals'][p['previous']['proposal_id']]['status'] == 'superseded'

    # with a confirmed conclusion, the policy change asks for the conclusion again
    flow.decide('conclusion', {'verdict': 'keep_baseline', 'text': CONCLUSION_TEXT},
                'I keep the baseline for now, as you stated the conclusion.')
    flow.run('policy.evaluate', '--rule', 'capacity:150')
    p = flow.preview(flow.propose('policy', 'capacity:150'))
    assert p['refit'] == [] and p['reconfirm_required'] == ['conclusion']
    assert {'fit.baseline', 'fit.logistic'} <= set(p['kept_slots'])
    flow.confirm(p['proposal_id'])


def test_bank_blocked_refusals(bank, tmp_path):
    flow = Previewing(fk.clone(bank.study, tmp_path / 'study'), fk.BANK, prefix='h')
    # an unevaluated rule: the precondition is missing, whatever the words
    p = flow.preview(flow.propose('policy', 'capacity:77'))
    assert [b['code'] for b in p['blocked']] == ['precondition_missing']
    assert tuple(p['blocked'][0]) == cc.PREVIEW_EFFECTS_BLOCKED_KEYS
    assert p['blocked'][0]['details']['missing']
    refused = flow.call('decide', 'confirm', p['proposal_id'], '--user-words',
                        'Yes, I want the policy exactly as you stated it', '--request-id',
                        flow.rid(), '--expected-revision', flow.rev(), '--study', flow.study,
                        expect=2)
    assert refused['error']['code'] == p['blocked'][0]['code']
    # an open hold comes first
    flow.call('decide', 'note', '--about', 'policy', '--text',
              "don't adopt anything until I bring my manager's figure", '--request-id',
              flow.rid(), '--expected-revision', flow.rev(), '--study', flow.study)
    p = flow.preview(p['proposal_id'])
    assert [b['code'] for b in p['blocked']] == ['decision_on_hold', 'precondition_missing']
    assert p['blocked'][0]['details']['notes'][0]['user_words'].startswith("don't adopt")
    refused = flow.call('decide', 'confirm', p['proposal_id'], '--user-words',
                        'Yes, I want the policy exactly as you stated it', '--request-id',
                        flow.rid(), '--expected-revision', flow.rev(), '--study', flow.study,
                        expect=2)
    assert refused['error']['code'] == 'decision_on_hold'


def test_bank_split_change_stales_both_fits_and_the_eda(bank, tmp_path):
    flow = Previewing(fk.clone(bank.study, tmp_path / 'study'), fk.BANK, prefix='s')
    pid = flow.propose('split', {**fk.SPLIT, 'seed': 7})
    before = read.open(flow.study)
    eda = [s for s in before.state['current'] if s.startswith('eda.') and before.is_current(s)]
    p = flow.preview(pid)
    assert {'fit.baseline', 'fit.logistic', *eda} <= set(p['stale_slots'])
    assert p['refit'] and set(p['refit']) <= {'fit.baseline', 'fit.logistic'}
    assert p['kept_slots'] == [] and 'policy' in p['reconfirm_required']
    flow.confirm(pid, 'Yes, I want the split with that other seed, exactly as you stated it')


def test_preview_refuses_without_effect(bank):
    before = cc.study_tree_digest(bank.study)
    code, p = cc.run('preview', 'effects', 'p_1', '--study', bank.study)
    assert code == 2 and cc.refusal(p) == ('proposal_not_open', {
        'proposal_id': 'p_1', 'status': 'confirmed'}), p
    code, p = cc.run('preview', 'effects', 'nope', '--study', bank.study)
    assert code == 2 and cc.refusal(p)[0] == 'unknown_proposal', p
    code, p = cc.run('preview', 'effects', 'p_1', '--value', 'x', '--study', bank.study)
    assert code == 2 and cc.refusal(p)[0] == 'invalid_arguments', p
    assert cc.study_tree_digest(bank.study) == before


def test_confirmation_plan_never_mutates_the_state(bank):
    study = read.open(bank.study)
    state = study.state
    pid = next(p for p in state['proposals'] if state['proposals'][p]['status'] == 'confirmed')
    # reopen a copy of a proposal: the plan of a closed one is still a pure function
    state['proposals'][pid]['status'] = 'open'
    frozen = json.dumps(state, sort_keys=True)
    from mlkit.study.store import StudyStore

    plan = cmd.confirmation_plan(state, StudyStore(study.study_dir), pid)
    assert json.dumps(state, sort_keys=True) == frozen
    assert set(plan) >= {'blocked', 'decision_id', 'value', 'previous', 'effects',
                         'invalidation'}


def test_auto_mpg_walkthrough_previews_equal_every_confirmation(tmp_path):
    flow = Previewing(tmp_path / 'study', AUTO, prefix='a')
    flow.init()
    flow.decide('prediction_time', 'when the technical characteristics of a new model are fixed')
    flow.decide('feature_availability', fk.availability(AUTO, acceleration='uncertain_excluded'))
    flow.decide('split', {'method': 'ordinal_cutoff', 'column': 'model_year', 'cutoff': 79})
    for activity in ('split', 'eda.target_summary', 'eda.special_values', 'fit.baseline',
                     'fit.linear', 'evaluate.regression'):
        flow.run(activity)
    flow.decide('model_choice', 'fit.linear')
    flow.decide('conclusion', {'verdict': 'adopt_model', 'text': CONCLUSION_TEXT},
                'I adopt the linear model, as you stated the conclusion.')
    pid = flow.propose('model_choice', 'fit.baseline')
    code, p = cc.r1_read_only(flow.study, 'preview', 'effects', pid)
    assert code == 0, p
    assert p['mutation'] == 'model_choice' and p['row'] == 13 and p['refit'] == []
    assert p['reconfirm_required'] == ['conclusion'] and p['stale_results'] == []
    assert {'fit.baseline', 'fit.linear', 'evaluate.regression'} <= set(p['kept_slots'])
    assert cc.r3_imported(flow.study, 'preview', 'effects', pid) == []
    flow.confirm(pid, 'Yes, I want the model_choice switched back, exactly as you stated it')
    assert len(flow.previews) == 6
