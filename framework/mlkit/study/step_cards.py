"""One structure for every step: the step cards (lot 2026-10-28, owner remarks R54 to R67;
LOT spec §2 to §4 and §7.2, EN-1 to EN-8, EN-10, EN-17 to EN-20; CLI-CONTRACT §18).

:func:`build` gives ``texts.<lang>.step_cards`` of ``status --summary --digest``: for every
step of the plan, in plan order, the step in one picture, what it must establish (two or
three engine-owned questions), "to answer, look" (one chart per question, with a three-part
reading bound to registered values) and the limit and what comes next. The same function
feeds the report (RE-1).

Every question is in :data:`QUESTIONS` (the registry, EN-1): its step, its source, its main
chart, its frame and its filler. A filler reads the view, the registered results, the digest
keys computed from them, the partition record, the case and its display file, and returns the
reading's variant and the values of its placeholders, each one cited
(``{name, result_id, path, value, text}``; ``result_id`` null and ``path``
``engine:<CONSTANT>``, ``case:<…>``, ``partition:<…>`` or ``digest:<…>`` for a value that is
not a result's). The texts are in ``content/step_cards.yaml`` (EN-2), which holds no digit.

Step cards exist for a regression study holding the decision set of this lot
(``state.has_error_metric``); for any other study :func:`build` returns None and the panel
keeps its Now as before (PA-2 fallback; binary step cards are cut, LOT spec §8).

Pure apart from reading the study through :class:`mlkit.study.read.Study`; it imports
neither pandas nor scikit-learn. Not fingerprinted (not in ``activities.MODULES``).
"""
from __future__ import annotations

import math
import os
import re
import string
import sys
from typing import Any, Callable, Mapping

from . import audience, cite, state as st

SCHEMA = 'hypotrail.step_cards/1'
CARDS_KEYS = ('schema', 'current', 'total', 'steps')
STEP_KEYS = ('step', 'n', 'name', 'short', 'moment', 'state', 'picture', 'prepares',
             'questions', 'no_chart', 'limit', 'next', 'decision')
PICTURE_KEYS = ('kind', 'caption', 'more', 'illustrative', 'data')
QUESTION_KEYS = ('id', 'n', 'text', 'source', 'chart', 'chart_data', 'other_charts', 'frame',
                 'status', 'result_id', 'result_revision', 'reading', 'cites', 'verdict',
                 'folds')
SOURCE_KEYS = ('kind', 'slot', 'key')
OTHER_CHART_KEYS = ('slot', 'chart', 'result_id', 'result_revision', 'status')
FRAME_KEYS = ('evidence', 'rows')
READING_KEYS = ('see', 'conclude', 'cannot')
CITE_KEYS = ('name', 'result_id', 'path', 'value', 'text')
VERDICT_KEYS = ('label', 'met', 'value', 'bound', 'result_id', 'path')
DECISION_KEYS = ('decision_id', 'words', 'basis', 'who')
FOLDS_KEYS = ('how', 'trap')
STATES = ('upcoming', 'current', 'done')
STATUSES = ('answered', 'stale', 'pending', 'no_chart', 'integrity_failed')
EVIDENCE = ('none', 'structure', 'development', 'final', 'illustration')
WHO = ('you', 'automatic', 'delegated')
SOURCE_KINDS = ('result', 'digest', 'case', 'illustration', 'decision')
PICTURE_KINDS = ('row_card', 'moment_timeline', 'variables_board', 'partition_strip',
                 'error_gap', 'criterion_bar', 'quality_checks', 'log_before_after',
                 'trend_reading', 'mean_vs_line', 'line_misses_curve', 'one_se_rule',
                 'sealed_once', 'dev_vs_final')
CHART_KINDS = ('sample_table', 'structure_bars', 'moment_timeline', 'variables_board',
               'partition_strata', 'folds', 'metric_bars', 'bars', 'verdicts_table',
               'distribution_before_after', 'histogram', 'trend_by_bins', 'correlation',
               'model_dots', 'observed_predicted', 'residual_by_feature', 'bias_by_period',
               'per_fold_dots', 'paired_intervals', 'one_se_rule', 'nested_cv', 'dev_vs_final',
               'criterion_gauge', 'rate_bar',
               # R67 (owner validation of 2026-10-28, CLI-CONTRACT §18): the made-up four
               # bars of the criterion step (reference, minimum, current method, PO target).
               'criterion_example')

# Engine constants of the illustrations (EN-10, R67), cited as ``engine:<NAME>``.
METRIC_EXAMPLE_ERRORS = (1, 1, 1, 1, 6)
UNIT_NOTE_MPG = 25
MPG_TO_L100 = 235.215
CRITERION_EXAMPLE_REFERENCE = 7.0
DEFAULT_MIN_SHARE = 0.1
# The bounds of the readings' rules, in the unit of the target (named, cited, LOT §8.7).
RESIDUAL_SHAPE_MIN = 1.0
DRIFT_BOUND = 1.0
# EN-8: the length caps of the engine texts, in words (enforced in tests).
CAPTION_MAX_WORDS = 30
PREPARES_MAX_WORDS = 60
READING_MAX_WORDS = 90
LIMIT_MAX_WORDS = 30
STRICT_ENV = 'HYPOTRAIL_STRICT_TEXTS'

EN, FR = 'en', 'fr'
_CONTENT: dict | None = None


def content() -> dict:
    global _CONTENT
    if _CONTENT is None:
        from . import texts
        _CONTENT = texts.load('step_cards')
    return _CONTENT


def placeholders(text: str) -> set[str]:
    return {f for _, f, _, _ in string.Formatter().parse(text) if f}


# --- the context of one build -----------------------------------------------------------------

