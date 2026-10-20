"""WP-A9 fresh-review fixes of the guided confirmation (B1, H1, H3).

* B1: a reply that accepts one part of a multi-part proposal and refuses another is refused
  (``conditional_reply``): "ok pour le plafonnement, pas pour le log", "Yes for the caps, not
  for the log transform."; "all features except X" stays accepted when the value excludes X.
* H1: an off-topic remark that shares one common noun with the proposal ("oui, la pizza du
  client est bonne") does not confirm; on a trade-off, "je confirme, j'aime la pizza" and
  "ok, 10%" give no reason (recorded as ``reason_given: false`` since v0.3, WP-B; they were
  ``reason_required`` before). The owner's sentences still confirm.
* H3: covered in ``test_guided_confirmation.py`` (the guided stop on a contradiction).

Studies live in ``tmp_path`` from the synthetic case.
"""
from __future__ import annotations

import json

import pytest

from mlkit.study import confirm as cf, state as st

import flowkit as fk
from flowkit import Flow

PT = 'Before the first call to the client'
PT_RESTATEMENT = 'You predict before the first call to the client.'
PREP = {'missing': 'none', 'rare_category_min_rows': 0,
        'caps': {'fines_outstanding': [0.01, 0.99]}, 'log_transform': ['membership_days']}
PREP_EN = 'You cap fines_outstanding at the 1st and 99th percentiles and log-transform ' \
          'membership_days.'
PREP_FR = 'Vous plafonnez fines_outstanding aux 1er et 99e centiles et passez ' \
          'membership_days au log.'


def _propose(flow, decision, value, restatement, *extra):
    return flow.call('decide', 'propose', decision, '--value-json', json.dumps(value),
                     '--restatement', restatement, '--rationale', 'It fits the scenario.',
                     *extra, '--request-id', flow.rid(), '--expected-revision', flow.rev(),
                     '--study', flow.study)['result']['proposal_id']


def _confirm(flow, pid, words, *extra, expect=0):
    return flow.call('decide', 'confirm', pid, '--user-words', words, *extra, '--request-id',
                     flow.rid(), '--expected-revision', flow.rev(), '--study', flow.study,
                     expect=expect)


def _reason(out):
    err = out['error']
    return err['details'].get('reason') or err['code']


@pytest.fixture(scope='module')
def at_split(tmp_path_factory, synthetic_case_dir):
    study = tmp_path_factory.mktemp('a9') / 'study'
    flow = Flow(study, synthetic_case_dir, prefix='a')
    flow.init()
    flow.pauses(model_decisions=False)
    flow.decide('success_criterion', fk.criterion(flow.state()))
    flow.run('split')
    return study


@pytest.fixture
def prep(at_split, tmp_path, synthetic_case_dir):
    return Flow(fk.clone(at_split, tmp_path / 's'), synthetic_case_dir, prefix='b')


@pytest.fixture
def fresh(tmp_path, synthetic_case_dir):
    f = Flow(tmp_path / 'fresh', synthetic_case_dir)
    f.init()
    return f


# --- B1: partial refusals -------------------------------------------------------------------

@pytest.mark.parametrize('words', ('ok pour le plafonnement, pas pour le log',
                                   'Yes for the caps, not for the log transform.',
                                   'oui pour le plafonnement, pas de log',
                                   'je confirme les plafonds, sans le log',
                                   'oui, plafonner oui, mais le log non merci'))
def test_a_partial_refusal_never_confirms(prep, words):
    pid = _propose(prep, 'preprocessing', PREP, PREP_EN, '--restatement-fr', PREP_FR)
    rev = prep.rev()
    out = _confirm(prep, pid, words, expect=2)
    assert out['error']['code'] == 'ambiguous_confirmation'
    assert out['error']['details']['reason'] == 'conditional_reply', words
    assert prep.rev() == rev
    assert prep.state()['decisions']['preprocessing']['status'] == 'proposed'


@pytest.mark.parametrize('words', ('ok pour le plafonnement et le log',
                                   'Yes, cap fines_outstanding and log membership_days.',
                                   'je confirme'))
def test_a_whole_acceptance_of_a_multi_part_proposal_confirms(prep, words):
    pid = _propose(prep, 'preprocessing', PREP, PREP_EN, '--restatement-fr', PREP_FR)
    assert _confirm(prep, pid, words)['result']['status'] == 'confirmed', words


def test_a_negation_the_value_agrees_with_is_a_restatement(prep):
    value = dict(PREP, log_transform=[])
    pid = _propose(prep, 'preprocessing', value,
                   'You cap fines_outstanding and apply no log transform.')
    done = _confirm(prep, pid, 'oui, on plafonne fines_outstanding, pas de log')
    assert done['result']['status'] == 'confirmed'


def test_all_features_except_an_excluded_one_is_accepted(fresh, synthetic_case_dir):
    fresh.decide('prediction_time', PT, words='Yes, before the first call to the client.')
    value = fk.availability(synthetic_case_dir)
    excluded = sorted(k for k, v in value.items() if v == 'not_available')
    kept = sorted(k for k, v in value.items() if v != 'not_available')
    assert excluded and kept
    pid = _propose(fresh, 'feature_availability', value,
                   f'You use every variable except {excluded[0]}.')
    out = _confirm(fresh, pid, f'yes, all the variables except {kept[0]}', expect=2)
    assert out['error']['details']['reason'] == 'conditional_reply'
    assert out['error']['details']['partial'] == {'negator': 'except', 'part': kept[0]}
    done = _confirm(fresh, pid, f'yes, all the variables except {excluded[0]}')
    assert done['result']['status'] == 'confirmed'


