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
def test_a_reply_sharing_no_word_is_an_endorsement_in_guided_mode(flow, words):
    """ADR 0005 (owner remark R1) changed this expectation: until v0.2a these replies were
    refused with ``unrelated_reply`` (no word shared with the proposal). In the guided mode a
    non-bare, non-negative, unconditional reply bound to the single open proposal confirms
    it, recorded as ``endorsed`` (not ``restated``). The token-overlap classifier itself is
    unchanged (``reply_problem`` with a value, used to resolve a hold, and kept for the
    training mode of v0.2b)."""
    pid = _propose(flow, 'prediction_time', PT, PT_RESTATEMENT)
    done = _confirm(flow, pid, words)
    assert done['result']['basis'] == 'endorsed', words
    assert cmd.reply_problem(words, value=PT, restatement=PT_RESTATEMENT) == 'unrelated_reply'


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


# --- P1 (post-v0.1 acceptance): a negation inside a caveat is not a refusal ----------------
#
# Table-driven, from the transcripts of the post-v0.1 Claude Code acceptance runs
# (``docs/acceptance/runs/claude-code-2026-10-18-post-v0.1.md``) and earlier runs: the
# simulated junior's replies verbatim ("run"), the report's shortened examples and the
# task's refusal openers ("report"), French renderings of the same replies ("fr"), and the
# H1 replies that must keep their classification ("h1"). ``True`` means a refusal
# (``negative_reply``).

AGREE_WITH_CAVEAT = [
    ('run', "Go with your recommendation: adopt the 100-call policy as an exploratory result "
            "only. It ranked better than the baseline on the validation rows, but those rows "
            "were used to choose the rule, so it's not a forecast and shows association, not "
            "that calling causes subscriptions. The next action is a randomised pilot at the "
            "100-call limit."),
    ('run', "Go with your recommendation: adopt the policy of calling the 156 highest logistic "
            "scores, as an exploratory result only. It's not a forecast because the same "
            "validation rows chose the rule, and it shows association rather than causation, so "
            "the next step is a randomised pilot with the real call limit."),
    ('run', "Yes, I'll hand that conclusion to my manager with the verdict to adopt the model. "
            "My main point: the linear model beat the mean baseline on the later model years, it "
            "still predicts mpg too low on newer cars, and this is an exploratory comparison, not "
            "a forecast, to be checked on cars from later years."),
    ('run', "Yes, that matches. We predict a new model's mpg once its specs (cylinders, "
            "displacement, horsepower, weight, origin) are fixed, before mpg is measured, so mpg "
            "is never an input."),
    ('run', "I confirm: we adopt the linear model because it made smaller errors than the mean "
            "baseline on the later model years (MAE 6.31 vs 10.10 mpg). It still underestimates "
            "the fuel efficiency of newer cars, and its validation errors aren't evidence of "
            "future error, so it should be checked on a later period before any use."),
    ('run', "I confirm: we keep the linear model for this exploratory exercise because it made "
            "smaller errors than the mean baseline on the later model years. It still "
            "underestimates fuel efficiency of newer cars, its validation errors aren't evidence "
            "of future error, and it needs to be checked on a later period before any use."),
    ('run', "I adopt the call-the-top-100 rule as an exploratory recommendation: on the "
            "validation rows it held more subscribers than the constant baseline, but it's not a "
            "forecast or a causal effect, and a randomised pilot on a new campaign should "
            "confirm it before routine use."),
    ('run', "I confirm calling the top 156 contacts with the highest logistic scores as a "
            "stand-in, since the team's real call limit isn't known yet."),
    ('run', "Yes, I agree. I'm excluding acceleration because it's a measured performance, and "
            "we don't know if it's available before mpg is measured, so it could leak "
            "information from after the prediction moment."),
    ('run', "That plan looks good to me, let's go with it. For questions I can't answer, use "
            "your recommended default and tell me what you assumed."),
    ('run', "Okay, I'll keep the recorded study as it is, with model year only ordering the rows "
            "and not used as a feature."),
    ('run', "Yes, save the draft as a note in the workbench. Keep the ask as the randomised "
            "pilot, not routine use, since only a test on a new campaign can show whether the "
            "ranking beats random calling."),
    ('report', "Yes, and it's not a forecast"),
    ('report', 'agreed, never an input'),
    ('report', "ok with that — these aren't evidence of future error"),
    ('h1', "Understood, the split was interrupted and its outcome is unknown; don't restart it."),
    ('h1', "Right: we don't know anything after the first call."),
    ('h1', 'Yes, duration is not available before the call.'),
    ('fr', "Oui, j'adopte la règle des 100 appels comme résultat exploratoire : ce n'est pas une "
           "prévision."),
    ('fr', "D'accord, on exclut duration : elle n'est jamais connue avant l'appel."),
    ('fr', "Je confirme : on garde le modèle linéaire, et ses erreurs de validation ne sont pas "
           "une preuve de l'erreur future."),
    ('fr', 'oui, on exclut age et job, ils ne sont pas disponibles avant'),
    ('fr', "Prends ta recommandation : ce n'est pas une prévision, juste un classement."),
]
REFUSALS = [
    ('h1', 'no'), ('h1', 'No, I do not agree with that at all'), ('h1', 'wait'), ('h1', 'non'),
    ('h1', 'Nope.'), ('h1', "I don't agree"), ('h1', 'stop'),
    ('h1', "attends, je ne suis pas d'accord"), ('h1', 'pas d’accord'), ('h1', 'ok... no'),
    ('h1', 'Yes, but not before the first call'), ('h1', 'I disagree with this'),
    ('h1', 'hold on, before the first call?'), ('h1', "No, I can't answer that, wait."),
    ('h1', 'I do not agree with that split.'), ('h1', 'non, je te laisse choisir'),
    ('run', "Keep the illustrative K and don't adopt anything until I bring my manager's "
            "figure."),
    ('report', 'not yet'), ('report', "Not yet, I need my manager's figure first."),
    ('report', 'ok, not yet'), ('report', 'Not before the first call.'),
    ('report', "I'm not sure about that."), ('report', "That's wrong."),
    ('report', 'Yes. No, wait.'), ('report', 'Not that one.'),
    ('fr', 'pas encore'), ('fr', 'Non, pas avant le premier appel.'),
    ('fr', 'oui, mais pas avant le premier appel'),
    ('fr', "d'accord, mais je ne veux pas de seuil"), ('fr', 'Je ne valide pas cette règle.'),
    ('fr', "c'est faux"), ('fr', 'Je ne suis pas sûr.'),
]
NEGATION_TABLE = ([(words, False, source) for source, words in AGREE_WITH_CAVEAT]
                  + [(words, True, source) for source, words in REFUSALS])


