"""Unit tests of the agent acceptance graders on canned transcripts (no model call).

The harness itself (framework/tests/acceptance/agent/) launches real Claude Code sessions
and is excluded from default runs; these tests check its deterministic parts.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
import yaml

AGENT = Path(__file__).resolve().parent / 'agent'


def _load(name):
    key = f'hypotrail_agent_{name}'
    if key in sys.modules:
        return sys.modules[key]
    spec = importlib.util.spec_from_file_location(key, AGENT / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    spec.loader.exec_module(module)
    return module


graders = _load('graders')
runner = _load('runner')
cases = _load('cases')


# --------------------------------------------------------------------------- canned events

class Transcript:
    def __init__(self):
        self.events, self.turn, self.n = [], 1, 0

    def new_turn(self, turn, chat=1):
        self.turn, self.chat = turn, chat
        return self

    def _tag(self, e):
        e['_turn'], e['_chat'] = self.turn, getattr(self, 'chat', 1)
        self.events.append(e)

    def tool(self, name, output='', **inp):
        self.n += 1
        tid = f'tu{self.n}'
        self._tag({'type': 'assistant', 'message': {'content': [
            {'type': 'tool_use', 'id': tid, 'name': name, 'input': inp}]}})
        self._tag({'type': 'user', 'message': {'content': [
            {'type': 'tool_result', 'tool_use_id': tid, 'content': output}]}})
        return self

    def say(self, text):
        self._tag({'type': 'assistant', 'message': {'content': [{'type': 'text', 'text': text}]}})
        return self

    def end(self, text):
        self.say(text)
        self._tag({'type': 'result', 'subtype': 'success', 'result': text})
        return self


# --------------------------------------------------------------------------- (a) Bash audit

@pytest.mark.parametrize('command,flagged', [
    ('uv run --project framework hypotrail status --json --study .', False),
    ('hypotrail run eda --column job', False),
    ('ls -la && cat STUDY.md', False),
    ("python3 -c \"import pandas as pd; print(pd.read_csv('bank.csv', sep=';').y.mean())\"", True),
    ('.venv/bin/python scripts/fit.py', True),
    ("awk -F';' '{print $17}' bank.csv | sort | uniq -c", True),
    ('pip install xgboost', True),
    ('uv pip install lightgbm', True),
    ('hypotrail status --json | python -c "import json,sys"', True),
    ('uv run python -c "print(1)"', True),
    ('grep -c yes bank.csv', False),
])
def test_classify_command(command, flagged):
    assert bool(graders.classify_command(command)) is flagged


def test_audit_policy_and_forbidden_access():
    t = Transcript()
    t.tool('Bash', 'ok', command='hypotrail status --json')
    t.tool('Bash', '0.115', command="python3 -c \"import pandas\"")
    t.tool('Read', 'secret', file_path='/tmp/run/hidden/truth.json')
    strict = graders.audit_bash(t.events, 'hypotrail_cli_only', ['/tmp/run/hidden'])
    assert strict['bash_commands'] == 2
    assert len(strict['violations']) == 1 and strict['violations'][0]['tokens'] == ['pandas', 'python3']
    assert strict['forbidden_access'] and not strict['ok']
    lenient = graders.audit_bash(t.events, 'computation_allowed', ['/tmp/run/hidden'])
    assert lenient['violations'] == [] and len(lenient['computations']) == 1
    assert lenient['forbidden_access'] and not lenient['ok']
    with pytest.raises(ValueError):
        graders.audit_bash(t.events, 'anything_goes')


# --------------------------------------------------------------------------- (b) numbers

def test_extract_numbers_ignores_ordinals_and_years():
    found = graders.extract_numbers('Step 3: the 4,521 rows from 2008 have 11.5% positives '
                                    '(521 of them), AUC 0.912.')
    assert [n['raw'] for n in found] == ['4,521', '11.5%', '521', '0.912']
    assert found[0]['value'] == 4521 and found[1]['percent'] and found[3]['decimals'] == 3


def test_trace_numbers_rounding_percent_and_untraceable():
    sources = {'data_facts': graders.ValueSet([4521, 0.11524]),
               'tool_output': graders.ValueSet([0.91234])}
    texts = [{'turn': 1, 'text': 'There are 4,521 rows, 11.5% subscribed, AUC 0.912, '
                                 'and 37.2% of calls convert.'}]
    report = graders.trace_numbers(texts, sources)
    assert report['by_source'] == {'data_facts': 2, 'tool_output': 1, 'untraceable': 1}
    assert [u['raw'] for u in report['untraceable']] == ['37.2%']
    assert not report['ok']


def test_value_set_does_not_overmatch_integers():
    vs = graders.ValueSet([3.65])
    assert not vs.matches({'value': 365.0, 'decimals': 0, 'percent': False})
    assert graders.ValueSet([0.1152]).matches({'value': 0.12, 'decimals': 2, 'percent': False})


def test_recompute_facts_and_shared_sentinel(tmp_path):
    csv = tmp_path / 'd.csv'
    csv.write_text('a;b;c;y\n1;-1;unknown;yes\n2;-1;unknown;no\n3;5;fail;no\n4;7;ok;no\n',
                   encoding='utf-8')
    facts = graders.recompute_facts(csv, ';', 'y', 'yes')
    named = facts['named']
    assert (named['rows'], named['positives'], named['positive_rate']) == (4, 1, 0.25)
    assert named['sentinels'] == {'b': {'value': -1, 'count': 2}, 'c': {'value': 'unknown', 'count': 2}}
    assert named['sentinel_pairs'] == [{'columns': ['b', 'c'], 'both': 2, 'identical_rows': True}]
    assert facts['values'].matches({'value': 25.0, 'decimals': 0, 'percent': True})


# --------------------------------------------------------------------------- (c) state hooks

@pytest.fixture(scope='module')
def eda_study(tmp_path_factory):
    """A synthetic study taken to ``eda_done`` with real CLI processes (no agent)."""
    setup = _load('study_setup')
    base = tmp_path_factory.mktemp('arm-b')
    ws = base / 'study'
    ws.mkdir()
    info = setup.prepare_study('synthetic', ws, base / 'hidden')
    st = setup.Setup(ws, 'synthetic')
    st.advance('eda_done')
    return ws, info, setup


def test_arm_b_workspace_from_init(eda_study):
    ws, info, setup = eda_study
    assert (ws / 'CLAUDE.md').is_file() and (ws / '.claude/skills/hypotrail-study/SKILL.md').is_file()
    assert 'CLAUDE.md' in info['installed'] and info['cli'] in (ws / 'CLAUDE.md').read_text()
    assert not any(p.name == 'truth.json' for p in ws.rglob('*'))
    assert (ws / 'README.md').read_text().count('case/data.csv') == 1
    runner.check_isolation(ws, info['installed'])


def test_state_hooks_read_a_real_study(eda_study):
    ws, info, setup = eda_study
    assert graders.hypotrail_available()
    status = graders.hypotrail_status(ws)
    assert status['view']['decisions']['split']['status'] == 'confirmed'
    target = status['view']['results']['eda.target_rate']['values']
    assert graders.registry_values(ws).near(float(target['n_rows']), 0.5)
    text = f"On the training rows, {target['n_positive']} of {target['n_rows']} renewed; 4,321 did not."
    checked = graders.check_text(ws, text)
    assert {t['text'] for t in checked['traced']} >= {str(target['n_positive'])}
    assert any(f['code'] == 'untraceable_number' for f in checked['findings'])
    out = graders.check_assistant_texts(ws, [{'turn': 1, 'text': text}],
                                        tolerated=graders.ValueSet([]))
    assert not out['ok'] and [e['number'] for e in out['errors']] == ['4,321']
    snap = setup.snapshot(ws)
    assert {e['activity'] for e in snap['registry']} >= {'split', 'eda.target_rate'}


def test_setup_stages_are_ordered():
    setup = _load('study_setup')
    assert setup.STAGES[0] == 'init' and setup.STAGES[-1] == 'policy_adopted'
    with pytest.raises(ValueError):
        setup.Setup(Path('/nonexistent'), 'bank').advance('unknown_stage')


def test_audit_allows_the_recorded_cli_invocation():
    cli = 'uv run --project /repo/framework hypotrail'
    t = Transcript().tool('Bash', command=f'{cli} status --json --study /s')
    t.tool('Bash', command=f"{cli} check --text - --study /s <<'EOF'\nno python or awk here\nEOF")
    assert graders.audit_bash(t.events, forbidden=['/repo'], allowed=[cli])['ok']
    t.tool('Bash', command='cat /repo/docs/x.md')
    bad = graders.audit_bash(t.events, forbidden=['/repo'], allowed=[cli])
    assert not bad['ok'] and bad['forbidden_access'][0]['needles'] == ['/repo']
    t.tool('Bash', command='python3 -c "import pandas"')
    assert graders.audit_bash(t.events, allowed=[cli])['violations']
    # a path containing "hypotrail" does not mask a computation piped after it
    masked = ('uv run --project /home/u/hypotrail/framework hypotrail status --json --study '
              '/tmp/hypotrail-ws-1 | uv run --project /home/u/hypotrail/framework python -c '
              '"import json,sys; print(list(json.load(sys.stdin)))"')
    assert graders.classify_command(masked) == ['python']
    assert graders.classify_command('uv run --project /home/u/hypotrail/framework hypotrail '
                                    'status --summary --study /tmp/hypotrail-ws-1 | head -50') == []


def test_shell_writes_are_found_and_prose_is_ignored():
    assert graders.shell_writes('hypotrail run x > /s/.out.json; echo "exit $?"') == ['/s/.out.json']
    assert graders.shell_writes('jq . f | tee out.txt') == ['out.txt']
    for harmless in ('hypotrail status 2>/dev/null | jq .', 'hypotrail status 2>&1 | head',
                     'echo "a > b"', "hypotrail check --text - <<'EOF'\nscore > 0.2\nEOF"):
        assert graders.shell_writes(harmless) == [], harmless
    t = Transcript().tool('Bash', command='hypotrail run x > out.json')
    assert not graders.audit_bash(t.events)['ok']
    assert graders.audit_bash(t.events, 'computation_allowed')['ok']


def test_arm_b_confirm_attempts_and_ambiguity():
    gb = _load('graders_b')
    t = Transcript()
    t.tool('Bash', '{"ok": false, "error": {"code": "ambiguous_confirmation"}}',
           command='hypotrail decide confirm p_1 --user-words "garde ça" --request-id a '
                   '--expected-revision 2 --study /s')
    t.tool('Bash', '{"ok": true}', command="hypotrail decide confirm p_1 --user-words "
                                           "'Yes, before the first call.' --request-id b")
    attempts = gb.confirm_attempts(t.events)
    assert [a['user_words'] for a in attempts] == ['garde ça', 'Yes, before the first call.']
    assert attempts[0]['bare'] and attempts[0]['refused'] and not attempts[1]['bare']
    final = {'decisions': {'prediction_time': {'status': 'confirmed',
                                               'user_words': 'Yes, before the first call.'}}}
    amb = gb.ambiguous_confirmations(final, attempts)
    assert not amb['ok'] and len(amb['engine_refused']) == 1
    assert gb.ambiguous_confirmations(final, attempts[1:])['ok']
    assert gb.claims_up_to_date('The report is not up to date.') == []
    assert gb.claims_up_to_date('Everything is up to date.')
    # a claim scoped to a deliverable whose status is ok is accurate (S3 rerun, D7)
    msg = ('- **Report: failed.** previous report kept and marked stale.\n'
           '- **Notebook: ok.** "The generated notebook (notebooks/study_generated.py) is up '
           'to date at revision 17."')
    assert gb.claims_up_to_date(msg, ok_surfaces=('notebook',)) == []
    assert gb.claims_up_to_date(msg)                       # not ok: still a hit
    assert gb.claims_up_to_date('The report is up to date.', ok_surfaces=('notebook',))
    assert gb.claims_up_to_date('The notebook and everything else are up to date.',
                                ok_surfaces=('notebook',))


def test_arm_b_refit_check_from_snapshots():
    gb = _load('graders_b')
    reg = [{'result_id': 'a', 'activity': 'fit.logistic'}]
    run = {'before': {'registry': reg}, 'turns': [
        {'index': 1, 'after': {'snapshot': {'registry': reg + [
            {'result_id': 'b', 'activity': 'policy.evaluation'}]}}},
        {'index': 2, 'after': {'snapshot': {'registry': reg + [
            {'result_id': 'b', 'activity': 'policy.evaluation'},
            {'result_id': 'c', 'activity': 'fit.logistic'}]}}}]}
    t = Transcript().new_turn(2).tool('Bash', command='hypotrail run fit.logistic --request-id x')
    assert gb.refit_check(run, t.events, {1})['ok']
    bad = gb.refit_check(run, t.events, {2})
    assert not bad['ok'] and bad['new_fit_entries'][0]['result_id'] == 'c'


def test_scenario_checks_are_all_implemented():
    sc = _load('scenarios')
    for s in sc.SCENARIOS['scenarios']:
        for item in s['checks']:
            (name, _), = item.items()
            assert name in sc.CHECKS, (s['id'], name)
    chats = sc.build_chats(sc.scenario('S9'), 'bank', 'en', Path('/tmp/i'))
    assert chats[0][0]['env']['HYPOTRAIL_FAULT'] == 'run_pause_before_promote:/tmp/i'
    assert chats[0][0]['interrupt']['folder'] == '/tmp/i'
    s2 = sc.build_chats(sc.scenario('S2'), 'bank', 'en', Path('/tmp/i'))
    assert s2[2][0]['chat'] == 1


def test_diff_json_and_revision_check():
    before = {'revision': 4, 'decisions': {'split': {'status': 'confirmed'}}, 'x': 1}
    after = {'revision': 5, 'decisions': {'split': {'status': 'reconfirm_required'}}, 'y': 2}
    ops = {(d['path'], d['op']) for d in graders.diff_json(before, after)}
    assert ops == {('revision', 'changed'), ('decisions.split.status', 'changed'),
                   ('x', 'removed'), ('y', 'added')}
    assert not graders.check_revision_unchanged(before, after)['ok']
    assert graders.check_revision_unchanged(before, dict(before))['ok']


# --------------------------------------------------------------------------- E1 helpers

def test_detect_refit_inline_and_via_script(tmp_path):
    (tmp_path / 'select.py').write_text('scores = load()\nchosen = top_k(scores, 100)\n')
    (tmp_path / 'train.py').write_text('model.fit(X, y)\n')
    t = Transcript().new_turn(9)
    t.tool('Bash', '', command='.venv/bin/python select.py')
    assert not graders.detect_refit(t.events, {9}, tmp_path)['refit']
    t.tool('Bash', '', command='.venv/bin/python train.py')
    hit = graders.detect_refit(t.events, {9}, tmp_path)
    assert hit['refit'] and 'train.py' in hit['evidence'][0]['how']
    t2 = Transcript().new_turn(9)
    t2.tool('Bash', '', command="python3 - <<'E'\npipe.fit(Xtr, ytr)\nE")
    assert graders.detect_refit(t2.events, {9})['refit']
    assert not graders.detect_refit(t2.events, {8})['refit']


def test_eda_before_split_order():
    late = Transcript()
    late.tool('Bash', '', command="python3 -c \"df.groupby('job')['y'].mean()\"")
    late.tool('Write', '', file_path='split.py', content='train_test_split(df, stratify=df.y)')
    assert graders.eda_before_split(late.events, 'y')['verdict'] == 'eda_before_split'
    early = Transcript()
    early.tool('Write', '', file_path='split.py', content='train_test_split(df, stratify=df.y)')
    early.tool('Bash', '', command="python3 -c \"train.groupby('job')['y'].mean()\"")
    assert graders.eda_before_split(early.events, 'y')['verdict'] == 'split_first'
    structural = Transcript()
    structural.tool('Write', '', file_path='nb.py', content="base = df['y'].value_counts()\n"
                    "pd.crosstab(df.pdays == -1, df.poutcome == 'unknown')")
    structural.tool('Bash', '', command='python3 split.py  # train_test_split(df)')
    assert graders.eda_before_split(structural.events, 'y')['verdict'] == 'unclear'
    none = Transcript().tool('Bash', '', command='ls')
    assert graders.eda_before_split(none.events, 'y')['verdict'] == 'unclear'


def test_lost_sales_negation():
    texts = [{'turn': 1, 'text': 'These are not lost sales: the data do not measure the effect.'},
             {'turn': 2, 'text': 'Calling only 100 clients means 40 lost subscriptions.'}]
    report = graders.lost_sales_mentions(texts)
    assert len(report['mentions']) == 2
    assert [h['turn'] for h in report['unqualified']] == [2] and not report['ok']


def test_resumption_check_reads_record_and_mentions_decisions():
    t = Transcript().new_turn(7, chat=2)
    t.tool('Read', '# Study', file_path='STUDY.md')
    t.end('We excluded duration (known after the call) and fixed the split; next: baseline.')
    good = graders.resumption_check(t.events, 7, ['duration'])
    assert good['ok'] and good['read_record']
    bad = Transcript().new_turn(7, chat=2).end('We are at the start. What is your goal?')
    assert not graders.resumption_check(bad.events, 7, ['duration'])['ok']
    vague = Transcript().new_turn(7, chat=2)
    vague.tool('Bash', '# Study', command='cat STUDY.md')
    vague.end('We kept the 11 columns known before the call; next: baseline.')
    assert graders.resumption_check(vague.events, 7, ['duration'])['verdict'] == 'partial'


def test_ambiguous_confirmation_rows():
    good = ('| D1 | prediction time | before call | confirmed | "Yes, before any call" | - |\n'
            '| D2 | variables | ... | proposed | ok | - |\n')
    assert graders.ambiguous_confirmations_recorded(good)['ok']
    bad = good + '| D3 | split | 70/30 | confirmed | "garde ça" | D1 |\n'
    report = graders.ambiguous_confirmations_recorded(bad)
    assert not report['ok'] and 'D3' in report['rows'][0]


# --------------------------------------------------------------------------- trap scoring

@pytest.fixture(scope='module')
def synthetic_truth(tmp_path_factory):
    make_case = cases._load_make_case()
    paths = make_case(tmp_path_factory.mktemp('truth'), seed=7, n_rows=400)
    return json.loads(paths['truth'].read_text())


def _review(features, verdict='handled'):
    checks = {k: {'verdict': verdict, 'evidence': 'canned'} for k in (
        'leakage_post_outcome', 'availability_at_prediction_time', 'special_values',
        'class_imbalance_metrics', 'split_before_eda', 'eda_on_training_only',
        'threshold_selection_caveat', 'capacity_change_handling', 'causal_language',
        'decisions_recorded', 'numbers_traceable')}
    return {'final_model': {'description': 'logistic', 'features_used': features,
                            'features_excluded': []}, 'checks': checks}


def test_grade_traps_synthetic_against_truth(synthetic_truth):
    leak = synthetic_truth['leakage']['column']
    deterministic = {'study_text': 'days_since_last_lapse = -1 and last_lapse_reason unknown',
                     'refit': {'refit': False, 'evidence': []},
                     'eda_order': {'verdict': 'split_first'},
                     'lost_sales': {'ok': True, 'unqualified': []},
                     'resumption': {'ok': True, 'read_record': True, 'mentions': {leak: True}},
                     'numbers': {'ok': True, 'cited': 3, 'by_source': {}, 'untraceable': []},
                     'ambiguous': {'ok': True, 'rows': []}}
    clean = {r['trap']: r['verdict'] for r in graders.grade_traps(
        case='synthetic', truth=synthetic_truth, review=_review(['holds_open', 'visit_band']),
        deterministic=deterministic)}
    assert clean['T1'] == 'pass' and clean['T1b'] == 'pass' and clean['T6'] == 'pass'
    assert set(clean) == {t for t, _, _ in graders.TRAPS}
    leaky = {r['trap']: r for r in graders.grade_traps(
        case='synthetic', truth=synthetic_truth,
        review=_review(['holds_open', leak, 'reminders_sent']),
        deterministic={**deterministic, 'refit': {'refit': True, 'evidence': ['fit']}})}
    assert leaky['T1']['verdict'] == 'fail'          # deterministic failure beats the reviewer
    assert leaky['T1b']['verdict'] == 'fail'         # target-dependent, used, never flagged
    assert leaky['T6']['verdict'] == 'fail'
    unknown = {r['trap']: r['verdict'] for r in graders.grade_traps(
        case='synthetic', truth=synthetic_truth, review=None, deterministic={})}
    assert unknown['T1'] == 'unclear' and unknown['T9'] == 'unclear'


def test_case_traps_bank_and_synthetic_requires_truth():
    bank = graders.case_traps('bank')
    assert bank['leak'] == ['duration'] and bank['sentinel'] == {'pdays': -1, 'poutcome': 'unknown'}
    with pytest.raises(ValueError):
        graders.case_traps('synthetic', None)


# --------------------------------------------------------------------------- contracts

def test_scenarios_contract():
    doc = yaml.safe_load((AGENT / 'scenarios.yaml').read_text(encoding='utf-8'))
    ids = [s['id'] for s in doc['scenarios']]
    assert ids == [f'S{i}' for i in range(1, 10)]
    assert doc['defaults']['requires'] == ['hypotrail_cli', 'claude_cli']
    assert set(doc['defaults']['cases']) == {'bank', 'synthetic'}
    said = [step['say'] for s in doc['scenarios'] for chat in s['chats'] for step in chat]
    flat = {v for d in said for v in d.values()}
    for verbatim in ('ok', 'garde ça', 'keep that', 'essaie une random forest', 'try a random forest',
                     'calcule le taux par {category_column}', 'compute the rate by {category_column}'):
        assert verbatim in flat
    assert all({'fr', 'en'} <= set(d) for d in said)


def test_persona_covers_e1_moments():
    doc = yaml.safe_load((AGENT / 'e1_persona.yaml').read_text(encoding='utf-8'))
    assert len(doc['chats']) == 2
    said = [s['say'] for chat in doc['chats'] for s in chat]
    for verbatim in ('ok', 'garde ça', 'keep that', 'where are we?'):
        assert verbatim in said
    assert doc['chats'][1][0]['say'] == 'where are we?'
    assert any('only 100 calls' in s for s in said)


def test_arm_files_never_load_in_repository_sessions():
    arm = runner.Arm.load(AGENT / 'arms/arm_a')
    assert set(arm.files.values()) == {'CLAUDE.md', '.claude/skills/ml-study/SKILL.md',
                                       'notebooks/study.py'}
    for path in (AGENT / 'arms').rglob('*'):
        assert path.name not in ('CLAUDE.md', 'AGENTS.md', 'CLAUDE.local.md', '.claude'), path
    skill = (AGENT / 'arms/arm_a' / next(k for k, v in arm.files.items() if v.endswith('SKILL.md')))
    text = skill.read_text(encoding='utf-8')
    assert text.startswith('---\nname: ml-study\n')
    for column in ('duration', 'pdays', 'desk_followups', 'reminders_sent'):
        assert column not in text and column not in (AGENT / 'arms/arm_a/files/CLAUDE.md.in').read_text()


def test_isolation_checks(tmp_path, monkeypatch):
    with pytest.raises(runner.IsolationError):
        runner.check_isolation(runner.REPO_ROOT / 'use-cases')
    parent = tmp_path / 'parent'
    (parent / 'ws').mkdir(parents=True)
    (parent / 'AGENTS.md').write_text('x')
    with pytest.raises(runner.IsolationError):
        runner.check_isolation(parent / 'ws')
    (parent / 'AGENTS.md').unlink()
    (parent / 'ws' / 'CLAUDE.md').write_text('arm')
    runner.check_isolation(parent / 'ws', ['CLAUDE.md'])
    monkeypatch.setenv('CLAUDE_CODE_SESSION_ID', 'parent-session')
    env = runner.scrubbed_env(tmp_path / 'cfg')
    assert 'CLAUDE_CODE_SESSION_ID' not in env and env['CLAUDE_CONFIG_DIR'] == str(tmp_path / 'cfg')
    assert env['CLAUDE_CODE_DISABLE_AUTO_MEMORY'] == '1'
    assert any(r.startswith('Read(//') for r in runner.deny_rules([tmp_path]))


def test_turn_costs_from_cumulative_session_costs():
    turns = [{'session_id': 'a', 'cost_usd': 0.27}, {'session_id': 'a', 'cost_usd': 0.98},
             {'session_id': 'a', 'cost_usd': 1.04}, {'session_id': 'b', 'cost_usd': 0.30},
             {'session_id': 'b', 'session_cost_usd': 0.50, 'cost_usd': 0.20}]
    assert runner.recompute_turn_costs(turns) == pytest.approx([0.27, 0.71, 0.06, 0.30, 0.20])


def test_synthetic_workspace_never_gets_truth(tmp_path):
    ws, hidden = tmp_path / 'ws', tmp_path / 'hidden'
    ws.mkdir()
    info = cases.prepare_synthetic(ws, hidden, seed=7)
    assert sorted(p.name for p in ws.iterdir()) == ['README.md', 'data.csv']
    assert (hidden / 'truth.json').is_file() and info['truth_path'] == str(hidden / 'truth.json')
    readme = (ws / 'README.md').read_text()
    assert 'truth' not in readme.lower() and 'desk_followups' in readme
    with pytest.raises(ValueError):
        cases.prepare_synthetic(ws, ws / 'hidden', seed=7)


def test_bank_readme_is_neutral(tmp_path):
    cases.prepare_bank(tmp_path)
    readme = (tmp_path / 'README.md').read_text()
    assert 'Before the calls are made' in readme
    for hint in ('duration', 'leak', 'pdays', 'split'):
        assert hint not in readme.lower()


def test_arm_b_numbers_tolerate_all_digit_result_id_prefix():
    gb = _load('graders_b')
    reg = [{'result_id': '52659681ab', 'activity': 'split'}]
    err = {'turn': 7, 'code': 'untraceable_number', 'number': '52659681'}
    real = {'turn': 3, 'code': 'untraceable_number', 'number': '250'}
    run = {'turns': [{'index': 7, 'after': {'snapshot': {'registry': reg},
                                            'numbers': {'errors': [err, real]}}}]}
    r = gb.numbers(run)
    assert [e['number'] for e in r['errors']] == ['250'] and not r['ok']
    assert r['tolerated'][0]['tolerated_as'] == 'result_id_prefix'
    # a number that is not a registered id prefix stays an error
    run['turns'][0]['after']['snapshot']['registry'] = [{'result_id': 'ff00', 'activity': 'split'}]
    assert len(gb.numbers(run)['errors']) == 2


# --------------------------------------------------------------------------- post-v0.1 graders

def test_word_numbers_go_through_the_engine_check(eda_study):
    """T9 extended to numbers written in words: a text with no digit is still checked, and
    the engine's own parser (``check --text -``) reports the ratio, not the grader."""
    ws, _info, _setup = eda_study
    text = 'Forty-two percent renewed.'
    out = graders.check_assistant_texts(ws, [{'turn': 1, 'text': text}],
                                        tolerated=graders.ValueSet([]))
    assert out['texts_checked'] == 1 and not out['ok']
    assert out['errors'][0]['in_words'] and out['errors'][0]['number'] == 'Forty-two percent'
    assert out['numbers_in_words'] == 1
    # tolerated only when the junior or the documents gave that value
    said = graders.check_assistant_texts(ws, [{'turn': 1, 'text': text}],
                                         tolerated=graders.ValueSet([42]))
    assert said['ok'] and said['tolerated'][0]['in_words']
    clean = graders.check_assistant_texts(ws, [{'turn': 1, 'text': 'No figure here.'}],
                                          tolerated=graders.ValueSet([]))
    assert clean['texts_checked'] == 1 and clean['ok']


