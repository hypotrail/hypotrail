"""Helpers of the Phase 2 study tests: drive a study through ``cli.run`` or real processes.

Studies always live in temporary directories. The committed Bank case is only read;
the synthetic case is generated in a temporary directory by
``framework/tests/fixtures/synthetic/make_case.py``. Both cases go through the same
flows, which shows that the activities contain no dataset-specific code.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from mlkit.study import case as c, cli, read, registry, store as sto

FRAMEWORK = Path(__file__).resolve().parents[2]
REPO = FRAMEWORK.parent
TESTS = FRAMEWORK / 'tests'
BANK = REPO / 'use-cases' / 'bank-marketing'
SPLIT = {'method': 'stratified_random', 'validation_fraction': 0.3, 'seed': 20261017}

_spec = importlib.util.spec_from_file_location('synthetic_make_case_for_flowkit',
                                               TESTS / 'fixtures/synthetic/make_case.py')
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
make_case = _module.make_case

# Real cases whose data are copied from the installed scikit-learn by the use case's
# ``prepare.py`` (not committed: redistribution terms are not stated).
WDBC = REPO / 'use-cases' / 'breast-cancer-wdbc'
DIABETES = REPO / 'use-cases' / 'diabetes'


def prepare_module(case_dir: Path):
    """The ``prepare.py`` module of a use case, imported by path."""
    spec = importlib.util.spec_from_file_location(f'prepare_{Path(case_dir).name}'.replace('-', '_'),
                                                  Path(case_dir) / 'prepare.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def materialize(case_dir: Path, out: Path) -> Path:
    """A complete copy of a ``prepare.py`` case (``case.yaml`` and data) in ``out``."""
    prepare_module(case_dir).materialize(Path(out))
    return Path(out)


def env(**extra) -> dict:
    path = [str(FRAMEWORK)] + [p for p in os.environ.get('PYTHONPATH', '').split(os.pathsep) if p]
    out = {**os.environ, 'PYTHONPATH': os.pathsep.join(path), **extra}
    for key in ('HYPOTRAIL_READ_ONLY', 'HYPOTRAIL_FAULT', 'HYPOTRAIL_TEST_HOOKS'):
        if key not in extra:
            out.pop(key, None)
    return out


def hyp(*args, cwd, extra_env=None, expect=None, timeout=300):
    """One real CLI process; ``(exit code, parsed JSON)``."""
    proc = subprocess.run([sys.executable, '-m', 'mlkit.study.cli', *map(str, args)],
                          capture_output=True, text=True, cwd=cwd, env=env(**(extra_env or {})),
                          timeout=timeout)
    assert proc.stderr == '', proc.stderr
    lines = proc.stdout.strip().splitlines()
    assert len(lines) == 1, proc.stdout
    payload = json.loads(lines[0])
    if expect is not None:
        assert proc.returncode == expect, payload
    return proc.returncode, payload


def spawn(*args, cwd, extra_env=None) -> subprocess.Popen:
    return subprocess.Popen([sys.executable, '-m', 'mlkit.study.cli', *map(str, args)],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=cwd,
                            env=env(**(extra_env or {})))


def criterion(state) -> dict:
    """A success criterion for a test study (a test choice, not a recommendation)."""
    from mlkit.study import state as st
    if st.task_of(state) == st.REGRESSION:
        return {'metric': 'mae_reduction', 'min_share': 0.1}
    return {'metric': 'precision_gain', 'min_points': 5}


def availability(case_dir, **overrides) -> dict:
    """An availability decision that follows the case: not_available where the case says
    so, available_at_prediction otherwise (a test choice, not a recommendation)."""
    case = c.load_case(case_dir, verify_data=False)
    value = {v['name']: ('not_available' if v['availability']['value'] == 'not_available'
                         else 'available_at_prediction')
             for v in case.document['variables'] if v['role'] == 'feature'}
    value.update(overrides)
    return value


# The trade-offs need a reason in the junior's words (ADR 0005; WP-A9: a repetition of the
# value is no reason), so the test words for them give one.
REASON_DECISIONS = ('policy', 'model_choice', 'conclusion')


def default_words(decision: str) -> str:
    """The words a test study confirms ``decision`` with (a test choice)."""
    words = f'Yes, I want the {decision} exactly as you stated it'
    if decision in REASON_DECISIONS:
        words += ', because it fits our situation'
    return words


class Flow:
    """A study driven in-process through ``cli.run`` (same code path as the CLI)."""

    def __init__(self, study: Path, case_dir: Path, prefix: str = 'r'):
        self.study, self.case_dir, self.prefix, self.n = Path(study), Path(case_dir), prefix, 0

    def rid(self) -> str:
        self.n += 1
        return f'{self.prefix}{self.n}'

    def call(self, *args, expect=0):
        outcome = cli.run([str(a) for a in args])
        json.dumps(outcome.payload)
        if expect is not None:
            assert outcome.exit_code == expect, outcome.payload
        return outcome.payload

    def rev(self) -> int:
        return self.call('status', '--study', self.study)['revision']

    def view(self) -> dict:
        return self.call('status', '--study', self.study)['view']

    def init(self):
        return self.call('init', '--case', self.case_dir, '--study', self.study)

    def decide(self, decision, value, words=None):
        p = self.call('decide', 'propose', decision, '--value-json', json.dumps(value),
                      '--restatement', f'You decide the {decision} as stated.',
                      '--rationale', 'It fits the scenario.', '--request-id', self.rid(),
                      '--expected-revision', self.rev(), '--study', self.study)
        return self.call('decide', 'confirm', p['result']['proposal_id'], '--user-words',
                         words or default_words(decision),
                         '--request-id', self.rid(), '--expected-revision', self.rev(),
                         '--study', self.study)

    def pauses(self, split=True, model_decisions=True, **availability_overrides):
        """The decisions before the models: the prediction moment, the availability, the
        split, and (WP-A4, in a study that has them, unless ``model_decisions`` is False) the
        success criterion and the default preprocessing, both required before any fit."""
        self.decide('prediction_time', 'before the first contact of the campaign')
        self.decide('feature_availability', availability(self.case_dir, **availability_overrides))
        if split:
            self.decide('split', SPLIT)
            if model_decisions:
                self.model_decisions()

    def model_decisions(self, preprocessing=None):
        """WP-A4: confirm the success criterion and the preprocessing (the engine's default
        unless given), when the study has these decisions."""
        from mlkit.study import governance, state as st
        decisions = self.state()['decisions']
        if not st.has_wp_a4_decisions(self.state()):
            return
        if decisions['success_criterion']['status'] != 'confirmed':
            self.decide('success_criterion', criterion(self.state()))
        if decisions['preprocessing']['status'] != 'confirmed':
            self.decide('preprocessing', preprocessing or dict(governance.DEFAULT_PREPROCESSING))

    def run(self, activity, *options, expect=0, request_id=None):
        return self.call('run', activity, *options, '--request-id', request_id or self.rid(),
                         '--expected-revision', self.rev(), '--study', self.study, expect=expect)

    def state(self) -> dict:
        return read.open(self.study).state


def prepare(case_dir: Path, study: Path, upto: str = 'fits') -> Path:
    """Create a study and take it to ``upto``: ``pauses``, ``split``, ``eda``, ``fits``."""
    flow = Flow(study, case_dir, prefix='prep')
    flow.init()
    flow.pauses()
    if upto == 'pauses':
        return study
    flow.run('split')
    if upto == 'split':
        return study
    if upto == 'eda':
        for a in ('eda.target_rate', 'eda.special_values'):
            flow.run(a)
        return study
    flow.run('fit.baseline')
    flow.run('fit.logistic')
    return study


def clone(source: Path, target: Path) -> Path:
    """Copy a prepared study (state holds no path to the study directory itself)."""
    shutil.copytree(source, target)
    return target


def registry_entries(study: Path) -> list[dict]:
    return list(registry.entries(sto.StudyStore(study)))


def tree_digest(study: Path) -> dict:
    """sha256 of every file under ``.hypotrail/`` (to prove a command wrote nothing)."""
    home = Path(study) / '.hypotrail'
    return {str(p.relative_to(home)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(home.rglob('*')) if p.is_file()}


def exposure_records(study: Path) -> list[dict]:
    return read.open(study).exposure_records()


def deep(x):
    return copy.deepcopy(x)


def partition_keys(study: Path, part: str) -> list[str]:
    """Row keys of the study's ``development`` or ``final_test`` rows (ADR 0006), read
    from the recorded blob; [] when the study has no final test."""
    s = read.open(study)
    record = s.state.get('partition')
    if record is None:
        return []
    return [k for k in s.blob(record[part]['row_keys']).decode().splitlines() if k]
