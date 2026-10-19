"""Guided confirmation (ADR 0005; owner remarks R1 and R3 of the first demo).

The owner's exact sentences are tests: "oui je confirme cela" confirms the prediction time;
"ok" and "oui" do not; "oui mais je veux réfléchir" does not; the feature-availability
sentence about duration and contact confirms, and a value that keeps contact returns a
``words_contradict_value`` warning that the agent can raise as a concern. Studies live in
``tmp_path`` (the Bank case is only read).
"""
from __future__ import annotations

import json

import pytest

from mlkit.study import cli, commands as cmd, confirm as cf, read, state as st, view

import flowkit as fk
from flowkit import Flow

PT = 'Before the first call of the campaign'
PT_RESTATEMENT = 'You predict before the first call of the campaign.'
PT_FR = 'Vous prédisez avant le premier appel de la campagne.'
OWNER_PT = 'oui je confirme cela'
OWNER_FA = ("je confirme, il faut clairement exclure duration qui n'est connu qu'après l'appel, "
            "on écarte aussi contact, sa valeur peut être gonflée")
OWNER_CONCERN = ("Inflation by later contacts applies to campaign (calls in this campaign), not "
                 "to contact (the channel); the junior kept the exclusion of contact.")


@pytest.fixture
def flow(tmp_path, synthetic_case_dir):
    f = Flow(tmp_path / 'study', synthetic_case_dir)
    f.init()
    return f


@pytest.fixture
def bank(tmp_path):
    f = Flow(tmp_path / 'bank', fk.BANK)
    f.call('init', '--case', fk.BANK, '--study', f.study, '--lang', 'fr')
    return f


def _propose(flow, decision, value, restatement, *extra):
    return flow.call('decide', 'propose', decision, '--value-json', json.dumps(value),
                     '--restatement', restatement, '--rationale', 'It fits the scenario.',
                     *extra, '--request-id', flow.rid(), '--expected-revision', flow.rev(),
                     '--study', flow.study)['result']['proposal_id']


def _confirm(flow, pid, words, *extra, expect=0):
    return flow.call('decide', 'confirm', pid, '--user-words', words, *extra, '--request-id',
                     flow.rid(), '--expected-revision', flow.rev(), '--study', flow.study,
                     expect=expect)


# --- R1: the owner's sentences ------------------------------------------------------------

def test_owner_endorsement_confirms_the_prediction_time(flow):
    pid = _propose(flow, 'prediction_time', PT, PT_RESTATEMENT)
    done = _confirm(flow, pid, OWNER_PT)
    assert done['result']['status'] == 'confirmed'
    assert done['result']['basis'] == st.ENDORSED
    conf = flow.state()['decisions']['prediction_time']['confirmation']
    assert conf['user_words'] == OWNER_PT and conf['basis'] == st.ENDORSED
    assert conf['agent_concern'] is None


@pytest.mark.parametrize('words', ('ok', 'oui', 'OK.', 'Oui !', 'yes'))
def test_a_bare_ok_or_oui_never_confirms(flow, words):
    pid = _propose(flow, 'prediction_time', PT, PT_RESTATEMENT)
    rev = flow.rev()
    out = _confirm(flow, pid, words, expect=2)
    assert out['error']['code'] == 'ambiguous_confirmation'
    assert out['error']['details']['reason'] == 'bare_acknowledgement', words
    assert flow.rev() == rev


@pytest.mark.parametrize('words', ('oui mais je veux réfléchir', "d'accord sauf pour contact",
                                   'yes but let me check with my manager',
                                   'ok, unless the call centre says otherwise',
                                   'je confirme, sauf si le client a déjà été appelé',
                                   'oui, à condition que ce soit avant le premier appel',
                                   'yes, except I am still thinking about it'))
def test_a_conditional_reply_never_confirms(flow, words):
    pid = _propose(flow, 'prediction_time', PT, PT_RESTATEMENT)
    out = _confirm(flow, pid, words, expect=2)
    assert out['error']['details']['reason'] == 'conditional_reply', words
    assert flow.state()['decisions']['prediction_time']['status'] == 'proposed'


@pytest.mark.parametrize('words', ('oui, avant le premier appel ?', 'Is that before the call?',
                                   'je confirme ?'))
