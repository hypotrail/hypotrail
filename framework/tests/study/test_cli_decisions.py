"""``hypotrail init``, ``status``, ``plan``, and ``decide`` through real processes (WP1.4).

Every CLI call is a fresh ``python -m mlkit.study.cli`` process whose working
directory is a temporary directory outside the repository, so nothing relies on the
current directory or on ``OSML_ROOT``. Studies live in ``tmp_path``; the committed
Bank case is only read.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from mlkit.study import case as c, commands as cmd, preconditions as pre, state as st

FRAMEWORK = Path(__file__).resolve().parents[2]
REPO = FRAMEWORK.parent
BANK = REPO / 'use-cases' / 'bank-marketing'
PT = 'before the first reminder is sent'
SPLIT = {'method': 'stratified_random', 'validation_fraction': 0.3, 'seed': 20261017}


def _env(**extra) -> dict:
    path = [str(FRAMEWORK)] + [p for p in os.environ.get('PYTHONPATH', '').split(os.pathsep) if p]
    return {**os.environ, 'PYTHONPATH': os.pathsep.join(path), **extra}


def hyp(*args, cwd, env=None, expect=None):
    """Run one CLI process; return ``(exit code, parsed JSON stdout)``."""
    proc = subprocess.run([sys.executable, '-m', 'mlkit.study.cli', *map(str, args)],
                          capture_output=True, text=True, cwd=cwd, env=env or _env(), timeout=120)
    assert proc.stderr == '', proc.stderr
    out = proc.stdout.strip().splitlines()
    assert len(out) == 1, proc.stdout                       # one JSON document
    payload = json.loads(out[0])
    if expect is not None:
        assert proc.returncode == expect, payload
    return proc.returncode, payload


@pytest.fixture
def work(tmp_path):
    folder = tmp_path / 'cwd'
    folder.mkdir()
    return folder


@pytest.fixture
def study(tmp_path, work, synthetic_case_dir):
    target = tmp_path / 'study'
    hyp('init', '--case', synthetic_case_dir, '--study', target, cwd=work, expect=0)
    return target


@pytest.fixture(scope='module')
def features(synthetic_case_dir):
    return cmd.candidate_features(c.load_case(synthetic_case_dir))


def _status(study, work):
    return hyp('status', '--study', study, '--json', cwd=work, expect=0)[1]


def propose(study, work, decision, *, value=None, value_json=None, rid, rev, expect=0,
            restatement=None):
    flag = ['--value', value] if value_json is None else ['--value-json', json.dumps(value_json)]
    return hyp('decide', 'propose', decision, *flag,
               '--restatement', restatement or f'You decide {decision} as stated.',
               '--rationale', 'It matches the scenario.', '--request-id', rid,
               '--expected-revision', rev, '--study', study, cwd=work, expect=expect)[1]


def confirm(study, work, pid, words, *, rid, rev, expect=0, extra=()):
    return hyp('decide', 'confirm', pid, '--user-words', words, '--request-id', rid,
               '--expected-revision', rev, *extra, '--study', study, cwd=work, expect=expect)[1]


def _availability(features, **overrides):
    value = {f: 'available_at_prediction' for f in features}
    value.update(overrides)
    return value


def _decide(study, work, decision, *, rid, words, value=None, value_json=None):
    rev = _status(study, work)['revision']
    pid = propose(study, work, decision, value=value, value_json=value_json, rid=f'{rid}-p',
                  rev=rev)['result']['proposal_id']
    return confirm(study, work, pid, words, rid=f'{rid}-c', rev=rev + 1)


# --- init -------------------------------------------------------------------------------

def test_init_creates_revision_one_and_never_overwrites(study, work, synthetic_case_dir):
    view = _status(study, work)['view']
    assert view['revision'] == 1
    assert all(d['status'] == 'open' for d in view['decisions'].values())
    assert view['open_proposals'] == [] and view['next_action']['kind'] == 'propose'
    assert view['exposure']['by_purpose'] == {'structural_inspection': 300}
    code, again = hyp('init', '--case', synthetic_case_dir, '--study', study, cwd=work)
    assert code == 2 and again['error']['code'] == 'state_exists'
    assert _status(study, work)['revision'] == 1


def test_init_ignores_answers_yaml_and_project_json_statuses(tmp_path, work, synthetic_case_dir):
    case_dir = tmp_path / 'case-with-companion-files'
    shutil.copytree(synthetic_case_dir, case_dir)
    (case_dir / 'answers.yaml').write_text(
        'prediction_time: {value: at renewal, status: confirmed}\n'
        'split: {value: random, status: confirmed}\n', encoding='utf-8')
    (case_dir / 'project.json').write_text(json.dumps(
        {'facts': [{'id': 'prediction_time', 'value': 'at renewal', 'status': 'confirmed'}],
         'decisions': {'policy': {'value': 'capacity:5', 'status': 'confirmed'}}}),
        encoding='utf-8')
    code, out = hyp('init', '--case', case_dir, '--study', tmp_path / 's', cwd=work)
    assert code == 0, out
    assert out['ignored_sources'] == ['answers.yaml', 'project.json']
    state = json.loads((tmp_path / 's' / '.hypotrail' / 'state.json').read_text())
    assert all(d['status'] == 'open' and d['value'] is None for d in state['decisions'].values())
    assert state['proposals'] == {}
    assert 'confirmed' not in {f['status'] for f in state['facts'].values()}
    assert 'at renewal' not in json.dumps(state)


def test_bank_init_imports_no_tutorial_confirmation(tmp_path, work):
    before = {n: hashlib.sha256((BANK / n).read_bytes()).hexdigest()
              for n in ('case.yaml', 'project.json', 'results.json')}
    code, out = hyp('init', '--case', BANK / 'case.yaml', '--study', tmp_path / 'bank', cwd=work)
    assert code == 0, out
    assert 'project.json' in out['ignored_sources'] and 'results.json' in out['ignored_sources']
    view = _status(tmp_path / 'bank', work)['view']
    assert all(d['status'] == 'open' for d in view['decisions'].values())
    assert view['dataset']['rows'] == 4521
    assert view['exposure']['rows_exposed'] == 4521
    assert view['exposure']['prior_exposure']
    statuses = {f['id']: s for s, items in view['facts']['by_status'].items() for f in items}
    assert statuses['prediction_time'] == 'scenario_assumption'
    assert 'public_data_already_explored' in [x['id'] for x in view['not_yet_defensible']]
    after = {n: hashlib.sha256((BANK / n).read_bytes()).hexdigest() for n in before}
    assert after == before


def test_init_refuses_an_unsupported_case(tmp_path, work):
    # A date time column is still unsupported (Auto MPG, regression with integer years,
    # became supported in M3).
    import flowkit as fk
    case_dir = fk.make_case(tmp_path / 'dated', n_rows=200, time=True)['case'].parent
    code, out = hyp('init', '--case', case_dir, '--study', tmp_path / 'a', cwd=work)
    assert code == 2 and out['error']['code'] == 'unsupported_capability'
    assert [r['capability'] for r in out['error']['details']['reasons']] == [
        c.CAPABILITY_TIME_SPLIT]
    assert not (tmp_path / 'a' / '.hypotrail').exists()



# --- propose and confirm ----------------------------------------------------------------

def test_propose_then_confirm_in_two_requests(study, work):
    out = propose(study, work, 'prediction_time', value=PT, rid='r1', rev=1,
                  restatement='You predict before the first reminder is sent.')
    assert out['schema'] == 'hypotrail.decide/1' and out['revision'] == 2
    pid = out['result']['proposal_id']
    view = _status(study, work)['view']
    assert view['decisions']['prediction_time']['status'] == 'proposed'
    assert [p['proposal_id'] for p in view['open_proposals']] == [pid]
    assert view['next_action'] == {**view['next_action'], 'kind': 'await_user_words',
                                   'proposal_id': pid}
    words = 'Yes: we predict before the first reminder goes out.'
    done = confirm(study, work, pid, words, rid='r2', rev=2)
    assert done['revision'] == 3 and done['result']['status'] == 'confirmed'
    decision = _status(study, work)['view']['decisions']['prediction_time']
    assert decision['status'] == 'confirmed' and decision['value'] == PT
    conf = decision['confirmation']
    assert conf['user_words'] == words and conf['channel'] == 'chat' and conf['actor'] == 'user'
    assert conf['restatement'] == 'You predict before the first reminder is sent.'
    assert conf['authenticated'] is False and conf['proposal_id'] == pid


def test_confirmation_records_channel_and_actor(study, work):
    pid = propose(study, work, 'prediction_time', value=PT, rid='r1', rev=1)['result']['proposal_id']
    confirm(study, work, pid, 'Yes, before the first reminder.', rid='r2', rev=2,
            extra=('--channel', 'webview', '--actor', 'junior'))
    conf = _status(study, work)['view']['decisions']['prediction_time']['confirmation']
    assert (conf['channel'], conf['actor']) == ('webview', 'junior')
    code, out = hyp('decide', 'confirm', pid, '--user-words', 'x y z', '--channel', 'email',
                    '--request-id', 'r3', '--expected-revision', 3, '--study', study, cwd=work)
    assert code == 2 and out['error']['code'] == 'invalid_arguments'


@pytest.mark.parametrize('words, reason', [
    ('   ', 'missing_user_words'), ('ok', 'bare_acknowledgement'),
    ('OK!', 'bare_acknowledgement'), ('garde ça', 'bare_acknowledgement'),
    ('keep that', 'bare_acknowledgement'), ("d'accord", 'bare_acknowledgement'),
    ('yes, that is right', 'bare_acknowledgement'),
])
def test_confirm_requires_open_proposal_and_user_words(study, work, words, reason):
    pid = propose(study, work, 'prediction_time', value=PT, rid='r1', rev=1)['result']['proposal_id']
    out = confirm(study, work, pid, words, rid='r2', rev=2, expect=2)
    assert out['schema'] == 'hypotrail.error/1' and out['ok'] is False
    assert out['error']['code'] == 'ambiguous_confirmation'
    assert out['error']['details']['reason'] == reason
    assert _status(study, work)['revision'] == 2


DEFAULT_RESTATEMENT = ('My recommended default: you predict before the first reminder is sent, '
                       'the earliest moment the team can act.')
DELEGATIONS = ('Use your recommended default and tell me what you assumed.',
               'Go with your recommendation.', 'je te laisse choisir', 'prends ta recommandation')


@pytest.mark.parametrize('words', DELEGATIONS)
def test_a_delegation_confirms_a_recommended_default(study, work, words):
    """D1: an explicit delegation confirms a proposal that states it is the assistant's
    recommended default; it is recorded as delegated and listed as not yet defensible."""
    pid = propose(study, work, 'prediction_time', value=PT, rid='r1', rev=1,
                  restatement=DEFAULT_RESTATEMENT)['result']['proposal_id']
    done = confirm(study, work, pid, words, rid='r2', rev=2,
                   extra=('--basis', 'delegated_default'))
    assert done['result']['status'] == 'confirmed' and done['result']['basis'] == 'delegated_default'
    view = _status(study, work)['view']
    conf = view['decisions']['prediction_time']['confirmation']
    assert conf['basis'] == 'delegated_default' and conf['user_words'] == words
    assert conf['restatement'] == DEFAULT_RESTATEMENT
    item = next(x for x in view['not_yet_defensible'] if x['id'] == 'delegated_decisions')
    assert item['decisions'] == ['prediction_time']
    assert "decided by delegation to the assistant's default, not by the junior's own " \
           'judgment' in item['text'].lower()
    state = json.loads((study / '.hypotrail' / 'state.json').read_text())
    assert st.validate_state(state) == []
    assert state['decisions']['prediction_time']['confirmation']['basis'] == 'delegated_default'


@pytest.mark.parametrize('words, reason', [
    ('ok', 'bare_acknowledgement'), ('garde ça', 'bare_acknowledgement'),
    ('yes', 'bare_acknowledgement'), ("Let's go with it.", 'bare_acknowledgement'),
    ('Before the first reminder, as you wrote.', 'not_a_delegation'),
])
def test_a_bare_or_non_delegating_reply_never_confirms_a_default(study, work, words, reason):
    pid = propose(study, work, 'prediction_time', value=PT, rid='r1', rev=1,
                  restatement=DEFAULT_RESTATEMENT)['result']['proposal_id']
    out = confirm(study, work, pid, words, rid='r2', rev=2, expect=2,
                  extra=('--basis', 'delegated_default'))
    assert out['error']['code'] == 'ambiguous_confirmation'
    assert out['error']['details']['reason'] == reason
    assert _status(study, work)['revision'] == 2


def test_a_delegation_needs_a_restatement_of_the_default(study, work):
    pid = propose(study, work, 'prediction_time', value=PT, rid='r1', rev=1,
                  restatement='You predict before the first reminder is sent.')['result']['proposal_id']
    out = confirm(study, work, pid, DELEGATIONS[0], rid='r2', rev=2, expect=2,
                  extra=('--basis', 'delegated_default'))
    assert out['error']['details']['reason'] == 'restatement_not_default'
    assert _status(study, work)['revision'] == 2


def test_a_delegation_is_never_recorded_as_explicit(study, work):
    """D1: words that delegate cannot be filed as the junior's own decision."""
    pid = propose(study, work, 'prediction_time', value=PT, rid='r1', rev=1,
                  restatement=DEFAULT_RESTATEMENT)['result']['proposal_id']
    out = confirm(study, work, pid, DELEGATIONS[1], rid='r2', rev=2, expect=2)
    assert out['error']['details']['reason'] == 'delegation_needs_basis'
    done = confirm(study, work, pid, 'Yes: we predict before the first reminder goes out.',
                   rid='r3', rev=2)
    assert done['result']['basis'] == 'explicit'
    view = _status(study, work)['view']
    assert view['decisions']['prediction_time']['confirmation']['basis'] == 'explicit'
    assert 'delegated_decisions' not in {x['id'] for x in view['not_yet_defensible']}
    code, bad = hyp('decide', 'confirm', pid, '--user-words', 'x y z', '--basis', 'guessed',
                    '--request-id', 'r4', '--expected-revision', 3, '--study', study, cwd=work)
    assert code == 2 and bad['error']['code'] == 'invalid_arguments'


