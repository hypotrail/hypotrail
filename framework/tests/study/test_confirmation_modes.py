"""Training and express confirmation modes (ADR 0005, v0.2b, WP-B2).

* The concept matrix: each decision, in the training mode, with replies in French and in
  English that restate its concepts (accepted) or leave one out (refused, and which one).
* The owner's sentences by mode: "oui je confirme cela" confirms in guided and express and is
  refused in training with ``paraphrase_required`` and a junior-facing message.
* R3 by mode: words that contradict a feature availability value are a refusal in training,
  a warning in guided and express.
* Express: a standing delegation also covers the success criterion and the preprocessing;
  never the policy or the conclusion.
* ``mode set``: raising the strictness needs no words, lowering it needs words that name the
  mode; a mode change never invalidates a confirmation, and each one records its mode.

Studies live in ``tmp_path`` (the Bank case is only read).
"""
from __future__ import annotations

import json

import pytest

from mlkit.study import concepts, governance, state as st

import flowkit as fk
from flowkit import Flow

PT = 'Before the first call of the campaign'
PT_RESTATEMENT = 'You predict before the first call of the campaign.'
OWNER_PT = 'oui je confirme cela'
OWNER_FA = ("je confirme, il faut clairement exclure duration qui n'est connu qu'après l'appel, "
            "on écarte aussi contact, sa valeur peut être gonflée")
STANDING = "for questions I can't answer, use your recommended default"


# --- the concept matrix (pure) -------------------------------------------------------------

BINARY, REGRESSION = {'task': 'binary'}, {'task': 'regression'}
AVAILABILITY = {'duration': 'not_available', 'contact': 'available_at_prediction',
                'age': 'available_at_prediction', 'pdays': 'uncertain_included'}
DEFAULT_PREP = dict(governance.DEFAULT_PREPROCESSING)
PREP = {'missing': {'balance': 'indicator'}, 'rare_category_min_rows': 0, 'caps': {},
        'log_transform': ['balance']}


def _proposal(decision_id, value, restatement='You decide as stated.', labels=None):
    p = {'proposal_id': 'p_1', 'decision_id': decision_id, 'value': value,
         'restatement': restatement}
    if labels:
        p['labels'] = labels
    return p


