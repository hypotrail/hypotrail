"""What a confirmation's words must say (review finding H1, and L5 for acknowledgements).

A reply confirms a proposal only if it is not a refusal (``negative_reply``), says
something beyond acknowledgements, filler and identifiers (``bare_acknowledgement``),
and relates to the proposal: it shares a word or a number with its value or its
restatement (``unrelated_reply``). The replies below are the independent reviewer's
reproductions (``t2.py``, ``t3.py``) that used to confirm. Studies live in ``tmp_path``.
"""
from __future__ import annotations

import json

import pytest

from mlkit.study import commands as cmd, executions as ex

import flowkit as fk
from flowkit import Flow

PT = 'Before the first call of the campaign'
PT_RESTATEMENT = 'You predict before the first call of the campaign.'


@pytest.fixture
def flow(tmp_path, synthetic_case_dir):
    f = Flow(tmp_path / 'study', synthetic_case_dir)
    f.init()
    return f


def _propose(flow, decision, value, restatement):
    return flow.call('decide', 'propose', decision, '--value-json', json.dumps(value),
                     '--restatement', restatement, '--rationale', 'It fits the scenario.',
                     '--request-id', flow.rid(), '--expected-revision', flow.rev(),
                     '--study', flow.study)['result']['proposal_id']


def _confirm(flow, pid, words, *extra, expect=0):
    return flow.call('decide', 'confirm', pid, '--user-words', words, *extra, '--request-id',
                     flow.rid(), '--expected-revision', flow.rev(), '--study', flow.study,
                     expect=expect)


NEGATIVE = ('no', 'No, I do not agree with that at all', 'wait', 'non', 'Nope.',
            "I don't agree", 'stop', "attends, je ne suis pas d'accord", 'pas d’accord',
            'ok... no', 'Yes, but not before the first call', 'I disagree with this',
            'hold on, before the first call?')
CONTENT_FREE = ('sure, sounds good to me', 'yes go with that', 'ok p_5', 'yes!!! 👍',
                'ok ok ok, fine by me', 'OK.', 'yes, that is right', "d'accord", 'garde ça',
                'ok r-1a2b3c4d', 'fine with me, go ahead with it')


@pytest.mark.parametrize('words', NEGATIVE)
def test_a_refusal_never_confirms(flow, words):
    pid = _propose(flow, 'prediction_time', PT, PT_RESTATEMENT)
    rev = flow.rev()
    out = _confirm(flow, pid, words, expect=2)
    assert out['error']['code'] == 'ambiguous_confirmation'
    assert out['error']['details']['reason'] == 'negative_reply', words
    assert flow.rev() == rev
    assert flow.state()['decisions']['prediction_time']['status'] == 'proposed'


@pytest.mark.parametrize('words', CONTENT_FREE)
def test_a_content_free_reply_never_confirms(flow, words):
    pid = _propose(flow, 'prediction_time', PT, PT_RESTATEMENT)
    out = _confirm(flow, pid, words, expect=2)
    assert out['error']['details']['reason'] == 'bare_acknowledgement', words


@pytest.mark.parametrize('words', ('yes, I like pizza', 'sounds great, ship it tomorrow',
                                   'oui, très clair'))
def test_a_reply_unrelated_to_the_proposal_never_confirms(flow, words):
    pid = _propose(flow, 'prediction_time', PT, PT_RESTATEMENT)
    out = _confirm(flow, pid, words, expect=2)
    assert out['error']['details']['reason'] == 'unrelated_reply', words


@pytest.mark.parametrize('words', ('Yes, use prediction before the call',
                                   'oui, avant le premier call de la campagne',
                                   'We predict before the first call.',
                                   "Right: we don't know anything after the first call."))
def test_a_genuine_reply_confirms(flow, words):
    pid = _propose(flow, 'prediction_time', PT, PT_RESTATEMENT)
    done = _confirm(flow, pid, words)
    assert done['result']['status'] == 'confirmed' and done['result']['user_words'] == words


def test_genuine_replies_to_availability_and_split_confirm(flow, synthetic_case_dir):
    flow.decide('prediction_time', PT, words='Yes, before the first call of the campaign.')
    features = cmd.candidate_features(cmd.case_of(flow.state()))
    excluded = features[:2]
    value = {f: ('not_available' if f in excluded else 'available_at_prediction')
             for f in features}
    pid = _propose(flow, 'feature_availability', value,
                   f'You exclude {excluded[0]} and {excluded[1]}; the others are known then.')
    # French, naming the excluded features; a negated availability is descriptive.
    _confirm(flow, pid, f'oui, on exclut {excluded[0]} et {excluded[1]}, ils ne sont pas '
                        'disponibles avant')
    pid = _propose(flow, 'split', fk.SPLIT, 'Seventy-thirty stratified split, seed 20261017.')
    _confirm(flow, pid, 'seventy thirty stratified split with that seed')
    assert flow.state()['decisions']['split']['status'] == 'confirmed'