def test_an_explicit_reply_confirms_a_recommended_default(study, work):
    """F4: the junior may answer a "My recommended default:" proposal in their own words;
    it is then an explicit confirmation, not a delegation."""
    pid = propose(study, work, 'prediction_time', value=PT, rid='r1', rev=1,
                  restatement=DEFAULT_RESTATEMENT)['result']['proposal_id']
    done = confirm(study, work, pid, 'Yes, before the first reminder is sent: that is when we act.',
                   rid='r2', rev=2)
    assert done['result']['status'] == 'confirmed' and done['result']['basis'] == 'explicit'
    assert done['result']['delegation_scope'] is None
    view = _status(study, work)['view']
    assert view['decisions']['prediction_time']['confirmation']['restatement'] \
        == DEFAULT_RESTATEMENT
    assert 'delegated_decisions' not in {x['id'] for x in view['not_yet_defensible']}


def test_delegation_patterns():
    for words in DELEGATIONS + ("It's up to you.", 'I leave it to you', 'Use the default.',
                                'Prenez votre recommandation.', 'je vous laisse décider'):
        assert cmd.is_delegation(words), words
    for words in ('ok', 'garde ça', 'yes', 'keep that', 'continue', "Let's go with it",
                  'Yes, your suggestion of before the first call is right.',
                  'Before the first call.', ''):
        assert not cmd.is_delegation(words), words
    assert cmd.states_default(DEFAULT_RESTATEMENT)
    assert cmd.states_default('Ma recommandation par défaut : avant le premier appel.')
    assert not cmd.states_default('You predict before the first reminder is sent.')