def test_a_question_never_confirms(flow, words):
    pid = _propose(flow, 'prediction_time', PT, PT_RESTATEMENT)
    out = _confirm(flow, pid, words, expect=2)
    assert out['error']['details']['reason'] == 'question_reply', words


@pytest.mark.parametrize('words, basis', (
    ('je confirme', st.ENDORSED), ('I agree', st.ENDORSED), ("je suis d'accord", st.ENDORSED),
    ('je valide', st.ENDORSED),
    ('oui, avant le premier appel de la campagne', st.RESTATED),
    ('Yes, before the first call.', st.RESTATED)))
def test_endorsed_and_restated_bases(flow, words, basis):
    pid = _propose(flow, 'prediction_time', PT, PT_RESTATEMENT)
    assert _confirm(flow, pid, words)['result']['basis'] == basis, words


@pytest.mark.parametrize('words', ("d'accord pour moi", 'ça me va', "c'est bon pour moi",
                                   'agreed', 'that works for me', 'I confirm'))
def test_agreement_phrases_are_endorsements(flow, words):
    pid = _propose(flow, 'prediction_time', PT, PT_RESTATEMENT)
    assert _confirm(flow, pid, words)['result']['basis'] == st.ENDORSED, words


@pytest.mark.parametrize('words', ('yes, I like pizza', 'oui, très clair', 'ok, ship it tomorrow',
                                   'sure, the weather is nice'))
def test_a_bare_agreement_word_with_unrelated_content_is_refused(flow, words):
    """Integrator fix: an off-topic reply never becomes a decision (``unrelated_reply``)."""
    pid = _propose(flow, 'prediction_time', PT, PT_RESTATEMENT)
    out = _confirm(flow, pid, words, expect=2)
    assert out['error']['details']['reason'] == 'unrelated_reply', words
    assert flow.state()['decisions']['prediction_time']['status'] == 'proposed'


def test_the_proposal_flag_binds_the_reply(flow):
    pid = _propose(flow, 'prediction_time', PT, PT_RESTATEMENT)
    out = flow.call('decide', 'confirm', '--proposal', pid, '--user-words', OWNER_PT,
                    '--request-id', flow.rid(), '--expected-revision', flow.rev(),
                    '--study', flow.study)
    assert out['result']['proposal_id'] == pid
    both = flow.call('decide', 'confirm', pid, '--proposal', pid, '--user-words', OWNER_PT,
                     '--request-id', flow.rid(), '--expected-revision', flow.rev(),
                     '--study', flow.study, expect=2)
    assert both['error']['code'] == 'invalid_arguments'
    none = flow.call('decide', 'confirm', '--user-words', OWNER_PT, '--request-id', flow.rid(),
                     '--expected-revision', flow.rev(), '--study', flow.study, expect=2)
    assert none['error']['code'] == 'invalid_arguments'


def test_only_the_single_open_proposal_can_be_confirmed(flow):
    old = _propose(flow, 'prediction_time', PT, PT_RESTATEMENT)
    new = _propose(flow, 'prediction_time', 'At the renewal', 'You predict at the renewal.')
    out = _confirm(flow, old, OWNER_PT, expect=2)
    assert out['error']['details']['reason'] == 'proposal_superseded'
    assert _confirm(flow, new, OWNER_PT)['result']['proposal_id'] == new


def test_an_old_basis_reads_as_explicit_and_stays_valid(flow):
    """Studies written before v0.2a keep ``explicit`` (no migration)."""
    pid = _propose(flow, 'prediction_time', PT, PT_RESTATEMENT)
    _confirm(flow, pid, OWNER_PT)
    state = flow.state()
    conf = state['decisions']['prediction_time']['confirmation']
    conf['basis'] = st.EXPLICIT
    conf.pop('agent_concern')
    for key in ('mode', 'language'):
        state.pop(key)
    assert st.validate_state(state) == []
    assert st.mode_of(state) == st.GUIDED and st.language_of(state) == st.DEFAULT_LANGUAGE
    assert view._decisions(state)['prediction_time']['confirmation']['agent_concern'] is None


# --- the reason rule (policy, conclusion; model_choice in regression) ----------------------

@pytest.fixture(scope='module')
def fitted(tmp_path_factory, synthetic_case_dir):
    return fk.prepare(synthetic_case_dir, tmp_path_factory.mktemp('fitted') / 'study')


