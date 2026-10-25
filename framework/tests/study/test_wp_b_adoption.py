"""v0.3 WP-B: confirmation by adoption (owner remarks R14, R16 and R27 of the second demo;
ADR 0005, amendment of 2026-10-20).

* Guided and express: an endorsement bound to the open proposal suffices for every decision,
  the trade-offs included; the reason is optional and recorded (``reason_given``).
* The closed adoption question: a short yes ("oui", "ok", "vas-y", "d'accord avec ta
  recommandation") confirms only with ``--adoption-question`` or through ``--channel
  choice``; without it a bare "ok" is still refused.
* ``--channel choice``: the option label is recorded verbatim, basis ``endorsed``.
* The refusals stay: negation, condition, question, unrelated content, words that contradict
  the value; training still needs a paraphrase and a reason.

Studies live in ``tmp_path`` from the synthetic case.
"""
from __future__ import annotations

import json

import pytest

from mlkit.study import confirm as cf, state as st

import flowkit as fk
from flowkit import Flow

PT = 'Before the first call of the campaign'
PT_RESTATEMENT = 'You predict before the first call of the campaign.'
ADOPT_FR = "J'adopte cette décision"
ADOPT_EN = 'I adopt this decision'


@pytest.fixture
def flow(tmp_path, synthetic_case_dir):
    f = Flow(tmp_path / 'study', synthetic_case_dir, prefix='w')
    f.init()
    return f


@pytest.fixture(scope='module')
def evaluated(tmp_path_factory, synthetic_case_dir):
    study = fk.prepare(synthetic_case_dir, tmp_path_factory.mktemp('wpb') / 'study')
    f = Flow(study, synthetic_case_dir, prefix='e')
    f.run('policy.evaluate', '--rule', 'capacity:20')
    f.decide('model_choice', 'fit.logistic')
    return study


@pytest.fixture
def pause3(evaluated, tmp_path, synthetic_case_dir):
    return Flow(fk.clone(evaluated, tmp_path / 'p3'), synthetic_case_dir, prefix='g')


def _propose(flow, decision, value, restatement):
    return flow.call('decide', 'propose', decision, '--value-json', json.dumps(value),
                     '--restatement', restatement, '--rationale', 'It fits the scenario.',
                     '--request-id', flow.rid(), '--expected-revision', flow.rev(),
                     '--study', flow.study)['result']['proposal_id']


def _confirm(flow, pid, words, *extra, expect=0):
    return flow.call('decide', 'confirm', '--proposal', pid, '--user-words', words, *extra,
                     '--request-id', flow.rid(), '--expected-revision', flow.rev(),
                     '--study', flow.study, expect=expect)


def _reason(out):
    return out['error']['details'].get('reason') or out['error']['code']


# --- the closed adoption question ------------------------------------------------------------

@pytest.mark.parametrize('words', ('oui', 'ok', 'OK.', 'ok pour moi', 'parfait', 'vas-y',
                                   'allons-y', "d'accord avec ta recommandation", 'yes'))
def test_a_short_yes_to_the_adoption_question_confirms(flow, words):
    pid = _propose(flow, 'prediction_time', PT, PT_RESTATEMENT)
    done = _confirm(flow, pid, words, '--adoption-question')['result']
    assert done['status'] == 'confirmed' and done['basis'] == st.ENDORSED, words
    assert done['adoption_question'] is True and done['reason_given'] is None
    conf = flow.state()['decisions']['prediction_time']['confirmation']
    assert conf['user_words'] == words and conf['adoption_question'] is True
    assert flow.view()['decisions']['prediction_time']['confirmation']['adoption_question']


@pytest.mark.parametrize('words', ('ok', 'oui', 'ok pour moi', 'vas-y'))
def test_without_the_adoption_question_a_bare_yes_is_still_refused(flow, words):
    pid = _propose(flow, 'prediction_time', PT, PT_RESTATEMENT)
    rev = flow.rev()
    out = _confirm(flow, pid, words, expect=2)
    assert _reason(out) == 'bare_acknowledgement', words
    assert 'Do you adopt this decision?' in out['error']['message']
    assert flow.rev() == rev