# (state, decision, value, accepted replies, refused replies with the concepts they miss)
MATRIX = [
    (BINARY, 'prediction_time', PT,
     ['oui, avant le premier appel de la campagne', 'Before the first call, I agree',
      'avant le premier contact de la campagne'],
     [(OWNER_PT, ['timing_before', 'event']),
      ('je confirme, après le premier appel', ['timing_before']),
      ('yes, before', ['event'])]),
    (BINARY, 'feature_availability', AVAILABILITY,
     ["on retire duration, connue seulement après l'appel",
      'exclude duration because it is only known after the call',
      'sans duration'],
     [('je confirme', ['exclude', 'variable:duration']),
      ('on exclut contact', ['variable:duration']),
      ('duration est importante', ['exclude'])]),
    (BINARY, 'feature_availability', {k: 'available_at_prediction' for k in AVAILABILITY},
     ['on garde toutes les variables', 'keep every variable'],
     [('je confirme', ['keep_all'])]),
    (BINARY, 'split', {'method': 'stratified_random', 'validation_fraction': 0.3, 'seed': 7},
     ['30 % des lignes mises de côté au hasard pour la validation',
      'a random 70/30 split, 30% held out for validation',
      'stratified split with thirty percent kept apart to validate'],
     [('je confirme le découpage', ['validation', 'random', 'proportion']),
      ('30 % au hasard', ['validation']),
      ('a random split held out for validation', ['proportion'])]),
    (REGRESSION, 'split', {'method': 'ordinal_cutoff', 'column': 'model_year', 'cutoff': 80},
     ['les années à partir de 80 servent à la validation',
      'validate on the later years, from 80 on'],
     [('je confirme', ['validation', 'proportion']),
      ('validate on the later years', ['proportion'])]),
    (BINARY, 'success_criterion', {'metric': 'precision_gain', 'min_points': 5},
     ['au moins 5 points de précision de plus que la référence',
      'precision must beat the baseline by five points'],
     [('ok pour le critère, je confirme', ['precision', 'min_gain']),
      ('precision must beat the baseline', ['min_gain'])]),
    (REGRESSION, 'success_criterion', {'metric': 'mae_reduction', 'min_share': 0.1},
     ["réduire l'erreur moyenne d'au moins 10 %", 'the model must cut the MAE by 10%'],
     [('je confirme le critère', ['error', 'reduction', 'min_gain']),
      ("réduire l'erreur", ['min_gain'])]),
    (BINARY, 'preprocessing', DEFAULT_PREP,
     ['on garde les variables telles quelles, sans transformation',
      'use the default preparation, nothing changed'],
     [('je valide', ['no_preprocessing'])]),
    (BINARY, 'preprocessing', PREP,
     ['un indicateur pour les valeurs manquantes et un log de balance',
      'add a missing-value indicator and a log transform of balance'],
     [('un log de balance', ['missing_indicator']),
      ('I agree', ['missing_indicator', 'log_transform'])]),
    (BINARY, 'policy', 'capacity:100',
     ['appeler les 100 meilleurs parce que le centre a cette capacité',
      'call the top 100 because that is the capacity of the desk',
      'les cent premiers clients'],
     [(OWNER_PT, ['capacity', 'rule_number']),
      ('les meilleurs clients', ['rule_number'])]),
    (BINARY, 'policy', 'threshold:0.3',
     ['un seuil de 0,3 sur le score', 'act on every score above 30%'],
     [('je confirme', ['threshold', 'rule_number']), ('un seuil sur le score', ['rule_number'])]),
    (REGRESSION, 'model_choice', 'fit.linear',
     ['je choisis le modèle linéaire', 'adopt the linear model'],
     [('je confirme', ['linear_model'])]),
    (REGRESSION, 'model_choice', 'fit.baseline',
     ['on garde la moyenne', 'keep the mean baseline'],
     [('I agree', ['baseline_model'])]),
    (BINARY, 'conclusion', {'verdict': 'adopt_policy', 'text': 'Adopt the rule.'},
     ["j'adopte la règle", 'we should use the rule'],
     [('je confirme', ['adopt'])]),
    (BINARY, 'conclusion', {'verdict': 'keep_baseline', 'text': 'Keep the baseline.'},
     ['garder la référence', 'keep the baseline, no model'],
     [('je confirme', ['keep_baseline'])]),
    (BINARY, 'conclusion', {'verdict': 'inconclusive', 'text': 'Inconclusive.'},
     ["ce n'est pas concluant", 'the evidence is not enough'],
     [('je confirme', ['inconclusive'])]),
]


@pytest.mark.parametrize('state, decision, value, accepted, refused', MATRIX,
                         ids=[f'{m[1]}-{i}' for i, m in enumerate(MATRIX)])
def test_concept_matrix(state, decision, value, accepted, refused):
    proposal = _proposal(decision, value)
    for words in accepted:
        found = concepts.check(state, proposal, words)
        assert found['missing'] == [], (decision, words, found)
    for words, missing in refused:
        found = concepts.check(state, proposal, words)
        assert [m['concept'] for m in found['missing']] == missing, (decision, words, found)
        assert all(m['hint'] and m['hint'] != m['concept'] for m in found['missing'])


def test_a_prediction_moment_restates_through_its_label():
    proposal = _proposal('prediction_time', 'At the renewal of the membership',
                         labels={'fr': 'Au moment du renouvellement de l’adhésion.'})
    assert concepts.check(BINARY, proposal, 'au moment du renouvellement')['missing'] == []
    assert concepts.check(BINARY, proposal, 'at the renewal')['missing'] == []
    missing = concepts.check(BINARY, proposal, 'au moment du départ')['missing']
    assert [m['concept'] for m in missing] == ['event']


