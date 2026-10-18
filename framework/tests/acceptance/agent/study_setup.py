"""Hypotrail study workspaces for agent acceptance (arm B of E1, scenarios S1-S9).

The study workspace is created exactly as a junior would get it: the case is copied into
``<workspace>/case/`` (Bank: ``case.yaml`` and its ``data/`` files; synthetic: the
``case.yaml`` and ``data.csv`` written by ``make_case`` into a hidden directory, never
``truth.json``), a neutral ``README.md`` describes the scenario (the same text arm A got,
with the file paths of the case folder), and ``hypotrail init --case <case.yaml> --study
<workspace>`` installs ``CLAUDE.md``, the skill, and the resume command.

``advance`` then builds the study state with direct CLI processes (no agent) up to a named
stage of the WP4.2 walkthrough, with the junior's words of
``framework/tests/study/test_walkthrough.py``, so that a scenario starts where it matters.

Every CLI call is a fresh ``python -m mlkit.study.cli`` process of the framework
environment, run from a directory outside the repository.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[3]
FRAMEWORK = REPO_ROOT / 'framework'
BANK = REPO_ROOT / 'use-cases' / 'bank-marketing'
AUTO_MPG = REPO_ROOT / 'use-cases' / 'auto-mpg'

SPLIT = {'method': 'stratified_random', 'validation_fraction': 0.3, 'seed': 20261017}
THRESHOLD = 'threshold:0.2'

# The junior's words, as in the WP4.2 walkthrough (framework/tests/study/test_walkthrough.py).
JUNIOR = {
    'bank': {
        'prediction_time': 'before the first contact of the campaign, from the client file',
        'restatement': 'You score each client before the first call, from what the client '
                       'file holds at that moment.',
        'words': 'Yes, before the first call, using only the client file.',
        'exclusions': {'duration': 'not_available', 'day': 'not_available',
                       'month': 'not_available', 'campaign': 'not_available',
                       'contact': 'uncertain_included'},
        'availability_words': 'Drop duration, day, month and campaign: they describe the calls '
                              'of this campaign. Keep contact but list it as a doubt.',
        'rate_by': 'job',
        # S2: an earlier, different prediction moment that the junior corrects in a second chat
        'prediction_time_s2': 'before each call of the campaign, from the client file and the '
                              'calls made so far',
        'restatement_s2': 'You score each client before each call, from the client file and the '
                          'calls made so far.',
        'words_s2': 'Yes, before each call, with what we know at that point.',
    },
    'synthetic': {
        'prediction_time': 'when the membership expires, before any reminder is sent',
        'restatement': 'You score each member when the membership expires, before the first '
                       'reminder.',
        'words': 'Yes, at expiry, before any reminder goes out.',
        'exclusions': {'desk_followups': 'not_available', 'reminders_sent': 'not_available',
                       'last_reminder_weekday': 'not_available',
                       'fines_outstanding': 'uncertain_included'},
        'availability_words': 'Leave out the desk follow-ups and both reminder columns; keep the '
                              'fines but mark them as uncertain.',
        'rate_by': 'home_branch',
        'prediction_time_s2': 'before each reminder of the cycle, from the member file and the '
                              'reminders sent so far',
        'restatement_s2': 'You score each member before each reminder, from the member file and '
                          'the reminders sent so far.',
        'words_s2': 'Yes, before each reminder, with what we know at that point.',
    },
}

STAGES = ('init', 'availability_proposed', 'split_confirmed', 'eda_done',
          'baseline_and_logistic_fitted', 'policy_evaluated', 'policy_adopted')

BANK_README = """\
# Term deposit campaign: whom to call first

## Files

- `case/data/bank.csv`: one row per client contacted in a past phone campaign of a
  Portuguese bank; semicolon-separated, header on the first line. The target column is `y`
  (`yes` = the client subscribed a term deposit).
- `case/data/bank-names.txt`: the original documentation distributed with the data.
- `case/case.yaml`: the case description used by the study tool.

The data are the public UCI "Bank Marketing" extract (Moro, Laureano and Cortez, 2011;
CC BY 4.0). Do not modify these files.

## Scenario