@pytest.mark.parametrize('words, reason', (
    ('non', 'negative_reply'), ('pas encore', 'negative_reply'),
    ('oui mais je veux réfléchir', 'conditional_reply'), ('ok, but not yet', 'negative_reply'),
    ('oui ?', 'question_reply'), ('yes, I like pizza', 'unrelated_reply'),
    ('oui, la pizza du client est bonne', 'unrelated_reply'),
))
def test_the_adoption_question_never_lifts_a_refusal(flow, words, reason):
    pid = _propose(flow, 'prediction_time', PT, PT_RESTATEMENT)
    rev = flow.rev()
    for extra in (('--adoption-question',), ('--channel', 'choice')):
        out = _confirm(flow, pid, words, *extra, expect=2)
        assert out['error']['code'] == 'ambiguous_confirmation', (words, extra)
        assert _reason(out) in (reason, 'negative_reply', 'conditional_reply'), (words, out)
    assert flow.rev() == rev


def test_closed_affirmative_is_a_pure_function():
    for words in ('oui', 'ok pour moi', "d'accord avec ta recommandation", 'je confirme',
                  'oui, cette décision'):
        assert cf.closed_affirmative(words), words
    for words in ('yes, I like pizza', 'oui, la pizza du client est bonne',
                  'je veux changer quelque chose', 'explique-moi d’abord'):
        assert not cf.closed_affirmative(words), words


# --- the choice channel (R16) ---------------------------------------------------------------

@pytest.mark.parametrize('label', (ADOPT_FR, ADOPT_EN, 'Adopt'))
def test_the_adoption_option_is_recorded_verbatim_as_endorsed(flow, label):
    pid = _propose(flow, 'prediction_time', PT, PT_RESTATEMENT)
    done = _confirm(flow, pid, label, '--channel', 'choice')['result']
    assert done['channel'] == 'choice' and done['basis'] == st.ENDORSED
    conf = flow.state()['decisions']['prediction_time']['confirmation']
    assert conf['user_words'] == label and conf['channel'] == 'choice'
    assert st.validate_state(flow.state()) == []


@pytest.mark.parametrize('label', ('Je veux changer quelque chose', "Explique-moi d'abord",
                                   'I want to change something', 'Explain first'))
def test_the_other_options_never_confirm(flow, label):
    pid = _propose(flow, 'prediction_time', PT, PT_RESTATEMENT)
    rev = flow.rev()
    out = _confirm(flow, pid, label, '--channel', 'choice', expect=2)
    assert out['error']['code'] == 'ambiguous_confirmation', label
    assert flow.rev() == rev


# R9UX-2: the Copilot agent offers the picker in the study language. Its labels, per
# language, are the ones ``copilot-agent.md.in`` names; the adopt label confirms through the
# choice channel in a study of either language, the two others never do, and the closed
# question it asks is the one ``next_action.pause.question`` ends with.
PICKER = {'en': ('Do you adopt this decision?', ADOPT_EN, 'Change something', 'Explain first'),
          'fr': ('Adoptez-vous cette décision ?', ADOPT_FR, 'Changer quelque chose',
                 "Expliquer d'abord")}


@pytest.mark.parametrize('lang', sorted(PICKER))
def test_the_copilot_picker_labels_work_in_the_study_language(tmp_path, synthetic_case_dir,
                                                              lang):
    from mlkit.study import agent_files as af
    agent = ' '.join((af.SOURCE / 'copilot-agent.md.in').read_text().split())
    question, adopt, change, explain = PICKER[lang]
    for text in PICKER[lang]:
        assert f'"{text}"' in agent, text
    flow = Flow(tmp_path / 'study', synthetic_case_dir, prefix='l')
    flow.call('init', '--case', synthetic_case_dir, '--study', flow.study, '--lang', lang)
    pid = _propose(flow, 'prediction_time', PT, PT_RESTATEMENT)
    pause = flow.call('status', '--summary', '--study', flow.study)['next_action']['pause']
    closed = pause['question'].replace('\N{NO-BREAK SPACE}', ' ').rsplit('\n\n', 1)[-1]
    assert pause['language'] == lang and closed == question
    rev = flow.rev()
    for label in (change, explain):
        out = _confirm(flow, pid, label, '--channel', 'choice', expect=2)
        assert out['error']['code'] == 'ambiguous_confirmation', label
    assert flow.rev() == rev
    done = _confirm(flow, pid, adopt, '--channel', 'choice')['result']
    assert done['status'] == 'confirmed' and done['basis'] == st.ENDORSED
    assert flow.state()['decisions']['prediction_time']['confirmation']['user_words'] == adopt


