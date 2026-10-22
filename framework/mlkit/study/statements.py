"""Whitelisted, deterministic evidence statements for sensitive conclusions (J5)."""
from __future__ import annotations

from typing import Mapping

from . import cite, evidence_ref
from .errors import StudyError

KINDS = ('metric_observed', 'comparison_observed', 'criterion_assessment',
         'calibration_description', 'limitation', 'next_action')
CAUSAL_PHRASES = ('prevents', 'causes', 'avoids cancellations', 'empêche', 'cause',
                  'évite les annulations')


def causal_warning(text: str) -> dict | None:
    """A disclosed lexical aid, not an unrestricted semantic verifier."""
    lower = text.casefold()
    if any(phrase in lower for phrase in CAUSAL_PHRASES) \
            and not any(mark in lower for mark in ('does not ', "doesn't ", 'ne ', 'n’', 'n\'')):
        return {'code': 'unsupported_causal_language',
                'message': 'Causal wording detected by the implemented lexical checks; '
                           'coverage is incomplete.'}
    return None


def render(study, statement: Mapping, language: str = 'en', *, historical: bool = False) -> dict:
    """Validate references and render one small typed statement in EN or FR."""
    kind = statement.get('kind') if isinstance(statement, Mapping) else None
    if kind not in KINDS:
        raise StudyError('invalid_arguments',
                         f'Statement kind must be one of {", ".join(KINDS)}.')
    refs = list(statement.get('refs') or [])
    values = [evidence_ref.resolve(study, ref, historical=historical) for ref in refs]
    if kind in ('metric_observed', 'comparison_observed', 'criterion_assessment',
                'calibration_description') and not refs:
        raise StudyError('invalid_arguments', f'{kind} needs checked evidence references.')
    metric = statement.get('metric') or (refs[0].get('metric') if refs else None)
    fmt = statement.get('format', 'fraction' if metric in evidence_ref.FRACTION_METRICS else 'auto')
    shown = cite.format_value(values[0], fmt, language) if values else None
    if kind == 'metric_observed':
        text = (f'{metric} observée sur {statement.get("population", "la population indiquée")} : {shown}.'
                if language == 'fr' else
                f'Observed {metric} on {statement.get("population", "the stated population")}: {shown}.')
    elif kind == 'comparison_observed':
        text = (f'Écart apparié observé par rapport à {statement.get("reference_model")} : {shown}.'
                if language == 'fr' else
                f'Observed paired difference from {statement.get("reference_model")}: {shown}.')
    elif kind == 'criterion_assessment':
        status = statement.get('status', 'undetermined')
        text = (f'Évaluation du critère : {status} ({shown}).' if language == 'fr'
                else f'Criterion assessment: {status} ({shown}).')
    elif kind == 'calibration_description':
        text = (f'Calibration observée sur la population indiquée : {shown} ; '
                'ceci ne garantit pas la calibration future.' if language == 'fr' else
                f'Calibration observed on the stated population: {shown}; this is not a '
                'guarantee of future calibration.')
    elif kind == 'limitation':
        text = str(statement.get('text') or statement.get('code') or '')
    else:
        text = str(statement.get('text') or statement.get('reason') or '')
    warning = causal_warning(text)
    if warning and kind != 'limitation':
        raise StudyError('causal_or_forecast_wording', warning['message'], details=warning)
    return {'kind': kind, 'language': language, 'text': text, 'refs': refs}
