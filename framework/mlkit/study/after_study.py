"""What comes after the study (L7, owner decision D15): ``next_action.after_study``.

On ``next_action.kind == "done"`` the view adds::

    after_study: {
      handoff: {command},
      azureml: {supported, reason_id, reason, plan_command, model, template},
      cloud_status: "not_qualified",
      junior_text,
    }

``supported`` reads the support matrix of the Azure ML template (``capabilities`` of
``team-azureml-v1``'s ``template.json``) for the chosen model's task, family and output, the
way the exporter matches them (:func:`mlkit.exporters.azureml.snapshot.build`): binary
``logistic`` (every linear binary candidate or variant, tuned or not) and regression
``linear`` (the plain linear regression; a tuned or penalised one is ``ridge``). A study
whose export would be refused for another known reason (created before the final test, no
model chosen, the constant baseline, a tuned model without a current capture, changed
sources) is not ``supported`` either, with ``reason_id`` and a ``reason`` in the study
language. ``plan_command`` (``export azureml --plan``, which writes nothing) is given only
when ``supported``. ``cloud_status`` is always ``not_qualified``: no Azure job or endpoint
has ever been run from this engine's exports (AZUREML-EXPORT-V1 §9).

This module reads state, the case and the template's JSON only; it imports no exporter
module, fits nothing, records nothing, and is not part of any activity fingerprint.
"""
from __future__ import annotations

import json
import shlex
from pathlib import Path
from typing import Mapping

from . import state as st

TEMPLATE_ID = 'team-azureml-v1'
TEMPLATE_FILE = (Path(__file__).resolve().parent.parent / 'exporters' / 'azureml'
                 / 'templates' / TEMPLATE_ID / 'template.json')
CLOUD_STATUS = 'not_qualified'
OUTPUT_KINDS = {st.BINARY: 'binary_score', st.REGRESSION: 'regression_point'}
AFTER_STUDY_KEYS = ('handoff', 'azureml', 'cloud_status', 'junior_text')
AZUREML_KEYS = ('supported', 'reason_id', 'reason', 'plan_command', 'model', 'template')
REASON_IDS = ('study_before_final_test', 'sources_changed', 'no_model_chosen',
              'baseline_chosen', 'family_not_supported', 'no_recipe')

MODEL_WORDS = {
    ('binary', 'logistic'): ('the logistic regression', 'la régression logistique'),
    ('regression', 'linear'): ('the linear regression', 'la régression linéaire'),
    ('regression', 'ridge'): ('a penalised (ridge) linear regression',
                              'une régression linéaire pénalisée (ridge)'),
    ('binary', 'ebm'): ('an Explainable Boosting Machine (EBM)',
                        'une Explainable Boosting Machine (EBM)'),
    ('regression', 'ebm'): ('an Explainable Boosting Machine (EBM)',
                            'une Explainable Boosting Machine (EBM)'),
    ('binary', 'hgb'): ('a histogram gradient boosting model',
                        'un modèle de gradient boosting par histogrammes'),
    ('regression', 'hgb'): ('a histogram gradient boosting model',
                            'un modèle de gradient boosting par histogrammes'),
}

REASONS = {
    'study_before_final_test': (
        'this study was created before the final test and the model capture existed, so it '
        'has no selected model to export',
        "cette étude a été créée avant que le test final et la capture du modèle n'existent : "
        "elle n'a pas de modèle choisi à exporter"),
    'sources_changed': (
        'the case or the data changed since the study started',
        'le cas ou les données ont changé depuis le début de l\'étude'),
    'no_model_chosen': ('no model is chosen', "aucun modèle n'est choisi"),
    'baseline_chosen': (
        'the chosen model is the constant baseline, which has no fitted model to export',
        "le modèle choisi est la référence constante, qui n'a pas de modèle ajusté à exporter"),
    'family_not_supported': (
        'this Azure ML template does not export {model} yet',
        "ce gabarit Azure ML n'exporte pas encore {model}"),
    'no_recipe': (
        "the chosen model's tuned setting exists only in a captured predictor, and none is "
        'current, so the export has no recipe to describe',
        "le réglage du modèle choisi n'existe que dans un prédicteur capturé, et aucun n'est à "
        "jour : l'export n'a pas de recette à décrire"),
}


def capabilities() -> list[dict]:
    """The template's support matrix (``capabilities`` of its ``template.json``)."""
    return list(json.loads(TEMPLATE_FILE.read_text(encoding='utf-8'))['capabilities'])


