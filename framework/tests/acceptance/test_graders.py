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

def test_state_hooks_are_stubs_without_cli(monkeypatch, tmp_path):
    monkeypatch.setattr(graders.shutil, 'which', lambda name: None)
    assert not graders.hypotrail_available()
    for hook in (graders.hypotrail_status, graders.registry_values):
        with pytest.raises(graders.GraderUnavailable):
            hook(tmp_path)
    with pytest.raises(graders.GraderUnavailable):
        graders.check_text(tmp_path, 'text')


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
    assert doc['defaults']['requires'] == ['hypotrail_cli']
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