def test_partial_refusal_is_a_pure_function():
    prop = {'decision_id': 'preprocessing', 'value': PREP, 'restatement': PREP_EN,
            'labels': {'fr': PREP_FR}}
    pr = cf.partial_refusal
    assert pr('ok pour le plafonnement, pas de log', prop) == {'negator': 'pas', 'part': 'log'}
    assert pr('yes, no cap please', prop) == {'negator': 'no', 'part': 'cap'}
    assert pr('oui, plafonner et passer au log', prop) is None
    assert pr("je confirme, ce n'est pas connu avant", prop) is None       # descriptive
    fa = {'decision_id': 'feature_availability', 'restatement': 'r',
          'value': {'duration': 'not_available', 'contact': 'available_at_prediction'}}
    assert pr('everything except duration', fa) is None
    assert pr('sans duration', fa) is None
    assert pr('everything except contact', fa) == {'negator': 'except', 'part': 'contact'}
    # Single-part decisions are not checked this way ("not for" stays conditional anywhere).
    assert pr('yes, not after the call', {'decision_id': 'prediction_time', 'value': 'x',
                                          'restatement': 'r'}) is None
    assert cf.is_conditional('ok pour le plafonnement, pas pour le log')
    assert cf.is_conditional('Yes for the caps, not for the log transform.')


# --- H1: off-topic remarks and non-reasons ----------------------------------------------------

@pytest.mark.parametrize('words', ('oui, la pizza du client est bonne',
                                   'ok, the client was nice today',
                                   'yes, I like pizza'))
def test_one_shared_common_noun_does_not_confirm(fresh, words):
    pid = _propose(fresh, 'prediction_time', PT, PT_RESTATEMENT)
    out = _confirm(fresh, pid, words, expect=2)
    assert out['error']['details']['reason'] == 'unrelated_reply', words
    assert fresh.state()['decisions']['prediction_time']['status'] == 'proposed'


@pytest.mark.parametrize('words', ('oui je confirme cela', 'oui, avant le premier appel du client',
                                   'Yes, before the first call.',
                                   'We predict before the first call.'))
def test_the_owner_sentence_and_restatements_still_confirm(fresh, words):
    pid = _propose(fresh, 'prediction_time', PT, PT_RESTATEMENT,
                   '--restatement-fr', 'Vous prédisez avant le premier appel au client.')
    assert _confirm(fresh, pid, words)['result']['status'] == 'confirmed', words


@pytest.fixture(scope='module')
def evaluated(tmp_path_factory, synthetic_case_dir):
    study = fk.prepare(synthetic_case_dir, tmp_path_factory.mktemp('h1') / 'study')
    flow = Flow(study, synthetic_case_dir, prefix='e')
    flow.run('policy.evaluate', '--rule', 'share:0.1', '--rule', 'capacity:20')
    return study


@pytest.fixture
def pause3(evaluated, tmp_path, synthetic_case_dir):
    return Flow(fk.clone(evaluated, tmp_path / 'p3'), synthetic_case_dir, prefix='g')


@pytest.mark.parametrize('rule, restatement, words', (
    ('capacity:20', 'You call the 20 highest-scored members.', "je confirme, j'aime la pizza"),
    ('share:0.1', 'You call the top 10% of the scored members.', 'ok, 10%'),
    ('capacity:20', 'You call the 20 highest-scored members.', 'yes, 20'),
))
def test_a_non_reason_on_the_policy_is_recorded_as_no_reason(pause3, rule, restatement, words):
    # v0.3 (WP-B, R27): the guided mode no longer requires a reason; a non-reason is
    # recorded as "no reason given" (reason_given false) instead of refused.
    pid = _propose(pause3, 'policy', rule, restatement)
    done = _confirm(pause3, pid, words)['result']
    assert done['status'] == 'confirmed' and done['reason_given'] is False, words


def test_an_off_topic_reply_on_the_policy_is_still_refused(pause3):
    pid = _propose(pause3, 'policy', 'capacity:20', 'You call the 20 highest-scored members.')
    rev = pause3.rev()
    out = _confirm(pause3, pid, 'oui, la pizza du client est bonne', expect=2)
    assert _reason(out) == 'unrelated_reply'
    assert pause3.rev() == rev


@pytest.mark.parametrize('words', ('je confirme parce que le centre a cette capacité',
                                   'yes, the desk handles twenty calls',
                                   'ok, 10% car le budget couvre un client sur dix',
                                   'oui, dix pour cent, le service suit'))
def test_a_real_reason_confirms_the_policy(pause3, words):
    rule = 'capacity:20' if 'twenty' in words or 'centre' in words else 'share:0.1'
    restatement = ('You call the 20 highest-scored members.' if rule == 'capacity:20'
                   else 'You call the top 10% of the scored members.')
    pid = _propose(pause3, 'policy', rule, restatement)
    done = _confirm(pause3, pid, words)['result']
    assert done['status'] == 'confirmed' and done['reason_given'] is True, words


def test_reason_and_relation_are_pure_functions():
    topic = cf.Topic('capacity:20', ['You call the 20 highest-scored members.'],
                     domain=['desk', 'budget*'])
    assert not cf.has_reason('ok, 20', topic)
    assert not cf.has_reason("je confirme, j'aime la pizza", topic)
    assert cf.has_reason('yes, the desk handles twenty calls', topic)
    assert cf.has_reason('je confirme car le service est limité')        # a connector alone
    assert not cf.has_reason('oui je confirme cela')
    pt = cf.Topic(PT, [PT_RESTATEMENT])
    assert not cf.relates_to('oui, la pizza du client est bonne', pt)
    assert cf.relates_to('oui, avant le premier call du client', pt)
    assert cf.relates_to('Right: we know nothing after the first call.', pt)
    assert not cf.relates_to('the client', pt)                     # no agreement, one word
    assert st.GUIDED == 'guided'
