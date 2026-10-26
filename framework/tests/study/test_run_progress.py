"""Owner session 2026-10-26, lot L4 level 1 (R10; journey check J-PROG): ``run --progress``.

``hypotrail run ACTIVITY --progress`` writes progress lines on **stderr** while the activity
computes and while the deliverables are regenerated: one line at the start, a heartbeat at
least every 10 s, one line at the end with the elapsed time, in the study language. stdout is
the same JSON document with or without the flag; without it nothing is written to stderr
(CLI-CONTRACT §1, NR-17), so every test asserting ``stderr == ''`` keeps holding.

The slow runs are stubs: the test hook ``run_slow_compute:SECONDS`` (``HYPOTRAIL_TEST_HOOKS=1``
only) lengthens the computation, and ``HYPOTRAIL_PROGRESS_INTERVAL`` shortens the heartbeat in
the process tests; one test keeps the real 10 s heartbeat.
"""
from __future__ import annotations

import io
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

import flowkit as fk
from mlkit.study import cmd_run, executions, progress


def _study(base: Path, case_dir: Path, language: str = 'en') -> fk.Flow:
    """A synthetic study whose next activity, ``split``, needs the framing decisions."""
    flow = fk.Flow(base / f'study-{language}', case_dir)
    flow.call('init', '--case', case_dir, '--study', flow.study, '--lang', language)
    flow.pauses(split=True, model_decisions=False)
    return flow


def _cli(study: Path, *args, extra_env=None, rid='prog1', rev=None, timeout=600):
    rev = rev if rev is not None else json.loads(subprocess.run(
        [sys.executable, '-m', 'mlkit.study.cli', 'status', '--study', str(study)],
        capture_output=True, text=True, env=fk.env(), timeout=timeout).stdout)['revision']
    return subprocess.run([sys.executable, '-m', 'mlkit.study.cli', 'run', *args,
                           '--request-id', rid, '--expected-revision', str(rev), '--study',
                           str(study)], capture_output=True, text=True,
                          env=fk.env(**(extra_env or {})), timeout=timeout)


SLOW = {'HYPOTRAIL_TEST_HOOKS': '1', 'HYPOTRAIL_FAULT': 'run_slow_compute:1.5',
        'HYPOTRAIL_PROGRESS_INTERVAL': '0.4'}


def test_progress_goes_to_stderr_only(tmp_path, synthetic_case_dir):
    """The same run on two copies of one study, with and without ``--progress``: stdout is
    the same one JSON document (the study path and the random exposure ids aside), and only
    the flagged run writes on stderr, in lines."""
    flow = _study(tmp_path, synthetic_case_dir)
    twin = fk.clone(flow.study, tmp_path / 'twin')
    plain = _cli(flow.study, 'eda.quality', extra_env=SLOW)
    flagged = _cli(twin, 'eda.quality', '--progress', extra_env=SLOW)
    assert plain.returncode == flagged.returncode == 0, (plain.stderr, flagged.stderr)
    assert plain.stderr == ''
    assert len(plain.stdout.splitlines()) == len(flagged.stdout.splitlines()) == 1

    def comparable(stdout: str, study: Path) -> str:
        payload = json.loads(stdout.replace(json.dumps(str(study))[1:-1], '<study>'))
        assert len(payload['result'].pop('exposure_ids')) == 1
        return json.dumps(payload, ensure_ascii=False)
    assert comparable(flagged.stdout, twin) == comparable(plain.stdout, flow.study)
    lines = flagged.stderr.splitlines()
    assert lines[0] == 'The data quality check · started', lines
    assert any(' · running · ' in line for line in lines), lines
    assert any(line.startswith('The data quality check · done in ') for line in lines), lines
    assert lines[-1].startswith('The report and the notebook · done in '), lines
    assert not any(line.lstrip().startswith('{') for line in lines)


def test_no_progress_without_the_flag(tmp_path, synthetic_case_dir):
    """NR-17: without ``--progress`` a slow run writes nothing on stderr, and a replay or an
    already current result writes nothing either, flag or not."""
    flow = _study(tmp_path, synthetic_case_dir)
    rev = flow.rev()
    out = _cli(flow.study, 'split', extra_env=SLOW, rid='s1', rev=rev)
    assert out.returncode == 0 and out.stderr == '', out.stderr
    replay = _cli(flow.study, 'split', '--progress', rid='s1', rev=rev)
    assert replay.returncode == 0 and replay.stderr == '', replay.stderr
    assert json.loads(replay.stdout)['replayed'] is True
    again = _cli(flow.study, 'split', '--progress', rid='s2')
    assert again.returncode == 0 and again.stderr == '', again.stderr
    assert json.loads(again.stdout)['status'] == 'already_current'


@pytest.mark.parametrize('language,words', [
    ('en', ('The split · started', 'The split · running · ', 'The split · done in ',
            'The report and the notebook · done in ')),
    ('fr', ('Le découpage · démarré', 'Le découpage · en cours · ', 'Le découpage · terminé en ',
            'Le rapport et le notebook · terminé en '))])