def test_an_old_confirmation_without_basis_reads_as_explicit(study, work):
    """A state written before the basis existed stays valid; its confirmations are explicit."""
    pid = propose(study, work, 'prediction_time', value=PT, rid='r1', rev=1)['result']['proposal_id']
    confirm(study, work, pid, 'Yes, before the first reminder.', rid='r2', rev=2)
    state = json.loads((study / '.hypotrail' / 'state.json').read_text())
    conf = state['decisions']['prediction_time']['confirmation']
    del conf['basis']
    assert st.validate_state(state) == []
    assert st.confirmation_basis(conf) == 'explicit'
    conf['basis'] = 'implied'
    assert [p['path'] for p in st.validate_state(state)] == [
        'decisions.prediction_time.confirmation.basis']


def test_confirm_without_user_words_or_without_proposal_is_refused(study, work):
    code, out = hyp('decide', 'confirm', 'p_1', '--request-id', 'r1', '--expected-revision', 1,
                    '--study', study, cwd=work)
    assert code == 2 and out['error']['code'] == 'invalid_arguments'
    out = confirm(study, work, 'p_1', 'Yes, before the first reminder.', rid='r1', rev=1, expect=2)
    assert out['error']['code'] == 'ambiguous_confirmation'
    assert out['error']['details']['reason'] == 'proposal_not_found'
    assert _status(study, work)['revision'] == 1