def test_an_unmapped_decision_needs_a_restatement():
    proposal = _proposal('final_test', {'open': True}, 'You open the final test once.')
    assert [i['concept'] for i in concepts.concept_map(BINARY, proposal)] == ['restatement']
    assert concepts.check(BINARY, proposal, 'je confirme')['missing'][0]['concept'] == 'restatement'
    assert concepts.check(BINARY, proposal, 'open the final test once')['missing'] == []


def test_endorsement_words_never_say_a_concept():
    proposal = _proposal('split', {'method': 'stratified_random', 'validation_fraction': 0.3,
                                   'seed': 7})
    said = concepts.check(BINARY, proposal, 'je valide, je confirme')['said']
    assert 'validation' not in said


def test_reason_connector_and_mode_names():
    assert concepts.has_reason_connector('appeler les 100 meilleurs parce que le centre suit')
    assert concepts.has_reason_connector('call the top 100 since the desk is small')
    assert not concepts.has_reason_connector('appeler les 100 meilleurs, le centre suit')
    assert concepts.mode_named('express', 'passons en mode rapide')
    assert concepts.mode_named('guided', 'je préfère le mode guidé')
    assert not concepts.mode_named('express', 'oui, je veux changer')


# --- the CLI: modes, the owner's sentences, R3 by mode -----------------------------------

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


def _mode(flow, mode, words=None, expect=0):
    extra = ('--user-words', words) if words is not None else ()
    return flow.call('mode', 'set', mode, *extra, '--request-id', flow.rid(),
                     '--expected-revision', flow.rev(), '--study', flow.study, expect=expect)


def _to(flow, mode):
    """Set ``mode`` from guided: training is a raise (no words), express a lowering."""
    if mode == st.TRAINING:
        _mode(flow, mode)
    elif mode == st.EXPRESS:
        _mode(flow, mode, 'je veux passer en mode express')


@pytest.mark.parametrize('mode', st.MODES)
def test_owner_sentence_by_mode(flow, mode):
    _to(flow, mode)
    pid = _propose(flow, 'prediction_time', PT, PT_RESTATEMENT)
    rev = flow.rev()
    if mode == st.TRAINING:
        out = _confirm(flow, pid, OWNER_PT, expect=2)
        error = out['error']
        assert error['code'] == 'paraphrase_required'
        details = error['details']
        assert [m['concept'] for m in details['missing']] == ['timing_before', 'event']
        assert details['mode'] == 'training' and details['decision_id'] == 'prediction_time'
        assert details['user_words'] == OWNER_PT and details['said'] == []
        junior = details['junior_message']
        assert 'training mode' in junior and 'relative to the event' in junior
        assert not any(w in junior for w in ('--', 'prediction_time', 'decide confirm'))
        assert flow.rev() == rev
        done = _confirm(flow, pid, 'oui, avant le premier appel de la campagne')
        assert done['result']['basis'] == st.RESTATED
    else:
        done = _confirm(flow, pid, OWNER_PT)
        assert done['result']['basis'] == st.ENDORSED
    assert done['result']['mode'] == mode
    assert flow.state()['decisions']['prediction_time']['confirmation']['mode'] == mode
    assert flow.view()['decisions']['prediction_time']['confirmation']['mode'] == mode


@pytest.mark.parametrize('mode', st.MODES)
@pytest.mark.parametrize('words', ('ok', 'oui', 'oui mais je veux réfléchir', 'avant ?',
                                   'non, pas avant le premier appel'))
def test_the_guided_refusals_hold_in_every_mode(flow, mode, words):
    _to(flow, mode)
    pid = _propose(flow, 'prediction_time', PT, PT_RESTATEMENT)
    out = _confirm(flow, pid, words, expect=2)
    assert out['error']['code'] == 'ambiguous_confirmation', (mode, words)
    assert out['error']['details']['reason'] in ('bare_acknowledgement', 'conditional_reply',
                                                 'question_reply', 'negative_reply')


def test_training_keeps_the_unrelated_reply_classifier(flow):
    _to(flow, st.TRAINING)
    pid = _propose(flow, 'prediction_time', PT, PT_RESTATEMENT)
    out = _confirm(flow, pid, 'yes, I like pizza', expect=2)
    assert out['error']['details']['reason'] == 'unrelated_reply'