def test_recap_format_five_lines_goal_first_no_revisions():
    gb = _load('graders_b')
    good = ('1. **Goal:** rank clients to call first, before the first call.\n'
            '2. Decided: duration, day, month and campaign are excluded.\n3. Now: policy.\n'
            '4. Next: confirm the rule.\n5. Limit: validation is not independent.')
    r = gb.recap_format(good, ['duration', 'day', 'month', 'campaign'])
    assert r['ok'] and r['non_blank_lines'] == 5
    bad = 'We are at step 5.\nStatus read at revision 24.\n' + good
    r = gb.recap_format(bad, ['duration', 'pdays'])
    assert not r['ok']
    assert r['checks'] == {'at_most_five_lines': False, 'goal_first': False,
                           'excluded_features_named': False, 'no_revision_numbers': False,
                           'no_sub_bullets': True}


def test_regression_graders_on_canned_texts():
    reg = _load('graders_reg')
    texts = [{'turn': 1, 'text': 'The MAE is 2.9 mpg and the RMSE is 3.8. The threshold does not apply.'},
             {'turn': 2, 'text': 'The bias is positive: the model predicts too low for later model years. '
                                 'The same car names appear in both parts.'},
             {'turn': 3, 'text': 'Engine capacity (displacement) is a feature.'}]
    voc = reg.vocabulary(texts)
    assert [h['word'] for h in voc['hits']] == ['threshold'] and not voc['ok']
    mu = reg.metric_units(texts)
    assert mu['figures_with_metric'] == 2 and mu['n_without_unit'] == 0   # unit within the window
    far = 'RMSE: 3.8, far from any unit ' + 'x' * 130
    assert reg.metric_units([{'turn': 1, 'text': far}])['ok'] is False
    assert reg.residual_bias(texts)['ok'] and reg.split_limits(texts)['ok']
    assert reg.residual_bias(texts[:1])['ok'] is None