class Ctx:
    """What the fillers read, computed once per build."""

    def __init__(self, study, built: Mapping, lang: str, records: list | None = None):
        from . import case_brief, case_display, panel_digest
        self.study, self.built, self.lang = study, built, lang
        self.fr = lang == FR
        self.state = study.state
        self.case, self.display = case_display.of_state(self.state)
        self.brief = case_brief.of_state(self.state)
        self.unit = (self.case.target_unit if self.case is not None else None) or ''
        self.target = self.case.target_column if self.case is not None else 'target'
        final = built.get('final_test') or {}
        self.sealed = final.get('rows')
        self.dev = final.get('development_rows')
        self.results = built.get('results') or {}
        records = records if records is not None else study.revisions(0)
        self.revisions = {}
        for r in records:
            if r.get('action') == 'run.promote':
                rid = (r.get('result') or {}).get('result_id')
                if rid:
                    self.revisions[rid] = r.get('revision')
        try:
            entries = study.exposure_records()
            self.looks = (panel_digest.ledger(built, entries).get('target_looks') or {}).get(
                'total')
        except Exception:                # noqa: BLE001 - the frame then omits the count
            self.looks = None
        self._values: dict[str, Any] = {}
        self._verdicts = None
        self._structure = None

    def item(self, slot: str) -> Mapping | None:
        return self.results.get(slot)

    def values(self, slot: str) -> Mapping | None:
        item = self.item(slot)
        if not item or not item.get('result_id'):
            return None
        rid = item['result_id']
        if rid not in self._values:
            vals = item.get('values')
            if not isinstance(vals, Mapping):
                try:
                    vals = self.study.result(rid)['output']['values']
                except Exception:        # noqa: BLE001 - an unreadable result: not cited
                    vals = None
            self._values[rid] = vals
        return self._values[rid]

    def status(self, slot: str) -> str:
        item = self.item(slot)
        if not item or not item.get('result_id'):
            return 'pending'
        if item.get('integrity') not in (None, 'ok'):
            return 'integrity_failed'
        return 'answered' if item.get('current') else 'stale'

    def quality_verdicts(self) -> Mapping | None:
        if self._verdicts is None:
            from . import drafts
            try:
                self._verdicts = drafts.quality_verdicts(self.study, self.state, self.lang) or {}
            except Exception:            # noqa: BLE001
                self._verdicts = {}
        return self._verdicts or None

    def structure(self) -> Mapping | None:
        if self._structure is None:
            from . import cmd_data
            try:
                self._structure = cmd_data.structure_of(self.study) or {}
            except Exception:            # noqa: BLE001
                self._structure = {}
        return self._structure or None

    def col(self, column: str) -> str:
        from . import case_display
        return case_display.column_name(self.display, column, self.lang)

    def model(self, slot: str, capital: bool = False) -> str:
        if capital:
            from . import junior
            return junior._model_label(slot, self.state, self.lang)
        return audience.model_words(slot, self.lang)


def C(value, kind: str, result_id: str | None, path: str) -> dict:
    """A cited value."""
    return {'value': value, 'kind': kind, 'result_id': result_id, 'path': path}


def _path(*segments) -> str:
    return cite.format_path([str(s) for s in segments])


class Fill(dict):
    """A filler's answer: ``status``, ``slot``, ``variant``, ``values`` (cited), ``words``
    (names, no digit), and optionally ``chart_data``, ``verdict``, ``other_charts``."""


def _fill(status='answered', slot=None, variant='default', values=None, words=None, **extra):
    out = Fill(status=status, slot=slot, variant=variant, values=values or {},
               words=words or {})
    out.update(extra)
    return out


def _pending(slot=None, **extra) -> Fill:
    return _fill(status='pending', slot=slot, variant=None, **extra)


# --- the fillers ------------------------------------------------------------------------------

def f_data_row(x: Ctx) -> Fill:
    from . import panel_digest
    try:
        sample = panel_digest.sample(x.study, x.state, x.study.exposure_records())
    except Exception:                    # noqa: BLE001 - no sample: nothing to read yet
        sample = None
    n_columns = len(x.case.column_names) if x.case is not None else None
    if n_columns is None or not sample:
        return _pending()
    n_sample = len(sample['row_keys'])
    return _fill(values={'n_columns': C(n_columns, 'int', None, 'case:variables'),
                         'n_sample': C(n_sample, 'int', None, 'digest:sample.row_keys')})


def f_data_structure(x: Ctx) -> Fill:
    s = x.structure()
    if not s:
        return _pending()
    dup = s.get('duplicates') or {}
    groups = s.get('groups') or []
    values = {'duplicates': C(dup.get('rows', 0), 'int', None, 'digest:data_structure.duplicates.rows'),
              'identical': C(dup.get('identical_feature_rows', 0), 'int', None,
                             'digest:data_structure.duplicates.identical_feature_rows')}
    if groups:
        g = groups[0]
        values.update(n_groups=C(g.get('groups'), 'int', None, 'digest:data_structure.groups.0.groups'),
                      repeated=C(g.get('rows_in_repeated_groups'), 'int', None,
                                 'digest:data_structure.groups.0.rows_in_repeated_groups'))
        return _fill(variant='groups', values=values, words={'group_column': x.col(g['column'])})
    return _fill(variant='no_groups', values=values)


def _timeline(x: Ctx, decision: str) -> dict | None:
    from . import case_display
    if x.case is None:
        return None
    return case_display.timeline_data(x.state, x.case, x.display, x.lang, decision)


def f_moment(x: Ctx) -> Fill:
    data = _timeline(x, 'prediction_time')
    if data is None:
        return _pending()
    positions = data['positions']
    at = next((p for p in positions if p['after'] == data['moment_after']), None)
    if at is not None:
        values = {'n_kept': C(len(at['kept']), 'int', None, 'case:display.positions.kept'),
                  'n_uncertain': C(len(at['uncertain']), 'int', None,
                                   'case:display.positions.uncertain')}
        return _fill(variant='timeline', values=values, chart_data=data)
    cols = [c for c in data['columns'] if c['state'] != 'not_feature']
    values = {'n_kept': C(sum(c['known_at'] is not None or not c['uncertain'] for c in cols),
                          'int', None, 'case:availability'),
              'n_uncertain': C(sum(c['uncertain'] for c in cols), 'int', None, 'case:availability')}
    return _fill(variant='no_timeline', values=values, chart_data=data)


def f_variables(x: Ctx) -> Fill:
    data = _timeline(x, 'feature_availability')
    if data is None:
        return _pending()
    count = {s: sum(c['state'] == s for c in data['columns']) for s in
             ('kept', 'excluded', 'not_feature')}
    values = {'n_kept': C(count['kept'], 'int', None, 'decision:feature_availability'),
              'n_excluded': C(count['excluded'], 'int', None, 'decision:feature_availability'),
              'n_not_feature': C(count['not_feature'], 'int', None, 'case:variables')}
    return _fill(values=values, chart_data=data)


def _strata_data(x: Ctx) -> dict:
    part = x.state.get('partition') or {}
    strata = part.get('strata_counts')
    return {'total': part.get('n_rows'), 'development': x.dev, 'sealed': x.sealed,
            'method': part.get('method'), 'bins': part.get('bins'),
            'strata': [dict(s) for s in strata] if strata else None,
            'opened': part.get('status') == 'opened'}


def f_split_sealed(x: Ctx) -> Fill:
    data = _strata_data(x)
    values = {'sealed': C(x.sealed, 'int', None, 'partition:final_test.n_rows'),
              'development': C(x.dev, 'int', None, 'partition:development.n_rows')}
    if data['strata']:
        values['bins'] = C(len(data['strata']), 'int', None, 'partition:strata_counts')
        return _fill(variant='strata', values=values, chart_data=data)
    return _fill(variant='recorded', values=values, chart_data=data)


def _split_value(x: Ctx) -> Mapping | None:
    decision = (x.state.get('decisions') or {}).get('split') or {}
    if isinstance(decision.get('value'), Mapping):
        return decision['value']
    for p in (x.state.get('proposals') or {}).values():
        if p.get('decision_id') == 'split' and p.get('status') == 'open' \
                and isinstance(p.get('value'), Mapping):
            return p['value']
    return st.b1_default_value(x.state, 'split')