@pytest.fixture(scope='module')
def fitted(tmp_path_factory, synthetic_case_dir):
    return fk.prepare(synthetic_case_dir, tmp_path_factory.mktemp('fitted') / 'study')


@pytest.fixture
def pause3(fitted, tmp_path, synthetic_case_dir):
    study = fk.clone(fitted, tmp_path / 'p3')
    f = Flow(study, synthetic_case_dir, prefix='m')
    f.run('policy.evaluate', '--rule', 'capacity:20')
    return f


def test_training_policy_needs_the_rule_and_a_reason_connector(pause3):
    _mode(pause3, 'training')
    pid = _propose(pause3, 'policy', 'capacity:20', 'You call the 20 highest-scored members.')
    out = _confirm(pause3, pid, 'oui je confirme cela', expect=2)
    assert out['error']['code'] == 'paraphrase_required'
    assert [m['concept'] for m in out['error']['details']['missing']] == ['capacity',
                                                                           'rule_number']
    # Guided accepts any content word as a reason; training wants a reason clause.
    out = _confirm(pause3, pid, 'appeler les 20 meilleurs, le service suit', expect=2)
    assert out['error']['code'] == 'reason_required'
    assert out['error']['details']['mode'] == 'training'
    done = _confirm(pause3, pid, 'appeler les 20 meilleurs parce que le service a cette capacité')
    assert done['result']['status'] == 'confirmed' and done['result']['mode'] == 'training'
    assert done['result']['basis'] == st.RESTATED


def test_guided_policy_takes_a_clause_beyond_the_value_as_a_reason(pause3):
    pid = _propose(pause3, 'policy', 'capacity:20', 'You call the 20 highest-scored members.')
    done = _confirm(pause3, pid, 'appeler les 20 meilleurs, le service suit')
    assert done['result']['mode'] == 'guided'


# --- R3 by mode -------------------------------------------------------------------------

@pytest.mark.parametrize('mode', st.MODES)
def test_words_that_contradict_the_value_by_mode(bank, mode):
    bank.decide('prediction_time', 'avant le premier appel de la campagne',
                words='oui, avant le premier appel')
    _to(bank, mode)
    value = fk.availability(fk.BANK, duration='not_available',
                            contact='available_at_prediction')
    pid = _propose(bank, 'feature_availability', value,
                   'You exclude duration; contact and the others are known then.')
    rev = bank.rev()
    if mode == st.TRAINING:
        out = _confirm(bank, pid, OWNER_FA, expect=2)
        error = out['error']
        assert error['code'] == 'words_contradict_value'
        assert [(w['variable'], w['said'], w['value']) for w in error['details']['warnings']] \
            == [('contact', 'exclude', 'available_at_prediction')]
        assert 'contact' in error['details']['junior_message']
        assert bank.rev() == rev
        assert bank.state()['decisions']['feature_availability']['status'] == 'proposed'
    elif mode == st.GUIDED:
        # WP-A9 (H3): the guided stop; confirmed once the agent raised the point.
        out = _confirm(bank, pid, OWNER_FA, expect=2)
        assert out['error']['code'] == 'words_contradict_value'
        assert bank.rev() == rev
        done = _confirm(bank, pid, OWNER_FA, '--agent-concern', 'contact is kept by the value')
        assert done['result']['status'] == 'confirmed'
        assert [w['variable'] for w in done['result']['warnings']] == ['contact']
    else:
        done = _confirm(bank, pid, OWNER_FA)
        assert done['result']['status'] == 'confirmed'
        assert [w['variable'] for w in done['result']['warnings']] == ['contact']


def test_training_accepts_the_owner_availability_sentence_when_it_matches(bank):
    bank.decide('prediction_time', 'avant le premier appel de la campagne',
                words='oui, avant le premier appel')
    _to(bank, st.TRAINING)
    value = fk.availability(fk.BANK, duration='not_available', contact='not_available')
    pid = _propose(bank, 'feature_availability', value, 'You exclude duration and contact.')
    assert sorted(k for k, v in value.items() if v == 'not_available') == ['contact', 'duration']
    done = _confirm(bank, pid, OWNER_FA, '--agent-concern',
                    'Inflation applies to campaign, not to contact.')
    assert done['result']['status'] == 'confirmed' and done['result']['warnings'] == []
    assert done['result']['basis'] == st.RESTATED and done['result']['mode'] == 'training'
    # The misattributed reason is the agent's stop (R3); the engine records the concern.
    assert done['result']['agent_concern'].startswith('Inflation')