def test_progress_words_in_the_study_language(tmp_path, synthetic_case_dir, language, words):
    flow = _study(tmp_path, synthetic_case_dir, language)
    out = _cli(flow.study, 'split', '--progress', extra_env=SLOW)
    assert out.returncode == 0, out.stderr
    lines = out.stderr.splitlines()
    assert lines[0] == words[0]
    for start in words[1:]:
        assert any(line.startswith(start) for line in lines), (start, lines)
    other = {'en': 'démarré', 'fr': 'started'}[language]
    assert other not in out.stderr


class _Clocked(io.StringIO):
    """A stream that records when each line is written."""

    def __init__(self, tty: bool = False):
        super().__init__()
        self.times: list[float] = []
        self.tty = tty

    def write(self, text):
        self.times.append(time.monotonic())
        return super().write(text)

    def isatty(self):
        return self.tty


def test_heartbeat_at_least_every_interval_on_a_slow_activity(tmp_path, synthetic_case_dir,
                                                              monkeypatch):
    """A monkeypatched slow activity on the synthetic case, run in process: the gaps between
    two progress lines never exceed the heartbeat (plus a small tolerance), and the study's
    outcome is the run's as usual."""
    flow = _study(tmp_path, synthetic_case_dir)
    compute = executions.act.compute

    def slow(store, plan):
        out = compute(store, plan)
        time.sleep(2.0)
        return out
    monkeypatch.setattr(executions.act, 'compute', slow)
    stream = _Clocked()
    outcome = executions.run(flow.study, 'split', {}, request_id='hb1',
                             expected_revision=flow.rev(), progress=stream,
                             progress_interval=0.25)
    assert outcome.exit_code == 0 and outcome.payload['status'] == 'promoted'
    lines = stream.getvalue().splitlines()
    assert lines[0] == 'The split · started' and sum('· running ·' in x for x in lines) >= 6
    split = [t for t, x in zip(stream.times, lines) if x.startswith('The split')]
    gaps = [b - a for a, b in zip(split, split[1:])]
    assert max(gaps) <= 0.25 + 0.2, gaps


def test_the_heartbeat_is_ten_seconds_by_default(tmp_path, synthetic_case_dir, monkeypatch):
    """D12: the heartbeat is 10 s; the shorter test interval is honoured only under the test
    hooks. A computation of 12 s gets its first heartbeat 10 s after the start line."""
    assert progress.HEARTBEAT_SECONDS == 10
    monkeypatch.delenv(cmd_run.HOOKS_ENV, raising=False)
    monkeypatch.setenv(progress.INTERVAL_ENV, '0.1')
    assert cmd_run.progress_interval() == 10
    monkeypatch.setenv(cmd_run.HOOKS_ENV, '1')
    assert cmd_run.progress_interval() == 0.1
    stream = _Clocked()
    reporter = progress.Reporter(stream, 'fr')
    with reporter.activity('fit.variant:2'):
        time.sleep(12.0)
    lines = stream.getvalue().splitlines()
    assert lines == ['La deuxième variante · démarré', 'La deuxième variante · en cours · 10 s',
                     'La deuxième variante · terminé en 12 s']
    assert 9.9 <= stream.times[1] - stream.times[0] <= 10.5


def test_progress_lines_on_a_terminal_and_on_failure():
    """On a terminal the heartbeat rewrites one line (carriage return), ended by one newline
    per phase; a phase that raises ends with "stopped after"; a closed stream never breaks
    the run."""
    tty = _Clocked(tty=True)
    reporter = progress.Reporter(tty, 'en', interval=0.05)
    with reporter.deliverables():
        time.sleep(0.2)
    text = tty.getvalue()
    assert text.count('\n') == 1 and text.count('\r') >= 3 and text.endswith('\n')
    assert text.rstrip().split('\r')[-1].startswith('The report and the notebook · done in 0 s')
    plain = _Clocked()
    with pytest.raises(RuntimeError):
        with progress.Reporter(plain, 'en', interval=10).activity('fit.logistic'):
            raise RuntimeError('boom')
    assert plain.getvalue().splitlines() == ['The logistic model · started',
                                             'The logistic model · stopped after 0 s']
    closed = io.StringIO()
    closed.close()
    with progress.Reporter(closed, 'en', interval=0.01).activity('split'):
        time.sleep(0.05)
    assert progress.elapsed_words(72.4) == '1 min 12 s' and progress.elapsed_words(180) == '3 min'


def test_the_progress_flag_is_documented():
    """The names L4 adds to the contract (CLI-CONTRACT §1 and §8.1), pinned here until the
    integrator moves them into ``test_contract_freeze.py`` (plan §1.3)."""
    doc = (Path(fk.REPO) / 'docs' / 'specs' / 'CLI-CONTRACT.md').read_text(encoding='utf-8')
    for phrase in ('except the progress lines of `run --progress`', '`progress.HEARTBEAT_SECONDS`',
                   '`HYPOTRAIL_FAULT=run_slow_compute:SECONDS`', '`HYPOTRAIL_PROGRESS_INTERVAL`',
                   'The study panel never passes the flag'):
        assert phrase in doc, phrase
    assert progress.INTERVAL_ENV == 'HYPOTRAIL_PROGRESS_INTERVAL'