@pytest.fixture
def pause3(fitted, tmp_path, synthetic_case_dir):
    study = fk.clone(fitted, tmp_path / 'p3')
    f = Flow(study, synthetic_case_dir, prefix='g')
    f.run('policy.evaluate', '--rule', 'capacity:20')
    return f


@pytest.mark.parametrize('words', ('oui je confirme cela', 'je confirme', 'I agree',
                                   "je suis d'accord, tout à fait"))
def test_the_policy_needs_a_reason(pause3, words):
    pid = _propose(pause3, 'policy', 'capacity:20', 'You call the 20 highest-scored members.')
    rev = pause3.rev()
    out = _confirm(pause3, pid, words, expect=2)
    assert out['error']['code'] == 'reason_required', words
    assert out['error']['details']['decision_id'] == 'policy'
    assert pause3.rev() == rev


@pytest.mark.parametrize('words', ('je confirme parce que le centre a cette capacité',
                                   'I agree because the desk handles twenty calls',
                                   'oui, vingt appels car le service ne peut pas en faire davantage'))
def test_a_reason_confirms_the_policy(pause3, words):
    pid = _propose(pause3, 'policy', 'capacity:20', 'You call the 20 highest-scored members.')
    assert _confirm(pause3, pid, words)['result']['status'] == 'confirmed', words


def test_a_delegation_needs_no_reason(pause3):
    pid = _propose(pause3, 'policy', 'capacity:20',
                   'My recommended default: you call the 20 highest-scored members.')
    done = _confirm(pause3, pid, 'je te laisse choisir', '--basis', 'delegated_default',
                    '--delegation-scope', 'this_decision')
    assert done['result']['basis'] == st.DELEGATED_DEFAULT


def test_reason_decisions_by_task():
    # WP-B1: the opening of the final test too.
    assert cf.REASON_DECISIONS == {'binary': ('policy', 'conclusion', 'final_test'),
                                   'regression': ('model_choice', 'conclusion', 'final_test')}
    assert not cf.has_reason('oui je confirme cela') and not cf.has_reason('I agree')
    assert cf.has_reason('je confirme car le service est limité')
    assert cf.has_reason('yes, since the baseline is weaker')


# --- R3: agent concern, correction note, contradiction warning -----------------------------

def _bank_availability(**overrides):
    value = fk.availability(fk.BANK)
    value.update(overrides)
    return value


def test_owner_availability_sentence_confirms_and_records_the_concern(bank):
    bank.decide('prediction_time', 'avant le premier appel de la campagne',
                words='oui, avant le premier appel')
    value = _bank_availability(duration='not_available', contact='not_available')
    pid = _propose(bank, 'feature_availability', value,
                   'You exclude duration and contact; the others are known then.',
                   '--restatement-fr', 'Vous excluez duration et contact ; les autres sont '
                                       'connues à ce moment.')
    done = _confirm(bank, pid, OWNER_FA, '--agent-concern', OWNER_CONCERN)
    result = done['result']
    assert result['status'] == 'confirmed' and result['warnings'] == []
    assert result['agent_concern'] == OWNER_CONCERN
    assert result['basis'] == st.RESTATED
    v = bank.view()
    conf = v['decisions']['feature_availability']['confirmation']
    assert conf['agent_concern'] == OWNER_CONCERN and conf['user_words'] == OWNER_FA
    decisions = bank.call('decisions', '--study', bank.study)
    item = next(d for d in decisions['decisions'] if d['decision_id'] == 'feature_availability')
    assert item['confirmation']['agent_concern'] == OWNER_CONCERN
    html = (bank.study / 'reports' / 'study.html').read_text(encoding='utf-8')
    assert 'Point raised by the agent' in html and 'kept by the user' in html