def f_split_folds(x: Ctx) -> Fill:
    order_col = x.case.time_column if x.case is not None else None
    order = x.col(order_col) if order_col else None
    vals = x.values('split')
    base = {'dev': C(x.dev, 'int', None, 'partition:development.n_rows'),
            'sealed': C(x.sealed, 'int', None, 'partition:final_test.n_rows')}
    if vals is None or x.status('split') == 'pending':
        value = _split_value(x) or {}
        k = value.get('folds') or st.DEFAULT_FOLDS
        data = {'illustrative': True, 'k': k, 'n_rows': x.dev, 'order_column': order,
                'sealed': x.sealed, 'blocks': None}
        values = dict(base, k=C(k, 'int', None, 'decision:split.folds'))
        return _fill(variant='illustrative', values=values,
                     words={'order': order or audience.decision_words('split', x.lang)},
                     chart_data=data, slot=None)
    rid = x.item('split')['result_id']
    rows = vals.get('fold_rows') or []
    ranges = {r['fold']: r for r in vals.get('fold_ranges') or []}
    blocks = [{'fold': r['fold'], 'n_rows': r['n_rows'],
               'min': (ranges.get(r['fold']) or {}).get('min'),
               'max': (ranges.get(r['fold']) or {}).get('max')} for r in rows]
    k = vals.get('folds') or len(rows)
    sizes = [r['n_rows'] for r in rows]
    i_min, i_max = sizes.index(min(sizes)), sizes.index(max(sizes))
    values = dict(base, k=C(k, 'int', rid, 'folds'),
                  min_rows=C(min(sizes), 'int', rid, _path('fold_rows', i_min, 'n_rows')),
                  max_rows=C(max(sizes), 'int', rid, _path('fold_rows', i_max, 'n_rows')))
    ordered = bool(vals.get('order_column'))
    data = {'illustrative': False, 'k': k, 'n_rows': vals.get('n_rows'),
            'order_column': x.col(vals['order_column']) if ordered else None,
            'sealed': x.sealed, 'blocks': blocks}
    return _fill(status=x.status('split'), slot='split',
                 variant='ordered' if ordered else 'random', values=values,
                 words={'order': x.col(vals['order_column']) if ordered else ''},
                 chart_data=data)


def f_metric(x: Ctx) -> Fill:
    errors = list(METRIC_EXAMPLE_ERRORS)
    squares = [e * e for e in errors]
    mae = sum(errors) / len(errors)
    mean_square = sum(squares) / len(squares)
    rmse = math.sqrt(mean_square)
    e = 'engine:METRIC_EXAMPLE_ERRORS'
    values = {f'e{i + 1}': C(v, 'int', None, f'{e}.{i}') for i, v in enumerate(errors)}
    values.update(mae=C(mae, 'auto', None, f'{e}:mean'),
                  mean_square=C(mean_square, 'auto', None, f'{e}:mean_square'),
                  rmse=C(rmse, 'f2', None, f'{e}:root_mean_square'),
                  big=C(max(errors), 'int', None, f'{e}.{errors.index(max(errors))}'),
                  sum=C(sum(errors), 'int', None, f'{e}:sum'),
                  big_square=C(max(squares), 'int', None, f'{e}:max_square'),
                  sum_square=C(sum(squares), 'int', None, f'{e}:sum_square'))
    unit_note = None
    if x.unit == 'mpg':
        per = MPG_TO_L100 / UNIT_NOTE_MPG
        unit_note = (f'{cite.format_value(UNIT_NOTE_MPG, "int", x.lang)} mpg ≈ '
                     f'{cite.format_value(per, "f1", x.lang)} L/100 km')
    data = {'illustrative': True, 'errors': errors, 'squares': squares, 'mae': mae,
            'mean_square': mean_square, 'rmse': rmse, 'unit': x.unit or None,
            'unit_note': unit_note}
    return _fill(values=values, words={'unit': x.unit}, chart_data=data)


def _min_share(x: Ctx) -> float:
    decision = (x.state.get('decisions') or {}).get(st.SUCCESS_CRITERION) or {}
    value = decision.get('value')
    if isinstance(value, Mapping) and isinstance(value.get('min_share'), (int, float)):
        return float(value['min_share'])
    for p in (x.state.get('proposals') or {}).values():
        if p.get('decision_id') == st.SUCCESS_CRITERION and p.get('status') == 'open' \
                and isinstance((p.get('value') or {}).get('min_share'), (int, float)):
            return float(p['value']['min_share'])
    return DEFAULT_MIN_SHARE


def f_criterion(x: Ctx) -> Fill:
    share = _min_share(x)
    ref = CRITERION_EXAMPLE_REFERENCE
    bound = (1 - share) * ref
    values = {'reference': C(ref, 'auto', None, 'engine:CRITERION_EXAMPLE_REFERENCE'),
              'min_share': C(share, 'pct0', None, 'decision:success_criterion.min_share'),
              'bound': C(bound, 'f1', None, 'engine:CRITERION_EXAMPLE_REFERENCE:bound')}
    bars = [{'id': 'reference', 'value': ref, 'source': 'example'},
            {'id': 'minimum', 'value': bound, 'source': 'example'}]
    current = (x.brief or {}).get('current_method_error')
    target = (x.brief or {}).get('target_error')
    variant = 'no_brief'
    if current:
        values['current'] = C(current['value'], 'f1', None,
                              'case:brief.current_method_error.value')
        bars.append({'id': 'current_method', 'value': current['value'], 'source': 'brief'})
        variant = 'brief'
    if target:
        values['target'] = C(target['value'], 'f1', None, 'case:brief.target_error.value')
        bars.append({'id': 'target', 'value': target['value'], 'source': 'brief'})
    if variant == 'brief' and not target:
        values['target'] = values['current']
    data = {'illustrative': True, 'unit': x.unit or None, 'min_share': share, 'bars': bars}
    return _fill(variant=variant, values=values, words={'unit': x.unit}, chart_data=data)


def _verdict(x: Ctx, check: Mapping, rid: str | None) -> dict:
    labels = content()['verdicts']
    over = bool(check.get('exceeds'))
    return {'label': labels['over' if over else 'under'][x.lang], 'met': over,
            'value': check.get('value'), 'bound': check.get('threshold'), 'result_id': rid,
            'path': check.get('path')}


def f_quality_missing(x: Ctx) -> Fill:
    vals = x.values('eda.quality')
    if vals is None:
        return _pending('eda.quality')
    rid = x.item('eda.quality')['result_id']
    missing = vals.get('missing') or []
    n_rows = vals.get('n_rows')
    some = [(i, m) for i, m in enumerate(missing) if (m.get('n_missing') or 0) > 0]
    values = {'n_rows': C(n_rows, 'int', rid, 'n_rows')}
    if not some:
        return _fill(status=x.status('eda.quality'), slot='eda.quality', variant='none',
                     values=values)
    i, top = max(some, key=lambda im: im[1]['n_missing'])
    values.update(n_columns=C(len(some), 'int', rid, 'missing'),
                  n_missing=C(top['n_missing'], 'int', rid, _path('missing', i, 'n_missing')),
                  share=C(top['share'], 'pct1', rid, _path('missing', i, 'share')))
    verdict = None
    for col in (x.quality_verdicts() or {}).get('columns') or []:
        if col.get('column') == top['column']:
            check = next((c for c in col.get('checks') or [] if c['rule'] == 'missing_indicator'),
                         None)
            if check:
                verdict = _verdict(x, check, rid)
    return _fill(status=x.status('eda.quality'), slot='eda.quality', variant='some',
                 values=values, words={'column': x.col(top['column'])}, verdict=verdict)