# --- express: standing delegation of the framing decisions ------------------------------

def _framing(flow):
    flow.decide('prediction_time', 'before the first contact of the renewal cycle')
    flow.decide('feature_availability', fk.availability(flow.case_dir))
    flow.decide('split', fk.SPLIT)


def _delegate(flow, decision, value, scope='standing', expect=0):
    pid = _propose(flow, decision, value, 'My recommended default: as stated in the value.')
    return _confirm(flow, pid, STANDING, '--basis', 'delegated_default', '--delegation-scope',
                    scope, expect=expect)


@pytest.mark.parametrize('decision', ('success_criterion', 'preprocessing'))
def test_express_standing_delegation_covers_the_framing_decisions(flow, decision):
    # B6c: a guided standing delegation covers the default preprocessing (below); a
    # preparation that changes something is covered only in express.
    value = fk.criterion(flow.state()) if decision == 'success_criterion' \
        else {**governance.DEFAULT_PREPROCESSING, 'missing': 'indicator'}
    _framing(flow)
    refused = _delegate(flow, decision, value, expect=2)            # guided: not covered
    assert refused['error']['details']['reason'] == 'delegation_not_given_at_this_pause'
    assert decision not in refused['error']['details']['standing_covers']
    _mode(flow, 'express', 'on passe en mode express')
    done = _delegate(flow, decision, value)
    assert done['result']['basis'] == st.DELEGATED_DEFAULT
    assert done['result']['delegation_scope'] == 'standing' and done['result']['mode'] == 'express'
    delegated = next(i for i in flow.view()['not_yet_defensible'] if i['id'] == 'delegated_decisions')
    assert decision in delegated['decisions']


def test_a_guided_standing_delegation_covers_the_default_preprocessing_only(flow):
    """B6c (integrator decision, ADR 0005): fewer pauses for a junior who delegated; a
    preparation that changes anything still needs their words."""
    _framing(flow)
    criterion = _propose(flow, 'success_criterion', fk.criterion(flow.state()),
                         'You fix the minimum gain as stated.')
    _confirm(flow, criterion, 'Yes, that minimum gain is what makes the model worth it')
    changed = {**governance.DEFAULT_PREPROCESSING, 'caps': {}, 'missing': 'indicator'}
    refused = _delegate(flow, 'preprocessing', changed, expect=2)
    assert refused['error']['details']['reason'] == 'delegation_not_given_at_this_pause'
    assert 'when it is the engine\'s default' in refused['error']['message']
    done = _delegate(flow, 'preprocessing', dict(governance.DEFAULT_PREPROCESSING))
    assert done['result']['basis'] == st.DELEGATED_DEFAULT and done['result']['mode'] == 'guided'
    assert done['result']['delegation_scope'] == 'standing'
    delegated = next(i for i in flow.view()['not_yet_defensible']
                     if i['id'] == 'delegated_decisions')
    assert 'preprocessing' in delegated['decisions']


def test_express_never_covers_the_policy_or_the_conclusion(pause3):
    _mode(pause3, 'express', 'mode express, s’il te plaît')
    pid = _propose(pause3, 'policy', 'capacity:20',
                   'My recommended default: you call the 20 highest-scored members.')
    out = _confirm(pause3, pid, STANDING, '--basis', 'delegated_default', '--delegation-scope',
                   'standing', expect=2)
    assert out['error']['details']['reason'] == 'delegation_not_given_at_this_pause'
    assert out['error']['details']['standing_covers'] == list(
        st.EXPRESS_STANDING_DELEGATION_DECISIONS)
    assert out['error']['details']['mode'] == 'express'
    # Express keeps the guided reason rule for its own words.
    out = _confirm(pause3, pid, 'oui je confirme cela', expect=2)
    assert out['error']['code'] == 'reason_required'
    assert set(st.EXPRESS_STANDING_DELEGATION_DECISIONS) & {'policy', 'model_choice',
                                                           'conclusion', 'final_test'} == set()


