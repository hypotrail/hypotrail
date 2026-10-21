"""``hypotrail run`` and ``hypotrail preview`` through real processes (WP2.1-WP2.4).

Every call is a fresh ``python -m mlkit.study.cli`` process whose working directory is
a temporary directory outside the repository. Concurrency is real: a paused ``run``
process (test hook) holds its lease while other processes decide or replay.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time

import pytest

from mlkit.study import cmd_preview, executions as ex, read

import flowkit as fk


@pytest.fixture(scope='module')
def cases(tmp_path_factory):
    return {'bank': fk.BANK,
            'synthetic': fk.make_case(tmp_path_factory.mktemp('synthetic'),
                                      n_rows=4000)['case'].parent}


@pytest.fixture
def work(tmp_path):
    folder = tmp_path / 'cwd'
    folder.mkdir()
    return folder


class Cli:
    """A study driven only by CLI processes."""

    def __init__(self, study, case_dir, work):
        self.study, self.case_dir, self.work, self.n = study, case_dir, work, 0

    def __call__(self, *args, expect=0, extra_env=None):
        return fk.hyp(*args, '--study', self.study, cwd=self.work, expect=expect,
                      extra_env=extra_env)[1]

    def rid(self):
        self.n += 1
        return f'cli-{self.n}'

    def rev(self):
        return self('status')['revision']

    def decide(self, decision, value, words):
        p = self('decide', 'propose', decision, '--value-json', json.dumps(value),
                 '--restatement', f'You decide the {decision} as stated.', '--rationale',
                 'It fits the scenario.', '--request-id', self.rid(),
                 '--expected-revision', self.rev())
        return self('decide', 'confirm', p['result']['proposal_id'], '--user-words', words,
                    '--request-id', self.rid(), '--expected-revision', self.rev())

    def run(self, *args, expect=0):
        return self('run', *args, '--request-id', self.rid(), '--expected-revision', self.rev(),
                    expect=expect)

    def split_pause(self):
        """The split, then (WP-A4) the success criterion and the default preprocessing."""
        self.decide('split', fk.SPLIT, 'Yes, split 70/30 with that seed before exploring')
        self.decide('success_criterion', {'metric': 'precision_gain', 'min_points': 5},
                    'Yes, at least 5 points over the baseline')
        self.decide('preprocessing', {'missing': 'none', 'rare_category_min_rows': 0, 'caps': {},
                                      'log_transform': []},
                    'Yes, I confirm the default preparation')


def _start(tmp_path, work, case_dir):
    cli = Cli(tmp_path / 'study', case_dir, work)
    fk.hyp('init', '--case', case_dir, '--study', cli.study, cwd=work, expect=0)
    cli.decide('prediction_time', 'before the first contact of the campaign',
               'Yes, we predict before the first contact')
    cli.decide('feature_availability', fk.availability(case_dir),
               'Yes, keep every variable available at prediction, except the ones known '
               'only afterwards')
    return cli


@pytest.mark.parametrize('name', ['bank', 'synthetic'])
def test_the_activity_flow_through_processes(tmp_path, work, cases, name):
    cli = _start(tmp_path, work, cases[name])
    refused = cli.run('split', expect=2)                            # pause 2 not confirmed
    assert refused['error']['code'] == 'precondition_missing'
    assert cli.run('eda.target_rate', expect=2)['error']['code'] == 'precondition_missing'
    cli.split_pause()
    # WP-B1: the variant the policy compares (named in words, fitted like the candidate).
    cli.decide('model_variant', {'kind': 'regularisation', 'strength': 'strong'},
               'Yes, compare it with the more strongly regularised variant')
    payloads = {}
    for args in (('split',), ('eda.target_rate',), ('eda.special_values',),
                 ('fit.baseline',), ('fit.logistic',), ('fit.variant',),
                 ('policy.evaluate', '--rule', 'threshold:0.5', '--rule', 'capacity:100')):
        payload = cli.run(*args)
        assert tuple(payload) == ex.PAYLOAD_KEYS and payload['schema'] == 'hypotrail.run/1'
        assert payload['status'] == 'promoted' and payload['replayed'] is False
        assert payload['revision'] == cli.rev()
        payloads[args[0]] = payload
    view = cli('status')['view']
    for slot, payload in (('split', payloads['split']), ('fit.logistic', payloads['fit.logistic']),
                          ('policy.evaluation', payloads['policy.evaluate'])):
        item = view['results'][slot]
        assert item['current'] is True and item['integrity'] == 'ok'
        assert item['result_id'] == payload['result_id'] and item['values'] == payload['values']
    steps = {step['id']: step['status'] for step in view['plan']}
    assert steps['train_eda'] == 'done' and steps['models'] == 'done'
    # v0.3 (WP-F1, R28): the diagnostics are part of the choice step, before the rule.
    assert view['next_action']['kind'] == 'run' and \
        view['next_action']['activity'] == 'diag.binary'
    assert cli.run('diag.binary')['status'] == 'promoted'
    after = cli('status')['view']['next_action']
    assert after['kind'] == 'propose' and after['decision'] == 'policy'
    by_purpose = view['exposure']['by_purpose']
    # ADR 0006: init inspects the development rows; the final test is sealed, not inspected.
    n = view['final_test']['development_rows']
    assert by_purpose['structural_inspection'] == n == payloads['split']['values']['n_rows']
    assert by_purpose['sealed'] == view['final_test']['rows'] == view['dataset']['rows'] - n
    train = payloads['split']['values']['partitions']['train']['n_rows']
    validation = payloads['split']['values']['partitions']['validation']['n_rows']
    assert by_purpose['train_eda'] == by_purpose['train_fit'] == train
    assert by_purpose['validation_model_evaluation'] == validation
    assert by_purpose['validation_policy_selection'] == validation
    adopted = cli.decide('policy', 'capacity:100', 'Yes, we call the top 100 and no more')
    assert adopted['result']['status'] == 'confirmed'
    preview = cli('preview', 'policy', '--rule', 'capacity:100')
    assert preview['adopted'] == {'status': 'confirmed', 'value': 'capacity:100'}
    assert preview['evaluations']['capacity:100'] == \
        payloads['policy.evaluate']['values']['rules']['capacity:100']['models']
    if name == 'bank':
        assert payloads['eda.target_rate']['values']['n_positive'] == 292   # v0.1: 365 (ADR 0006)
        assert payloads['fit.logistic']['values']['validation']['n_positive'] == 125   # v0.1: 156
        assert 'duration' not in payloads['fit.logistic']['values']['features']


def test_a_replay_while_the_execution_runs_reports_it_running(tmp_path, work, cases):
    cli = _start(tmp_path, work, cases['synthetic'])
    cli.split_pause()
    cli.run('split')
    gate = tmp_path / 'gate'
    rev = cli.rev()
    args = ('run', 'fit.logistic', '--request-id', 'slow-fit', '--expected-revision', rev,
            '--study', cli.study)
    proc = fk.spawn(*args, cwd=work, extra_env={
        'HYPOTRAIL_TEST_HOOKS': '1', 'HYPOTRAIL_FAULT': f'run_pause_before_promote:{gate}'})
    try:
        deadline = time.monotonic() + 120
        while not (gate / 'ready').exists():
            assert proc.poll() is None, proc.communicate()
            assert time.monotonic() < deadline
            time.sleep(0.05)
        code, replay = fk.hyp(*args, cwd=work)                  # the same request again
        assert code == 0 and replay['replayed'] is True and replay['status'] == 'running'
        other = cli.run('fit.baseline')                         # others can still work
        assert other['status'] == 'promoted'
        (gate / 'go').write_text('')
        out, err = proc.communicate(timeout=300)
    finally:
        if proc.poll() is None:
            proc.kill()
    assert proc.returncode == 0 and err == ''
    done = json.loads(out)
    # Other commits happened meanwhile, but none changed the logistic inputs.
    assert done['status'] == 'promoted' and done['revision'] > other['revision']
    code, later = fk.hyp(*args, cwd=work)
    assert later['replayed'] is True and later['status'] == 'promoted'
    assert later['result_id'] == done['result_id']
    assert read.open(cli.study).state['current']['fit.logistic'] == done['result_id']


def test_a_decision_taken_during_a_fit_makes_it_late(tmp_path, work, cases):
    cli = _start(tmp_path, work, cases['synthetic'])
    cli.split_pause()
    cli.run('split')
    gate = tmp_path / 'gate'
    proc = fk.spawn('run', 'fit.logistic', '--request-id', 'fit-during', '--expected-revision',
                    cli.rev(), '--study', cli.study, cwd=work,
                    extra_env={'HYPOTRAIL_TEST_HOOKS': '1',
                               'HYPOTRAIL_FAULT': f'run_pause_before_promote:{gate}'})
    try:
        deadline = time.monotonic() + 120
        while not (gate / 'ready').exists():
            assert proc.poll() is None, proc.communicate()
            assert time.monotonic() < deadline
            time.sleep(0.05)
        feature = next(f for f, v in fk.availability(cli.case_dir).items()
                       if v == 'available_at_prediction')
        cli.decide('feature_availability', fk.availability(cli.case_dir, **{feature: 'not_available'}),
                   f'Yes, {feature} is not known in time, exclude it')
        (gate / 'go').write_text('')
        out, err = proc.communicate(timeout=300)
    finally:
        if proc.poll() is None:
            proc.kill()
    assert proc.returncode == 0 and err == ''
    done = json.loads(out)
    assert done['status'] == 'late_not_promoted' and done['result_id']
    view = cli('status')['view']
    assert 'fit.logistic' not in view['results']
    assert done['execution_id'] in view['executions']['late']
    s = read.open(cli.study)
    assert feature in s.result(done['result_id'])['inputs']['features']


def test_activity_modules_import_neither_pandas_nor_sklearn():
    code = ('import json, sys\n'
            'import mlkit.study.cli, mlkit.study.cmd_run, mlkit.study.cmd_preview\n'
            'import mlkit.study.executions, mlkit.study.activities\n'
            'print(json.dumps(sorted(m for m in ("pandas", "sklearn", "scipy") '
            'if m in sys.modules)))\n')
    proc = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True,
                          env=fk.env(), timeout=120)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout.strip().splitlines()[-1]) == []


def test_run_argument_errors(tmp_path, work, cases):
    cli = _start(tmp_path, work, cases['synthetic'])
    rev = cli.rev()
    for args in (('run', '--request-id', 'a', '--expected-revision', rev),
                 ('run', 'split', '--acknowledge-interruption', 'e_x', '--request-id', 'a',
                  '--expected-revision', rev),
                 ('run', '--acknowledge-interruption', 'e_x', '--request-id', 'a',
                  '--expected-revision', rev),                      # no --user-words (D2)
                 ('run', 'split', '--user-words', 'go', '--request-id', 'a',
                  '--expected-revision', rev),
                 ('run', 'fit.forest', '--request-id', 'a', '--expected-revision', rev),
                 ('run', 'split', '--request-id', 'a')):
        payload = cli(*args, expect=2)
        assert payload['error']['code'] == 'invalid_arguments' and payload['command'] == 'run'
    assert cli('preview', 'policy', '--rule', 'capacity:5',
               expect=2)['error']['code'] == 'precondition_missing'
    assert tuple(cmd_preview.PAYLOAD_KEYS)[:2] == ('schema', 'ok')