SHAPE_RULES = ('signed_log', 'cap_extreme_tail')


def f_quality_shape(x: Ctx) -> Fill:
    qv = x.quality_verdicts()
    if not qv:
        return _pending('eda.quality')
    rid = qv.get('result_id')
    cols = qv.get('columns') or []
    flagged = [(c, ch) for c in cols for ch in c.get('checks') or []
               if ch['rule'] in SHAPE_RULES and ch.get('exceeds')]
    status = x.status('eda.quality')
    if not flagged:
        return _fill(status=status, slot='eda.quality', variant='none',
                     values={'n_columns': C(len(cols), 'int', rid, 'ranges')})
    col, check = flagged[0]
    return _fill(status=status, slot='eda.quality', variant='flagged',
                 values={'value': C(check['value'], 'f2', rid, check['path']),
                         'threshold': C(check['threshold'], 'auto', None,
                                        'engine:drafts.SKEW_THRESHOLD'),
                         'n_others': C(len(cols) - len({c['column'] for c, _ in flagged}),
                                       'int', rid, 'ranges')},
                 words={'column': x.col(col['column'])}, verdict=_verdict(x, check, rid))


def f_prep_changed(x: Ctx) -> Fill:
    qv = x.quality_verdicts()
    if not qv:
        return _pending('eda.quality')
    rid = qv.get('result_id')
    changed = [c for c in qv.get('columns') or [] if c.get('changed')]
    if not changed:
        return _fill(status=x.status('eda.quality'), slot='eda.quality', variant='none')
    col = changed[0]
    check = next((ch for ch in col.get('checks') or [] if ch.get('exceeds')),
                 (col.get('checks') or [{}])[0])
    slot = f'eda.distribution:{col["column"]}'
    status = x.status(slot) if x.item(slot) else x.status('eda.quality')
    return _fill(status=status, slot=slot if x.item(slot) else 'eda.quality', variant='changed',
                 values={'value': C(check.get('value'), 'f2', rid, check.get('path')),
                         'threshold': C(check.get('threshold'), 'auto', None,
                                        'engine:drafts.SKEW_THRESHOLD')},
                 words={'column': x.col(col['column'])})


def f_prep_unchanged(x: Ctx) -> Fill:
    qv = x.quality_verdicts()
    if not qv:
        return _pending('eda.quality')
    rid = qv.get('result_id')
    unchanged = [c for c in qv.get('columns') or [] if c.get('kept') and not c.get('changed')]
    return _fill(status=x.status('eda.quality'), slot='eda.quality',
                 values={'n_unchanged': C(len(unchanged), 'int', rid, 'ranges')})


def f_explore_target(x: Ctx) -> Fill:
    slot = 'eda.target_summary'
    vals = x.values(slot)
    if vals is None:
        return _pending(slot)
    rid = x.item(slot)['result_id']
    values = {k: C(vals.get(k), 'f1', rid, k) for k in ('min', 'max', 'median', 'q25', 'q75')}
    values['mean'] = C(vals.get('mean'), 'f1', rid, 'mean')
    values['n'] = C(vals.get('n'), 'int', rid, 'n')
    other = [_other(x, 'eda.special_values', 'bars')] if x.item('eda.special_values') else []
    return _fill(status=x.status(slot), slot=slot, values=values,
                 words={'target': x.col(x.target), 'unit': x.unit}, other_charts=other)


def _other(x: Ctx, slot: str, chart: str) -> dict:
    item = x.item(slot) or {}
    rid = item.get('result_id')
    return {'slot': slot, 'chart': chart, 'result_id': rid,
            'result_revision': x.revisions.get(rid), 'status': x.status(slot)}


def f_explore_features(x: Ctx) -> Fill:
    from . import drafts
    slots = []
    if x.case is not None:
        slots = [f'{a}:{c}' for a, c in drafts.exploration_slots(x.state, x.case)
                 if a == 'eda.mean_by' and c]
    slots = [s for s in slots if x.item(s)]
    if not slots:
        return _pending(None)

    def spread(s):
        # The chart whose bands differ most (``null_band.chart.observed``, registered);
        # the case's order breaks ties (EN-16's rank correlation is deferred).
        observed = (((x.values(s) or {}).get('null_band') or {}).get('chart') or {}).get(
            'observed')
        return observed if isinstance(observed, (int, float)) else float('-inf')
    slot = max(slots, key=spread)
    slots = [slot] + [s for s in slots if s != slot]
    vals = x.values(slot) or {}
    rid = x.item(slot)['result_id']
    groups = vals.get('groups') or []
    if len(groups) < 2:
        return _pending(slot)
    outside = bool(((vals.get('null_band') or {}).get('chart') or {}).get('outside'))
    last = len(groups) - 1
    values = {'first_mean': C(groups[0]['mean'], 'f1', rid, _path('groups', 0, 'mean')),
              'last_mean': C(groups[last]['mean'], 'f1', rid, _path('groups', last, 'mean'))}
    return _fill(status=x.status(slot), slot=slot, variant='outside' if outside else 'inside',
                 values=values, words={'target': x.col(x.target),
                                       'column': x.col(vals.get('column') or '')},
                 other_charts=[_other(x, s, 'trend_by_bins') for s in slots[1:]])


def f_explore_redundant(x: Ctx) -> Fill:
    slot = 'eda.correlation'
    vals = x.values(slot)
    if vals is None:
        return _pending(slot)
    rid = x.item(slot)['result_id']
    flagged = vals.get('flagged') or []
    values = {'level': C(vals.get('level'), 'f1', rid, 'level')}
    if not flagged:
        return _fill(status=x.status(slot), slot=slot, variant='none', values=values)
    i, top = max(enumerate(flagged), key=lambda it: abs(it[1].get('value') or 0))
    values.update(n_flagged=C(len(flagged), 'int', rid, 'n_flagged'),
                  value=C(top['value'], 'f2', rid, _path('flagged', i, 'value')))
    return _fill(status=x.status(slot), slot=slot, variant='flagged', values=values,
                 words={'a': x.col(top['a']), 'b': x.col(top['b'])})


def _measure(x: Ctx) -> str:
    return st.confirmed_error_metric(x.state) or st.DEFAULT_ERROR_METRIC