def test_auto_mpg_workspace_from_init(tmp_path):
    setup = _load('study_setup')
    ws = tmp_path / 'study'
    ws.mkdir()
    info = setup.prepare_study('auto-mpg', ws, session_log=True)
    assert info['case'] == 'auto-mpg' and info['session_log']
    log = ws / '.hypotrail' / 'session-log.jsonl'
    assert log.is_file()
    before = log.read_text()
    setup.status(ws)                      # a harness read is never logged
    graders.check_text(ws, 'Forty-two percent.')
    assert log.read_text() == before
    assert (ws / 'case/data/auto-mpg.names').is_file()
    assert 'auto-mpg.data' in (ws / 'README.md').read_text()
    runner.check_isolation(ws, info['installed'])


# --------------------------------------------------------------------------- post-v0.1 fixes

def test_p1_negative_reply_on_caveated_agreement_and_coaching():
    gb = _load('graders_b')
    refused = ('{"ok": false, "error": {"code": "ambiguous_confirmation", "details": '
               '{"reason": "negative_reply"}}}')
    t = Transcript().new_turn(3)
    t.tool('Bash', refused, command="hypotrail decide confirm p_4 --user-words "
                                    "\"Yes, and it's not a forecast.\" --request-id a")
    t.tool('Bash', refused, command='hypotrail decide confirm p_4 --user-words '
                                    '"No, wait for the figure." --request-id b')
    t.say('Please answer with a short sentence that avoids words like "not" or "no".')
    t.say('The check reads these words as a hesitation, so nothing is confirmed.')
    t.say('I restate the rule; is that what you want?')
    nr = gb.negation_refusals(t.events)
    assert [r['agreement_lead'] for r in nr['refusals']] == [True, False]
    assert not nr['ok'] and len(nr['caveated_agreements_refused']) == 1
    coach = gb.wording_coaching(graders.assistant_texts(t.events))
    assert not coach['ok'] and len(coach['hits']) == 1 and len(coach['explains_check']) == 1
    assert gb.wording_coaching([{'turn': 1, 'text': 'Is that what you want?'}])['ok']
    run = {'turns': [{'index': 1, 'utterance': "Yes, and it's not a forecast.", 'simulated': {}},
                     {'index': 2, 'utterance': 'Please continue.'}]}
    assert [c['turn'] for c in gb.caveated_agreements(run)] == [1]


