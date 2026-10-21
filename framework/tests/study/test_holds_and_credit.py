"""Post-v0.1 acceptance fixes P2, P3, and P7 (``docs/acceptance/runs/
claude-code-2026-10-18-post-v0.1.md``; ``docs/specs/CLI-CONTRACT.md`` §5.1, §3, §8.3).

* P2: a condition the junior states at a pause ("don't adopt anything until I bring my
  manager's figure") is recorded verbatim with ``decide note --about``, persists across
  chats (summary, recap, report, ``not_yet_defensible``), and blocks the confirmation of
  its decision until the junior's own words resolve it (``decide note --resolve``).
* P3: the resume recap and the deliverable messages hold no revision number, and each
  recap line is one flat line.
* P7: a delegated decision is credited to the assistant's recommended default in the
  report's conclusion, and a text that credits a default to the analyst is refused.

Studies live in ``tmp_path``.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent / 'deliverables'))

import phase3_study as fx  # noqa: E402
from mlkit.reliability import CommandRefused  # noqa: E402
from mlkit.study import cli, cmd_check, commands as cmd, read, state as st, view  # noqa: E402


HOLD = "For now keep the illustrative K and don't adopt anything until I bring my manager's figure."
STANDING = "For questions I can't answer, use your recommended default."


def _run(*argv, expect=0):
    outcome = cli.run([str(a) for a in argv])
    json.dumps(outcome.payload)
    if expect is not None:
        assert outcome.exit_code == expect, outcome.payload
    return outcome.payload


def _rev(study) -> int:
    return read.open(study).revision


def _note(study, rid, *args, expect=0):
    return _run('decide', 'note', *args, '--request-id', rid, '--expected-revision', _rev(study),
                '--study', study, expect=expect)


@pytest.fixture
def pause(tmp_path, synthetic_case_dir):
    """The policy pause (fixture results), the first three decisions delegated."""
    b = fx.build(tmp_path / 'study', synthetic_case_dir, upto='models',
                 standing_delegation=STANDING)
    fx.put_policy_evaluation(b)
    return b


def _propose_policy(b) -> str:
    out = b.apply(cmd.ACTION_PROPOSE, {'decision_id': 'policy', 'value': fx.POLICY_RULE,
                                       'restatement': 'You call the 20 highest-scored members.',
                                       'rationale': 'The evaluated rule.'})
    return out.payload['result']['proposal_id']


def _confirm(b, pid, words):
    try:
        return b.apply(cmd.ACTION_CONFIRM, {'proposal_id': pid, 'user_words': words,
                                            'channel': 'chat', 'actor': 'user',
                                            'basis': 'explicit', 'delegation_scope': None})
    except CommandRefused as exc:
        return cmd.refused('decide confirm', exc)


# --- P2 -----------------------------------------------------------------------------------

def test_a_hold_blocks_the_decision_until_the_junior_resolves_it(pause):
    study = pause.study
    out = _note(study, 'hold-1', '--about', 'policy', '--text', HOLD)
    assert out['result'] == {'note_id': 'n_1', 'decision_id': 'policy', 'status': 'open',
                             'user_words': HOLD, 'open_holds': ['n_1'],
                             'reconfirm_required': [],
                             'kind': 'hold'}  # ADR 0005: the result names the kind
    pid = _propose_policy(pause)                                       # proposing is allowed
    before = _rev(study)
    refused = _confirm(pause, pid, 'Yes, twenty calls is what the desk can handle.')
    assert refused.exit_code == cmd.EXIT_REFUSED
    error = refused.payload['error']
    assert error['code'] == 'decision_on_hold'
    assert error['details']['notes'] == [{'note_id': 'n_1', 'user_words': HOLD}]
    assert _rev(study) == before
    assert read.open(study).state['decisions']['policy']['status'] == 'proposed'

    # Only the junior's own words resolve it: not "not yet", not "ok", not something else.
    for words, reason in (('not yet', 'negative_reply'), ('ok', 'bare_acknowledgement'),
                          ('I like pizza', 'unrelated_reply')):
        res = _note(study, f'res-{reason}', '--resolve', 'n_1', '--text', words, expect=2)
        assert res['error']['code'] == 'ambiguous_confirmation'
        assert res['error']['details']['reason'] == reason, words
    words = "My manager's figure is twenty calls, so the hold is over."
    res = _note(study, 'res-ok', '--resolve', 'n_1', '--text', words)
    assert res['result']['status'] == 'resolved' and res['result']['open_holds'] == []
    assert _note(study, 'res-again', '--resolve', 'n_1', '--text', words,
                 expect=2)['error']['code'] == 'note_not_open'
    assert _note(study, 'res-none', '--resolve', 'n_9', '--text', words,
                 expect=2)['error']['code'] == 'unknown_note'
    done = _confirm(pause, pid, 'Yes, twenty calls is what the desk can handle.')
    assert done.exit_code == 0, done.payload
    state = read.open(study).state
    assert st.validate_state(state) == []
    note = state['notes']['n_1']
    assert note['user_words'] == HOLD and note['resolution']['user_words'] == words


def test_a_hold_persists_across_chats_in_summary_recap_report_and_limits(pause):
    study = pause.study
    _note(study, 'hold-1', '--about', 'policy', '--text', HOLD)
    # A new chat reads only the recorded state.
    summary = _run('status', '--summary', '--study', study)
    assert summary['notes'] == [{'note_id': 'n_1', 'decision_id': 'policy', 'status': 'open',
                                 'user_words': HOLD, 'resolution_words': None}]
    assert f'On hold in the junior\'s words: "{HOLD}" (the policy)' in summary['recap'][3]
    assert summary['recap'][4].startswith('Limit: ') and HOLD not in summary['recap'][4]
    limits = {x['id']: x for x in _run('status', '--study', study)['view']['not_yet_defensible']}
    assert limits['open_holds']['decisions'] == ['policy'] and HOLD in limits['open_holds']['text']
    assert summary['not_yet_defensible']['top'][0]['id'] == 'open_holds'
    page = (study / 'reports' / 'study.html').read_text(encoding='utf-8')
    card = page[page.index('data-decision="policy"'):]
    card = card[:card.index('</article>')]
    assert 'data-note="n_1" data-status="open"' in card
    assert f'<q data-literal="user_words">{HOLD.replace(chr(39), "&#x27;")}</q>' in card
    # A draft that repeats a figure of the hold is traced to the junior's words.
    findings, _ = cmd_check.check_text(view.build(study), 'Your note says the hold stays on.')
    assert not [f for f in findings if f['severity'] == 'error']


def test_a_note_names_a_decision_and_states_a_condition(pause):
    study = pause.study
    out = _note(study, 'n-bad', '--about', 'threshold', '--text', HOLD, expect=2)
    assert out['error']['code'] == 'unknown_decision'
    out = _note(study, 'n-ack', '--about', 'policy', '--text', 'ok', expect=2)
    assert out['error']['code'] == 'invalid_value'
    out = _run('decide', 'note', '--text', HOLD, '--request-id', 'n-none', '--expected-revision',
               _rev(study), '--study', study, expect=2)
    assert out['error']['code'] == 'invalid_arguments'


def test_the_session_log_never_keeps_a_note_s_words(pause, monkeypatch):
    study = pause.study
    monkeypatch.setenv('HYPOTRAIL_SESSION_LOG', '1')
    _note(study, 'hold-1', '--about', 'policy', '--text', HOLD)
    log = (study / '.hypotrail' / 'session-log.jsonl').read_text(encoding='utf-8')
    line = json.loads(log.strip().splitlines()[-1])
    assert line['verb'] == 'note' and line['note_id'] == 'n_1'
    assert line['options'] == {'about': 'policy'}
    assert 'manager' not in log


# --- P3 -----------------------------------------------------------------------------------

def test_recap_and_deliverable_messages_hold_no_revision_number(pause):
    study = pause.study
    _note(study, 'hold-1', '--about', 'policy', '--text', HOLD)
    summary = _run('status', '--summary', '--study', study)
    revision = str(summary['revision'])
    for name, item in summary['artifacts']['items'].items():
        message = item['message'].replace('reports/study.html', '').replace(
            'notebooks/study_generated.py', '').replace('notebooks/workbench.py', '')
        assert not re.search(r'\d', message), (name, item['message'])
    for line in summary['recap']:
        assert '\n' not in line and not re.match(r'\s*[-*•]', line), line
        assert not re.search(rf'\b{revision}\b', line) or revision in HOLD, line
        assert 'revision' not in line.lower(), line


# --- P7 -----------------------------------------------------------------------------------

def test_the_report_credits_delegated_defaults_to_the_assistant(pause):
    b = pause
    b.decide('policy', fx.POLICY_RULE, 'You call the 20 highest-scored members.',
             'Yes, twenty calls is what the desk can handle.')
    b.decide('conclusion', {'verdict': 'keep_baseline',
                            'text': 'Keep the simple rule for now; the model ranks better on '
                                    'validation rows that were used to choose it.'},
             'You keep the baseline and record the limits.', 'I keep the baseline and note why.')
    page = (b.study / 'reports' / 'study.html').read_text(encoding='utf-8')
    card = page[page.index('data-decision="conclusion"'):]
    card = card[:card.index('</article>')]
    delegated = card[card.index('data-basis="delegated_default"'):]
    delegated = delegated[:delegated.index('</li>')]
    assert "assistant&#x27;s recommended default, delegated by the analyst" in delegated
    assert "not the analyst&#x27;s own choice" in delegated
    for title in ('Define the prediction moment', 'Split the data before exploring it'):
        assert title in delegated
    explicit = card[card.index('data-basis="explicit"'):]
    assert 'Choose a decision policy' in explicit[:explicit.index('</li>')]


def test_a_default_credited_to_the_analyst_is_refused(pause):
    b = pause
    b.decide('policy', fx.POLICY_RULE, 'You call the 20 highest-scored members.',
             'Yes, twenty calls is what the desk can handle.')
    text = ("The prediction moment, the variables used and the split followed the analyst's "
            'recommended defaults.')
    findings, _ = cmd_check.check_text(view.build(b.study), text)
    assert [f['code'] for f in findings] == ['misattributed_delegation']
    assert not cmd_check.check_text(view.build(b.study),
                                    "They are the assistant's recommended defaults, delegated by "
                                    'the analyst.')[0]
    with pytest.raises(CommandRefused) as exc:
        b.apply(cmd.ACTION_PROPOSE, {'decision_id': 'conclusion',
                                     'value': {'verdict': 'keep_baseline', 'text': text},
                                     'restatement': 'You keep the baseline.',
                                     'rationale': 'The limits are recorded.'})
    assert exc.value.code == 'misattributed_delegation'
    assert exc.value.details['delegated'] == list(st.STANDING_DELEGATION_DECISIONS)
