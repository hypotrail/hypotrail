"""L7 (D15): ``next_action.after_study``, the reasons and the words (unit level).

The whole path (a study followed to ``done``, the plan command run as given, the HGB
refusal) is in ``framework/tests/exporters/azureml/test_after_study.py``. Here the chosen
model is given directly, so every reason is checked in both languages: the export is
offered only when the support matrix holds the model, never without the honest cloud
status, and the junior text carries no command, id or revision.
"""
from __future__ import annotations

import copy
import re

import pytest

from mlkit.study import after_study as aft, state as st

VIEW = {'study': '/tmp/a study', 'revision': 41, 'results': {}}


def _model(task, family, tuned=False):
    return {'task': task, 'family': family,
            'output_kind': aft.OUTPUT_KINDS[task], 'tuned': tuned}


def _build(monkeypatch, model, reason=None, lang='en', results=None):
    monkeypatch.setattr(aft, 'chosen_model', lambda state, case: (model, reason))
    view = dict(VIEW, language=lang, results=results or {})
    return aft.build(view, {}, None)


@pytest.mark.parametrize('lang', ['en', 'fr'])
@pytest.mark.parametrize('model', [_model('binary', 'logistic'),
                                   _model('regression', 'linear')])
def test_a_supported_model_is_offered_the_plan(monkeypatch, model, lang):
    out = _build(monkeypatch, model, lang=lang)
    azure = out['azureml']
    assert azure['supported'] is True and azure['reason_id'] is None
    assert azure['plan_command'] == ("hypotrail export azureml --study '/tmp/a study' "
                                     '--expected-revision 41 --plan')
    assert out['handoff'] == {'command': "hypotrail export handoff --study '/tmp/a study' "
                                         '--expected-revision 41'}
    assert out['cloud_status'] == 'not_qualified'
    _junior_only(out['junior_text'])


@pytest.mark.parametrize('lang', ['en', 'fr'])
@pytest.mark.parametrize('model,reason,expected', [
    (_model('binary', 'hgb'), None, 'family_not_supported'),
    (_model('regression', 'ebm'), None, 'family_not_supported'),
    (_model('regression', 'ridge', tuned=True), None, 'family_not_supported'),
    (_model('binary', 'logistic', tuned=True), None, 'no_recipe'),
    (None, 'baseline_chosen', 'baseline_chosen'),
    (None, 'no_model_chosen', 'no_model_chosen'),
    (None, 'study_before_final_test', 'study_before_final_test'),
    (None, 'sources_changed', 'sources_changed')])
def test_an_unsupported_study_is_told_why_and_offered_no_plan(monkeypatch, model, reason,
                                                              expected, lang):
    out = _build(monkeypatch, model, reason, lang=lang)
    azure = out['azureml']
    assert azure['supported'] is False and azure['plan_command'] is None
    assert azure['reason_id'] == expected and expected in aft.REASON_IDS
    assert azure['reason'] and azure['reason'] in out['junior_text']
    assert out['handoff']['command'] and out['cloud_status'] == 'not_qualified'
    if lang == 'fr':
        assert "L'export Azure ML n'est pas possible pour cette étude" in out['junior_text']
    else:
        assert 'The Azure ML export is not available for this study' in out['junior_text']
    _junior_only(out['junior_text'])


def test_a_tuned_logistic_model_with_a_current_capture_is_supported(monkeypatch):
    out = _build(monkeypatch, _model('binary', 'logistic', tuned=True),
                 results={'predictor.capture': {'current': True}})
    assert out['azureml']['supported'] is True


def test_the_family_words_name_the_model(monkeypatch):
    out = _build(monkeypatch, _model('binary', 'ebm'), lang='fr')
    assert out['azureml']['reason'] == ("ce gabarit Azure ML n'exporte pas encore une "
                                        'Explainable Boosting Machine (EBM)')
    out = _build(monkeypatch, _model('regression', 'ridge', tuned=True))
    assert out['azureml']['reason'] == ('this Azure ML template does not export a penalised '
                                        '(ridge) linear regression yet')


def _junior_only(text):
    """Junior-facing: no command, no revision number, no id; the honest cloud status."""
    assert 'hypotrail' not in text and '--' not in text and not re.search(r'\d', text)
    assert ('No Azure job or endpoint has ever been run' in text
            or "Aucun job ni point de terminaison Azure n'a jamais été lancé" in text)


def test_the_chosen_model_reads_the_family_as_the_recipe_names_it(tmp_path):
    """Without a fit: a study created before WP-B1 has no selected model, a study without
    a confirmed choice has none chosen, and changed sources (no case) are said."""
    from mlkit.study import case as c
    import flowkit as fk
    case = c.load_case(fk.make_case(tmp_path / 'case', n_rows=120)['case'])
    state = st.initial_state(case, created='2026-10-26T00:00:00+00:00')
    assert aft.chosen_model(state, None) == (None, 'sources_changed')
    assert aft.chosen_model(state, case) == (None, 'no_model_chosen')
    legacy = copy.deepcopy(state)
    for d in ('model_variant', 'final_test'):
        legacy['decisions'].pop(d, None)
    assert not st.has_wp_b1_decisions(legacy)
    assert aft.chosen_model(legacy, case) == (None, 'study_before_final_test')
