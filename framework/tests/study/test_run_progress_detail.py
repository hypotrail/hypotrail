"""Owner session 2026-10-26, lot L8 (R10 level 2): where a long run is, fold by fold.

``run --progress`` (lot L4) writes start, heartbeat and end lines on stderr. Level 2 adds the
position inside the computation: the fingerprinted modules call ``progress.step`` at each
outer fold of a cross-validated fit (``fit``), each value of an inner tuning grid
(``families.choose``) and each bootstrap replicate (``policy``, ``regression``,
``objective``); the activity's phase writes "Le modèle logistique · en cours · pli 2/5 · 14 s".
``step`` does nothing without a listener, so stdout and every computed value are the same with
or without the flag, and nothing is written to stderr without it (NR-17).
"""
from __future__ import annotations

import io
import json

import pytest

from mlkit.study import executions, families, fit, objective, policy, progress, regression

import flowkit as fk
from test_run_progress import _cli, _study

CV = {'method': 'kfold_stratified', 'folds': 5, 'seed': 7}
TUNED = {'kind': 'tuned', 'question': 'Does a tuned penalty rank the rows better?'}


class _Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def _reporter(language='en'):
    clock = _Clock()
    return progress.Reporter(io.StringIO(), language, interval=1000, clock=clock), clock


def test_step_does_nothing_without_a_listener():
    assert progress._LISTENER.get() is None
    progress.step('fold', 1, 5)                    # no reporter: nothing, no error
    reporter, clock = _reporter()
    with reporter.deliverables():                  # the deliverables never listen
        progress.step('fold', 1, 5)
    assert reporter.stream.getvalue().splitlines() == [
        'The report and the notebook · started', 'The report and the notebook · done in 0 s']
    assert progress._LISTENER.get() is None


def test_a_fold_line_each_fold_and_finer_steps_at_most_every_second():
    reporter, clock = _reporter('fr')
    with reporter.activity('fit.logistic'):
        for f in (1, 2):
            clock.now += 0.4
            progress.step('fold', f, 2)
            for g in range(1, 6):
                clock.now += 0.3
                progress.step('grid', g, 5, 'C')
        clock.now += 0.2
        progress.step('replicate', 1, 200)
    assert progress._LISTENER.get() is None
    assert reporter.stream.getvalue().splitlines() == [
        'Le modèle logistique · démarré',
        'Le modèle logistique · en cours · pli 1/2 · 0 s',
        'Le modèle logistique · en cours · pli 1/2 · pénalité 4/5 · 1 s',
        'Le modèle logistique · en cours · pli 2/2 · 2 s',
        'Le modèle logistique · en cours · pli 2/2 · pénalité 4/5 · 3 s',
        'Le modèle logistique · terminé en 3 s']


def test_the_heartbeat_repeats_where_the_run_is_and_words_follow_the_language():
    reporter, clock = _reporter('en')
    with reporter.activity('policy.evaluation'):
        progress.step('replicate', 1, 1000)
        clock.now += 0.5
        progress.step('replicate', 600, 1000)       # within a second: no line
        assert reporter._running('X', 0.0) == 'X · running · bootstrap replicate 600/1000 · 0 s'
        progress.step('grid', 2, 2, 'max_depth')    # a coarser step clears the replicate
        assert reporter._detail() == 'grid value 2/2'
    lines = reporter.stream.getvalue().splitlines()
    assert lines[1].endswith('· running · bootstrap replicate 1/1000 · 0 s'), lines
    assert len(lines) == 3, lines
    assert progress.step_words('grid', 3, 5, 'alpha', 'fr') == 'pénalité 3/5'
    assert progress.step_words('grid', 1, 2, 'interactions', 'fr') == 'valeur de la grille 1/2'
    assert progress.step_words('replicate', 9, 10, None, 'fr') == 'réplication bootstrap 9/10'
    assert progress.step_words('fold', 2, 5, None, 'en') == 'fold 2/5'


def test_a_listener_that_fails_never_changes_the_run():
    token = progress._LISTENER.set(lambda *a: 1 / 0)
    try:
        progress.step('fold', 1, 2)
    finally:
        progress._LISTENER.reset(token)


