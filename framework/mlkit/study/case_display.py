"""How a case is displayed: short column names and the prediction-moment timeline (lot
2026-10-28, owner remarks R57, R58, R59; LOT spec EN-18 and §8.6).

An optional file ``use-cases/<id>/case-display.yaml`` (schema ``hypotrail.case-display/1``)::

    columns:            # short display names (titles, axes, matrix)
      model_year: {en: model year, fr: année du modèle}
    timeline:
      status: scenario_assumption
      source: Teaching scenario assumption
      milestones:       # in time order
        - {id: design, label: {en: Engine designed, fr: Moteur conçu}}
      proposed_after: body          # the moment sits after this milestone
      known_at: {cylinders: design, weight: body, mpg: measured}

It is validated against the case: every column it names is a case variable; a column whose
availability is ``available_at_prediction`` sits at or before ``proposed_after``; the target
sits after it; a column whose availability is ``unknown`` has no milestone (it is drawn in
the "?" lane, ``known_at: null``). A malformed file gives no display (``None``) with a warning
on stderr, never a refusal. The milestones are a scenario hypothesis and are drawn as such
(``status``). The file is not a source of any result and never part of a dataset digest;
drafts never read it.

:func:`timeline_data` gives the ``chart_data`` of the ``moment_timeline`` and
``variables_board`` charts (CLI-CONTRACT §18): the milestones, the moment, every column with
its group, its milestone, its state (kept, excluded or not a feature) and the reason of an
exclusion, and the lists for every position of the slider (``positions``), computed here so
the panel derives nothing. The slider stops before the target's milestone.

Pure: no pandas, numpy or scikit-learn. Not fingerprinted (not in ``activities.MODULES``).
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Mapping

import yaml

SCHEMA = 'hypotrail.case-display/1'
FILE = 'case-display.yaml'
LANGS = ('en', 'fr')
TOP_KEYS = ('schema', 'columns', 'timeline')
TIMELINE_KEYS = ('status', 'source', 'milestones', 'proposed_after', 'known_at')
CHART_KEYS = ('milestones', 'moment_after', 'slider', 'decided', 'status', 'columns',
              'positions')
COLUMN_KEYS = ('column', 'name', 'group', 'known_at', 'uncertain', 'state', 'reason')
POSITION_KEYS = ('after', 'kept', 'dropped', 'uncertain')
STATES = ('kept', 'excluded', 'not_feature')
KEPT = ('available_at_prediction', 'uncertain_included')
REASONS = {
    'unknown': ('availability at the prediction moment not documented',
                'disponibilité au moment de la prédiction non documentée'),
    'not_available': ('known after the prediction moment',
                      'connue après le moment de la prédiction'),
    'uncertain_excluded': ('availability at the prediction moment uncertain',
                           'disponibilité au moment de la prédiction incertaine'),
    'target': ('the target, measured after the moment', 'la cible, mesurée après le moment'),
    'group_id': ('an identifier: a name does not carry over to another row',
                 "un identifiant : un nom ne se transpose pas à une autre ligne"),
    'time': ('orders the split, not a variable', "ordonne le découpage, pas une variable"),
    'other': ('not a feature of the case', "pas une variable du cas"),
}


class DisplayError(ValueError):
    pass


def _pair(value, where: str) -> dict:
    if not isinstance(value, Mapping) or set(value) != set(LANGS) \
            or not all(isinstance(value[k], str) and value[k].strip() for k in LANGS):
        raise DisplayError(f'{where} is {{en, fr}}, two non-empty texts.')
    return {k: value[k] for k in LANGS}


def validate(document: Any, case_document: Mapping) -> dict:
    """The display file, validated against the case (``DisplayError`` otherwise)."""
    if not isinstance(document, Mapping) or document.get('schema') != SCHEMA:
        raise DisplayError(f'A case display file has schema {SCHEMA}.')
    unknown = sorted(set(document) - set(TOP_KEYS))
    if unknown:
        raise DisplayError(f'Unknown keys: {unknown}.')
    variables = {v['name']: v for v in case_document.get('variables') or []}
    columns = {}
    for name, pair in (document.get('columns') or {}).items():
        if name not in variables:
            raise DisplayError(f'columns.{name} is not a variable of the case.')
        columns[name] = _pair(pair, f'columns.{name}')
    out = {'schema': SCHEMA, 'columns': columns, 'timeline': None}
    timeline = document.get('timeline')
    if timeline is None:
        return out
    if not isinstance(timeline, Mapping) or set(timeline) != set(TIMELINE_KEYS):
        raise DisplayError(f'timeline is {{{", ".join(TIMELINE_KEYS)}}}.')
    milestones = []
    for i, m in enumerate(timeline['milestones'] or []):
        if not isinstance(m, Mapping) or set(m) != {'id', 'label'} or not isinstance(m['id'], str):
            raise DisplayError(f'timeline.milestones[{i}] is {{id, label: {{en, fr}}}}.')
        milestones.append({'id': m['id'], 'label': _pair(m['label'], f'milestones[{i}].label')})
    ids = [m['id'] for m in milestones]
    if len(ids) < 2 or len(set(ids)) != len(ids):
        raise DisplayError('timeline.milestones are at least two, with distinct ids.')
    after = timeline['proposed_after']
    if after not in ids:
        raise DisplayError('timeline.proposed_after names a milestone.')
    known = {}
    for name, milestone in (timeline['known_at'] or {}).items():
        if name not in variables:
            raise DisplayError(f'timeline.known_at.{name} is not a variable of the case.')
        if milestone not in ids:
            raise DisplayError(f'timeline.known_at.{name} names no milestone.')
        availability = ((variables[name].get('availability') or {}).get('value'))
        if availability == 'unknown':
            raise DisplayError(f'timeline.known_at.{name}: its availability is unknown, so it '
                               'has no milestone (the "?" lane).')
        if availability == 'available_at_prediction' and ids.index(milestone) > ids.index(after):
            raise DisplayError(f'timeline.known_at.{name}: an available column sits at or '
                               'before the proposed moment.')
        known[name] = milestone
    target = (case_document.get('target') or {}).get('column')
    if target in known and ids.index(known[target]) <= ids.index(after):
        raise DisplayError('timeline.known_at: the target is known after the proposed moment.')
    out['timeline'] = {'status': str(timeline['status']), 'source': str(timeline['source']),
                       'milestones': milestones, 'proposed_after': after, 'known_at': known}
    return out


def load(case) -> dict | None:
    """The validated display of a case (a :class:`mlkit.study.case.Case`), or None (no file,
    or a malformed one, reported on stderr and never refused)."""
    path = Path(case.root) / FILE
    if not path.is_file():
        return None
    try:
        return validate(yaml.safe_load(path.read_text(encoding='utf-8')), case.document)
    except (DisplayError, yaml.YAMLError) as exc:
        print(f'hypotrail: ignoring {path}: {exc}', file=sys.stderr)
        return None


def of_state(state: Mapping) -> tuple[Any, dict | None]:
    """``(case, display)`` of a study, ``(None, None)`` without a readable case."""
    try:
        from .case import case_of
        case = case_of(state)
    except Exception:                    # noqa: BLE001 - no readable case: no display
        return None, None
    return case, load(case)


def digest(display: Mapping | None) -> dict | None:
    """``case_display`` of the digest: ``{"columns": {name: {en, fr}}}`` or null."""
    if display is None:
        return None
    return {'columns': {k: dict(v) for k, v in display['columns'].items()}}


def column_name(display: Mapping | None, column: str, lang: str) -> str:
    """A column's short display name: the file's, else the column name with ``_`` as spaces
    (never code styling)."""
    pair = ((display or {}).get('columns') or {}).get(column)
    return pair[lang] if pair else column.replace('_', ' ')


def _availability_value(state: Mapping, case) -> tuple[dict, bool]:
    """``({column: status}, decided)``: the confirmed availability decision, else its open
    proposal, else the case's own availability."""
    decision = (state.get('decisions') or {}).get('feature_availability') or {}
    value = decision.get('value')
    if decision.get('status') in ('confirmed', 'reconfirm_required') and isinstance(value, Mapping):
        return dict(value), decision.get('status') == 'confirmed'
    for proposal in (state.get('proposals') or {}).values():
        if proposal.get('decision_id') == 'feature_availability' \
                and proposal.get('status') == 'open' and isinstance(proposal.get('value'), Mapping):
            return dict(proposal['value']), False
    out = {}
    for v in case.document.get('variables') or []:
        if v.get('role') == 'feature':
            availability = (v.get('availability') or {}).get('value')
            out[v['name']] = availability if availability in KEPT + ('not_available',) \
                else 'uncertain_excluded'
    return out, False