def test_withdrawn_superseded_and_stale_proposals_are_refused(study, work, features):
    p1 = propose(study, work, 'prediction_time', value=PT, rid='a', rev=1)['result']['proposal_id']
    out = hyp('decide', 'withdraw', p1, '--reason', 'the user hesitates', '--request-id', 'b',
              '--expected-revision', 2, '--study', study, cwd=work, expect=0)[1]
    assert out['result']['status'] == 'withdrawn' and out['result']['decision_status'] == 'open'
    refused = confirm(study, work, p1, 'Yes, before the first reminder.', rid='c', rev=3, expect=2)
    assert refused['error']['details']['reason'] == 'proposal_withdrawn'
    code, again = hyp('decide', 'withdraw', p1, '--request-id', 'd', '--expected-revision', 3,
                      '--study', study, cwd=work)
    assert code == 2 and again['error']['code'] == 'proposal_not_open'

    p2 = propose(study, work, 'prediction_time', value=PT, rid='e', rev=3)['result']['proposal_id']
    p3 = propose(study, work, 'prediction_time', value='at renewal time', rid='f',
                 rev=4)['result']
    assert p3['superseded'] == [p2]
    refused = confirm(study, work, p2, 'Yes, before the first reminder.', rid='g', rev=5, expect=2)
    assert refused['error']['details']['reason'] == 'proposal_superseded'

    # A proposal resting on a decision that then changes is stale.
    confirm(study, work, p3['proposal_id'], 'Yes, we predict at renewal time.', rid='h', rev=5)
    fa = propose(study, work, 'feature_availability', value_json=_availability(features),
                 rid='i', rev=6)['result']['proposal_id']
    _decide(study, work, 'prediction_time', value=PT, rid='j',
            words='Actually before the first reminder is sent.')
    rev = _status(study, work)['revision']
    refused = confirm(study, work, fa, 'Yes, all of them are known then.', rid='k', rev=rev,
                      expect=2)
    assert refused['error']['details']['reason'] == 'proposal_stale'
    assert refused['error']['details']['basis'] == {'prediction_time': 'at renewal time'}
    assert _status(study, work)['revision'] == rev