def test_the_computation_modules_report_their_steps(monkeypatch):
    """Each module the plan names calls ``step`` (the shared function, not a copy)."""
    for module in (fit, families, policy, regression, objective):
        assert module.step is progress.step, module.__name__
    seen = []
    token = progress._LISTENER.set(lambda *a: seen.append(a))
    try:
        import numpy as np
        y = np.array([0, 1] * 20)
        policy.paired_bootstrap(y, {'a': np.linspace(0, 1, 40), 'b': np.linspace(1, 0, 40)},
                                'share:0.2', 3, 1)
        regression.paired_bootstrap(np.arange(10.0), {'a': np.arange(10.0) + 1,
                                                      'b': np.arange(10.0)}, 2, 1)
    finally:
        progress._LISTENER.reset(token)
    assert seen == [('replicate', 1, 3, None), ('replicate', 2, 3, None),
                    ('replicate', 3, 3, None), ('replicate', 1, 2, None),
                    ('replicate', 2, 2, None)]


def _cv_study(tmp_path, case_dir, language):
    flow = fk.Flow(tmp_path / f'cv-{language}', case_dir)
    flow.call('init', '--case', case_dir, '--study', flow.study, '--lang', language)
    flow.decide('prediction_time', 'before the first contact of the campaign')
    flow.decide('feature_availability', fk.availability(case_dir))
    flow.decide('split', CV)
    flow.model_decisions()
    flow.run('split')
    return flow


@pytest.mark.parametrize('language, fold', [('en', 'fold'), ('fr', 'pli')])
def test_a_cross_validated_fit_says_each_fold_on_stderr_only(tmp_path, synthetic_case_dir,
                                                             language, fold):
    flow = _cv_study(tmp_path, synthetic_case_dir, language)
    twin = fk.clone(flow.study, tmp_path / f'twin-{language}')
    plain = _cli(flow.study, 'fit.logistic')
    flagged = _cli(twin, 'fit.logistic', '--progress')
    assert plain.returncode == flagged.returncode == 0, flagged.stderr
    assert plain.stderr == ''

    def comparable(stdout, study):
        payload = json.loads(stdout.replace(json.dumps(str(study))[1:-1], '<study>'))
        payload['result'].pop('exposure_ids')
        return json.dumps(payload, ensure_ascii=False)
    assert comparable(flagged.stdout, twin) == comparable(plain.stdout, flow.study)
    lines = flagged.stderr.splitlines()
    for k in range(1, 6):
        assert any(f' · {fold} {k}/5 · ' in line for line in lines), (k, lines)
    assert not any(line.lstrip().startswith('{') for line in lines)
    # The same values with and without the flag.
    import mlkit.study.read as read
    a = read.open(flow.study).current('fit.logistic')['output']
    b = read.open(twin).current('fit.logistic')['output']
    assert a['sha256'] == b['sha256']


def test_a_tuned_variant_and_the_policy_bootstrap_say_where_they_are(tmp_path,
                                                                    synthetic_case_dir):
    """In process: the inner grid of a tuned variant ("penalty k/5") and the replicates of
    the policy evaluation's bootstrap."""
    flow = _study(tmp_path, synthetic_case_dir)
    flow.model_decisions()
    flow.run('split')
    flow.run('fit.baseline')
    flow.run('fit.logistic')
    flow.variant({'variants': [TUNED]}, run=False)
    stream = io.StringIO()
    out = executions.run(flow.study, 'fit.variant', {}, request_id='v1',
                         expected_revision=flow.rev(), progress=stream)
    assert out.exit_code == 0 and out.payload['status'] == 'promoted'
    lines = stream.getvalue().splitlines()
    assert lines[0] == 'The variant model · started', lines
    assert any(' · penalty 1/5 · ' in line for line in lines), lines
    stream = io.StringIO()
    out = executions.run(flow.study, 'policy.evaluation', {'rules': ['share:0.2']},
                         request_id='p1', expected_revision=flow.rev(), progress=stream)
    assert out.exit_code == 0, out.payload
    assert any(' · bootstrap replicate 1/' in line for line in stream.getvalue().splitlines())