def test_a_choice_is_never_a_delegation(flow):
    pid = _propose(flow, 'prediction_time', PT, 'My recommended default: ' + PT_RESTATEMENT)
    out = _confirm(flow, pid, 'use your recommended default', '--channel', 'choice', '--basis',
                   'delegated_default', '--delegation-scope', 'this_decision', expect=2)
    assert out['error']['code'] == 'invalid_value'
    assert out['error']['details']['field'] == 'channel'


def test_a_proposal_never_comes_from_the_choice_channel(flow):
    out = flow.call('decide', 'propose', 'prediction_time', '--value', PT, '--restatement',
                    PT_RESTATEMENT, '--rationale', 'r', '--channel', 'choice', '--request-id',
                    flow.rid(), '--expected-revision', flow.rev(), '--study', flow.study,
                    expect=2)
    assert out['error']['code'] == 'invalid_value'


def test_training_refuses_an_option_label(flow):
    flow.call('mode', 'set', 'training', '--request-id', flow.rid(), '--expected-revision',
              flow.rev(), '--study', flow.study)
    pid = _propose(flow, 'prediction_time', PT, PT_RESTATEMENT)
    out = _confirm(flow, pid, ADOPT_FR, '--channel', 'choice', expect=2)
    assert out['error']['code'] == 'paraphrase_required'
    out = _confirm(flow, pid, 'oui', '--adoption-question', expect=2)
    assert out['error']['code'] in ('ambiguous_confirmation', 'paraphrase_required')


# --- R27: no reason needed in guided and express; recorded when given -------------------------

def test_the_policy_is_adopted_without_a_reason_and_the_report_says_so(pause3):
    pid = _propose(pause3, 'policy', 'capacity:20', 'You call the 20 highest-scored members.')
    done = _confirm(pause3, pid, 'oui', '--adoption-question')['result']
    assert done['status'] == 'confirmed' and done['reason_given'] is False
    view = pause3.view()['decisions']['policy']['confirmation']
    assert view['reason_given'] is False and view['adoption_question'] is True
    pause3.call('render', '--study', pause3.study)
    html = (pause3.study / 'reports' / 'study.html').read_text(encoding='utf-8')
    assert 'data-reason-given="false"' in html and 'no reason given' in html


def test_a_reason_given_is_recorded(pause3):
    pid = _propose(pause3, 'policy', 'capacity:20', 'You call the 20 highest-scored members.')
    words = 'oui, parce que le centre traite vingt appels par jour'
    done = _confirm(pause3, pid, words, '--adoption-question')['result']
    assert done['reason_given'] is True
    conf = pause3.state()['decisions']['policy']['confirmation']
    assert conf['user_words'] == words and conf['reason_given'] is True


def test_a_non_trade_off_records_no_reason_flag(flow):
    pid = _propose(flow, 'prediction_time', PT, PT_RESTATEMENT)
    _confirm(flow, pid, 'je confirme')
    conf = flow.state()['decisions']['prediction_time']['confirmation']
    assert 'reason_given' not in conf and 'adoption_question' not in conf


def test_training_still_needs_a_reason_on_a_trade_off(pause3):
    pause3.call('mode', 'set', 'training', '--request-id', pause3.rid(), '--expected-revision',
                pause3.rev(), '--study', pause3.study)
    pid = _propose(pause3, 'policy', 'capacity:20', 'You call the 20 highest-scored members.')
    out = _confirm(pause3, pid, 'appeler les 20 meilleurs', expect=2)
    assert out['error']['code'] == 'reason_required'
    assert cf.needs_reason(pause3.state(), 'policy')
    done = _confirm(pause3, pid, 'appeler les 20 meilleurs parce que le centre suit')['result']
    assert done['reason_given'] is True and done['basis'] == st.RESTATED