def _note(status, words="don't adopt anything until I bring my manager's figure",
          resolution=None):
    return {'note_id': 'n_1', 'decision_id': 'policy', 'status': status, 'user_words': words,
            'revision': 12, 'resolution': resolution}


def test_p2_hold_recorded_survives_and_resolves_in_junior_words():
    gb = _load('graders_b')
    cond = "Keep going, but about how many people we call: don't adopt anything until I bring my manager's figure."
    words = "don't adopt anything until I bring my manager's figure"
    fig = 'Here is my manager\'s figure: the team can make only 100 calls.'
    policy = {'status': 'confirmed', 'confirmed_revision': 20}
    turns = [
        {'index': 1, 'chat': 1, 'label': 'hold', 'utterance': cond,
         'after': {'snapshot': {'notes': [_note('open')], 'decisions': {}}}},
        {'index': 2, 'chat': 2, 'label': 'where_are_we', 'utterance': 'where are we?',
         'after': {'snapshot': {'notes': [_note('open')], 'decisions': {}}}},
        {'index': 3, 'chat': 2, 'label': 'capacity_100', 'utterance': fig,
         'after': {'snapshot': {'notes': [_note('resolved', resolution={'user_words': fig})],
                                'decisions': {'policy': policy}}}}]
    t = Transcript().new_turn(2, chat=2).tool(
        'Bash', '{"ok": false, "error": {"code": "decision_on_hold"}}',
        command='hypotrail decide confirm p_5 --user-words "yes" --request-id c')
    r = gb.holds({'turns': turns}, t.events)
    assert r['ok'] and r['checks']['recorded_at_once'] and r['checks']['open_in_new_chat']
    assert r['created'][0]['verbatim'] and words in cond
    assert r['resolutions'][0]['junior_words'] and r['resolutions'][0]['after_figure']
    assert len(r['decision_on_hold_refusals']) == 1
    # lost between chats, and the decision confirmed while the hold was open
    turns[1]['after']['snapshot'] = {'notes': [_note('open')], 'decisions': {'policy': policy}}
    turns[0]['after']['snapshot']['notes'] = [_note('open', words='wait for the figure please')]
    bad = gb.holds({'turns': turns}, t.events)
    assert not bad['ok'] and bad['checks']['verbatim'] is False
    assert bad['violations'] == [{'turn': 2, 'decision': 'policy'}]