def test_reply_classification_is_a_pure_function():
    problem = cmd.reply_problem
    assert problem('', value=PT, restatement=PT_RESTATEMENT) == 'missing_user_words'
    assert problem('No.', value=PT, restatement=PT_RESTATEMENT) == 'negative_reply'
    assert problem('ok p_12', value=PT, restatement=PT_RESTATEMENT) == 'bare_acknowledgement'
    assert problem('I confirm capacity 100', value='capacity:100',
                   restatement='Call the 100 top-scored clients.') is None
    assert problem('call the hundred top-scored clients', value='capacity:100',
                   restatement='Call the top 100 scored clients.') is None
    # A number relates only when it is the proposal's.
    assert problem('yes, 250', value='capacity:100',
                   restatement='Call the top 100 scored clients.') == 'unrelated_reply'
    assert problem('yes, 100', value='capacity:100',
                   restatement='Call the top 100 scored clients.') is None
    # Duration is not available at prediction: descriptive, not a refusal.
    assert problem('Yes, duration is not available before the call.',
                   value={'duration': 'not_available'},
                   restatement='You exclude duration.') is None
    assert cmd.is_bare_acknowledgement('sure, sounds good to me')
    assert not cmd.is_bare_acknowledgement('before the first call')


def test_delegations_still_confirm_a_recommended_default(flow):
    """D1 keeps working: a delegation relates to the restatement by delegating to it."""
    restatement = 'My recommended default: you predict before the first call of the campaign.'
    for words in ('je te laisse choisir', 'Use your recommended default.'):
        pid = _propose(flow, 'prediction_time', PT, restatement)
        done = _confirm(flow, pid, words, '--basis', 'delegated_default')
        assert done['result']['basis'] == 'delegated_default'
    pid = _propose(flow, 'prediction_time', PT, restatement)
    out = _confirm(flow, pid, 'non, je te laisse choisir', '--basis', 'delegated_default',
                   expect=2)
    assert out['error']['details']['reason'] == 'negative_reply'


def test_the_cli_refuses_the_reviewers_replies_in_a_real_process(flow, tmp_path):
    work = tmp_path / 'cwd'
    work.mkdir()
    pid = _propose(flow, 'prediction_time', PT, PT_RESTATEMENT)
    for words, reason in (('no', 'negative_reply'), ('ok p_5', 'bare_acknowledgement')):
        code, out = fk.hyp('decide', 'confirm', pid, '--user-words', words, '--request-id',
                           flow.rid(), '--expected-revision', flow.rev(), '--study', flow.study,
                           cwd=work)
        assert code == 2 and out['error']['details']['reason'] == reason


# --- L5: acknowledgement words -----------------------------------------------------------

def _interrupted(tmp_path, synthetic_case_dir):
    study = fk.prepare(synthetic_case_dir, tmp_path / 'ack', upto='pauses')
    work = tmp_path / 'ackcwd'
    work.mkdir()
    flow = Flow(study, synthetic_case_dir, prefix='a')
    proc = fk.spawn('run', 'split', '--request-id', 'dying', '--expected-revision', flow.rev(),
                    '--study', study, cwd=work,
                    extra_env={'HYPOTRAIL_TEST_HOOKS': '1', 'HYPOTRAIL_FAULT': 'run_after_reserve'})
    proc.communicate(timeout=300)
    assert flow.run('split', expect=4)['error']['code'] == 'interrupted_execution_pending'
    return flow, ex.execution_id('dying')


def test_an_acknowledgement_needs_words_about_the_interruption(tmp_path, synthetic_case_dir):
    flow, eid = _interrupted(tmp_path, synthetic_case_dir)
    for words, reason in (('ok', 'bare_acknowledgement'), ('no', 'negative_reply'),
                          ('wait', 'negative_reply'), ('ok e_1234abcd', 'bare_acknowledgement'),
                          ('sounds good, I like pizza', 'unrelated_reply')):
        out = flow.call('run', '--acknowledge-interruption', eid, '--user-words', words,
                        '--request-id', flow.rid(), '--expected-revision', flow.rev(),
                        '--study', flow.study, expect=2)
        assert out['error']['code'] == 'ambiguous_confirmation', words
        assert out['error']['details']['reason'] == reason, words
    assert eid in flow.state()['executions']['interrupted']
    words = "Understood, the split was interrupted and its outcome is unknown; don't restart it."
    ack = flow.call('run', '--acknowledge-interruption', eid, '--user-words', words,
                    '--request-id', flow.rid(), '--expected-revision', flow.rev(),
                    '--study', flow.study)
    assert ack['status'] == 'acknowledged' and ack['result']['user_words'] == words
