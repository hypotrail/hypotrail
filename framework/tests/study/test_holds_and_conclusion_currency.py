"""Post-v0.1 fixes D1, D2, D5, and D6 (``docs/acceptance/runs/
claude-code-2026-10-18-p-fixes.md``; ``docs/specs/CLI-CONTRACT.md`` §5.1, §6).

* D1: a hold added to an already confirmed decision asks for it again: the decision and the
  decisions resting on it become ``reconfirm_required`` (values and words kept), so the
  study never shows "on hold" next to "confirmed".
* D2: a confirmed conclusion becomes ``reconfirm_required`` when a decision it summarizes
  changes status, value, or basis after it, and ``not_yet_defensible`` names
  ``conclusion_outdated`` until it is confirmed again.
* D5: ``decide note --withdraw`` drops a hold in the junior's words; ``status --summary``
  groups the open holds by decision.
* D6: ``inconclusive`` is allowed without an adopted policy, and named in
  ``not_yet_defensible``.

Studies live in ``tmp_path``.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent / 'deliverables'))

import phase3_study as fx  # noqa: E402
from mlkit.reliability import CommandRefused  # noqa: E402
from mlkit.study import cli, commands as cmd, read, state as st, view  # noqa: E402

STANDING = "For questions I can't answer, use your recommended default."
HOLD = "I'm still waiting for my manager's figure, so the call limit isn't confirmed."
KEEP = {'verdict': 'keep_baseline',
        'text': 'Keep the simple rule for now; the model ranks better on validation rows that '
                'were used to choose it.'}


def _run(*argv, expect=0):
    outcome = cli.run([str(a) for a in argv])
    json.dumps(outcome.payload)
    if expect is not None:
        assert outcome.exit_code == expect, outcome.payload
    return outcome.payload


def _note(study, rid, *args, expect=0):
    return _run('decide', 'note', *args, '--request-id', rid, '--expected-revision',
                read.open(study).revision, '--study', study, expect=expect)


def _state(b):
    return read.open(b.study).state


def _status(b, d):
    return _state(b)['decisions'][d]['status']


def _limits(b) -> dict:
    return {x['id']: x for x in view.build(b.study)['not_yet_defensible']}


def _confirm_policy(b):
    return b.decide('policy', fx.POLICY_RULE, 'You call the 20 highest-scored members.',
                    'Yes, twenty calls is what the desk can handle.')


def _conclude(b, value=KEEP, words='I keep the baseline and note why.'):
    return b.decide('conclusion', value, 'You keep the baseline and record the limits.', words)


@pytest.fixture
def adopted(tmp_path, synthetic_case_dir):
    """Policy adopted and conclusion confirmed, the first three decisions explicit."""
    b = fx.build(tmp_path / 'study', synthetic_case_dir, upto='policy')
    _conclude(b)
    return b


@pytest.fixture
def evaluated(tmp_path, synthetic_case_dir):
    """The policy pause: the rules evaluated, the first three decisions delegated."""
    b = fx.build(tmp_path / 'study', synthetic_case_dir, upto='models',
                 standing_delegation=STANDING)
    fx.put_policy_evaluation(b)
    return b


# --- D1 -----------------------------------------------------------------------------------

def test_a_hold_on_a_confirmed_decision_asks_for_it_and_its_dependants_again(adopted):
    b = adopted
    before = _state(b)
    assert _status(b, 'policy') == _status(b, 'conclusion') == 'confirmed'
    out = _note(b.study, 'hold-late', '--about', 'policy', '--text', HOLD)
    assert out['result']['reconfirm_required'] == ['policy', 'conclusion']
    state = _state(b)
    assert st.validate_state(state) == []
    for d in ('policy', 'conclusion'):
        dec = state['decisions'][d]
        assert dec['status'] == 'reconfirm_required' and 'n_1' in dec['reason']
        assert dec['value'] == before['decisions'][d]['value']               # value kept
        assert dec['confirmation'] == before['decisions'][d]['confirmation']  # words kept
    for d in ('prediction_time', 'feature_availability', 'split'):
        assert state['decisions'][d]['status'] == 'confirmed'
    record = state['invalidations'][-1]
    assert (record['mutation'], record['row'], record['decision_id']) == ('hold_added', None,
                                                                           'policy')
    assert record['reconfirm_required'] == ['policy', 'conclusion']
    assert record['stale_results'] == []
    assert state['current'] == before['current'] and state['stale'] == before['stale']

    # No surface shows "on hold" next to "confirmed".
    summary = _run('status', '--summary', '--study', b.study)
    held = {n['decision_id'] for n in summary['notes'] if n['status'] == 'open'}
    assert all(summary['decisions'][d]['status'] != 'confirmed' for d in held)
    assert summary['holds'] == [{'decision_id': 'policy', 'status': 'reconfirm_required',
                                 'notes': [{'note_id': 'n_1', 'user_words': HOLD}]}]
    decided = summary['recap'][1]
    assert 'policy capacity:20' in decided and '[to confirm again]' in decided
    page = (b.study / 'reports' / 'study.html').read_text(encoding='utf-8')
    card = page[page.index('data-decision="policy"'):]
    card = card[:card.index('</article>')]
    assert 'data-note="n_1" data-status="open"' in card
    assert 'data-status="confirmed"' not in card.split('data-note=')[0]

    # Once the junior's words resolve the hold, the policy is confirmed again; the
    # conclusion still waits for its own confirmation.
    _note(b.study, 'res', '--resolve', 'n_1', '--text',
          "My manager's figure is in: twenty calls is the limit.")
    _confirm_policy(b)
    assert _status(b, 'policy') == 'confirmed'
    assert _status(b, 'conclusion') == 'reconfirm_required'
    assert 'conclusion_outdated' in _limits(b)
    _conclude(b)
    assert _status(b, 'conclusion') == 'confirmed' and 'conclusion_outdated' not in _limits(b)


def test_a_hold_on_an_upstream_decision_reaches_every_decision_resting_on_it(adopted):
    out = _note(adopted.study, 'hold-split', '--about', 'split', '--text',
                'Wait, the data owner has to approve this split first.')
    assert out['result']['reconfirm_required'] == ['split', 'policy', 'conclusion']
    out = _note(adopted.study, 'hold-pt', '--about', 'prediction_time', '--text',
                'Hold the prediction moment until I check the calling calendar.')
    assert out['result']['reconfirm_required'] == ['prediction_time', 'feature_availability']


def test_a_hold_on_an_open_decision_changes_no_status(evaluated):
    b = evaluated
    before = _state(b)
    out = _note(b.study, 'hold-open', '--about', 'policy', '--text', HOLD)
    assert out['result']['reconfirm_required'] == []
    state = _state(b)
    assert {d: x['status'] for d, x in state['decisions'].items()} == \
        {d: x['status'] for d, x in before['decisions'].items()}
    assert state['invalidations'] == before['invalidations']


# --- D2 -----------------------------------------------------------------------------------

def test_a_policy_adopted_after_the_conclusion_outdates_it(evaluated):
    b = evaluated
    _conclude(b)
    assert _status(b, 'conclusion') == 'confirmed' and _status(b, 'policy') == 'open'
    assert 'conclusion_outdated' not in _limits(b)
    _confirm_policy(b)
    state = _state(b)
    assert state['decisions']['conclusion']['status'] == 'reconfirm_required'
    record = state['invalidations'][-1]
    assert record['mutation'] == 'first_confirmation' and record['decision_id'] == 'policy'
    assert record['reconfirm_required'] == ['conclusion']
    assert 'after the conclusion' in state['decisions']['conclusion']['reason']
    item = _limits(b)['conclusion_outdated']
    assert item['decisions'] == ['conclusion'] and item['reason']
    assert view.build(b.study)['next_action'] == {
        'kind': 'reconfirm', 'decision': 'conclusion',
        'message': f'Decision conclusion must be confirmed again: '
                   f'{state["decisions"]["conclusion"]["reason"]}',
        # v0.2a (WP-A1): the message names an id, so it is the agent's; the junior's variant.
        'audience': 'agent',
        'junior_message': 'Your answer on the conclusion must be confirmed again: something '
                          'it depends on changed after you confirmed it.'}
    summary = _run('status', '--summary', '--study', b.study)
    assert summary['not_yet_defensible']['top'][0]['id'] == 'conclusion_outdated'
    assert 'conclusion keep baseline' in summary['recap'][1] \
        and '[to confirm again]' in summary['recap'][1]
    assert not summary['recap'][4].startswith('Limit: The conclusion was confirmed')
    _conclude(b, words='I keep the baseline, with the policy now adopted as a pilot rule.')
    assert _status(b, 'conclusion') == 'confirmed' and 'conclusion_outdated' not in _limits(b)


def test_a_delegated_decision_confirmed_again_in_own_words_outdates_the_conclusion(evaluated):
    b = evaluated
    _confirm_policy(b)
    _conclude(b)
    split = _state(b)['decisions']['split']['value']
    # The same value with the same basis changes nothing.
    b.decide('split', split, 'My recommended default: stratified split with 30% validation '
             'and seed 20261017.', STANDING, basis='delegated_default',
             delegation_scope='standing')
    assert _status(b, 'conclusion') == 'confirmed'
    # The same value, now in the junior's own words: the credit line changed.
    b.decide('split', split, 'Stratified split with 30% validation and seed 20261017.',
             'Yes, I choose that split myself: 30% validation, stratified.')
    state = _state(b)
    # ADR 0005: own words repeating the proposal are recorded as restated (was explicit).
    assert state['decisions']['split']['confirmation']['basis'] == 'restated'
    assert state['decisions']['conclusion']['status'] == 'reconfirm_required'
    assert 'basis restated (was delegated_default)' in state['decisions']['conclusion']['reason']
    assert state['decisions']['policy']['status'] == 'confirmed'      # values unchanged
    assert state['invalidations'][-1]['mutation'] == 'unchanged_value'


def test_a_conclusion_confirmed_after_its_decisions_stays_current(adopted):
    assert _status(adopted, 'conclusion') == 'confirmed'
    assert 'conclusion_outdated' not in _limits(adopted)
    # Confirming the conclusion again (a new text) never outdates itself.
    _conclude(adopted, value={**KEEP, 'text': 'Keep the simple rule for now.'},
              words='I keep the baseline with the shorter text.')
    assert _status(adopted, 'conclusion') == 'confirmed'


# --- D5 -----------------------------------------------------------------------------------

def test_a_hold_is_withdrawn_in_the_junior_s_words_and_holds_are_grouped(evaluated):
    b = evaluated
    _note(b.study, 'h1', '--about', 'policy', '--text', HOLD)
    _note(b.study, 'h2', '--about', 'policy', '--text', "I don't have the number yet.")
    _note(b.study, 'h3', '--about', 'conclusion', '--text', 'Do not conclude before the pilot.')
    summary = _run('status', '--summary', '--study', b.study)
    assert summary['holds'] == [
        {'decision_id': 'policy', 'status': 'open',
         'notes': [{'note_id': 'n_1', 'user_words': HOLD},
                   {'note_id': 'n_2', 'user_words': "I don't have the number yet."}]},
        {'decision_id': 'conclusion', 'status': 'open',
         'notes': [{'note_id': 'n_3', 'user_words': 'Do not conclude before the pilot.'}]}]
    assert (f'"{HOLD}"; "I don\'t have the number yet." (the policy); "Do not conclude before '
            f'the pilot." (the conclusion)') in summary['recap'][3]

    for words, reason in (('', 'missing_user_words'), ('ok', 'bare_acknowledgement')):
        out = _note(b.study, f'w-{reason}', '--withdraw', 'n_2', '--text', words, expect=2)
        assert out['error']['code'] == 'ambiguous_confirmation'
        assert out['error']['details']['reason'] == reason
    words = 'No need to keep that one, it says the same as my first condition.'
    out = _note(b.study, 'w-ok', '--withdraw', 'n_2', '--text', words)
    assert out['result'] == {'note_id': 'n_2', 'decision_id': 'policy', 'status': 'withdrawn',
                             'user_words': words, 'open_holds': ['n_1']}
    assert _note(b.study, 'w-again', '--withdraw', 'n_2', '--text', words,
                 expect=2)['error']['code'] == 'note_not_open'
    assert _note(b.study, 'r-withdrawn', '--resolve', 'n_2', '--text',
                 'My figure is in, the number is twenty.', expect=2)['error']['code'] \
        == 'note_not_open'
    state = _state(b)
    assert st.validate_state(state) == []
    assert state['notes']['n_2']['resolution']['user_words'] == words
    summary = _run('status', '--summary', '--study', b.study)
    assert [n['note_id'] for h in summary['holds'] for n in h['notes']] == ['n_1', 'n_3']
    assert {n['note_id']: (n['status'], n['resolution_words']) for n in summary['notes']}['n_2'] \
        == ('withdrawn', words)
    page = (b.study / 'reports' / 'study.html').read_text(encoding='utf-8')
    assert 'data-note="n_2" data-status="withdrawn"' in page
    # A withdrawn hold no longer blocks; the other hold on the policy still does.
    out = b.apply(cmd.ACTION_PROPOSE, {'decision_id': 'policy', 'value': fx.POLICY_RULE,
                                       'restatement': 'You call the 20 highest-scored members.',
                                       'rationale': 'The evaluated rule.'})
    with pytest.raises(CommandRefused) as exc:
        b.apply(cmd.ACTION_CONFIRM, {'proposal_id': out.payload['result']['proposal_id'],
                                     'user_words': 'Yes, twenty calls is what the desk can '
                                                   'handle.', 'channel': 'chat',
                                     'actor': 'user', 'basis': 'explicit',
                                     'delegation_scope': None})
    assert exc.value.code == 'decision_on_hold'
    assert [n['note_id'] for n in exc.value.details['notes']] == ['n_1']


# --- D6 -----------------------------------------------------------------------------------

def test_inconclusive_needs_no_adopted_policy_and_is_named(evaluated):
    b = evaluated
    _note(b.study, 'h1', '--about', 'policy', '--text', HOLD)
    with pytest.raises(CommandRefused) as exc:
        b.decide('conclusion', {'verdict': 'adopt_policy', 'text': 'Adopt the call rule.'},
                 'You adopt the call rule.', 'I adopt the call rule.')
    assert exc.value.code == 'precondition_missing'
    assert exc.value.details['missing'][0]['decision'] == 'policy'
    value = {'verdict': 'inconclusive',
             'text': 'Inconclusive until the call limit is known; the ranking cannot be judged.'}
    b.decide('conclusion', value, 'You call the study inconclusive until the limit is known.',
             'Yes, inconclusive until my manager gives the limit.')
    assert _status(b, 'conclusion') == 'confirmed' and _status(b, 'policy') == 'open'
    item = _limits(b)['inconclusive_without_choice']
    assert item['decisions'] == ['policy'] and 'no policy is adopted' in item['text']
    summary = _run('status', '--summary', '--study', b.study)
    assert 'inconclusive_without_choice' in [x['id'] for x in summary['not_yet_defensible']['top']]