def chosen_model(state: Mapping, case) -> tuple[dict | None, str | None]:
    """``(model, reason_id)``: the chosen model's ``{task, family, output_kind, tuned}``, or
    None with the reason it cannot be described."""
    if not st.has_wp_b1_decisions(state):
        return None, 'study_before_final_test'
    if case is None:
        return None, 'sources_changed'
    config = st.choice_config(state)
    if config is None:
        return None, 'no_model_chosen'
    from . import activities as act, trials
    model = config['model']
    try:
        if model in act.CANDIDATE_FITS:
            _, params = act.model_plan(state, case, model)
        elif trials.is_variant_slot(model):
            _, params = act.model_plan(state, case, act.VARIANT,
                                       index=trials.variant_index(model))
        else:
            return None, 'baseline_chosen'
    except Exception:                    # noqa: BLE001 - a plan the engine refuses: no model
        return None, 'no_model_chosen'
    task = st.task_of(state)
    family = params.get('family') or 'linear'
    tuned = bool(params.get('tuning'))
    if family == 'linear':
        # As the recipe names it (mlkit.contracts.recipe._family).
        if task == st.BINARY:
            family = 'logistic'
        elif tuned or params.get('alpha') is not None:
            family = 'ridge'
    return {'task': task, 'family': family, 'output_kind': OUTPUT_KINDS.get(task),
            'tuned': tuned}, None


def _words(pair: tuple[str, str], lang: str) -> str:
    return pair[1] if lang == 'fr' else pair[0]


def build(view: Mapping, state: Mapping, case) -> dict:
    """The ``after_study`` block of a ``done`` next action (see the module docstring)."""
    lang = view.get('language') or 'en'
    study = shlex.quote(str(view['study']))
    revision = view['revision']
    handoff = {'command': f'hypotrail export handoff --study {study} '
                          f'--expected-revision {revision}'}
    model, reason_id = chosen_model(state, case)
    supported = False
    if model is not None:
        matrix = capabilities()
        supported = any(c['task'] == model['task'] and c['family'] == model['family']
                        and c['output_kind'] == model['output_kind'] for c in matrix)
        if not supported:
            reason_id = 'family_not_supported'
        elif model['tuned'] and not ((view.get('results') or {}).get('predictor.capture')
                                     or {}).get('current'):
            # A tuned value exists only in a capture (read_export_source): no recipe.
            supported, reason_id = False, 'no_recipe'
    words = (_words(MODEL_WORDS[(model['task'], model['family'])], lang)
             if model is not None and (model['task'], model['family']) in MODEL_WORDS
             else None)
    reason = None
    if reason_id is not None:
        reason = _words(REASONS[reason_id], lang).format(
            model=words or (model or {}).get('family', ''))
    azureml = {'supported': supported, 'reason_id': reason_id, 'reason': reason,
               'plan_command': (f'hypotrail export azureml --study {study} '
                                f'--expected-revision {revision} --plan' if supported else None),
               'model': ({k: model[k] for k in ('task', 'family', 'output_kind')}
                         if model is not None else None),
               'template': TEMPLATE_ID}
    # Third session of 2026-10-26: a model the export supports but that was not captured
    # before the opening is exported as its recipe only; the junior text says so.
    recipe_only = supported and st.final_test_opened(state) and not (
        (view.get('results') or {}).get('predictor.capture') or {}).get('current')
    out = {'handoff': handoff, 'azureml': azureml, 'cloud_status': CLOUD_STATUS,
           'junior_text': junior_text(supported, reason, words, lang, recipe_only)}
    return {k: out[k] for k in AFTER_STUDY_KEYS}


def junior_text(supported: bool, reason: str | None, words: str | None, lang: str,
                recipe_only: bool = False) -> str:
    """What comes next, for the junior, in the study language: no command, id or revision.
    ``recipe_only``: the model was not captured before the final test was opened, so the
    export carries its recipe, not the evaluated model."""
    if lang == 'fr':
        head = ('Et ensuite : le dossier de passation rassemble vos décisions, les résultats '
                'cités et les limites, pour une relecture.')
        if supported:
            mid = (f' Le modèle choisi, {words}, peut aussi être exporté en projet Azure ML : '
                   "le plan d'export liste d'abord les fichiers et n'écrit rien.")
            if recipe_only:
                mid += (" Il n'a pas été capturé avant l'ouverture du test final : l'export "
                        "en emporte la recette, pas le modèle évalué.")
        else:
            mid = f" L'export Azure ML n'est pas possible pour cette étude : {reason}."
        tail = (" Aucun job ni point de terminaison Azure n'a jamais été lancé à partir de ces "
                'exports : ils ne sont vérifiés que sur cet ordinateur.')
        return head + mid + tail
    head = ('What comes next: the handoff pack collects your decisions, the cited results and '
            'the limits for a reviewer.')
    if supported:
        mid = (f' The chosen model, {words}, can also be exported as an Azure ML project: the '
               'export plan lists the files first and writes nothing.')
        if recipe_only:
            mid += (' It was not captured before the final test was opened, so the export '
                    'carries its recipe, not the evaluated model.')
    else:
        mid = f' The Azure ML export is not available for this study: {reason}.'
    tail = (' No Azure job or endpoint has ever been run from these exports: they are checked '
            'on this computer only.')
    return head + mid + tail


__all__ = ['build', 'capabilities', 'chosen_model', 'junior_text', 'TEMPLATE_ID',
           'CLOUD_STATUS', 'REASON_IDS', 'AFTER_STUDY_KEYS', 'AZUREML_KEYS']