def timeline_data(state: Mapping, case, display: Mapping | None, lang: str,
                  decision: str = 'prediction_time') -> dict:
    """The ``chart_data`` of ``moment_timeline`` (``decision`` ``prediction_time``) and
    ``variables_board`` (``feature_availability``): see the module docstring."""
    from . import l10n
    fr = lang == 'fr'
    tr = l10n.translations(state, case.document)
    availability, availability_decided = _availability_value(state, case)
    timeline = (display or {}).get('timeline')
    milestones = ([{'id': m['id'], 'label': m['label'][lang]} for m in timeline['milestones']]
                  if timeline else [])
    ids = [m['id'] for m in milestones]
    known = (timeline or {}).get('known_at') or {}
    target = case.target_column
    columns = []
    for v in case.document.get('variables') or []:
        name = v['name']
        case_availability = (v.get('availability') or {}).get('value')
        role = v.get('role')
        if role == 'feature':
            status = availability.get(name)
            state_ = 'kept' if status in KEPT else 'excluded'
            reason_key = None if state_ == 'kept' else (
                'unknown' if case_availability == 'unknown' else (status or 'unknown'))
        else:
            state_ = 'not_feature'
            reason_key = role if role in ('target', 'group_id', 'time') else 'other'
        uncertain = case_availability == 'unknown' or (role == 'feature' and str(
            availability.get(name, '')).startswith('uncertain'))
        group = v.get('group')
        columns.append({'column': name, 'name': column_name(display, name, lang),
                        'group': (tr.group(group, lang) or group) if fr else group,
                        'known_at': None if case_availability == 'unknown' else known.get(name),
                        'uncertain': bool(uncertain), 'state': state_,
                        'reason': REASONS[reason_key][fr] if reason_key else None})
    positions = []
    stop = ids.index(known[target]) if target in known else len(ids)
    for i, mid in enumerate(ids[:stop]):
        kept, dropped, unsure = [], [], []
        for col in columns:
            if col['state'] == 'not_feature':
                continue
            if col['known_at'] is None:
                unsure.append(col['column'])
            elif ids.index(col['known_at']) <= i:
                kept.append(col['column'])
            else:
                dropped.append(col['column'])
        positions.append({'after': mid, 'kept': kept, 'dropped': dropped, 'uncertain': unsure})
    decided_moment = ((state.get('decisions') or {}).get('prediction_time') or {}).get(
        'status') == 'confirmed'
    return {'milestones': milestones,
            'moment_after': (timeline or {}).get('proposed_after'),
            'slider': bool(timeline) and decision == 'prediction_time' and len(positions) > 1,
            'decided': decided_moment if decision == 'prediction_time' else availability_decided,
            'status': (timeline or {}).get('status') or 'scenario_assumption',
            'columns': columns, 'positions': positions}


__all__ = ['SCHEMA', 'FILE', 'load', 'of_state', 'validate', 'digest', 'column_name',
           'timeline_data', 'DisplayError']
