"""The use-case brief that opens step 1 (lot 2026-10-28, owner remark R66; LOT spec §9.2).

An optional file ``use-cases/<id>/case-brief.yaml`` (schema ``hypotrail.case-brief/1``) holds
the product owner's brief of the use case, in English and French: who wrote it and whether
the scenario is fictitious (``source``), the problem, the decision it helps, the objective,
how it runs in production, where the data come from (the real source and the scenario's
framing), the users and the cost of an error, what is out of scope and the risks, and what
the brief changes for the study (``links``). It also gives two business numbers, in the
target's unit and on a named error measure: the error of the current method
(``current_method_error``) and the error the product owner aims at (``target_error``). They
come from the product owner, never from the data: no result reads them.

Two readers use it: the digest (``case_brief`` and ``texts.<lang>.case_brief``, CLI-CONTRACT
§18) and the success criterion's draft, whose optional business bar
(``business_max_error``, R67) defaults to ``current_method_error`` (:func:`business_bar`).
A missing file means no brief; a malformed one too, with a warning on stderr, never a
refusal. The file is not a source of any result and is never part of a dataset digest.

Pure: no pandas, numpy or scikit-learn. Not fingerprinted (not in ``activities.MODULES``).
"""
from __future__ import annotations

import string
import sys
from pathlib import Path
from typing import Any, Mapping

import yaml

SCHEMA = 'hypotrail.case-brief/1'
FILE = 'case-brief.yaml'
LANGS = ('en', 'fr')
# The texts of the brief, in the order the panel and the report show them.
TEXT_KEYS = ('problem', 'decision', 'objective', 'production')
NESTED_KEYS = {'data_provenance': ('real', 'scenario'),
               'users_and_cost_of_error': ('users', 'cost'),
               'out_of_scope_and_risks': ('out_of_scope', 'risks'),
               'links': ('prediction_moment', 'error_measure', 'conclusion')}
SOURCE_KEYS = ('text', 'fictitious')
NUMBER_KEYS = ('current_method_error', 'target_error')
NUMBER_ITEM_KEYS = ('value', 'unit', 'measure')
MEASURES = ('mae', 'rmse')
TOP_KEYS = ('schema', 'source') + TEXT_KEYS + tuple(NESTED_KEYS) + NUMBER_KEYS
# ``case_brief`` of the digest (top level) and ``texts.<lang>.case_brief``.
DIGEST_KEYS = ('fictitious',) + NUMBER_KEYS
TEXTS_KEYS = ('source',) + TEXT_KEYS + tuple(NESTED_KEYS)
# The placeholders a text may hold, filled from the brief's own numbers.
PLACEHOLDERS = NUMBER_KEYS


class BriefError(ValueError):
    pass


def _pair(value, where: str) -> dict:
    if not isinstance(value, Mapping) or set(value) != set(LANGS) \
            or not all(isinstance(value[k], str) and value[k].strip() for k in LANGS):
        raise BriefError(f'{where} is {{en, fr}}, two non-empty texts.')
    for lang in LANGS:
        names = {f for _, f, _, _ in string.Formatter().parse(value[lang]) if f}
        unknown = names - set(PLACEHOLDERS)
        if unknown:
            raise BriefError(f'{where}.{lang} names unknown placeholders: {sorted(unknown)}.')
    return {k: value[k] for k in LANGS}


def _number(value, where: str) -> dict | None:
    if value is None:
        return None
    if not isinstance(value, Mapping) or set(value) != set(NUMBER_ITEM_KEYS):
        raise BriefError(f'{where} is {{value, unit, measure}}.')
    number = value['value']
    if isinstance(number, bool) or not isinstance(number, (int, float)) or not number > 0:
        raise BriefError(f'{where}.value is a positive number.')
    if value['measure'] not in MEASURES:
        raise BriefError(f'{where}.measure is mae or rmse.')
    if not isinstance(value['unit'], str) or not value['unit'].strip():
        raise BriefError(f'{where}.unit is the unit of the target.')
    return {'value': float(number), 'unit': value['unit'], 'measure': value['measure']}