def f_models_beat(x: Ctx) -> Fill:
    lin, base = x.values('fit.linear'), x.values('fit.baseline')
    if lin is None or base is None:
        return _pending('fit.linear')
    m = _measure(x)
    rl, rb = x.item('fit.linear')['result_id'], x.item('fit.baseline')['result_id']
    per_l = ((lin.get('cross_validation') or {}).get('per_fold')) or []
    per_b = ((base.get('cross_validation') or {}).get('per_fold')) or []
    better = sum(1 for a, b in zip(per_l, per_b) if a.get(m) is not None and b.get(m) is not None
                 and a[m] < b[m])
    k = len(per_l)
    values = {'linear': C((lin.get('validation') or {}).get(m), 'f2', rl, _path('validation', m)),
              'reference': C((base.get('validation') or {}).get(m), 'f2', rb,
                             _path('validation', m)),
              'n_better': C(better, 'int', rl, _path('cross_validation', 'per_fold')),
              'k': C(k, 'int', rl, _path('cross_validation', 'folds'))}
    status = 'answered' if 'stale' not in (x.status('fit.linear'), x.status('fit.baseline')) \
        else 'stale'
    return _fill(status=status, slot='fit.linear', variant='beats' if better == k else 'mixed',
                 values=values, words={'unit': x.unit, 'measure': m.upper()},
                 other_charts=[_other(x, 'fit.baseline', 'model_dots')])


def _diag_model(x: Ctx, slot: str) -> tuple[Mapping | None, str | None]:
    vals = x.values(slot)
    if vals is None:
        return None, None
    models = vals.get('models') or {}
    name = vals.get('model') if vals.get('model') in models else (
        'fit.linear' if 'fit.linear' in models else next(iter(models), None))
    return (models.get(name) if name else None), name


def f_models_where(x: Ctx) -> Fill:
    slot = 'diag.regression'
    d, name = _diag_model(x, slot)
    if d is None:
        return _pending(slot)
    rid = x.item(slot)['result_id']
    het = d.get('heteroscedasticity') or {}
    values = {'n': C((d.get('scatter') or {}).get('n_rows'), 'int', rid,
                     _path('models', name, 'scatter', 'n_rows')),
              'rho': C(het.get('abs_residual_prediction_correlation'), 'f2', rid,
                       _path('models', name, 'heteroscedasticity',
                             'abs_residual_prediction_correlation'))}
    return _fill(status=x.status(slot), slot=slot, variant='grows' if het.get('flag') else 'even',
                 values=values)


def f_variants_shape(x: Ctx) -> Fill:
    slot = 'diag.regression'
    d, name = _diag_model(x, slot)
    if d is None:
        return _pending(slot)
    rid = x.item(slot)['result_id']
    best = None
    for i, feat in enumerate(d.get('by_feature') or []):
        groups = [(j, g) for j, g in enumerate(feat.get('groups') or [])
                  if not g.get('small_cell') and g.get('mean_residual') is not None]
        if len(groups) < 2:
            continue
        lo = min(groups, key=lambda jg: jg[1]['mean_residual'])
        hi = max(groups, key=lambda jg: jg[1]['mean_residual'])
        spread = hi[1]['mean_residual'] - lo[1]['mean_residual']
        if best is None or spread > best[0]:
            best = (spread, i, feat, lo, hi)
    if best is None:
        return _pending(slot)
    spread, i, feat, lo, hi = best
    base = ('models', name, 'by_feature', i, 'groups')
    values = {'low': C(lo[1]['mean_residual'], 'f1', rid, _path(*base, lo[0], 'mean_residual')),
              'high': C(hi[1]['mean_residual'], 'f1', rid, _path(*base, hi[0], 'mean_residual')),
              'bound': C(RESIDUAL_SHAPE_MIN, 'auto', None, 'engine:RESIDUAL_SHAPE_MIN')}
    others = [{'slot': f'{slot}#{f["column"]}', 'chart': 'residual_by_feature',
               'result_id': rid, 'result_revision': x.revisions.get(rid),
               'status': x.status(slot)} for f in d.get('by_feature') or []
              if f.get('column') != feat.get('column')]
    return _fill(status=x.status(slot), slot=slot,
                 variant='shape' if spread >= RESIDUAL_SHAPE_MIN else 'flat', values=values,
                 words={'column': x.col(feat.get('column') or ''), 'unit': x.unit},
                 other_charts=others, main_column=feat.get('column'))


def f_variants_period(x: Ctx) -> Fill:
    slot = 'evaluate.regression'
    vals = x.values(slot)
    if vals is None:
        return _pending(slot)
    rid = x.item(slot)['result_id']
    by = vals.get('residuals_by') or []
    i, entry = next(((i, e) for i, e in enumerate(by) if e.get('column')), (None, None))
    if entry is None:
        return _pending(slot)
    groups = entry.get('groups') or []
    if len(groups) < 2:
        return _pending(slot)
    model = 'fit.linear'
    first = (groups[0].get('models') or {}).get(model) or {}
    last = (groups[-1].get('models') or {}).get(model) or {}
    if first.get('mean_residual') is None or last.get('mean_residual') is None:
        return _pending(slot)
    j = len(groups) - 1
    values = {'first_bias': C(first['mean_residual'], 'f1', rid,
                              _path('residuals_by', i, 'groups', 0, 'models', model,
                                    'mean_residual')),
              'last_bias': C(last['mean_residual'], 'f1', rid,
                             _path('residuals_by', i, 'groups', j, 'models', model,
                                   'mean_residual')),
              'bound': C(DRIFT_BOUND, 'auto', None, 'engine:DRIFT_BOUND'),
              'n_bands': C(len(groups), 'int', rid, _path('residuals_by', i, 'groups'))}
    drift = abs(last['mean_residual'] - first['mean_residual']) >= DRIFT_BOUND
    return _fill(status=x.status(slot), slot=slot, variant='drift' if drift else 'stable',
                 values=values, words={'column': x.col(entry['column']), 'unit': x.unit})


def _selection(x: Ctx) -> tuple[Mapping | None, str | None]:
    vals = x.values('evaluate.regression')
    if vals is None:
        return None, None
    ms = vals.get('model_selection')
    if not isinstance(ms, Mapping) or not ms.get('available'):
        return None, x.item('evaluate.regression')['result_id']
    return ms, x.item('evaluate.regression')['result_id']


def _criterion_verdict(x: Ctx, slot: str | None) -> dict | None:
    from . import panel_digest
    cc = panel_digest.criterion_configurations(x.built) or {}
    labels = content()['verdicts']
    for c in cc.get('configurations') or []:
        if c['slot'] == slot:
            met = bool(c['point_meets_bound'])
            return {'label': labels['met' if met else 'not_met'][x.lang], 'met': met,
                    'value': c['value'], 'bound': (cc.get('bound') or {}).get('value'),
                    'result_id': c['result_id'], 'path': c['path']}
    return None