def test_the_negation_table_has_enough_cases_in_both_directions_and_languages():
    assert len(NEGATION_TABLE) >= 30
    assert sum(1 for _, neg, _ in NEGATION_TABLE if neg) >= 15
    assert sum(1 for _, neg, _ in NEGATION_TABLE if not neg) >= 15
    assert {s for _, _, s in NEGATION_TABLE} >= {'run', 'report', 'fr', 'h1'}


@pytest.mark.parametrize('words,negative,source', NEGATION_TABLE)
def test_a_negation_is_a_refusal_only_when_it_targets_the_agreement(words, negative, source):
    assert cmd.is_negative(words) is negative, (source, words)
    if negative:
        assert cmd.reply_problem(words) == 'negative_reply', words
    else:
        assert cmd.reply_problem(words) != 'negative_reply', words


@pytest.mark.parametrize('words', [w for _, w in AGREE_WITH_CAVEAT[:6]])
def test_the_refused_acceptances_now_confirm_in_a_real_process(flow, words):
    """The six replies the post-v0.1 runs refused confirm a proposal they relate to, and the
    recorded words keep the limits the junior stated."""
    restatement = ('You adopt the recommended option as an exploratory result, the linear model '
                   'or the call policy, with a pilot or a later check as the next step.')
    extra = ()
    if cmd.is_delegation(words):   # "Go with your recommendation: ..." delegates (D1)
        restatement = 'My recommended default: ' + restatement
        extra = ('--basis', 'delegated_default', '--delegation-scope', 'this_decision')
    pid = _propose(flow, 'prediction_time', PT, restatement)
    done = _confirm(flow, pid, words, *extra)
    assert done['result']['status'] == 'confirmed'
    assert done['result']['user_words'] == words
