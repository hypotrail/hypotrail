"""L7 (D15): what comes after the study, and the export it offers.

At ``done``, ``next_action.after_study`` names the handoff pack, offers the Azure ML export
plan only when the chosen model is in the template support matrix, and says that no Azure
job or endpoint has ever been run (``cloud_status: not_qualified``). Each study here is a
temporary synthetic study taken to ``done`` by following ``next_action`` as the engine
gives it (the walker of ``test_review_round5_engine``); the plan command it offers is run
as given and must succeed; a study whose chosen model is outside the matrix (histogram
boosting) is offered no plan, with the reason, and the export refuses it the same way.
"""
from __future__ import annotations

import json
import os
import shlex
import sys
from pathlib import Path

import pytest

from export_env import needs_hydra, needs_mlflow

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'study'))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'study' / 'libraries'))

pytestmark = [needs_mlflow, needs_hydra]

AFTER_KEYS = ('handoff', 'azureml', 'cloud_status', 'junior_text')
AZUREML_KEYS = ('supported', 'reason_id', 'reason', 'plan_command', 'model', 'template')


def _done(flow, task):
    from test_review_round5_engine import _follow
    log, last = _follow(flow, task, False)
    assert last['kind'] == 'done', log[-5:]
    return last


def _run_command(command: str, expect=0) -> dict:
    from mlkit.study import cli
    args = shlex.split(command)
    assert args[0] == 'hypotrail'
    outcome = cli.run(args[1:])
    if expect is not None:
        assert outcome.exit_code == expect, outcome.payload
    return outcome.payload


@pytest.mark.parametrize('task,language,family,output', [
    ('binary', 'en', 'logistic', 'binary_score'),
    ('regression', 'fr', 'linear', 'regression_point')])
def test_done_offers_the_export_plan_of_a_supported_model(tmp_path, task, language, family,
                                                          output):
    import flowkit as fk
    from test_review_round5_engine import _legacy_flow
    flow = _legacy_flow(tmp_path, task, language)
    last = _done(flow, task)
    after = last['after_study']
    assert tuple(after) == AFTER_KEYS and tuple(after['azureml']) == AZUREML_KEYS
    assert after['cloud_status'] == 'not_qualified'
    azure = after['azureml']
    assert azure['model'] == {'task': task, 'family': family, 'output_kind': output}
    assert azure['supported'] is True and azure['reason_id'] is None and azure['reason'] is None
    assert azure['template'] == 'team-azureml-v1'
    revision = flow.rev()
    assert azure['plan_command'].endswith(f'--expected-revision {revision} --plan')
    assert after['handoff']['command'].startswith('hypotrail export handoff --study ')
    text = after['junior_text']
    if language == 'fr':
        assert text.startswith('Et ensuite : le dossier de passation')
        assert 'la régression linéaire' in text and "plan d'export" in text
        assert "Aucun job ni point de terminaison Azure n'a jamais été lancé" in text
    else:
        assert text.startswith('What comes next: the handoff pack')
        assert 'the logistic regression' in text and 'export plan' in text
        assert 'No Azure job or endpoint has ever been run' in text
    # Junior-facing: no command, no revision number, no id.
    assert 'hypotrail' not in text and '--' not in text and str(revision) not in text
    # The commands run as given: the plan writes nothing and changes nothing.
    before = fk.tree_digest(flow.study)
    plan = _run_command(azure['plan_command'])
    assert plan['ok'] and plan['plan'] is True and plan['out'] is None
    assert plan['study_revision'] == revision
    assert fk.tree_digest(flow.study) == before
    summary = flow.call('status', '--summary', '--study', flow.study)
    assert summary['next_action']['after_study'] == after


FAMILY_WORDS = {'hgb': 'a histogram gradient boosting model',
                'ebm': 'an Explainable Boosting Machine (EBM)'}