def test_words_that_contradict_the_value_stop_until_the_agent_raises_them(bank):
    """WP-A9 (H3): in the guided mode a contradiction is the one stop of R3. Without
    ``--agent-concern`` it is refused (``words_contradict_value``); once the agent raised it
    and the junior kept their words, it is confirmed and the warning is kept on the record,
    in the view, ``decisions``, and the report."""
    bank.decide('prediction_time', 'avant le premier appel de la campagne',
                words='oui, avant le premier appel')
    value = _bank_availability(duration='not_available', contact='available_at_prediction')
    pid = _propose(bank, 'feature_availability', value,
                   'You exclude duration; contact and the others are known then.')
    rev = bank.rev()
    refused = _confirm(bank, pid, OWNER_FA, expect=2)
    assert refused['error']['code'] == 'words_contradict_value'
    assert refused['error']['details']['mode'] == 'guided'
    assert [w['variable'] for w in refused['error']['details']['warnings']] == ['contact']
    assert bank.rev() == rev
    done = _confirm(bank, pid, OWNER_FA, '--agent-concern',
                    'The value keeps contact although your words exclude it; you kept them.')
    assert done['result']['status'] == 'confirmed'
    assert [(w['code'], w['variable'], w['said'], w['value']) for w in done['result']['warnings']] \
        == [('words_contradict_value', 'contact', 'exclude', 'available_at_prediction')]
    record = bank.state()['decisions']['feature_availability']['confirmation']
    assert [w['variable'] for w in record['warnings']] == ['contact']
    conf = bank.view()['decisions']['feature_availability']['confirmation']
    assert [w['variable'] for w in conf['warnings']] == ['contact']
    decisions = bank.call('decisions', '--study', bank.study)
    item = next(d for d in decisions['decisions'] if d['decision_id'] == 'feature_availability')
    assert [w['variable'] for w in item['confirmation']['warnings']] == ['contact']
    html = (bank.study / 'reports' / 'study.html').read_text(encoding='utf-8')
    assert 'data-warning="words_contradict_value"' in html
    assert 'Your words exclude contact, but the value keeps it' in html


def test_a_confirmation_without_contradiction_records_no_warnings(bank):
    bank.decide('prediction_time', 'avant le premier appel de la campagne',
                words='oui, avant le premier appel')
    state = bank.state()
    assert 'warnings' not in state['decisions']['prediction_time']['confirmation']
    assert bank.view()['decisions']['prediction_time']['confirmation']['warnings'] == []


def test_contradiction_check_is_a_pure_function():
    value = {'duration': 'not_available', 'contact': 'available_at_prediction',
             'pdays': 'available_at_prediction', 'campaign': 'not_available'}
    warn = cf.availability_warnings
    assert [w['variable'] for w in warn('exclure duration, contact et pdays', value)] \
        == ['contact', 'pdays']
    assert [w['variable'] for w in warn('on garde campaign et contact', value)] == ['campaign']
    assert warn("on ne garde pas campaign", value) == []
    assert warn('we drop duration; keep contact and pdays', value) == []
    assert [w['variable'] for w in warn('I agree, remove contact', value)] == ['contact']
    assert warn('sans duration', value) == []


def test_a_correction_note_attaches_without_reconfirming(bank):
    bank.decide('prediction_time', 'avant le premier appel de la campagne',
                words='oui, avant le premier appel')
    value = _bank_availability(duration='not_available', contact='not_available')
    pid = _propose(bank, 'feature_availability', value, 'You exclude duration and contact.')
    _confirm(bank, pid, OWNER_FA)
    words = ("Correction : j'écarte contact parce que je ne sais pas quand le canal est connu, "
             "pas parce que sa valeur est gonflée.")
    out = bank.call('decide', 'note', '--about', 'feature_availability', '--kind', 'correction',
                    '--user-words', words, '--request-id', bank.rid(),
                    '--expected-revision', bank.rev(), '--study', bank.study)
    assert out['result']['kind'] == 'correction' and out['result']['status'] == 'recorded'
    assert out['result']['reconfirm_required'] == [] and out['result']['open_holds'] == []
    state = bank.state()
    assert state['decisions']['feature_availability']['status'] == 'confirmed'
    assert st.open_holds(state) == []
    v = bank.view()
    assert [(n['kind'], n['status']) for n in v['notes']] == [('correction', 'recorded')]
    assert 'open_holds' not in {x['id'] for x in v['not_yet_defensible']}
    # A correction is not a hold: it cannot be resolved or withdrawn.
    res = bank.call('decide', 'note', '--resolve', 'n_1', '--text', 'resolved now',
                    '--request-id', bank.rid(), '--expected-revision', bank.rev(),
                    '--study', bank.study, expect=2)
    assert res['error']['code'] == 'note_not_open'
    # Before a confirmation there is nothing to correct.
    early = bank.call('decide', 'note', '--about', 'split', '--kind', 'correction',
                      '--text', 'the split should keep the outcome share', '--request-id',
                      bank.rid(), '--expected-revision', bank.rev(), '--study', bank.study,
                      expect=2)
    assert early['error']['code'] == 'invalid_value'


