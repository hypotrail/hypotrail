"""The scope of a delegation (acceptance rerun, R1; ``docs/specs/CLI-CONTRACT.md`` §5).

A standing delegation ("for questions I can't answer, use your recommended default")
covers the prediction moment, the feature availability and the split only. The policy
and the conclusion need the junior's own words, or a delegation given at that very pause
(``--delegation-scope this_decision``).
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent / 'deliverables'))

import phase3_study as fx  # noqa: E402
from mlkit.reliability import CommandRefused  # noqa: E402
from mlkit.study import commands as cmd, read, state as st, view  # noqa: E402

STANDING = "For questions I can't answer, use your recommended default."
NOW = 'You choose: use your recommended default for this one.'
POLICY_DEFAULT = 'My recommended default: call the 20 highest-scored members.'
CONCLUSION_DEFAULT = 'My recommended default: keep the baseline and record the limits.'
CONCLUSION = {'verdict': 'keep_baseline',
              'text': 'Keep the simple rule for now; the model ranks better on validation rows '
                      'that were used to choose it.'}


@pytest.fixture
def pause(tmp_path, synthetic_case_dir):
    """The policy pause, reached with fixture results (``phase3_study.build``) after the
    first three decisions were confirmed by a standing delegation."""
    b = fx.build(tmp_path / 'study', synthetic_case_dir, upto='models',
                 standing_delegation=STANDING)
    b.decide('model_choice', 'fit.logistic', 'Retain fit.logistic for the rule.',
             'I adopt fit.logistic because it fits the study.')
    fx.put_policy_evaluation(b)
    return b


def _confirm(b: fx.Builder, decision_id, value, restatement, words, **kw) -> cmd.Outcome:
    """Propose, then confirm; a refusal comes back as the CLI's error outcome."""
    try:
        return b.decide(decision_id, value, restatement, words, **kw)
    except CommandRefused as exc:
        return cmd.refused('decide confirm', exc)


def _state(b):
    return read.open(b.study).state


def test_an_inability_to_answer_is_not_a_refusal():
    """The scripted persona's standing delegation is a delegation, not a refusal; a reply
    that opens with a refusal stays one."""
    persona = ("That plan looks good to me, let's go with it. For questions I can't answer, "
               'use your recommended default and tell me what you assumed.')
    for words in (STANDING, persona, 'Je ne peux pas répondre : je te laisse choisir.'):
        assert not cmd.is_negative(words) and cmd.is_delegation(words), words
        assert cmd.reply_problem(words) is None
    assert cmd.is_negative("No, I can't answer that, wait.")
    assert cmd.is_negative('I do not agree with that split.')


def test_a_standing_delegation_covers_the_first_three_decisions(pause):
    state = _state(pause)
    assert st.validate_state(state) == []
    for d in st.STANDING_DELEGATION_DECISIONS:
        conf = state['decisions'][d]['confirmation']
        assert conf['basis'] == st.DELEGATED_DEFAULT and conf['delegation_scope'] == st.STANDING
        assert conf['user_words'] == STANDING
    v = view.build(read.open(pause.study))
    assert v['decisions']['split']['confirmation']['delegation_scope'] == st.STANDING
    assert view.summary(v)['decisions']['split']['delegation_scope'] == st.STANDING


@pytest.mark.parametrize('scope', [st.STANDING, None])
def test_a_standing_delegation_never_confirms_the_policy(pause, scope):
    before = _state(pause)['revision']
    out = _confirm(pause, 'policy', fx.POLICY_RULE, POLICY_DEFAULT, STANDING,
                   basis=st.DELEGATED_DEFAULT, delegation_scope=scope)
    assert out.exit_code == cmd.EXIT_REFUSED
    error = out.payload['error']
    assert error['code'] == 'ambiguous_confirmation'
    assert error['details']['reason'] == 'delegation_not_given_at_this_pause'
    assert error['details']['decision_id'] == 'policy'
    assert error['details']['delegation_scope'] == scope
    assert error['details']['standing_covers'] == list(st.STANDING_DELEGATION_DECISIONS)
    assert 'own words' in error['message'] and 'this_decision' in error['message']
    state = _state(pause)
    assert state['decisions']['policy']['status'] == 'proposed'      # only the proposal
    assert state['revision'] == before + 1


def test_a_delegation_given_at_the_policy_pause_confirms_it(pause):
    out = _confirm(pause, 'policy', fx.POLICY_RULE, POLICY_DEFAULT, NOW,
                   basis=st.DELEGATED_DEFAULT, delegation_scope=st.THIS_DECISION)
    assert out.exit_code == 0, out.payload
    assert out.payload['result']['delegation_scope'] == st.THIS_DECISION
    state = _state(pause)
    assert st.validate_state(state) == []
    conf = state['decisions']['policy']['confirmation']
    assert conf['basis'] == st.DELEGATED_DEFAULT and conf['delegation_scope'] == st.THIS_DECISION
    assert conf['user_words'] == NOW
    assert 'policy' in st.delegated_decisions(state)