def f_choice_best(x: Ctx) -> Fill:
    ms, rid = _selection(x)
    slot = 'evaluate.regression'
    if ms is None:
        return _pending(slot)
    confs = ms.get('configurations') or []
    idx = {c['slot']: i for i, c in enumerate(confs)}
    best = ms.get('best') or (min(confs, key=lambda c: c['mean'])['slot'] if confs else None)
    if best not in idx or 'fit.linear' not in idx:
        return _pending(slot)
    values = {'best_mean': C(confs[idx[best]]['mean'], 'f2', rid,
                             _path('model_selection', 'configurations', idx[best], 'mean')),
              'linear_mean': C(confs[idx['fit.linear']]['mean'], 'f2', rid,
                               _path('model_selection', 'configurations', idx['fit.linear'],
                                     'mean'))}
    optimism = (ms.get('optimism') or {}).get('estimate')
    if optimism is not None:
        values['optimism'] = C(optimism, 'f2', rid, _path('model_selection', 'optimism',
                                                          'estimate'))
    if best == 'fit.linear':
        variant = 'alone'
    else:
        diff = confs[idx[best]].get('difference') or {}
        within = diff.get('within_fold_noise')
        variant = 'within' if within else 'beyond'
    if variant != 'alone' and optimism is None:
        values['optimism'] = C(0.0, 'f2', rid, _path('model_selection', 'optimism', 'estimate'))
    return _fill(status=x.status(slot), slot=slot, variant=variant, values=values,
                 words={'best_name': x.model(best, capital=True), 'unit': x.unit},
                 verdict=_criterion_verdict(x, best),
                 other_charts=[{**_other(x, slot, 'paired_intervals')}])


def f_choice_simplest(x: Ctx) -> Fill:
    ms, rid = _selection(x)
    slot = 'evaluate.regression'
    if ms is None or not isinstance(ms.get('one_se'), Mapping):
        return _pending(slot)
    one = ms['one_se']
    within = sum(1 for c in ms.get('configurations') or [] if c.get('within_one_se'))
    values = {'bound': C(one.get('bound'), 'f2', rid, _path('model_selection', 'one_se', 'bound')),
              'se': C(one.get('se_of_best'), 'f2', rid,
                      _path('model_selection', 'one_se', 'se_of_best')),
              'n_within': C(within, 'int', rid, _path('model_selection', 'configurations'))}
    return _fill(status=x.status(slot), slot=slot, values=values, words={'unit': x.unit},
                 verdict=_criterion_verdict(x, one.get('pick')))


def f_final_what(x: Ctx) -> Fill:
    data = _strata_data(x)
    values = {'sealed': C(x.sealed, 'int', None, 'partition:final_test.n_rows')}
    chosen = st.choice_config(x.state)
    if chosen and chosen.get('model'):
        return _fill(variant='chosen', values=values,
                     words={'model_name': x.model(chosen['model'])}, chart_data=data)
    return _fill(variant='unchosen', values=values, chart_data=data)


def f_conclusion_beat(x: Ctx) -> Fill:
    slot = 'final_test.evaluation'
    vals = x.values(slot)
    if vals is None:
        return _pending(slot)
    rid = x.item(slot)['result_id']
    m = _measure(x)
    model = vals.get('model')
    models = vals.get('models') or {}
    mine = (models.get(model) or {}).get(m)
    ref = (models.get('fit.baseline') or {}).get(m)
    dev_vals = x.values('evaluate.regression') or {}
    dev = ((dev_vals.get('models') or {}).get(model) or {}).get(m)
    dev_rid = (x.item('evaluate.regression') or {}).get('result_id')
    values = {'final': C(mine, 'f2', rid, _path('models', model, m)),
              'final_reference': C(ref, 'f2', rid, _path('models', 'fit.baseline', m)),
              'development': C(dev, 'f2', dev_rid, _path('models', model, m))}
    if any(v['value'] is None for v in values.values()):
        return _pending(slot)
    data = {'measure': m, 'unit': x.unit or None,
            'development': {'model': dev, 'reference': ((dev_vals.get('models') or {}).get(
                'fit.baseline') or {}).get(m), 'result_id': dev_rid},
            'final': {'model': mine, 'reference': ref, 'result_id': rid}}
    return _fill(status=x.status(slot), slot=slot, variant='beats' if mine < ref else 'loses',
                 values=values, words={'model_name': x.model(model), 'unit': x.unit},
                 chart_data=None, dev_final=data)


def f_conclusion_criterion(x: Ctx) -> Fill:
    slot = 'final_test.evaluation'
    vals = x.values(slot)
    if vals is None:
        return _pending(slot)
    rid = x.item(slot)['result_id']
    from . import panel_digest
    cc = panel_digest.criterion_configurations(x.built) or {}
    final = cc.get('final_test')
    if not isinstance(final, Mapping) or final.get('gain') is None:
        return _pending(slot)
    p = 'criterion'
    values = {'gain': C(final['gain'], 'pct1', rid, _path(p, 'gain')),
              'low': C(final.get('low'), 'pct1', rid, _path(p, 'low')),
              'high': C(final.get('high'), 'pct1', rid, _path(p, 'high')),
              'min_share': C((final.get('bound') or {}).get('minimum'), 'pct0', rid,
                             _path(p, 'minimum'))}
    if any(v['value'] is None for v in values.values()):
        return _pending(slot)
    status = final.get('status')
    if status == 'met':
        variant = 'met_low'
    elif final.get('point_meets_bound'):
        variant = 'met_point'
    else:
        variant = 'not_met'
    labels = content()['verdicts']
    met = status == 'met'
    verdict = {'label': labels['met' if met else 'not_met'][x.lang], 'met': met,
               'value': final['value'], 'bound': (final.get('bound') or {}).get('value'),
               'result_id': rid, 'path': final.get('path')}
    business = cc.get('business')
    extra = {}
    if isinstance(business, Mapping) and isinstance(business.get('final_test'), Mapping):
        b = business['final_test']
        values['bar'] = C(business['max_error'], 'f1', None,
                          'decision:success_criterion.business_max_error')
        values['final'] = C(b['value'], 'f2', b.get('result_id'), b.get('path'))
        extra['business'] = 'met' if b.get('met') else 'not_met'
    return _fill(status=x.status(slot), slot=slot, variant=variant, values=values,
                 verdict=verdict, **extra)


def f_conclusion_where(x: Ctx) -> Fill:
    slot = 'diag.final_test'
    d, name = _diag_model(x, slot)
    if d is None:
        return _pending(slot)
    rid = x.item(slot)['result_id']
    errors = d.get('errors') or {}
    values = {'n': C(errors.get('n') or (d.get('scatter') or {}).get('n_rows'), 'int', rid,
                     _path('models', name, 'errors', 'n')),
              'mean_residual': C(errors.get('mean_residual'), 'f2', rid,
                                 _path('models', name, 'errors', 'mean_residual')),
              'max_abs': C(errors.get('max_abs_residual'), 'f1', rid,
                           _path('models', name, 'errors', 'max_abs_residual'))}
    if any(v['value'] is None for v in values.values()):
        return _pending(slot)
    return _fill(status=x.status(slot), slot=slot, values=values, words={'unit': x.unit})