def test_replay_has_no_effect_and_a_reused_request_id_conflicts(study, work):
    first = propose(study, work, 'prediction_time', value=PT, rid='r1', rev=1)
    again = propose(study, work, 'prediction_time', value=PT, rid='r1', rev=1)
    assert again['replayed'] is True and first['replayed'] is False
    assert again['result'] == first['result'] and again['revision'] == first['revision'] == 2
    view = _status(study, work)['view']
    assert view['revision'] == 2 and len(view['open_proposals']) == 1
    code, out = hyp('decide', 'propose', 'prediction_time', '--value', 'at renewal',
                    '--restatement', 'You predict at renewal.', '--rationale', 'Other.',
                    '--request-id', 'r1', '--expected-revision', 1, '--study', study, cwd=work)
    assert code == 2 and out['error']['code'] == 'idempotency_conflict'


def test_stale_revision_is_refused_with_the_diff(study, work):
    propose(study, work, 'prediction_time', value=PT, rid='chat-1', rev=1)
    code, out = hyp('decide', 'propose', 'prediction_time', '--value', 'at renewal',
                    '--restatement', 'You predict at renewal.', '--rationale', 'Other.',
                    '--request-id', 'webview-1', '--expected-revision', 1, '--study', study,
                    cwd=work)
    assert code == 2 and out['error']['code'] == 'stale_revision'
    details = out['error']['details']
    assert details['expected_revision'] == 1 and details['current_revision'] == 2
    [change] = details['changes_since']
    assert change['revision'] == 2 and change['request_id'] == 'chat-1'
    assert change['action'] == 'decide.propose'


def test_fresh_process_status_restores_everything(study, work, features):
    _decide(study, work, 'prediction_time', value=PT, rid='pt',
            words='Yes, before the first reminder is sent.')
    _decide(study, work, 'feature_availability', rid='fa', words='Yes, desk follow-ups are out.',
            value_json=_availability(features, desk_followups='not_available',
                                     reminders_sent='uncertain_included'))
    pending = propose(study, work, 'split', value_json=SPLIT, rid='sp', rev=5,
                      restatement='Split 70/30 with seed 20261017, stratified on the outcome.')
    status = _status(study, work)
    assert status['schema'] == 'hypotrail.status/1' and status['revision'] == 6
    view = status['view']
    assert view['decisions']['prediction_time']['confirmation']['user_words'] == \
        'Yes, before the first reminder is sent.'
    assert view['decisions']['feature_availability']['value']['desk_followups'] == 'not_available'
    assert [p['proposal_id'] for p in view['open_proposals']] == \
        [pending['result']['proposal_id']]
    assert view['current_step'] == 'split'
    assert view['next_action']['kind'] == 'await_user_words'
    assert 'uncertain_features_included' in [x['id'] for x in view['not_yet_defensible']]
    since = hyp('status', '--since', 4, '--study', study, cwd=work, expect=0)[1]
    assert since['changed'] is True
    assert [c['revision'] for c in since['changes_since']] == [5, 6]
    quiet = hyp('status', '--since', 6, '--study', study, cwd=work, expect=0)[1]
    assert quiet['changed'] is False and quiet['changes_since'] == []
    plan = hyp('plan', '--study', study, cwd=work, expect=0)[1]
    assert plan['schema'] == 'hypotrail.plan/1'
    assert [s['status'] for s in plan['steps']][:3] == ['done', 'done', 'awaiting_confirmation']


def test_a_confirmed_change_applies_the_dependency_table(study, work, features):
    _decide(study, work, 'prediction_time', value=PT, rid='pt', words='Yes, before the reminder.')
    _decide(study, work, 'feature_availability', value_json=_availability(features), rid='fa',
            words='Yes, every listed variable is available then.')
    out = _decide(study, work, 'prediction_time', value='at renewal time', rid='pt2',
                  words='We now predict at renewal time instead.')
    inv = out['result']['invalidation']
    assert inv['mutation'] == 'prediction_time' and inv['row'] == 1
    assert inv['reconfirm_required'] == ['feature_availability']
    view = _status(study, work)['view']
    fa = view['decisions']['feature_availability']
    assert fa['status'] == 'reconfirm_required' and 'prediction_time changed' in fa['reason']
    assert fa['confirmation']['user_words'] == 'Yes, every listed variable is available then.'
    assert view['invalidations'][-1]['previous']['value'] == PT
    assert view['next_action'] == {**view['next_action'], 'kind': 'reconfirm',
                                   'decision': 'feature_availability'}