def test_the_junior_s_own_words_confirm_the_policy(pause):
    out = _confirm(pause, 'policy', fx.POLICY_RULE, 'You call the 20 highest-scored members.',
                   'Yes, twenty calls is what the desk can handle.')
    assert out.exit_code == 0, out.payload
    conf = _state(pause)['decisions']['policy']['confirmation']
    # ADR 0005: own words that repeat the value ("twenty") are recorded as restated (was explicit).
    assert conf['basis'] == st.RESTATED and conf['delegation_scope'] is None


def test_the_conclusion_needs_a_delegation_given_at_that_pause(pause):
    assert _confirm(pause, 'policy', fx.POLICY_RULE, 'You call the 20 highest-scored members.',
                    'Yes, twenty calls is what the desk can handle.').exit_code == 0
    out = _confirm(pause, 'conclusion', CONCLUSION, CONCLUSION_DEFAULT, STANDING,
                   basis=st.DELEGATED_DEFAULT, delegation_scope=st.STANDING)
    assert out.exit_code == cmd.EXIT_REFUSED
    assert out.payload['error']['details']['reason'] == 'delegation_not_given_at_this_pause'
    assert out.payload['error']['details']['decision_id'] == 'conclusion'
    assert _state(pause)['decisions']['conclusion']['status'] == 'proposed'
    out = _confirm(pause, 'conclusion', CONCLUSION, CONCLUSION_DEFAULT, NOW,
                   basis=st.DELEGATED_DEFAULT, delegation_scope=st.THIS_DECISION)
    assert out.exit_code == 0, out.payload
    conf = _state(pause)['decisions']['conclusion']['confirmation']
    assert conf['delegation_scope'] == st.THIS_DECISION


@pytest.mark.parametrize('basis, scope', [(st.EXPLICIT, st.THIS_DECISION),
                                          (st.EXPLICIT, st.STANDING),
                                          (st.DELEGATED_DEFAULT, 'forever')])
def test_a_scope_goes_with_a_delegation_only(tmp_path, synthetic_case_dir, basis, scope):
    b = fx.Builder(tmp_path / 'study', synthetic_case_dir)
    cmd.init(synthetic_case_dir, b.study)
    words = STANDING if basis == st.DELEGATED_DEFAULT else 'Yes: at expiry, before any reminder.'
    out = _confirm(b, 'prediction_time', 'at expiry, before any reminder',
                   'My recommended default: at expiry, before any reminder.', words,
                  basis=basis, delegation_scope=scope)
    assert out.exit_code == cmd.EXIT_REFUSED
    assert out.payload['error']['code'] == 'invalid_value'
    assert out.payload['error']['details']['field'] == 'delegation_scope'
    assert _state(b)['decisions']['prediction_time']['status'] == 'proposed'


def test_a_record_without_a_scope_stays_valid(pause):
    """Confirmations recorded before R1 (no ``delegation_scope``) are retained, including
    a delegated policy; an explicit record never carries a scope."""
    assert _confirm(pause, 'policy', fx.POLICY_RULE, POLICY_DEFAULT, NOW,
                    basis=st.DELEGATED_DEFAULT, delegation_scope=st.THIS_DECISION).exit_code == 0
    state = _state(pause)
    for d in st.DECISION_IDS:
        conf = state['decisions'][d]['confirmation']
        if conf:
            conf.pop('delegation_scope')
    assert st.validate_state(state) == []
    assert view._decisions(state)['policy']['confirmation']['delegation_scope'] is None
    broken = copy.deepcopy(_state(pause))
    broken['decisions']['policy']['confirmation']['basis'] = st.EXPLICIT
    problems = st.validate_state(broken)
    assert any(p['path'].endswith('confirmation.delegation_scope') for p in problems), problems


def test_the_cli_records_the_scope(tmp_path, synthetic_case_dir):
    from test_cli_decisions import confirm, hyp, propose
    work = tmp_path / 'cwd'
    work.mkdir()
    study = tmp_path / 'study'
    hyp('init', '--case', synthetic_case_dir, '--study', study, cwd=work, expect=0)
    pid = propose(study, work, 'prediction_time', value='at expiry', rid='r1', rev=1,
                  restatement='My recommended default: at expiry.')['result']['proposal_id']
    out = confirm(study, work, pid, STANDING, rid='r2', rev=2, expect=2,
                  extra=('--delegation-scope', 'standing'))
    assert out['error']['code'] == 'invalid_value'                    # explicit by default
    done = confirm(study, work, pid, STANDING, rid='r3', rev=2,
                   extra=('--basis', 'delegated_default', '--delegation-scope', 'standing'))
    assert done['result']['delegation_scope'] == 'standing'
    state = json.loads((study / '.hypotrail' / 'state.json').read_text())
    assert state['decisions']['prediction_time']['confirmation']['delegation_scope'] == 'standing'
    _, summary = hyp('status', '--summary', '--study', study, cwd=work, expect=0)
    assert summary['decisions']['prediction_time']['delegation_scope'] == 'standing'