# --- the registry (EN-1) ----------------------------------------------------------------------

def _q(qid, step, chart, source, evidence, fill, when=None) -> dict:
    kind, _, ref = source.partition(':')
    return {'id': qid, 'step': step, 'tasks': (st.REGRESSION,), 'chart': chart,
            'source': {'kind': kind, 'slot': ref if kind == 'result' else None,
                       'key': ref if kind != 'result' else None},
            'frame': evidence, 'fill': fill, 'when': when}


QUESTIONS: tuple[dict, ...] = (
    _q('data.row', 'discover_data', 'sample_table', 'digest:sample', 'structure', f_data_row),
    _q('data.structure', 'discover_data', 'structure_bars', 'digest:data_structure',
       'structure', f_data_structure),
    _q('moment.when', 'prediction_time', 'moment_timeline', 'case:case_display.timeline',
       'none', f_moment),
    _q('variables.kept', 'feature_availability', 'variables_board',
       'decision:feature_availability', 'none', f_variables),
    _q('split.sealed', 'split', 'partition_strata', 'case:partition.strata_counts', 'structure',
       f_split_sealed),
    _q('split.folds', 'split', 'folds', 'result:split', 'structure', f_split_folds),
    _q('metric.weigh', st.ERROR_METRIC, 'metric_bars', 'illustration:METRIC_EXAMPLE_ERRORS',
       'illustration', f_metric),
    _q('criterion.bar', st.SUCCESS_CRITERION, 'criterion_example',
       'illustration:CRITERION_EXAMPLE_REFERENCE', 'illustration', f_criterion),
    _q('quality.missing', 'structural_eda', 'bars', 'result:eda.quality', 'structure',
       f_quality_missing),
    _q('quality.shape', 'structural_eda', 'verdicts_table', 'digest:quality_verdicts',
       'structure', f_quality_shape),
    _q('prep.changed', st.PREPROCESSING, 'distribution_before_after', 'digest:quality_verdicts',
       'structure', f_prep_changed),
    _q('prep.unchanged', st.PREPROCESSING, 'verdicts_table', 'digest:quality_verdicts',
       'structure', f_prep_unchanged),
    _q('explore.target', 'train_eda', 'histogram', 'result:eda.target_summary', 'development',
       f_explore_target),
    _q('explore.features', 'train_eda', 'trend_by_bins', 'result:eda.mean_by', 'development',
       f_explore_features),
    _q('explore.redundant', 'train_eda', 'correlation', 'result:eda.correlation', 'structure',
       f_explore_redundant),
    _q('models.beat', 'models', 'model_dots', 'result:fit.linear', 'development',
       f_models_beat),
    _q('models.where', 'models', 'observed_predicted', 'result:diag.regression', 'development',
       f_models_where),
    _q('variants.shape', st.MODEL_VARIANT, 'residual_by_feature', 'result:diag.regression',
       'development', f_variants_shape),
    _q('variants.period', st.MODEL_VARIANT, 'bias_by_period', 'result:evaluate.regression',
       'development', f_variants_period),
    _q('choice.best', 'model_choice', 'per_fold_dots', 'result:evaluate.regression',
       'development', f_choice_best),
    _q('choice.simplest', 'model_choice', 'one_se_rule', 'result:evaluate.regression',
       'development', f_choice_simplest),
    _q('final.what', st.FINAL_TEST, 'partition_strata', 'decision:model_choice', 'none',
       f_final_what),
    _q('conclusion.beat', 'conclusion', 'dev_vs_final', 'result:final_test.evaluation', 'final',
       f_conclusion_beat),
    _q('conclusion.criterion', 'conclusion', 'criterion_gauge', 'result:final_test.evaluation',
       'final', f_conclusion_criterion),
    _q('conclusion.where', 'conclusion', 'observed_predicted', 'result:diag.final_test', 'final',
       f_conclusion_where),
)
QUESTION_IDS = tuple(q['id'] for q in QUESTIONS)

# Block 1 of each step (LOT §3.1; §8.5: always illustrative or structural).
PICTURES = {'discover_data': ('row_card', False), 'prediction_time': ('moment_timeline', True),
            'feature_availability': ('variables_board', False),
            'split': ('partition_strip', False), st.ERROR_METRIC: ('error_gap', True),
            st.SUCCESS_CRITERION: ('criterion_bar', True),
            'structural_eda': ('quality_checks', True),
            st.PREPROCESSING: ('log_before_after', True), 'train_eda': ('trend_reading', True),
            'models': ('mean_vs_line', True), st.MODEL_VARIANT: ('line_misses_curve', True),
            'model_choice': ('one_se_rule', True), st.FINAL_TEST: ('sealed_once', False),
            'conclusion': ('dev_vs_final', True)}


# --- formatting and the card ------------------------------------------------------------------

def _text(value, kind: str, lang: str) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return str(value)
    if kind == 'pct1':
        return cite.format_value(value, 'pct1', lang)
    return cite.format_value(value, kind, lang)


def _fill_text(template: str, mapping: Mapping[str, str]) -> str:
    return template.format_map(mapping)


def _words(text: str | None) -> int:
    return len(re.findall(r"[\w'’-]+", text or ''))


def _strict(problem: str) -> None:
    if os.environ.get(STRICT_ENV) == '1':
        raise AssertionError(problem)
    print(f'hypotrail: step card text over its length: {problem}', file=sys.stderr)


def _reading(x: Ctx, qid: str, fill: Fill) -> tuple[dict | None, list[dict]]:
    if fill.get('variant') is None or fill['status'] in ('pending', 'integrity_failed'):
        return None, []
    q = content()['questions'][qid]
    parts = q['reading'][fill['variant']]
    texts = {name: _text(c['value'], c['kind'], x.lang) for name, c in fill['values'].items()}
    mapping = {**texts, **fill['words']}
    out = {k: _fill_text(parts[k][x.lang], mapping) for k in READING_KEYS}
    if fill.get('business'):
        extra = content()['business'][fill['business']][x.lang]
        out['conclude'] = f'{out["conclude"]} {_fill_text(extra, mapping)}'
    used = set()
    for k in READING_KEYS:
        used |= placeholders(parts[k][x.lang])
    if fill.get('business'):
        used |= placeholders(content()['business'][fill['business']][x.lang])
    cites = [{'name': name, 'result_id': c['result_id'], 'path': c['path'], 'value': c['value'],
              'text': texts[name]} for name, c in fill['values'].items() if name in used]
    total = sum(_words(out[k]) for k in READING_KEYS)
    if total > READING_MAX_WORDS:
        _strict(f'{qid} reading has {total} words')
    return out, cites


def _frame(x: Ctx, evidence: str) -> dict:
    template = content()['frames'][evidence][x.lang]
    mapping = {'dev': _text(x.dev, 'int', x.lang) if x.dev is not None else '',
               'sealed': _text(x.sealed, 'int', x.lang) if x.sealed is not None else '',
               'looks': _text(x.looks, 'int', x.lang) if x.looks is not None else ''}
    return {'evidence': evidence, 'rows': _fill_text(template, mapping)}