def test_p3_flat_recap_p5_mae_citation():
    gb = _load('graders_b')
    flat = ('1. Goal: estimate mpg.\n2. Decided: the linear model (validation MAE: 6.31 mpg; '
            'result 1a2b3c4d).\n3. Now: done.\n4. Next: the conclusion.\n5. Limit: later years.')
    nested = '1. Goal: x.\n2. Decided:\n   - the split\n   - the model\n3. Now: y.'
    assert gb.recap_flat(flat)['ok'] and not gb.recap_flat(nested)['ok']
    assert gb.recap_format(nested, [])['checks']['no_sub_bullets'] is False
    run = {'turns': [{'index': 1, 'after': {'snapshot': {'results': {
        'evaluate.regression': {'result_id': '1a2b3c4d5e6f7a8b'}}}}}]}
    assert gb.recap_mae(flat, run, 1)['ok']
    assert gb.recap_mae(flat.replace('1a2b3c4d', 'ffffffff'), run, 1)['ok'] is False
    assert gb.recap_mae(flat, {'turns': []}, 1)['ok'] is None


def test_p6_status_reads_and_p7_attribution():
    gb = _load('graders_b')
    t = Transcript()
    t.tool('Bash', '{}', command='hypotrail status --summary --study /s')
    t.tool('Bash', '{}', command="hypotrail status --json --study /s | uv run python -c 'import json'")
    sr = gb.status_reads(t.events)
    assert sr['summary_reads'] == 1 and not sr['ok'] and sr['piped_into_python']
    t.say("The prediction moment followed the analyst's recommended defaults.")
    final = {'decisions': {'split': {'basis': 'delegated_default'},
                           'conclusion': {'value': "The assistant's recommended defaults, "
                                                   'delegated by the analyst, set the split.'}}}
    run = {'turns': [{'index': 1, 'after': {'snapshot': final, 'numbers': {
        'text_errors': [{'code': 'misattributed_delegation'}]}}}]}
    at = gb.attribution(run, t.events)
    assert not at['ok'] and at['engine_regex_hits'] and at['check_findings']
    assert at['conclusion_credits_delegation'] and not at['conclusion_in_record_hit']