def validate(document: Any, target_unit: str | None = None) -> dict:
    """The brief, validated (``BriefError`` otherwise). Its numbers must be in the unit of the
    case's target when the case declares one."""
    if not isinstance(document, Mapping) or document.get('schema') != SCHEMA:
        raise BriefError(f'A case brief has schema {SCHEMA}.')
    unknown = sorted(set(document) - set(TOP_KEYS))
    if unknown:
        raise BriefError(f'Unknown keys: {unknown}.')
    source = document.get('source')
    if not isinstance(source, Mapping) or set(source) != set(SOURCE_KEYS) \
            or not isinstance(source.get('fictitious'), bool):
        raise BriefError('source is {text: {en, fr}, fictitious: true|false}.')
    out = {'schema': SCHEMA,
           'source': {'text': _pair(source['text'], 'source.text'),
                      'fictitious': source['fictitious']}}
    for key in TEXT_KEYS:
        out[key] = _pair(document.get(key), key)
    for key, parts in NESTED_KEYS.items():
        item = document.get(key)
        if not isinstance(item, Mapping) or set(item) != set(parts):
            raise BriefError(f'{key} is {{{", ".join(parts)}}}.')
        out[key] = {p: _pair(item[p], f'{key}.{p}') for p in parts}
    for key in NUMBER_KEYS:
        out[key] = _number(document.get(key), key)
        if out[key] is not None and target_unit and out[key]['unit'] != target_unit:
            raise BriefError(f'{key}.unit must be the unit of the target ({target_unit}).')
    return out


def load(case_root: Path | str, target_unit: str | None = None) -> dict | None:
    """The validated brief next to a case file, or None (no file, or a malformed one, which
    is reported on stderr and never refused)."""
    path = Path(case_root) / FILE
    if not path.is_file():
        return None
    try:
        return validate(yaml.safe_load(path.read_text(encoding='utf-8')), target_unit)
    except (BriefError, yaml.YAMLError) as exc:
        print(f'hypotrail: ignoring {path}: {exc}', file=sys.stderr)
        return None


def of_state(state: Mapping) -> dict | None:
    """The brief of a study's case (read now, from the case's folder), or None."""
    try:
        from .case import case_of
        case = case_of(state)
    except Exception:                    # noqa: BLE001 - no readable case: no brief
        return None
    unit = case.target_unit if case.task == 'regression' else None
    return load(case.root, unit)


def _number_text(item: Mapping | None, lang: str) -> str:
    from .cite import format_value
    if item is None:
        return ''
    return f'{format_value(item["value"], "f1", lang)} {item["unit"]}'


def _fill(pair: Mapping, brief: Mapping, lang: str) -> str:
    values = {k: _number_text(brief.get(k), lang) for k in PLACEHOLDERS}
    return pair[lang].format(**values)


def digest(brief: Mapping | None) -> dict | None:
    """``case_brief`` of ``status --summary --digest``: null without a brief; else whether
    the scenario is fictitious and the two business numbers (``{value, unit, measure}`` or
    null)."""
    if brief is None:
        return None
    return {'fictitious': brief['source']['fictitious'],
            **{k: (dict(brief[k]) if brief.get(k) else None) for k in NUMBER_KEYS}}


def texts(brief: Mapping | None, lang: str) -> dict | None:
    """``texts.<lang>.case_brief``: every text of the brief in ``lang``, its numbers written
    in, or null without a brief."""
    if brief is None:
        return None
    out = {'source': _fill(brief['source']['text'], brief, lang)}
    for key in TEXT_KEYS:
        out[key] = _fill(brief[key], brief, lang)
    for key, parts in NESTED_KEYS.items():
        out[key] = {p: _fill(brief[key][p], brief, lang) for p in parts}
    return out


def business_bar(brief: Mapping | None, measure: str | None) -> float | None:
    """R67: the default business bar of a regression criterion on ``measure`` (``mae`` or
    ``rmse``): the current method's error when the brief states it on that measure, else
    None."""
    item = (brief or {}).get('current_method_error')
    if not item or (measure is not None and item['measure'] != measure):
        return None
    return item['value']


__all__ = ['SCHEMA', 'FILE', 'load', 'of_state', 'validate', 'digest', 'texts',
           'business_bar', 'BriefError']