def _question(x: Ctx, spec: Mapping, n: int, done_or_current: bool) -> dict:
    c = content()['questions'][spec['id']]
    try:
        fill = spec['fill'](x)
    except Exception as exc:             # noqa: BLE001 - a filler that fails shows pending
        if os.environ.get(STRICT_ENV) == '1':
            raise
        print(f'hypotrail: step card {spec["id"]}: {exc!r}', file=sys.stderr)
        fill = _pending()
    reading, cites = _reading(x, spec['id'], fill)
    slot = fill.get('slot')
    item = x.item(slot) if slot else None
    rid = item.get('result_id') if item else None
    chart_data = fill.get('chart_data')
    if spec['chart'] == 'dev_vs_final':
        chart_data = fill.get('dev_final')
    return {'id': spec['id'], 'n': n, 'text': c['text'][x.lang], 'source': dict(spec['source']),
            'chart': spec['chart'], 'chart_data': chart_data,
            'other_charts': list(fill.get('other_charts') or []),
            'frame': _frame(x, spec['frame']), 'status': fill['status'], 'result_id': rid,
            'result_revision': x.revisions.get(rid) if rid else None, 'reading': reading,
            'cites': cites, 'verdict': fill.get('verdict'),
            'folds': {'how': c['how'][x.lang], 'trap': c['trap'][x.lang]},
            '_fill': fill}


def _decision(x: Ctx, step: Mapping) -> dict | None:
    decision_id = step.get('decision')
    if not decision_id:
        return None
    d = (x.state.get('decisions') or {}).get(decision_id) or {}
    conf = d.get('confirmation')
    if d.get('status') != 'confirmed' or not isinstance(conf, Mapping):
        return None
    basis = st.confirmation_basis(conf)
    klass = st.basis_class(basis)
    who = 'automatic' if klass == 'automatic' else ('delegated' if klass == 'delegated'
                                                     else 'you')
    return {'decision_id': decision_id, 'words': conf.get('user_words'), 'basis': basis,
            'who': who}


def _step_mapping(x: Ctx) -> dict:
    part = x.state.get('partition') or {}
    from . import l10n
    unit_fact = None
    if x.case is not None:
        tr = l10n.translations(x.state, x.case.document)
        unit_fact = (tr.row_unit(x.lang) if x.fr else None) or \
            ((x.case.document.get('structure') or {}).get('row_unit') or {}).get('value')
    split = _split_value(x) or {}
    return {'row_unit': (unit_fact or '').rstrip('.'),
            'sealed': _text(x.sealed, 'int', x.lang) if x.sealed is not None else '',
            'dev': _text(x.dev, 'int', x.lang) if x.dev is not None else '',
            'k': _text(split.get('folds') or st.DEFAULT_FOLDS, 'int', x.lang),
            'min_share': _text(_min_share(x), 'pct0', x.lang),
            'bins': _text(part.get('bins') or 0, 'int', x.lang)}


def _card(x: Ctx, step: Mapping, n: int, current: str | None, moments: Mapping) -> dict:
    from . import companion_env as ce
    sid = step['id']
    texts = content()['steps'].get(sid) or {}
    mapping = _step_mapping(x)
    state_ = 'done' if step.get('status') == 'done' else (
        'current' if sid == current else 'upcoming')
    if sid == current:
        state_ = 'current'
    kind, illustrative = PICTURES.get(sid, ('row_card', True))
    questions = []
    if state_ != 'upcoming':
        specs = [q for q in QUESTIONS if q['step'] == sid
                 and (q['when'] is None or q['when'](x))]
        questions = [_question(x, spec, i + 1, True) for i, spec in enumerate(specs)]
    data = None
    if kind in ('partition_strip', 'sealed_once'):
        data = {'development': x.dev, 'sealed': x.sealed}
    elif kind in ('moment_timeline', 'variables_board') and questions:
        data = questions[0].get('chart_data')
    for q in questions:
        q.pop('_fill', None)
    caption = _fill_text(texts['caption'][x.lang], mapping) if texts else ''
    if _words(caption) > CAPTION_MAX_WORDS:
        _strict(f'{sid} caption has {_words(caption)} words')
    prepares = texts['prepares'][x.lang] if texts else ''
    if questions and _words(prepares) + sum(_words(q['text']) for q in questions) \
            > PREPARES_MAX_WORDS:
        _strict(f'{sid} prepares and questions exceed {PREPARES_MAX_WORDS} words')
    limit = texts['limit'][x.lang] if texts else ''
    nxt = texts['next'][x.lang] if texts else ''
    for label, value in (('limit', limit), ('next', nxt)):
        if _words(value) > LIMIT_MAX_WORDS:
            _strict(f'{sid} {label} has {_words(value)} words')
    no_chart = None
    if questions and all(q['chart'] is None for q in questions):
        no_chart = content()['no_chart_pending'][x.lang]
    return {'step': sid, 'n': n, 'name': ce.step_name(sid, x.lang),
            'short': ce.step_label(sid, x.lang), 'moment': moments.get(sid),
            'state': state_,
            'picture': {'kind': kind, 'caption': caption,
                        'more': _fill_text(texts['more'][x.lang], mapping) if texts else '',
                        'illustrative': illustrative, 'data': data},
            'prepares': prepares, 'questions': questions, 'no_chart': no_chart,
            'limit': limit, 'next': nxt,
            'decision': _decision(x, step) if state_ == 'done' else None}


def applies(state: Mapping) -> bool:
    """Whether a study has step cards: a regression study holding this lot's decision set."""
    return st.has_error_metric(state)


def build(study, built: Mapping, lang: str, *, records: list | None = None) -> dict | None:
    """``texts.<lang>.step_cards`` (§7.2), or None for a study without step cards."""
    from . import companion_env as ce
    from . import view as vw
    if not applies(study.state):
        return None
    x = Ctx(study, built, lang, records)
    plan = list(built.get('plan') or [])
    action = built.get('next_action') or {}
    current = None if action.get('kind') == 'done' else ce.current_step(action, plan)
    moments = {}
    try:
        for m in vw.moments(built.get('task') or st.REGRESSION, {**study.state,
                                                                  'language': lang}):
            for s in m['steps']:
                moments[s] = m['title']
    except Exception:                    # noqa: BLE001 - no moments: none named
        pass
    steps = [_card(x, s, i + 1, current, moments) for i, s in enumerate(plan)]
    return {'schema': SCHEMA, 'current': current if current in [s['id'] for s in plan] else None,
            'total': len(plan), 'steps': steps}


__all__ = ['SCHEMA', 'CARDS_KEYS', 'STEP_KEYS', 'QUESTION_KEYS', 'CHART_KINDS',
           'PICTURE_KINDS', 'QUESTIONS', 'QUESTION_IDS', 'build', 'applies', 'content',
           'placeholders']