# --- mode set ---------------------------------------------------------------------------

def test_raising_the_strictness_needs_no_words(flow):
    out = _mode(flow, 'training')
    assert out['result'] == {'mode': 'training', 'previous': 'guided', 'user_words': None,
                             'changed': True}
    assert flow.state()['mode_history'][-1]['user_words'] is None
    assert st.validate_state(flow.state()) == []


def test_lowering_the_strictness_needs_words_that_name_the_mode(flow):
    _mode(flow, 'training')
    rev = flow.rev()
    missing = _mode(flow, 'guided', expect=2)
    assert missing['error']['code'] == 'ambiguous_confirmation'
    assert missing['error']['details']['reason'] == 'missing_user_words'
    assert (missing['error']['details']['previous'], missing['error']['details']['mode']) \
        == ('training', 'guided')
    unrelated = _mode(flow, 'guided', "oui je confirme cela", expect=2)
    assert unrelated['error']['details']['reason'] == 'unrelated_reply'
    bare = _mode(flow, 'guided', 'ok', expect=2)
    assert bare['error']['details']['reason'] == 'bare_acknowledgement'
    assert flow.rev() == rev and flow.state()['mode'] == 'training'
    done = _mode(flow, 'guided', 'je préfère revenir au mode guidé')
    assert done['result']['previous'] == 'training' and done['result']['changed'] is True
    express = _mode(flow, 'express', 'on passe en mode rapide')
    assert express['result']['mode'] == 'express'
    back = _mode(flow, 'training')                                  # a raise again
    assert back['result']['user_words'] is None
    assert [(h['previous'], h['mode']) for h in flow.state()['mode_history']] == [
        ('guided', 'training'), ('training', 'guided'), ('guided', 'express'),
        ('express', 'training')]


def test_keeping_the_same_mode_needs_words(flow):
    out = _mode(flow, 'guided', expect=2)
    assert out['error']['details']['reason'] == 'missing_user_words'


def test_a_lowering_without_words_is_an_invalid_history(flow):
    assert st.lowers_strictness('guided', 'express') and st.raises_strictness('express', 'guided')
    assert not st.raises_strictness('guided', 'guided')
    assert not st.lowers_strictness('guided', 'training')
    _mode(flow, 'express', 'je veux le mode express')
    state = flow.state()
    assert st.validate_state(state) == []
    state['mode_history'][-1]['user_words'] = None
    assert [p['path'] for p in st.validate_state(state)] == ['mode_history.0']


def test_mode_changes_never_invalidate_confirmations(flow):
    pid = _propose(flow, 'prediction_time', PT, PT_RESTATEMENT)
    _confirm(flow, pid, OWNER_PT)
    before = flow.state()['decisions']['prediction_time']
    for mode, words in (('training', None), ('express', 'mode express maintenant'),
                        ('guided', 'retour au mode guidé')):
        _mode(flow, mode, words)
        after = flow.state()['decisions']['prediction_time']
        assert after['status'] == 'confirmed' and after['confirmation'] == before['confirmation']
        assert after['confirmation']['mode'] == 'guided'
    unconfirmed = next(i for i in flow.view()['not_yet_defensible']
                       if i['id'] == 'unconfirmed_decisions')
    assert 'prediction_time' not in unconfirmed['decisions']


def test_a_confirmation_before_v0_2b_has_no_mode_and_stays_valid(flow):
    pid = _propose(flow, 'prediction_time', PT, PT_RESTATEMENT)
    _confirm(flow, pid, OWNER_PT)
    state = flow.state()
    state['decisions']['prediction_time']['confirmation'].pop('mode')
    assert st.validate_state(state) == []
    state['decisions']['prediction_time']['confirmation']['mode'] = 'turbo'
    assert any(p['path'].endswith('.mode') for p in st.validate_state(state))