def test_three_pauses_are_preconditions(study, work, features):
    pid = propose(study, work, 'split', value_json=SPLIT, rid='s1', rev=1)['result']['proposal_id']
    out = confirm(study, work, pid, 'Yes, split before exploring.', rid='s2', rev=2, expect=2)
    assert out['error']['code'] == 'precondition_missing'
    assert {m['decision'] for m in out['error']['details']['missing']} == {
        'prediction_time', 'feature_availability'}
    _decide(study, work, 'prediction_time', value=PT, rid='pt', words='Yes, before the reminder.')
    _decide(study, work, 'feature_availability', value_json=_availability(features), rid='fa',
            words='Yes, all are known before the reminder.')
    rev = _status(study, work)['revision']
    split = propose(study, work, 'split', value_json=SPLIT, rid='s3', rev=rev)['result']
    assert split['superseded'] == [pid]
    confirm(study, work, split['proposal_id'], 'Yes, split before exploring.', rid='s4',
            rev=rev + 1)
    pol = propose(study, work, 'policy', value='capacity:100', rid='p1', rev=rev + 2,
                  restatement='Call the 100 highest-scored members.')['result']['proposal_id']
    out = confirm(study, work, pol, 'Yes, call the top hundred.', rid='p2', rev=rev + 3, expect=2)
    assert out['error']['code'] == 'precondition_missing'
    assert out['error']['details']['missing'][0]['slot'] == 'policy.evaluation'
    concl = propose(study, work, 'conclusion', value_json={'verdict': 'adopt_policy',
                                                           'text': 'Adopt the model.'},
                    rid='c1', rev=rev + 3)['result']['proposal_id']
    out = confirm(study, work, concl, 'Yes, adopt the model.', rid='c2', rev=rev + 4, expect=2)
    assert out['error']['code'] == 'precondition_missing'


def test_precondition_functions_for_phase_2(study):
    from mlkit.reliability import CommandRefused
    state = json.loads((study / '.hypotrail' / 'state.json').read_text())
    assert {m['decision'] for m in pre.missing_for_activity(state, 'split')} == {
        'prediction_time', 'feature_availability', 'split'}
    assert any(m.get('slot') == 'split' for m in pre.missing_for_activity(state, 'eda.target_rate'))
    with pytest.raises(CommandRefused) as err:
        pre.require_activity(state, 'fit.logistic')
    assert err.value.code == 'precondition_missing'
    for d in ('prediction_time', 'feature_availability', 'split'):
        state['decisions'][d]['status'] = 'confirmed'
    assert pre.missing_for_activity(state, 'split') == []
    state['current']['split'] = 'r_split'
    assert pre.missing_for_activity(state, 'eda.target_rate') == []
    assert [m['slot'] for m in pre.missing_for_activity(state, 'policy.evaluation')] == [
        'fit.baseline', 'fit.logistic']
    assert pre.missing_for_decision(state, 'conclusion',
                                    {'verdict': 'keep_baseline', 'text': 'x'}) == []
    assert pre.evaluated_rules({'params': {'rules': ['capacity:100', 'threshold:0.5']}}) == [
        'capacity:100', 'threshold:0.5']


@pytest.mark.parametrize('decision, value, code', [
    ('nonsense', '"x"', 'unknown_decision'),
    ('feature_availability', '{"holds_open": "available_at_prediction"}', 'invalid_value'),
    ('split', '{"method": "stratified_random", "validation_fraction": 1.5, "seed": 1}',
     'invalid_value'),
    ('split', '{"method": "temporal", "validation_fraction": 0.3, "seed": 1}',
     'unsupported_capability'),
    ('policy', '"top:3"', 'invalid_value'),
    ('conclusion', '{"verdict": "great", "text": "x"}', 'invalid_value'),
])
def test_invalid_proposals_are_refused_without_effect(study, work, decision, value, code):
    out = hyp('decide', 'propose', decision, '--value-json', value, '--restatement', 'You decide.',
              '--rationale', 'Because.', '--request-id', 'r1', '--expected-revision', 1,
              '--study', study, cwd=work, expect=2)[1]
    assert out['error']['code'] == code
    assert _status(study, work)['revision'] == 1


def test_literal_numbers_in_text_are_refused(study, work):
    code, out = hyp('decide', 'propose', 'policy', '--value', 'capacity:100', '--restatement',
                    'Call the 100 top members; that reaches 37% of buyers.', '--rationale', 'x',
                    '--request-id', 'r1', '--expected-revision', 1, '--study', study, cwd=work)
    assert code == 2 and out['error']['code'] == 'literal_number_in_text'
    # Since review fix L3 a refused percentage is reported as written, with its sign.
    assert out['error']['details']['numbers'] == ['37%']
    assert cmd.literal_numbers('Split 70/30, seed 20261017.', SPLIT) == []


