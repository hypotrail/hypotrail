"""Automatic render after every commit and failure isolation (plan WP3.4, WP3.1, §3.6).

``test_render::test_failed_html_keeps_previous_and_banner`` of the plan's §7 checklist is
``test_failed_html_keeps_previous_file_with_banner_and_manifest_failed`` here.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from mlkit.study import cmd_render, commands as cmd, manifest as mf, read, render_html, texts, view

import phase3_study as fx

FRAMEWORK = Path(__file__).resolve().parents[3]


def _env(**extra):
    env = {k: v for k, v in os.environ.items()
           if k not in ('HYPOTRAIL_READ_ONLY', 'HYPOTRAIL_FAULT', 'HYPOTRAIL_TEST_HOOKS')}
    env.update(extra)
    return env


def _cli(*argv, **env):
    proc = subprocess.run([sys.executable, '-m', 'mlkit.study.cli', *map(str, argv)],
                          capture_output=True, text=True, env=_env(**env), cwd=FRAMEWORK,
                          timeout=180)
    return proc.returncode, json.loads(proc.stdout), proc.stderr


def _propose(b: fx.Builder, text='Keep the baseline.') -> cmd.Outcome:
    return b.apply(cmd.ACTION_PROPOSE, {'decision_id': 'conclusion',
                                        'value': {'verdict': 'keep_baseline', 'text': text},
                                        'restatement': 'You keep the baseline.',
                                        'rationale': 'Proportionate.'})


@pytest.fixture
def b(full_study, synthetic_case_dir):
    builder = fx.Builder(full_study, synthetic_case_dir)
    builder.n = 1000
    return builder


@pytest.fixture
def no_hooks(monkeypatch):
    for k in ('HYPOTRAIL_FAULT', 'HYPOTRAIL_TEST_HOOKS', 'HYPOTRAIL_READ_ONLY'):
        monkeypatch.delenv(k, raising=False)


def _strip_banner(page: str) -> str:
    return render_html.inject_banner(page, '')


def test_every_commit_renders_every_artifact(b, no_hooks):
    out = _propose(b)
    assert out.exit_code == 0
    arts = out.payload['artifacts']
    assert set(arts) == {'report', 'notebook', 'workbench'}
    rev = out.payload['revision']
    assert all(a['status'] == 'ok' for a in arts.values())
    assert arts['report']['revision'] == arts['notebook']['revision'] == rev
    assert arts['workbench']['tracked'] is False
    v = view.build(b.study)
    assert v['artifacts']['status'] == 'ok' and v['artifacts']['manifest'] == 'artifacts.json'
    page = (b.study / mf.ARTIFACTS['report']).read_text()
    assert f'data-revision="{rev}"' in page
    manifest = mf.load(b.study)
    assert manifest['schema'] == mf.SCHEMA and manifest['revision'] == rev
    for name, item in manifest['artifacts'].items():
        assert set(mf.ITEM_KEYS) <= set(item), name
    assert set(manifest['artifacts']['report']['consumed']) == {
        r['result_id'] for r in v['results'].values() if r['current']}


def test_failed_html_keeps_previous_file_with_banner_and_manifest_failed(b, monkeypatch):
    report = b.study / mf.ARTIFACTS['report']
    previous = report.read_text()
    before_rev = read.open(b.study).revision
    monkeypatch.setenv('HYPOTRAIL_TEST_HOOKS', '1')
    monkeypatch.setenv('HYPOTRAIL_FAULT', 'render_html')
    out = _propose(b)
    assert out.exit_code == cmd.EXIT_ARTIFACT_STALE == 3
    assert read.open(b.study).revision == before_rev + 1 == out.payload['revision']  # committed
    assert out.payload['result']['proposal_id'] in read.open(b.study).state['proposals']
    arts = out.payload['artifacts']
    assert arts['report']['status'] == 'failed' and arts['report']['error']['code'] == 'render_failed'
    assert arts['report']['last_ok_revision'] == before_rev
    assert arts['notebook']['status'] == 'ok'
    page = report.read_text()
    assert page != previous and _strip_banner(page) == _strip_banner(previous)
    assert 'data-hypotrail-banner="stale"' in page and 'Stale report.' in page
    banner = page.split(render_html.BANNER_START)[1].split(render_html.BANNER_END)[0]
    assert f'<span data-literal="revision">{before_rev}</span>' in banner
    assert f'<span data-literal="revision">{before_rev + 1}</span>' in banner
    manifest = mf.load(b.study)
    assert manifest['status'] == 'failed'
    assert manifest['artifacts']['report']['status'] == 'failed'
    assert view.build(b.study)['artifacts']['status'] == 'failed'
    events = [json.loads(line) for line in (b.study / '.hypotrail/events.jsonl').read_text().splitlines()]
    assert events[-1]['kind'] == 'render_failed' and events[-1]['artifacts'] == ['report']
    # never "all up to date": the payload names each artefact with its own status
    assert {a['status'] for a in arts.values()} == {'ok', 'failed'}
    # the next successful render replaces the page and drops the banner
    monkeypatch.delenv('HYPOTRAIL_FAULT')
    again = _propose(b, 'Keep the baseline, again.')
    assert again.exit_code == 0 and again.payload['artifacts']['report']['status'] == 'ok'
    assert 'data-hypotrail-banner' not in report.read_text()


def test_artifact_messages_say_what_happened(b, monkeypatch):
    """D7: every artefact carries one sentence; after a failed render it says that the
    previous report is kept and marked stale at the failed revision."""
    before = read.open(b.study).revision
    monkeypatch.setenv('HYPOTRAIL_TEST_HOOKS', '1')
    monkeypatch.setenv('HYPOTRAIL_FAULT', 'render_html')
    out = _propose(b)
    rev = out.payload['revision']
    arts = out.payload['artifacts']
    assert f'previous report kept and marked stale at revision {rev}' in arts['report']['message']
    assert f'from revision {before}' in arts['report']['message']
    # P3: an up-to-date message holds no revision number (a recap may repeat it).
    assert arts['notebook']['message'] == (f'The generated notebook ({mf.ARTIFACTS["notebook"]}) '
                                           f'is up to date.')
    assert arts['notebook']['revision'] == rev
    assert 'not tracked' in arts['workbench']['message']
    items = view.build(b.study)['artifacts']['items']
    assert items['report']['message'] == arts['report']['message']
    monkeypatch.setenv('HYPOTRAIL_FAULT', 'render_notebook')
    out = _propose(b, 'Keep the baseline, again.')
    rev = out.payload['revision']
    message = out.payload['artifacts']['notebook']['message']
    assert f'previous generated notebook kept and marked stale at revision {rev}' in message
    from mlkit.study.store import StudyStore
    store = StudyStore(b.study)
    with store.writing() as state:
        store.commit(state, {'request_id': None, 'action': 'test.advance', 'params': {},
                             'result': {}})
    stale = view.build(b.study)['artifacts']['items']['notebook']
    assert stale['status'] == 'failed'
    monkeypatch.delenv('HYPOTRAIL_FAULT')
    cmd_render.render_all(b.study)
    with store.writing() as state:
        store.commit(state, {'request_id': None, 'action': 'test.advance', 'params': {},
                             'result': {}})
    now = read.open(b.study).revision
    stale = view.build(b.study)['artifacts']['items']['report']
    assert stale['status'] == 'stale'
    assert stale['message'] == (f'The report ({mf.ARTIFACTS["report"]}) is stale: the study '
                                'changed after it was written. Render again before relying on it.')
    assert stale['revision'] == now - 1 and not re.search(r'\d', stale['message'].replace(
        mf.ARTIFACTS['report'], ''))


def test_repeated_failures_keep_a_single_banner(b, monkeypatch):
    monkeypatch.setenv('HYPOTRAIL_TEST_HOOKS', '1')
    monkeypatch.setenv('HYPOTRAIL_FAULT', 'render_html')
    _propose(b)
    _propose(b, 'Again.')
    page = (b.study / mf.ARTIFACTS['report']).read_text()
    assert page.count('data-hypotrail-banner=') == 1


def test_fault_is_ignored_without_test_hooks(b, monkeypatch):
    monkeypatch.delenv('HYPOTRAIL_TEST_HOOKS', raising=False)
    monkeypatch.setenv('HYPOTRAIL_FAULT', 'render_html,render_notebook')
    out = _propose(b)
    assert out.exit_code == 0 and all(a['status'] == 'ok' for a in out.payload['artifacts'].values())


def test_failed_notebook_is_reported_and_the_report_says_so(b, monkeypatch):
    notebook = b.study / mf.ARTIFACTS['notebook']
    previous = notebook.read_bytes()
    monkeypatch.setenv('HYPOTRAIL_TEST_HOOKS', '1')
    monkeypatch.setenv('HYPOTRAIL_FAULT', 'render_notebook')
    out = _propose(b)
    assert out.exit_code == 3
    arts = out.payload['artifacts']
    assert arts['notebook']['status'] == 'failed' and arts['report']['status'] == 'ok'
    assert notebook.read_bytes() == previous
    page = (b.study / mf.ARTIFACTS['report']).read_text()
    assert ('<tr data-surface="notebook" data-status="failed">' in page
            and texts.report()['surface_status']['failed'] in page)


def test_unknown_number_refused_at_render_keeps_previous_report(b, monkeypatch, no_hooks):
    report = b.study / mf.ARTIFACTS['report']
    previous = report.read_text()
    steps = texts.load('steps')
    monkeypatch.setitem(steps['steps'], 'split', dict(
        steps['steps']['split'], interpretation='Rows: {{r:' + 'e' * 64 + '.rows|int}}.'))
    out = _propose(b)
    assert out.exit_code == 3
    err = out.payload['artifacts']['report']['error']
    assert err['code'] == 'untraceable_number'
    assert _strip_banner(report.read_text()) == _strip_banner(previous)


def test_first_render_failure_writes_a_page_without_numbers(tmp_path, synthetic_case_dir,
                                                            monkeypatch):
    monkeypatch.setenv('HYPOTRAIL_TEST_HOOKS', '1')
    monkeypatch.setenv('HYPOTRAIL_FAULT', 'render_html')
    b = fx.build(tmp_path / 'study', synthetic_case_dir, upto='prediction_time')
    assert b.outcomes[0].exit_code == 3
    page = (b.study / mf.ARTIFACTS['report']).read_text()
    assert 'data-hypotrail-banner="stale"' in page and '<data ' not in page
    assert mf.load(b.study)['artifacts']['report']['last_ok_revision'] is None


def test_after_commit_never_raises_and_never_undoes_the_commit(b, monkeypatch, no_hooks):
    def boom(_study):
        raise RuntimeError('disk full')
    monkeypatch.setattr(cmd_render, 'render_all', boom)
    before = read.open(b.study).revision
    out = _propose(b)
    assert out.exit_code == 3 and read.open(b.study).revision == before + 1
    assert all(a['status'] == 'failed' and a['error']['message'] == 'RuntimeError: disk full'
               for a in out.payload['artifacts'].values())


def test_replay_does_not_render(b, no_hooks, monkeypatch):
    out = _propose(b)
    calls = []
    monkeypatch.setattr(cmd_render, 'render_all', lambda s: calls.append(s))
    again = cmd.apply(b.study, action=cmd.ACTION_PROPOSE, params={
        'decision_id': 'conclusion', 'value': {'verdict': 'keep_baseline', 'text': 'Keep the baseline.'},
        'restatement': 'You keep the baseline.', 'rationale': 'Proportionate.'},
        request_id=f'req-{b.n}', expected_revision=out.payload['revision'] - 1)
    assert again.payload['replayed'] is True and again.payload['artifacts'] is None
    assert calls == []


def test_stale_artifact_is_reported_when_the_state_moves_without_render(b, no_hooks):
    from mlkit.study.store import StudyStore

    store = StudyStore(b.study)
    with store.writing() as state:
        store.commit(state, {'request_id': None, 'action': 'test.advance', 'params': {},
                             'result': {}})
    state = read.open(b.study).state
    summary = mf.summary(mf.load(b.study), state)
    assert summary['report']['status'] == 'stale' and summary['notebook']['status'] == 'stale'
    assert summary['workbench']['status'] == 'ok'


# --- CLI processes ----------------------------------------------------------------------

def test_cli_render_and_decide_report_artifact_statuses(b):
    code, payload, err = _cli('render', '--study', b.study)
    assert code == 0, err
    assert payload['schema'] == cmd_render.SCHEMA and payload['ok'] is True
    assert list(payload) == ['schema', 'ok', 'study', 'revision', 'status', 'artifacts']
    assert payload['status'] == 'ok'
    code, payload, err = _cli('render', '--study', b.study, HYPOTRAIL_TEST_HOOKS='1',
                              HYPOTRAIL_FAULT='render_html')
    assert code == 3 and payload['status'] == 'failed', err
    rev = read.open(b.study).revision
    code, payload, err = _cli('decide', 'propose', 'conclusion', '--value-json',
                              json.dumps({'verdict': 'inconclusive', 'text': 'Not enough yet.'}),
                              '--restatement', 'You call it inconclusive.', '--rationale', 'Few rows.',
                              '--request-id', 'cli-1', '--expected-revision', rev,
                              '--study', b.study, HYPOTRAIL_TEST_HOOKS='1',
                              HYPOTRAIL_FAULT='render_html')
    assert code == 3, err
    assert payload['ok'] is True and payload['revision'] == rev + 1
    assert payload['artifacts']['report']['status'] == 'failed'
    code, status, _ = _cli('status', '--study', b.study)
    assert code == 0 and status['revision'] == rev + 1
    assert status['view']['artifacts']['status'] == 'failed'


def test_cli_render_refuses_in_a_read_only_process(b):
    code, payload, _ = _cli('render', '--study', b.study, HYPOTRAIL_READ_ONLY='1')
    assert code == 2 and payload['error']['code'] == 'read_only'


def test_status_plan_and_check_stay_free_of_heavy_imports(b):
    code = ('import json, sys\n'
            'from mlkit.study import cli\n'
            f'for argv in (["status", "--study", {str(b.study)!r}], ["plan", "--study", {str(b.study)!r}]):\n'
            '    assert cli.run(argv).exit_code == 0\n'
            'import importlib, importlib.util\n'
            'for m in ("mlkit.study.cmd_render", "mlkit.study.cmd_check"):\n'
            '    if importlib.util.find_spec(m):\n'
            '        importlib.import_module(m)\n'
            'print(json.dumps(sorted(sys.modules)))\n')
    proc = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True,
                          env=_env(), cwd=FRAMEWORK, timeout=120)
    assert proc.returncode == 0, proc.stderr
    mods = json.loads(proc.stdout.strip().splitlines()[-1])
    heavy = [m for m in mods if m.split('.')[0] in {'pandas', 'numpy', 'sklearn', 'scipy', 'marimo'}]
    assert heavy == []


def test_view_artifacts_use_the_effective_status_not_the_stored_one(b, no_hooks):
    """A render that went well becomes stale when state moves on without a render
    (here a consumed result made stale): view.artifacts says so."""
    from mlkit.study.store import StudyStore

    assert _propose(b).exit_code == 0
    v = view.build(b.study)
    assert v['artifacts']['status'] == 'ok'
    assert {i['status'] for i in v['artifacts']['items'].values()} == {'ok'}
    store = StudyStore(b.study)
    rid = v['results']['fit.logistic']['result_id']
    with store.writing() as state:                  # a mutation that does not render
        state['stale'][rid] = {'reason': 'test: made stale without a render', 'since': 1}
        store.commit(state, {'request_id': None, 'action': 'test.mutate', 'params': {},
                             'result': {}})
    after = view.build(b.study)['artifacts']
    items = after['items']
    assert items['report']['status'] == 'stale' and items['report']['recorded_status'] == 'ok'
    assert items['notebook']['status'] == 'stale'
    assert items['workbench']['status'] == 'ok'     # generated: false, never stale
    assert after['status'] == 'stale'