@pytest.mark.parametrize('family', ['hgb', 'ebm'])
def test_done_says_why_a_boosting_model_is_not_exported(tmp_path, family):
    """NR-19 item 4: the HGB or EBM variant chosen: no plan is offered, the reason names the
    family, and the export itself refuses on the family (``capability_not_supported``,
    ``family_not_supported``), never substituting the logistic model, and names the study
    and its revision (R18)."""
    import libkit
    from mlkit.study import state as st
    from test_binary_logistic import VARIANT_WORDS, _adopt_policy
    flow = libkit.study_at_fits(tmp_path, task='binary', n_rows=300)
    flow.run('fit.baseline')
    flow.run('fit.logistic')
    flow.run('diag.binary')
    flow.decide('model_variant', {'variants': [{'kind': 'family', 'family': family,
                                                'question': 'Does boosting rank better?'}]})
    flow.run('fit.variant')
    flow.run('policy.evaluate', '--rule', 'capacity:30')
    if st.has_explicit_binary_model_choice(flow.state()):
        flow.decide('model_choice', 'fit.variant', words=VARIANT_WORDS)
    _adopt_policy(flow, 'capacity:30@fit.variant')
    last = _done(flow, 'binary')
    azure = last['after_study']['azureml']
    assert azure['supported'] is False and azure['plan_command'] is None
    assert azure['reason_id'] == 'family_not_supported'
    assert azure['model'] == {'task': 'binary', 'family': family,
                              'output_kind': 'binary_score'}
    reason = f'this Azure ML template does not export {FAMILY_WORDS[family]} yet'
    assert azure['reason'] == reason
    assert (f'The Azure ML export is not available for this study: {reason}.'
            in last['after_study']['junior_text'])
    assert last['after_study']['handoff']['command']
    refused = flow.call('export', 'azureml', '--plan', '--expected-revision', flow.rev(),
                        '--study', flow.study, expect=2)['error']
    assert refused['code'] == 'capability_not_supported'
    assert refused['details']['reason'] == 'family_not_supported'
    assert refused['details']['family'] == family
    assert refused['details']['path'] == 'model_recipe.family'
    assert 'captur' not in refused['details']['remediation'].lower()
    assert refused['details']['study'] == os.path.abspath(flow.study)
    assert refused['details']['study_revision'] == flow.rev()
    assert f'revision {flow.rev()}' in refused['message'] and str(flow.study) in \
        refused['message']
    out = tmp_path / 'export'
    again = flow.call('export', 'azureml', '--out', out, '--expected-revision', flow.rev(),
                      '--study', flow.study, expect=2)['error']
    assert again['code'] == 'capability_not_supported' and not out.exists()


def test_the_matrix_read_at_done_is_the_exporter_s():
    from mlkit.exporters.azureml import layout
    from mlkit.study import after_study
    template = layout.load(after_study.TEMPLATE_ID)
    assert after_study.capabilities() == template.document['capabilities']
    assert {(c['task'], c['family'], c['output_kind']) for c in after_study.capabilities()} \
        == {('regression', 'linear', 'regression_point'),
            ('binary', 'logistic', 'binary_score')}
    assert json.loads(after_study.TEMPLATE_FILE.read_text())['id'] == after_study.TEMPLATE_ID


def test_the_journey_captures_the_chosen_model_so_the_export_carries_it(tmp_path):
    """Third session of 2026-10-26 (the owner's French binary study did not export): a study
    walked to ``done`` along ``next_action`` opened its final test without a capture, so the
    export at ``done`` was the recipe only (``artifact_status: missing``), and a capture is
    possible only before the opening. The journey now captures the chosen model (the
    workshop profile, MLflow package) right before the opening is proposed; the export plan
    and the export run as given carry the evaluated, packaged model, and the final test is
    still opened once."""
    import flowkit as fk
    from mlkit.study import state as st
    from test_review_round5_engine import _follow, _legacy_flow
    flow = _legacy_flow(tmp_path, 'binary', 'fr')
    log, last = _follow(flow, 'binary', False)
    assert last['kind'] == 'done', log[-5:]
    steps = [what for _, what in log]
    assert steps.index('predictor.capture') < steps.index('final_test'), log
    assert steps.count('predictor.capture') == 1 and steps.count('final_test') == 1
    state = flow.state()
    assert st.final_test_opened(state) and state['current'].get('predictor.capture')
    opened = [r for r in fk.exposure_records(flow.study) if r.get('partition') == 'final_test'
              and r.get('purpose') == 'final_evaluation']
    assert len(opened) == 1, opened
    after = last['after_study']
    assert after['azureml']['supported'] is True
    assert "Il n'a pas été capturé" not in after['junior_text']
    plan = _run_command(after['azureml']['plan_command'])
    assert plan['ok'] and plan['artifact_status'] == 'packaged', plan['checks']
    out = tmp_path / 'export'
    written = flow.call('export', 'azureml', '--out', out, '--expected-revision', flow.rev(),
                        '--study', flow.study)
    assert written['ok'] and written['artifact_status'] == 'packaged' and out.is_dir()


def test_a_model_opened_without_a_capture_is_said_to_export_as_its_recipe(tmp_path):
    """A study opened before the journey captured (the owner's existing study): the export is
    still offered, and the junior text says it carries the recipe, not the evaluated
    model."""
    from mlkit.study import after_study, read, view
    from test_review_round5_engine import _chosen, _open
    flow = _chosen(tmp_path, 'binary', 'fr')
    _open(flow)
    study = read.open(flow.study)
    built = view.build(study)
    out = after_study.build(built, study.state, view._case_or_none(study.state))
    assert out['azureml']['supported'] is True
    assert ("Il n'a pas été capturé avant l'ouverture du test final : l'export en emporte la "
            'recette, pas le modèle évalué.') in out['junior_text']
    plan = _run_command(out['azureml']['plan_command'])
    assert plan['ok'] and plan['artifact_status'] == 'missing'