def test_numbers_of_current_results_may_be_cited_in_a_proposal(tmp_path, synthetic_case_dir):
    """D5: a restatement may repeat the figures of a current registry result it rests on,
    traced with the matcher of ``check``; a figure of no current result is still refused,
    and a result that became stale no longer counts."""
    import flowkit as fk

    study = fk.prepare(synthetic_case_dir, tmp_path / 's', upto='split')
    flow = fk.Flow(study, synthetic_case_dir, prefix='d5-')
    train = flow.view()['results']['split']['values']['partitions']['train']
    text = (f'Predict before the first contact; the split kept {train["n_rows"]:,} training rows '
            f'with a rate of {100 * train["rate"]:.1f}%.')
    payload = flow.call('decide', 'propose', 'prediction_time', '--value', 'before the contact',
                        '--restatement', text, '--rationale', 'The split is recorded.',
                        '--request-id', flow.rid(), '--expected-revision', flow.rev(),
                        '--study', study)
    assert payload['result']['restatement'] == text
    refused = flow.call('decide', 'propose', 'prediction_time', '--value', 'before the contact',
                        '--restatement', text + ' About 4321 clients answer.',
                        '--rationale', 'x', '--request-id', flow.rid(),
                        '--expected-revision', flow.rev(), '--study', study, expect=2)
    assert refused['error']['code'] == 'literal_number_in_text'
    assert refused['error']['details']['numbers'] == ['4321']


def test_changed_dataset_is_refused_at_confirmation(tmp_path, work, synthetic_case_dir):
    case_dir = tmp_path / 'case'
    shutil.copytree(synthetic_case_dir, case_dir)
    target = tmp_path / 's'
    hyp('init', '--case', case_dir, '--study', target, cwd=work, expect=0)
    pid = propose(target, work, 'prediction_time', value=PT, rid='r1', rev=1)['result']['proposal_id']
    data = next(p for p in case_dir.iterdir() if p.suffix == '.csv')
    with open(data, 'ab') as handle:
        handle.write(b'\n')
    out = confirm(target, work, pid, 'Yes, before the first reminder.', rid='r2', rev=2, expect=2)
    assert out['error']['code'] == 'dataset_changed'


# --- surface ----------------------------------------------------------------------------

def test_study_is_mandatory_and_never_taken_from_cwd_or_osml_root(study, work):
    code, out = hyp('status', cwd=study, env=_env(OSML_ROOT=str(study)))
    assert code == 2 and out['error']['code'] == 'invalid_arguments'
    assert '--study' in out['error']['message']


def test_text_format_and_unknown_extension(study, work):
    proc = subprocess.run([sys.executable, '-m', 'mlkit.study.cli', 'status', '--study', str(study),
                           '--format', 'text'], capture_output=True, text=True, cwd=work,
                          env=_env(), timeout=60)
    assert proc.returncode == 0 and 'at revision 1' in proc.stdout
    assert 'next action: propose' in proc.stdout
    # Extension commands whose module is absent are refused (Phase 3 added render and
    # check, so the refusal is exercised on whichever extension is still missing, and on
    # a module that never exists).
    import importlib.util
    from mlkit.study import cli
    for name, module in cli.EXTENSIONS.items():
        if importlib.util.find_spec(module) is None:
            code, out = hyp(name, '--study', study, cwd=work)
            assert code == 2 and out['error']['code'] == 'unsupported_capability'
    saved = dict(cli.EXTENSIONS)
    cli.EXTENSIONS['render'] = 'mlkit.study.cmd_absent_for_test'
    try:
        outcome = cli.run(['render', '--study', str(study)])
    finally:
        cli.EXTENSIONS.clear()
        cli.EXTENSIONS.update(saved)
    assert outcome.exit_code == 2
    assert outcome.payload['error']['code'] == 'unsupported_capability'
    assert outcome.payload['error']['details'] == {'command': 'render'}


def test_console_script_is_installed():
    script = Path(sys.executable).parent / 'hypotrail'
    if not script.exists():
        pytest.skip('hypotrail console script not installed (run uv sync --project framework)')
    proc = subprocess.run([str(script), 'plan'], capture_output=True, text=True, timeout=60)
    assert proc.returncode == 2
    assert json.loads(proc.stdout)['error']['code'] == 'invalid_arguments'