# --- language and mode --------------------------------------------------------------------

def test_labels_and_the_study_language(bank):
    pid = _propose(bank, 'prediction_time', PT, PT_RESTATEMENT, '--restatement-fr', PT_FR)
    v = bank.view()
    assert v['language'] == 'fr' and v['mode'] == 'guided'
    p = v['open_proposals'][0]
    assert p['labels'] == {'fr': PT_FR} and p['label'] == PT_FR
    assert p['restatement'] == PT_RESTATEMENT
    assert list(p)[-1] == 'origin'                         # CI.6: origin stays last
    summary = bank.call('status', '--summary', '--study', bank.study)
    assert 'label' not in summary['open_proposals'][0]     # CA.4: the v0.1 summary shape
    # A French paraphrase restates through the French label.
    assert _confirm(bank, pid, 'oui, avant le premier appel')['result']['basis'] == st.RESTATED


def test_lang_names_the_language_of_the_restatement(flow):
    _propose(flow, 'prediction_time', PT, PT_FR, '--lang', 'fr')
    p = flow.view()['open_proposals'][0]
    assert p['labels'] == {'fr': PT_FR} and p['label'] == PT_FR      # no English label


def test_labels_are_checked(flow):
    out = flow.call('decide', 'propose', 'prediction_time', '--value', PT, '--restatement',
                    PT_RESTATEMENT, '--rationale', 'r', '--restatement-fr', 'Avant 42 appels.',
                    '--request-id', flow.rid(), '--expected-revision', flow.rev(),
                    '--study', flow.study, expect=2)
    assert out['error']['code'] == 'literal_number_in_text'
    assert out['error']['details']['field'] == 'labels.fr'
    with pytest.raises(cmd.CommandRefused):
        cmd.check_labels({'de': 'Vor dem Anruf'})


def test_a_proposal_without_labels_keeps_its_request_identity(flow):
    """A propose request without a language carries no ``labels`` parameter."""
    rid = flow.rid()
    args = ('decide', 'propose', 'prediction_time', '--value', PT, '--restatement',
            PT_RESTATEMENT, '--rationale', 'r', '--request-id', rid, '--expected-revision',
            flow.rev(), '--study', flow.study)
    flow.call(*args)
    state = flow.state()
    assert 'labels' not in next(iter(state['proposals'].values()))
    assert 'labels' not in json.dumps(state['receipts'])
    assert flow.call(*args)['replayed'] is True


def test_mode_set(flow):
    state = flow.state()
    assert state['mode'] == 'guided' and state['language'] == 'en'
    # v0.2b (WP-B2): training and express are implemented; their rules are tested in
    # test_confirmation_modes.py.
    bad = flow.call('mode', 'set', 'turbo', '--user-words', 'turbo please', '--request-id',
                    flow.rid(), '--expected-revision', flow.rev(), '--study', flow.study,
                    expect=2)
    assert bad['error']['code'] == 'invalid_value'
    bare = flow.call('mode', 'set', 'guided', '--user-words', 'ok', '--request-id', flow.rid(),
                     '--expected-revision', flow.rev(), '--study', flow.study, expect=2)
    assert bare['error']['details']['reason'] == 'bare_acknowledgement'
    rid = flow.rid()
    args = ('mode', 'set', 'guided', '--user-words', 'je reste en mode guidé', '--request-id',
            rid, '--expected-revision', flow.rev(), '--study', flow.study)
    done = flow.call(*args)
    assert done['action'] == 'study.set_mode'
    assert done['result'] == {'mode': 'guided', 'previous': 'guided',
                              'user_words': 'je reste en mode guidé', 'changed': False}
    again = flow.call(*args)                                    # idempotent replay
    assert again['replayed'] is True and again['revision'] == done['revision']
    history = flow.state()['mode_history']
    assert [(h['mode'], h['user_words']) for h in history] == [('guided', 'je reste en mode guidé')]


def test_init_language_is_checked(tmp_path, synthetic_case_dir):
    out = cli.run(['init', '--case', str(synthetic_case_dir), '--study', str(tmp_path / 's'),
                   '--lang', 'de'])
    assert out.exit_code == 2 and out.payload['error']['code'] == 'invalid_arguments'