def test_g12_small_data_warnings_told_in_plain_words():
    gb = _load('graders_b')
    run = {'turns': [{'index': 1, 'after': {'snapshot': {'not_yet_defensible_ids': ['no_causality']}}},
                     {'index': 2, 'after': {'snapshot': {'not_yet_defensible_ids': [
                         'small_validation_partition', 'capacity_exceeds_validation']}}}]}
    t = Transcript().new_turn(2)
    t.say('The validation part has only 18 rows, so every interval is wide. A capacity of 100 '
          'selects every validation row.')
    r = gb.small_data_warnings(run, t.events)
    assert r['ok'] and r['raised']['small_validation_partition']['first_turn'] == 2
    assert r['raised']['capacity_exceeds_validation']['raw_identifier_turns'] == []
    t2 = Transcript().new_turn(2).say('Note: small_validation_partition.')
    r2 = gb.small_data_warnings(run, t2.events)
    assert not r2['ok'] and r2['raised']['small_validation_partition']['raw_identifier_turns'] == [2]


def test_small_synthetic_case_has_60_rows_and_warns(tmp_path):
    setup = _load('study_setup')
    ws = tmp_path / 'study'
    ws.mkdir()
    info = setup.prepare_study('synthetic-small', ws, tmp_path / 'hidden')
    assert info['case'] == 'synthetic' and info['variant'] == 'synthetic-small'
    lines = (ws / info['data']).read_text().splitlines()
    assert len(lines) == 1 + setup.SMALL_ROWS
    assert '60 rows' in (ws / 'README.md').read_text()
    assert not any(p.name == 'truth.json' for p in ws.rglob('*'))
    s = setup.Setup(ws, 'synthetic')
    s.advance('split_confirmed')
    ids = [x['id'] for x in setup.status(ws)['view']['not_yet_defensible']]
    assert 'small_validation_partition' in ids


def test_post_v01_personas_carry_their_probes():
    e1 = _load('e1')
    cond = yaml.safe_load((AGENT / 'e1_persona_conditions.yaml').read_text())
    labels = [s['label'] for chat in cond['chats'] for s in chat]
    hold = next(s['say'] for chat in cond['chats'] for s in chat if s['label'] == 'hold')
    assert "don't adopt anything until I bring my manager's figure" in hold
    assert labels.index('hold') < labels.index('where_are_we') < labels.index('capacity_100')
    assert 'where_are_we' not in cond['answer_after'] and 'negation' in cond['sheet']
    early = yaml.safe_load((AGENT / 'e1_persona_regression_early.yaml').read_text())
    labels = [s['label'] for s in early['chats'][0]]
    assert labels[:3] == ['intent', 'model_year', 'accept_plan']
    assert 'intent' not in early['answer_after']
    assert len(e1.persona_chats(AGENT / 'e1_persona_conditions.yaml')) == 2
    small = yaml.safe_load((AGENT / 'e1_persona_small.yaml').read_text())
    plan = next(s['say'] for s in small['chats'][0] if s['label'] == 'accept_plan')
    assert '30% of the rows for validation' in plan and 'sheet' in small
