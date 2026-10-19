"""``hypotrail session-report`` and the opt-in session log (post-v0.1, observation kit).

The report is read-only and content-free; the log records only when enabled
(``HYPOTRAIL_SESSION_LOG=1`` once, then while the file exists), never in a read-only
process, never a read other than ``status`` and ``check`` (owner decision: how often the
junior checks is observed; previews, evidence, explain, decisions and plan stay unlogged,
and ``export`` leaves the study tree byte-identical), and never the junior's words, a
restatement, a rationale, a value, or checked text. Studies live in temporary directories.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys

import pytest

from mlkit.study import cli, cmd_session_report as rep, sessionlog

import flowkit as fk

# Distinctive strings that must never reach the log or the report.
WORDS = 'Yes, before the reminder goes out, zebrafinch.'
RESTATEMENT = 'You predict before the reminder goes out, quokka.'
RATIONALE = 'It is the earliest moment, pangolin.'
DRAFT = 'The axolotl team can call 4242 members.'
SECRETS = ('zebrafinch', 'quokka', 'pangolin', 'axolotl', '4242')


def _snapshot(study) -> dict:
    return {str(p.relative_to(study)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(study.rglob('*')) if p.is_file()}


def _call(*args, expect=None):
    outcome = cli.run([str(a) for a in args])
    if expect is not None:
        assert outcome.exit_code == expect, outcome.payload
    return outcome.payload


@pytest.fixture
def logged(tmp_path, synthetic_case_dir, monkeypatch):
    """A study whose session log was enabled once, then used without the variable."""
    monkeypatch.delenv(sessionlog.ENV, raising=False)
    study = tmp_path / 'study'
    _call('init', '--case', synthetic_case_dir, '--study', study, expect=0)
    assert not sessionlog.path(study).exists()                 # off by default
    monkeypatch.setenv(sessionlog.ENV, '1')
    _call('status', '--summary', '--study', study, expect=0)
    monkeypatch.delenv(sessionlog.ENV)
    assert sessionlog.path(study).is_file()                    # the opt-in, and its line
    p = _call('decide', 'propose', 'prediction_time', '--value', 'before the reminder',
              '--restatement', RESTATEMENT, '--rationale', RATIONALE, '--request-id', 'a',
              '--expected-revision', 1, '--study', study)['result']['proposal_id']
    _call('decide', 'confirm', p, '--user-words', 'ok', '--request-id', 'b',
          '--expected-revision', 2, '--study', study, expect=2)
    _call('decide', 'confirm', p, '--user-words', WORDS, '--request-id', 'c',
          '--expected-revision', 2, '--study', study, expect=0)
    draft = tmp_path / 'draft.txt'
    draft.write_text(DRAFT)
    _call('check', '--text', draft, '--study', study, expect=0)
    _call('run', 'split', '--request-id', 'd', '--expected-revision', 3, '--study', study,
          expect=2)                                             # refused: pause 1 is not done
    return study


def test_the_log_is_off_by_default_and_the_report_says_so(tmp_path, synthetic_case_dir,
                                                         monkeypatch):
    monkeypatch.delenv(sessionlog.ENV, raising=False)
    flow = fk.Flow(tmp_path / 'study', synthetic_case_dir)
    flow.init()
    flow.pauses()
    flow.call('decide', 'confirm', 'p_1', '--user-words', 'ok', '--request-id', 'x',
              '--expected-revision', flow.rev(), '--study', flow.study, expect=2)
    assert not sessionlog.path(flow.study).exists()
    out = rep.report(flow.study)
    assert tuple(out) == rep.PAYLOAD_KEYS and out['schema'] == rep.SCHEMA
    assert out['sources']['session_log']['enabled'] is False
    assert 'not recorded' in out['sources']['session_log']['note']
    assert out['refusals'] == [] and out['checks'] == []
    assert [p['closed_at'] is not None for p in out['pauses']] == [True, True, False]
    assert [d['outcome'] for d in out['decisions']] == ['confirmed'] * 3


def test_the_log_records_mutations_refusals_status_and_checks(logged):
    lines = [json.loads(x) for x in sessionlog.path(logged).read_text().splitlines()]
    assert {x['schema'] for x in lines} == {sessionlog.SCHEMA}
    assert [(x['command'], x['verb'], x['exit_code']) for x in lines] == [
        ('status', None, 0), ('decide', 'propose', 0), ('decide', 'confirm', 2),
        ('decide', 'confirm', 0), ('check', None, 0), ('run', None, 2)]
    assert lines[0]['options'] == {'summary': True}
    out = rep.report(logged)
    assert out['sources']['session_log'] == {'enabled': True, 'entries': 6,
                                             'path': '.hypotrail/session-log.jsonl',
                                             'note': None}
    assert [(r['command'], r['code'], r['reason']) for r in out['refusals']] == [
        ('decide confirm', 'ambiguous_confirmation', 'bare_acknowledgement'),
        ('run', 'precondition_missing', None)]
    [decision] = out['decisions']
    assert decision['decision_id'] == 'prediction_time' and decision['outcome'] == 'confirmed'
    assert decision['refused_confirmations'] == 1
    assert decision['refusal_reasons'] == {'bare_acknowledgement': 1}
    # ADR 0005: own words repeating the proposal are recorded as restated (was explicit).
    assert decision['seconds_open'] >= 0 and decision['basis'] == 'restated'
    [check] = out['checks']                                     # a logged read
    assert check['target'] == 'text' and check['clean'] is False
    assert check['codes'] == {'untraceable_number': 1}
    assert out['commands'] == {'check': 1, 'decide confirm': 2, 'decide propose': 1, 'run': 1,
                               'status': 1}
    assert out['pauses'][0]['refused_confirmations'] == 1
    assert out['pauses'][0]['closed_at'] is None               # availability still open
    sources = {x['source'] for x in out['timeline']}
    assert sources == {'revision', 'event', 'session_log'}


def test_nothing_of_the_conversation_reaches_the_log_or_the_report(logged):
    log = sessionlog.path(logged).read_text()
    report = json.dumps(rep.report(logged))
    text = rep.markdown(rep.report(logged))
    for secret in SECRETS:
        assert secret not in log, secret
        assert secret not in report, secret
        assert secret not in text, secret
    # the study itself does hold them: the report filters, it does not just miss them
    revisions = (logged / '.hypotrail' / 'revisions.jsonl').read_text()
    assert 'zebrafinch' in revisions and 'quokka' in revisions


def test_disable_and_read_only_processes_write_nothing(logged, monkeypatch):
    before = sessionlog.path(logged).read_text()
    monkeypatch.setenv(sessionlog.ENV, '0')
    _call('status', '--study', logged, expect=0)
    monkeypatch.delenv(sessionlog.ENV)
    monkeypatch.setenv('HYPOTRAIL_READ_ONLY', '1')
    _call('status', '--study', logged, expect=0)
    monkeypatch.delenv('HYPOTRAIL_READ_ONLY')
    assert sessionlog.path(logged).read_text() == before
    _call('plan', '--study', logged, expect=0)                  # an unlogged read
    assert sessionlog.path(logged).read_text() == before
    _call('status', '--study', logged, expect=0)                # the file keeps it on
    assert sessionlog.path(logged).read_text().count('\n') == before.count('\n') + 1
    _call('run', 'split', '--request-id', 'e', '--expected-revision', 3, '--study', logged,
          expect=2)                                             # the file keeps it on
    assert sessionlog.path(logged).read_text() != before


def _lines(study) -> list[dict]:
    return [json.loads(x) for x in sessionlog.path(study).read_text().splitlines()]


def test_with_the_log_on_status_and_check_change_only_the_log_and_the_rest_nothing(
        logged, tmp_path, monkeypatch):
    """Owner decision: ``status`` and ``check`` add a line; other reads and the export none."""
    monkeypatch.setenv(sessionlog.ENV, '1')
    log = str(sessionlog.path(logged).relative_to(logged))
    before = _snapshot(logged)
    lines = len(_lines(logged))
    logged_reads = [('status',), ('status', '--summary'), ('status', '--summary', '--digest'),
                    ('check',)]
    for args in logged_reads:
        cli.run([*args, '--study', str(logged)])
    after = _snapshot(logged)
    assert {k: v for k, v in after.items() if k != log} == \
        {k: v for k, v in before.items() if k != log}               # only the log file moved
    added = _lines(logged)[lines:]
    assert [(x['command'], x['options'].get('summary', False), x['options'].get('digest', False))
            for x in added] == [('status', False, False), ('status', True, False),
                                ('status', True, True), ('check', False, False)]
    assert added[0]['current_step'] and added[3]['check']['target']
    before = after
    unlogged = [('plan',), ('decisions',), ('evidence',), ('explain',),
                ('preview', 'proposal', 'prediction_time', '--value', 'at signup'),
                ('preview', 'policy', '--rule', 'capacity:10'),     # refused: still a read
                ('session-report',)]
    for args in unlogged:
        cli.run([*args, '--study', str(logged)])
    for _ in range(20):                                             # a slider: no line
        cli.run(['preview', 'proposal', 'prediction_time', '--value', 'at signup',
                 '--study', str(logged)])
    assert _snapshot(logged) == before                              # byte-identical
    out = tmp_path / 'pack'
    outcome = cli.run(['export', 'handoff', '--out', str(out), '--study', str(logged)])
    assert outcome.payload['ok'] is True, outcome.payload
    assert _snapshot(logged) == before                              # byte-identical
    assert set(sessionlog.LOGGED_READS) == {a[0] for a in logged_reads}
    assert (set(sessionlog.READ_COMMANDS) - set(sessionlog.LOGGED_READS)) | \
        set(sessionlog.UNLOGGED) >= {a[0] for a in unlogged} | {'export'}


def test_with_the_log_off_every_read_and_the_export_leave_the_tree_byte_identical(
        tmp_path, synthetic_case_dir, monkeypatch):
    monkeypatch.delenv(sessionlog.ENV, raising=False)
    study = tmp_path / 'study'
    _call('init', '--case', synthetic_case_dir, '--study', study, expect=0)
    before = _snapshot(study)
    for args in [('status',), ('status', '--summary', '--digest'), ('check',), ('plan',),
                 ('decisions',), ('evidence',), ('explain',), ('session-report',),
                 ('export', 'handoff', '--out', str(tmp_path / 'pack'))]:
        cli.run([*args, '--study', str(study)])
    assert _snapshot(study) == before
    assert not sessionlog.path(study).exists()
    monkeypatch.setenv(sessionlog.ENV, '0')                         # the panel's reads
    sessionlog.path(study).touch()
    before = _snapshot(study)
    cli.run(['status', '--summary', '--digest', '--study', str(study)])
    cli.run(['check', '--study', str(study)])
    assert _snapshot(study) == before


def test_the_opt_in_on_a_read_creates_the_empty_log_only(tmp_path, synthetic_case_dir,
                                                         monkeypatch):
    monkeypatch.delenv(sessionlog.ENV, raising=False)
    study = tmp_path / 'study'
    _call('init', '--case', synthetic_case_dir, '--study', study, expect=0)
    monkeypatch.setenv(sessionlog.ENV, '1')
    _call('export', 'handoff', '--out', tmp_path / 'pack', '--study', study)
    assert not sessionlog.path(study).exists()                 # an export never touches it
    _call('evidence', '--study', study, expect=0)
    assert sessionlog.path(study).read_bytes() == b''


def test_the_report_is_read_only_and_never_logged(logged):
    before = _snapshot(logged)
    payload = _call('session-report', '--study', logged, expect=0)
    assert payload['schema'] == rep.SCHEMA
    _call('session-report', '--study', logged, '--since', 2, expect=0)
    assert _snapshot(logged) == before


def test_since_keeps_what_happened_after_the_revision(logged):
    out = rep.report(logged, since=2)
    assert [x['revision'] for x in out['timeline'] if x['source'] == 'revision'] == [3]
    assert [r['code'] for r in out['refusals']] == ['ambiguous_confirmation',
                                                    'precondition_missing']
    assert out['since'] == 2 and out['span']['revisions'] == 1


def test_markdown_and_json_through_a_real_process(logged):
    def run(*extra):
        return subprocess.run([sys.executable, '-m', 'mlkit.study.cli', 'session-report',
                               '--study', str(logged), *extra], capture_output=True, text=True,
                              env=fk.env(), timeout=120, cwd=logged.parent)
    proc = run()
    assert proc.returncode == 0 and proc.stderr == ''
    payload = json.loads(proc.stdout)
    assert tuple(payload) == rep.PAYLOAD_KEYS
    proc = run('--format', 'text')
    assert proc.returncode == 0 and proc.stdout.startswith('# Session report')
    for heading in ('## Pauses', '## Decisions', '## Refusals', '## Checks', '## Timeline'):
        assert heading in proc.stdout
    assert 'ambiguous_confirmation (bare_acknowledgement)' in proc.stdout
    proc = run('--gap-minutes', '0')
    assert proc.returncode == 2 and json.loads(proc.stdout)['error']['code'] == \
        'invalid_arguments'


def test_idle_gaps_mark_a_new_session():
    times = ['2026-10-18T09:00:00+00:00', '2026-10-18T09:05:00+00:00',
             '2026-10-19T10:00:00+00:00']
    assert rep._gaps(times, 20) == [{'from': '2026-10-18T09:05:00+00:00',
                                     'to': '2026-10-19T10:00:00+00:00', 'minutes': 1495.0}]
    assert rep._gaps(times[:2], 20) == []