def test_status_import_time_is_recorded_and_loads_no_heavy_library(study, work):
    """Plan §9 bis: a webview will call status often. Times are printed, no threshold."""
    code = ('import json, sys, time\n'
            't = time.perf_counter()\n'
            'import mlkit.study.cli\n'
            'elapsed = time.perf_counter() - t\n'
            'heavy = sorted(m for m in sys.modules if m.split(".")[0] in '
            '{"pandas", "numpy", "sklearn", "scipy"})\n'
            'print(json.dumps({"seconds": elapsed, "heavy": heavy}))\n')
    proc = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True,
                          env=_env(), cwd=work, timeout=60)
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout.strip().splitlines()[-1])
    start = time.perf_counter()
    hyp('status', '--study', study, cwd=work, expect=0)
    wall = time.perf_counter() - start
    print(f'\nimport mlkit.study.cli: {result["seconds"] * 1000:.1f} ms; '
          f'hypotrail status process: {wall * 1000:.1f} ms')
    assert result['heavy'] == []
    after = ('import json, sys\n'
             'from mlkit.study import cli\n'
             f'cli.run(["status", "--study", {str(study)!r}])\n'
             'print(json.dumps(sorted(m for m in sys.modules if m.split(".")[0] in '
             '{"pandas", "numpy", "sklearn", "scipy"})))\n')
    proc = subprocess.run([sys.executable, '-c', after], capture_output=True, text=True,
                          env=_env(), cwd=work, timeout=60)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout.strip().splitlines()[-1]) == []


def test_receipts_and_state_stay_valid(study, work):
    propose(study, work, 'prediction_time', value=PT, rid='r1', rev=1)
    state = json.loads((study / '.hypotrail' / 'state.json').read_text())
    assert st.validate_state(state) == []
    assert state['proposals']['p_1']['request_id'] == 'r1'
    assert state['proposals']['p_1']['basis'] == {}


SUMMARY_KEYS = ('schema', 'ok', 'study', 'revision', 'since', 'changed', 'goal', 'current_step',
                'plan', 'next_action', 'open_proposals', 'decisions', 'results', 'artifacts',
                'executions', 'not_yet_defensible', 'recap')


def test_status_summary_is_compact_and_complete(study, work, features):
    """D3: ``status --summary`` is the digest a chat reads first; ``--json`` is unchanged."""
    _decide(study, work, 'prediction_time', value=PT, rid='a',
            words='Yes: we predict before the first reminder goes out.')
    rev = _status(study, work)['revision']
    propose(study, work, 'feature_availability',
            value_json=_availability(features, desk_followups='not_available'), rid='b', rev=rev,
            restatement='Everything is known before the reminder except the desk follow-ups.')
    code, summary = hyp('status', '--summary', '--study', study, cwd=work, expect=0)
    full = hyp('status', '--json', '--study', study, cwd=work, expect=0)[1]
    assert tuple(summary) == SUMMARY_KEYS and summary['schema'] == 'hypotrail.summary/1'
    assert full['schema'] == 'hypotrail.status/1' and 'view' in full
    assert len(json.dumps(summary)) < len(json.dumps(full)) / 2   # far less once results exist
    assert summary['revision'] == full['revision'] == rev + 1
    assert summary['goal']['intended_use']['value'].startswith('Prioritise volunteer phone calls')
    assert summary['goal']['prediction_time'] == {'value': PT, 'source': 'decision',
                                                  'status': 'confirmed'}
    assert summary['current_step'] == 'feature_availability'
    assert summary['plan'][1] == {'id': 'feature_availability',
                                  'title': 'Decide which variables are available at prediction time',
                                  'status': 'awaiting_confirmation'}
    assert summary['next_action']['kind'] == 'await_user_words'
    [p] = summary['open_proposals']
    assert p['restatement'].startswith('Everything is known') and p['proposal_id'] == 'p_2'
    assert p['value']['not_available'] == ['desk_followups']
    pt = summary['decisions']['prediction_time']
    assert pt == {'status': 'confirmed', 'value': PT, 'basis': 'explicit', 'delegation_scope': None,
                  'user_words': 'Yes: we predict before the first reminder goes out.',
                  'reason': None, 'open_proposals': []}
    assert summary['decisions']['feature_availability']['status'] == 'proposed'
    assert summary['executions'] == {'active': [], 'interrupted': [], 'late': [],
                                     'suspected_interrupted': []}           # F1
    top = [x['id'] for x in summary['not_yet_defensible']['top']]
    assert top[0] == 'unconfirmed_decisions' and len(top) <= 5
    assert set(top) | set(summary['not_yet_defensible']['more']) == {
        x['id'] for x in full['view']['not_yet_defensible']}
    since = hyp('status', '--summary', '--since', 1, '--study', study, cwd=work, expect=0)[1]
    assert since['since'] == 1 and since['changed'] is True


def test_a_closed_pipe_writes_nothing_to_stderr(study, work):
    """D8: ``hypotrail status | head`` must not print a BrokenPipeError traceback."""
    read_end, write_end = os.pipe()
    os.close(read_end)                      # the reader is gone before the CLI writes
    try:
        proc = subprocess.run([sys.executable, '-m', 'mlkit.study.cli', 'status', '--study',
                               str(study)], stdout=write_end, stderr=subprocess.PIPE,
                              text=True, cwd=work, env=_env(), timeout=120)
    finally:
        os.close(write_end)
    assert proc.stderr == ''
    assert proc.returncode == 0