The bank is preparing its next phone campaign for the term deposit. The call team has
limited capacity and cannot call every client. **Before the calls are made**, we would like
to decide which clients to call first.

This is a learning exercise on public data: the scenario is an assumption for the
exercise, not a decision taken by the bank.
"""


AUTO_MPG_README = """\
# Fuel consumption of car models

## Files

- `case/data/auto-mpg.data`: one row per car model and model year, whitespace-separated,
  no header line. The column order is given in `case/data/auto-mpg.names`.
- `case/data/auto-mpg.names`: the original documentation distributed with the data.
- `case/case.yaml`: the case description used by the study tool.

The data are the public UCI "Auto MPG" data set (Quinlan, 1993; CC BY 4.0). Do not modify
these files.

## Scenario

We would like to estimate the fuel consumption (miles per gallon) of newer car models from
what we know about older ones.

This is a learning exercise on public data: the scenario is an assumption for the
exercise, not a decision taken by anyone.
"""


class CliError(RuntimeError):
    pass


def cli_env(extra: dict | None = None) -> dict:
    path = [str(FRAMEWORK)] + [p for p in os.environ.get('PYTHONPATH', '').split(os.pathsep) if p]
    env = {**os.environ, 'PYTHONPATH': os.pathsep.join(path)}
    for key in ('HYPOTRAIL_READ_ONLY', 'HYPOTRAIL_FAULT', 'HYPOTRAIL_TEST_HOOKS', 'HYPOTRAIL_CLI'):
        env.pop(key, None)
    env.update(extra or {})
    return env


def hyp(*args, cwd: Path | None = None, stdin: str | None = None, extra_env=None,
        expect: int | tuple | None = 0, timeout: int = 600) -> tuple[int, dict]:
    """One CLI process: ``(exit code, payload)``."""
    proc = subprocess.run([sys.executable, '-m', 'mlkit.study.cli', *map(str, args)],
                          input=stdin, capture_output=True, text=True,
                          cwd=str(cwd or Path(os.sep) / 'tmp'), env=cli_env(extra_env),
                          timeout=timeout)
    try:
        payload = json.loads(proc.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as exc:
        raise CliError(f'hypotrail {args[:2]}: no JSON (exit {proc.returncode}): '
                       f'{proc.stdout[-500:]} {proc.stderr[-500:]}') from exc
    if expect is not None:
        ok = proc.returncode in (expect if isinstance(expect, tuple) else (expect,))
        if not ok:
            raise CliError(f'hypotrail {" ".join(map(str, args[:3]))}: exit {proc.returncode}: '
                           f'{json.dumps(payload)[:800]}')
    return proc.returncode, payload


def status(study: Path) -> dict:
    return hyp('status', '--json', '--study', study)[1]


def check_text(study: Path, text: str) -> dict:
    return hyp('check', '--text', '-', '--study', study, stdin=text)[1]


def registry_entries(study: Path) -> list[dict]:
    reg = Path(study) / '.hypotrail' / 'registry'
    if not reg.is_dir():
        return []
    out = []
    for f in sorted(reg.glob('*.json')):
        try:
            out.append(json.loads(f.read_text(encoding='utf-8')))
        except json.JSONDecodeError:
            continue
    return out


def exposure_records(study: Path) -> list[dict]:
    f = Path(study) / '.hypotrail' / 'exposure.jsonl'
    if not f.is_file():
        return []
    return [json.loads(line) for line in f.read_text(encoding='utf-8').splitlines() if line.strip()]


def snapshot(study: Path) -> dict:
    """What a grader compares before and after an agent turn."""
    st = status(study)
    reg = registry_entries(study)
    return {'revision': st['revision'], 'view': st['view'],
            'registry': [{'result_id': e['result_id'], 'activity': e['activity'],
                          'created': e.get('created'), 'execution_id': e.get('execution_id'),
                          'params': e.get('params')} for e in reg],
            'exposure_n': len(exposure_records(study))}


# --------------------------------------------------------------------------- workspaces

def _load_make_case():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        'synthetic_make_case_for_arm_b', FRAMEWORK / 'tests/fixtures/synthetic/make_case.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.make_case


def prepare_case(case: str, workspace: Path, hidden_dir: Path | None = None,
                 seed: int = 20261018) -> dict:
    """Copy the case into ``workspace/case`` and write the neutral README. No init."""
    ws = Path(workspace)
    dest = ws / 'case'
    if case == 'bank':
        (dest / 'data').mkdir(parents=True, exist_ok=True)
        shutil.copyfile(BANK / 'case.yaml', dest / 'case.yaml')
        for name in ('bank.csv', 'bank-names.txt'):
            shutil.copyfile(BANK / 'data' / name, dest / 'data' / name)
        (ws / 'README.md').write_text(BANK_README, encoding='utf-8')
        return {'case': 'bank', 'data': 'case/data/bank.csv', 'sep': ';', 'target': 'y',
                'positive': 'yes', 'case_yaml': 'case/case.yaml',
                'files': ['README.md', 'case/case.yaml', 'case/data/bank.csv',
                          'case/data/bank-names.txt']}
    if case == 'auto-mpg':
        (dest / 'data').mkdir(parents=True, exist_ok=True)
        shutil.copyfile(AUTO_MPG / 'case.yaml', dest / 'case.yaml')
        for name in ('auto-mpg.data', 'auto-mpg.names'):
            shutil.copyfile(AUTO_MPG / 'data' / name, dest / 'data' / name)
        (ws / 'README.md').write_text(AUTO_MPG_README, encoding='utf-8')
        return {'case': 'auto-mpg', 'data': 'case/data/auto-mpg.data', 'sep': 'whitespace',
                'target': 'mpg', 'positive': None, 'case_yaml': 'case/case.yaml',
                'files': ['README.md', 'case/case.yaml', 'case/data/auto-mpg.data',
                          'case/data/auto-mpg.names']}
    if case == 'synthetic':
        from importlib import util as _u   # noqa: F401  (keeps the import local)
        if hidden_dir is None:
            raise ValueError('synthetic case needs a hidden directory for truth.json')
        hidden = Path(hidden_dir).resolve()
        if ws.resolve() == hidden or ws.resolve() in hidden.parents:
            raise ValueError('the hidden truth directory must be outside the workspace')
        hidden.mkdir(parents=True, exist_ok=True)
        paths = _load_make_case()(hidden, seed=seed)
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(paths['case'], dest / 'case.yaml')
        doc = yaml.safe_load(paths['case'].read_text(encoding='utf-8'))
        shutil.copyfile(paths['data'], dest / doc['dataset']['path'])
        import importlib.util
        spec = importlib.util.spec_from_file_location('agent_cases_for_arm_b', HERE / 'cases.py')
        cases = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cases)
        readme = cases.synthetic_readme(doc).replace(
            f"- `{doc['dataset']['path']}`:", f"- `case/{doc['dataset']['path']}`:")
        readme = readme.replace('## Scenario', '- `case/case.yaml`: the case description used '
                                               'by the study tool.\n\n## Scenario', 1)
        (ws / 'README.md').write_text(readme, encoding='utf-8')
        assert not any(p.name == 'truth.json' for p in ws.rglob('*'))
        return {'case': 'synthetic', 'data': f"case/{doc['dataset']['path']}", 'sep': ';',
                'target': 'outcome', 'positive': 'renewed', 'seed': seed,
                'case_yaml': 'case/case.yaml', 'truth_path': str(paths['truth']),
                'files': ['README.md', 'case/case.yaml', f"case/{doc['dataset']['path']}"]}
    raise ValueError(f'unknown case {case!r}')


def init_study(workspace: Path, info: dict) -> dict:
    """``hypotrail init`` in the workspace; returns the init payload."""
    ws = Path(workspace)
    _, payload = hyp('init', '--case', ws / info['case_yaml'], '--study', ws)
    return payload


def enable_session_log(workspace: Path) -> None:
    """Create the study's opt-in, content-free session log (``HYPOTRAIL_SESSION_LOG=1`` on
    one read-only-in-effect ``status`` call); every later CLI call of any chat appends to it."""
    hyp('status', '--summary', '--study', workspace, extra_env={'HYPOTRAIL_SESSION_LOG': '1'})


def prepare_study(case: str, workspace: Path, hidden_dir: Path | None = None,
                  seed: int = 20261018, session_log: bool = False) -> dict:
    info = prepare_case(case, workspace, hidden_dir, seed)
    init = init_study(workspace, info)
    if session_log:
        enable_session_log(workspace)
        info['session_log'] = True
    info['init'] = {k: init[k] for k in ('revision', 'case', 'dataset', 'agent_instructions')}
    info['installed'] = list(init['agent_instructions']['copied'])
    info['cli'] = init['agent_instructions']['cli']
    import hashlib
    info['data_sha256'] = hashlib.sha256((Path(workspace) / info['data']).read_bytes()).hexdigest()
    return info


# --------------------------------------------------------------------------- stages

class Setup:
    """Direct CLI driver that takes a study through the walkthrough stages."""

    def __init__(self, study: Path, case: str, variant: str | None = None):
        self.study, self.case, self.variant, self.n = Path(study), case, variant, 0
        self.junior = JUNIOR[case]
        self.log: list[dict] = []

    def rev(self) -> int:
        return status(self.study)['revision']

    def rid(self, what: str) -> str:
        self.n += 1
        return f'setup-{self.n}-{what}'

    def call(self, *args, expect=0):
        code, payload = hyp(*args, '--study', self.study, expect=expect)
        self.log.append({'args': [str(a) for a in args[:3]], 'exit': code})
        return payload

    def propose(self, decision, value, restatement, rationale='It fits the use case.'):
        flag = '--value' if isinstance(value, str) else '--value-json'
        shown = value if isinstance(value, str) else json.dumps(value)
        out = self.call('decide', 'propose', decision, flag, shown, '--restatement', restatement,
                        '--rationale', rationale, '--request-id', self.rid(f'propose-{decision}'),
                        '--expected-revision', self.rev())
        return out['result']['proposal_id']

    def confirm(self, proposal, words):
        return self.call('decide', 'confirm', proposal, '--user-words', words, '--request-id',
                         self.rid('confirm'), '--expected-revision', self.rev())

    def run(self, activity, *options):
        return self.call('run', activity, *options, '--request-id', self.rid(f'run-{activity}'),
                         '--expected-revision', self.rev())

    def availability_value(self) -> dict:
        case_yaml = Path(status(self.study)['view']['case']['path'])
        doc = yaml.safe_load(case_yaml.read_text(encoding='utf-8'))
        value = {v['name']: ('not_available' if v['availability']['value'] == 'not_available'
                             else 'available_at_prediction')
                 for v in doc['variables'] if v['role'] == 'feature'}
        value.update(self.junior['exclusions'])
        return value

    def advance(self, until: str) -> None:
        if until not in STAGES:
            raise ValueError(f'unknown stage {until!r}; one of {STAGES}')
        stop = STAGES.index(until)
        j = self.junior
        if stop >= 1:
            if self.variant == 's2':
                p = self.propose('prediction_time', j['prediction_time_s2'], j['restatement_s2'])
                self.confirm(p, j['words_s2'])
            else:
                p = self.propose('prediction_time', j['prediction_time'], j['restatement'])
                self.confirm(p, j['words'])
            self.availability_proposal = self.propose(
                'feature_availability', self.availability_value(),
                'You exclude the variables you listed and keep the doubtful one as a stated limit.')
        if stop >= 2:
            self.confirm(self.availability_proposal, j['availability_words'])
            p = self.propose('split', SPLIT, 'A stratified random split: 30% of rows for '
                                             'validation, seed 20261017, fixed before exploring.')
            self.confirm(p, 'Yes, fix that split now, before we look at the outcome.')
            self.run('split')
        if stop >= 3:
            self.run('eda.target_rate')
            self.run('eda.special_values')
            self.run('eda.rate_by', '--column', j['rate_by'])
        if stop >= 4:
            self.run('fit.baseline')
            self.run('fit.logistic')
        if stop >= 5:
            self.run('policy.evaluate', '--rule', THRESHOLD)
        if stop >= 6:
            p = self.propose('policy', THRESHOLD, 'You call every client whose score is at least 0.2.')
            self.confirm(p, 'Yes, call everyone scored 0.2 or more.')
