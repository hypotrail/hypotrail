"""Evidence tables, charts and method diagrams of the lesson-style report (owner remarks R41,
R42, R48, R52, R53 of 2026-10-28).

* R52: one table of development and final evidence, configuration by configuration
  (:func:`regression_table`), and the same values as dots with intervals on one scale, the
  criterion's final-test bound drawn (:func:`evidence_dots`);
* R48: the criterion judged on the final test as a chart (:func:`criterion_final`);
* R53: the method diagrams, each from registered values: the cross-validation rotation
  (:func:`cv_rotation`), the per-column view of the quality check (:func:`column_view`), the
  preparation pipeline (:func:`pipeline`), the one-standard-error rule (:func:`one_se`) and the
  exposure ledger as a timeline (:func:`exposure_timeline`).

Every number shown is cited from a registered result (:class:`mlkit.study.cite.Citer`) or is a
recorded literal of the study state; a position computed from recorded values (the
criterion's bound, a band) is used for the drawing only and never written. The renderer
computes no new figure. Each function returns the body of a frame (an empty string when its
values are not registered); the chapters wrap it with its guided reading
(:func:`mlkit.study.render_guide.frame`). Every word comes from ``content/lesson.yaml``
(``evidence``), in the edition's language.

Pure: no pandas, numpy, or scikit-learn.
"""
from __future__ import annotations

import html
from typing import Mapping

from . import cite, render_charts as rc, render_guide as g, texts
from . import render_html as rh

e = html.escape
CONFIG_ORDER = ('fit.linear', 'fit.logistic', 'fit.variant', 'fit.variant:2', 'fit.variant:3',
                'fit.baseline')


def say(key: str) -> str:
    return g.say('evidence.' + key)


def t(key: str, **values: str) -> str:
    return g.t('evidence.' + key, **values)


def _num(x) -> bool:
    return cite.is_number(x)


def _mapping(x) -> Mapping:
    return x if isinstance(x, Mapping) else {}


def _keys(items: list[tuple[str, str]]) -> str:
    return '<p class="keys">' + ''.join(f'<span><i class="sw {c}"></i>{e(w)}</span>'
                                       for c, w in items) + '</p>'


def _interval(citer, rid: str, base: str, fmt: str = 'f2') -> str:
    if citer.has(rid, base + '.low') and citer.has(rid, base + '.high'):
        return t('interval', low=citer.num(rid, base + '.low', fmt),
                 high=citer.num(rid, base + '.high', fmt))
    return ''


def configurations(models: Mapping) -> list[str]:
    known = [m for m in CONFIG_ORDER if m in models]
    return known + sorted(m for m in models if m not in known)


def chosen_model(view: Mapping, final_values: Mapping | None = None) -> str | None:
    """The configuration the study carries to the final test: the one the final test
    measured, else the criterion's model, else the confirmed model choice."""
    if final_values and final_values.get('model'):
        return str(final_values['model'])
    criterion = view.get('criterion') or {}
    if criterion.get('model'):
        return str(criterion['model'])
    choice = view['decisions'].get('model_choice') or {}
    if choice.get('status') in ('confirmed', 'reconfirm_required') and choice.get('value'):
        return str(choice['value'])
    return None


def _rids(view: Mapping, citer) -> tuple[str | None, Mapping, str | None, Mapping]:
    dev = citer.slot_rid('evaluate.regression')
    fin = citer.slot_rid('final_test.evaluation')
    return (dev, _mapping(citer.results[dev].values) if dev else {},
            fin, _mapping(citer.results[fin].values) if fin else {})


def _criterion_share(view: Mapping) -> float | None:
    sc = view['decisions'].get('success_criterion') or {}
    value = _mapping(sc.get('value'))
    if value.get('metric') == 'mae_reduction' and _num(value.get('min_share')):
        return value['min_share']
    return None


# --- R52: the evidence table ---------------------------------------------------------------------

def regression_table(view: Mapping, citer) -> str:
    """Development and final evidence in one table: one row per configuration (the reference
    last), then the paired difference of the chosen configuration with the reference, then the
    success criterion; the chosen row highlighted, an unmeasured final cell said in words."""
    dev, dv, fin, fv = _rids(view, citer)
    if dev is None:
        return ''
    models = _mapping(dv.get('models'))
    state = (view.get('final_test') or {}).get('status')
    chosen = chosen_model(view, fv)

    def final_missing() -> str:
        key = {'opened': 'unmeasured', 'sealed': 'sealed_cell'}.get(state, 'absent_cell')
        return f'<span class="unmeasured" data-unmeasured="{key}">{e(say(key))}</span>'

    rows = []
    for slot in configurations(models):
        path = cite.format_path(['models', slot, 'mae'])
        if not citer.has(dev, path):
            continue
        iv = cite.format_path(['intervals', slot, 'mae'])
        dcell = citer.num(dev, path, 'f2') + _interval(citer, dev, iv)
        if fin and citer.has(fin, path):
            fcell = citer.num(fin, path, 'f2') + _interval(citer, fin, iv)
        else:
            fcell = final_missing()
        mark = (f' <span class="chosen-mark">{e(say("chosen"))}</span>' if slot == chosen
                else '')
        cls = ' class="chosen"' if slot == chosen else ''
        rows.append(f'<tr{cls} data-config="{e(slot)}"><th scope="row">'
                    f'{e(rh.capital(rh.model_name(slot)))}{mark}</th>'
                    f'<td>{dcell}</td><td>{fcell}</td></tr>')
    if not rows:
        return ''
    if chosen and chosen != 'fit.baseline':
        d = cite.format_path(['deltas', chosen, 'mae'])
        if citer.has(dev, d + '.point'):
            dcell = citer.num(dev, d + '.point', 'f2') + _interval(citer, dev, d)
            fcell = (citer.num(fin, d + '.point', 'f2') + _interval(citer, fin, d)
                     if fin and citer.has(fin, d + '.point') else final_missing())
            rows.append(f'<tr class="sep" data-row="paired"><th scope="row">'
                        f'{t("paired", model=e(rh.model_short(chosen)), reference=e(rh.model_short("fit.baseline")))}'
                        f'</th><td>{dcell}</td><td>{fcell}</td></tr>')
    share = _criterion_share(view)
    if share is not None:
        language = texts.report_language()
        pct = rh.lit('decision_value', cite.format_value(share, 'pct0', language))
        criterion = view.get('criterion') or {}
        dev_status = criterion.get('status') or 'not_assessed'
        dcell = t('criterion_dev', status=e(say('status.' + dev_status)))
        if fin and citer.has(fin, 'criterion.gain'):
            status = _mapping(fv.get('criterion')).get('status') or 'not_assessed'
            fcell = (t('criterion_final', gain=citer.num(fin, 'criterion.gain', 'pct1'),
                       interval=_interval(citer, fin, 'criterion', 'pct1'))
                     + f' <b class="st-{e(status)}">{e(say("status_final." + status))}</b>')
        else:
            fcell = final_missing()
        rows.append(f'<tr class="sep" data-row="criterion"><th scope="row">'
                    f'{t("criterion", share=pct)}</th><td>{dcell}</td><td>{fcell}</td></tr>')
    unit = dv.get('unit')
    unit_html = rh.lit('case', unit) if unit else ''
    head = (f'<thead><tr><th scope="col">{e(say("col_config"))}</th>'
            f'<th scope="col" class="h-dev">{e(say("col_dev"))}</th>'
            f'<th scope="col" class="h-fin">{e(say("col_final"))}</th></tr></thead>')
    return (f'<div class="tbl"><table class="evtab" data-evidence-table="regression">{head}'
            f'<tbody>{"".join(rows)}</tbody></table></div>'
            f'<p class="cap">{t("table_note", unit=unit_html)}</p>')


def evidence_dots(view: Mapping, citer) -> str:
    """R52/R48: the table's errors as dots with their intervals on one scale, development
    (open) and final (filled) side by side, the criterion's final-test bound drawn (a position
    computed from recorded values, never written)."""
    dev, dv, fin, fv = _rids(view, citer)
    if dev is None:
        return ''
    models, fmodels = _mapping(dv.get('models')), _mapping(fv.get('models'))
    divs, fivs = _mapping(dv.get('intervals')), _mapping(fv.get('intervals'))
    rows = [m for m in configurations(models) if _num(_mapping(models.get(m)).get('mae'))]
    if not rows:
        return ''
    bound = None
    crit = _mapping(fv.get('criterion'))
    base = _mapping(fmodels.get('fit.baseline')).get('mae')
    if _num(crit.get('minimum')) and _num(base) and crit.get('metric') == 'mae_reduction':
        bound = base * (1 - crit['minimum'])
    edges = [] if bound is None else [bound]
    for m in rows:
        for src_models, src_iv in ((models, divs), (fmodels, fivs)):
            value = _mapping(src_models.get(m)).get('mae')
            if _num(value):
                edges.append(value)
                iv = _mapping(_mapping(src_iv.get(m)).get('mae'))
                edges += [v for v in (iv.get('low'), iv.get('high')) if _num(v)]
    lo, hi = min(edges), max(edges)
    pad = (hi - lo) * 0.08 or 0.5
    scale = rc.Scale(max(0.0, lo - pad), hi + pad, x1=rc.WIDTH - rc.RIGHT - 16)
    chosen = chosen_model(view, fv)
    body, y = [], rc.TOP + 4
    for m in rows:
        has_final = _num(_mapping(fmodels.get(m)).get('mae'))
        height = 36 if has_final else 22
        label = rh.capital(rh.model_short(m))
        weight = ' class="lbl-chosen"' if m == chosen else ''
        body.append(f'<text x="{rc.LEFT - 8}" y="{y + 12 + (6 if has_final else 0):.1f}" '
                    f'text-anchor="end" data-literal="identifier"{weight}>{e(label)}</text>')
        if m == chosen:
            body.append(f'<rect class="chosen-band" x="4" y="{y - 2}" '
                        f'width="{rc.WIDTH - 8}" height="{height + 2}" rx="4"/>')
        series = rc._series(m)
        marks = [('dev', dev, models, divs, y + 10)]
        if has_final:
            marks.append(('final', fin, fmodels, fivs, y + 26))
        for kind, rid, src, ivs, cy in marks:
            iv = _mapping(_mapping(ivs.get(m)).get('mae'))
            if _num(iv.get('low')) and _num(iv.get('high')):
                body.append(f'<line class="ci s-{series}" x1="{scale(iv["low"]):.1f}" y1="{cy}" '
                            f'x2="{scale(iv["high"]):.1f}" y2="{cy}"/>')
            cls = 'dot open' if kind == 'dev' else 'dot'
            body.append(f'<circle class="{cls} s-{series}" cx="{scale(src[m]["mae"]):.1f}" '
                        f'cy="{cy}" r="5"><title>{e(say("dot_" + kind))}</title></circle>')
            body.append(citer.svg_num(rid, cite.format_path(['models', m, 'mae']), 'f2',
                                      x=rc.WIDTH - rc.RIGHT + 2, y=cy + 4,
                                      prefix='◐ ' if kind == 'dev' else '● '))
        y += height + 8
    if bound is not None:
        xb = scale(bound)
        body.append(f'<line class="thr" x1="{xb:.1f}" y1="{rc.TOP - 8}" x2="{xb:.1f}" '
                    f'y2="{y - 4}"/>')
        body.append(f'<text x="{xb + 4:.1f}" y="{rc.TOP - 10}" class="thr-t">'
                    f'{e(say("bound"))}</text>')
    body.insert(0, scale.axis(rc.TOP - 6, y - 4))
    svg = rc._svg(y + rc.AXIS - 4, ''.join(body), say('dots_label'))
    keys = [('dot open', say('key_dev')), ('dot', say('key_final')), ('ci', say('key_ci'))]
    if bound is not None:
        keys.append(('thr', say('bound')))
    return rc.figure('evidence_dots', say('dots_question'), svg, _keys(keys),
                     e(say('dots_note')))


def criterion_final(view: Mapping, citer) -> str:
    """R48: the criterion judged on the final test: the reduction of the reference's error
    with its interval, the minimum fixed before any model, and zero."""
    _, _, fin, fv = _rids(view, citer)
    crit = _mapping(fv.get('criterion'))
    if not fin or not all(_num(crit.get(k)) for k in ('gain', 'low', 'high', 'minimum')):
        return ''
    edges = [0.0, crit['gain'], crit['low'], crit['high'], crit['minimum']]
    lo, hi = min(edges), max(edges)
    pad = (hi - lo) * 0.08 or 0.05
    scale = rc.Scale(lo - pad, hi + pad, x1=rc.WIDTH - rc.RIGHT - 16)
    cy = rc.TOP + 16
    body = [scale.axis(rc.TOP - 6, cy + 18, percent=True),
            rc.lit('identifier', rh.capital(rh.model_short(str(fv.get('model')))),
                   rc.LEFT - 8, cy + 4, 'end')]
    x0, xm = scale(0), scale(crit['minimum'])
    body.append(f'<rect class="zone" x="{xm:.1f}" y="{rc.TOP - 6}" '
                f'width="{max(0.0, scale(hi + pad) - xm):.1f}" height="{cy + 24 - rc.TOP}"/>')
    body.append(f'<line class="zero" x1="{x0:.1f}" y1="{rc.TOP - 6}" x2="{x0:.1f}" '
                f'y2="{cy + 18}"/>')
    body.append(f'<line class="thr" x1="{xm:.1f}" y1="{rc.TOP - 10}" x2="{xm:.1f}" '
                f'y2="{cy + 18}"/>')
    body.append(citer.svg_num(fin, 'criterion.minimum', 'pct0', x=xm + 4, y=rc.TOP - 12,
                              cls='thr-t', prefix=say('minimum') + ' '))
    body.append(f'<line class="ci s-ok" x1="{scale(crit["low"]):.1f}" y1="{cy}" '
                f'x2="{scale(crit["high"]):.1f}" y2="{cy}"/>')
    body.append(f'<circle class="dot s-ok" cx="{scale(crit["gain"]):.1f}" cy="{cy}" r="6">'
                f'<title>{e(say("key_final"))}</title></circle>')
    body.append(citer.svg_num(fin, 'criterion.gain', 'pct1', x=rc.WIDTH - rc.RIGHT + 2,
                              y=cy + 4, prefix='● '))
    svg = rc._svg(cy + 18 + rc.AXIS, ''.join(body), say('criterion_label'))
    keys = [('dot', say('key_final')), ('ci', say('key_ci')), ('thr', say('minimum'))]
    return rc.figure('criterion_final', say('criterion_question'), svg, _keys(keys),
                     e(say('criterion_note')))


# --- R53: the method diagrams --------------------------------------------------------------------

def cv_rotation(citer, rid: str, values: Mapping) -> str:
    """Each fold predicted once by a model fitted on the other folds: one line per fold, its
    block marked as predicted, the others as fitting rows; the predicted block's rows cited."""
    folds = [(i, f) for i, f in enumerate(values.get('fold_rows') or [])
             if isinstance(f, Mapping) and _num(f.get('n_rows'))]
    if len(folds) < 2:
        return ''
    total = sum(f['n_rows'] for _, f in folds) or 1
    x0, x1 = 150.0, rc.WIDTH - 20.0
    body, y = [], rc.TOP
    for i, f in folds:
        x = x0
        body.append(f'<text x="{x0 - 8}" y="{y + 15}" text-anchor="end" class="note">'
                    f'{e(say("cv_row"))} <tspan data-literal="ordinal">{e(str(f.get("fold")))}'
                    f'</tspan></text>')
        for j, h in folds:
            w = (x1 - x0) * h['n_rows'] / total
            cls = 'cv-val' if j == i else 'cv-fit'
            body.append(f'<rect class="{cls}" x="{x + 1:.1f}" y="{y}" width="{max(1.0, w - 2):.1f}" '
                        f'height="20" rx="2"/>')
            if j == i:
                body.append(citer.svg_num(rid, f'fold_rows.{i}.n_rows', 'int', x=x + w / 2,
                                          y=y + 14, anchor='middle', cls='val cv-n'))
            x += w
        y += 26
    order = values.get('order_column')
    if order:
        body.append(f'<text x="{x0:.1f}" y="{y + 10}" class="note">{e(say("cv_older"))}</text>')
        body.append(f'<text x="{x1:.1f}" y="{y + 10}" text-anchor="end" class="note">'
                    f'{e(say("cv_newer"))}</text>')
        y += 14
    svg = rc._svg(y + 10, ''.join(body), say('cv_label'))
    note = e(say('cv_note_temporal' if values.get('method') == 'temporal_folds' else 'cv_note'))
    return rc.figure('cv_rotation', say('cv_question'), svg,
                     _keys([('cvv', say('cv-val')), ('cvf', say('cv-fit'))]), note)


def column_view(citer, rid: str, values: Mapping, transformed: list[str] | None = None) -> str:
    """R41/R45: the quality check column by column: missing cells, the range (minimum and
    maximum cited; the band from the first to the ninety-ninth percentile and the median
    drawn), and the skewness; a categorical column shows its distinct values. The columns the
    preparation transformed come first, marked."""
    transformed = list(transformed or [])
    missing = {m.get('column'): (i, m) for i, m in enumerate(values.get('missing') or [])
               if isinstance(m, Mapping)}
    ranges = [(i, r) for i, r in enumerate(values.get('ranges') or [])
              if isinstance(r, Mapping) and _num(r.get('min')) and _num(r.get('max'))]
    cats = [(i, r) for i, r in enumerate(values.get('cardinality') or [])
            if isinstance(r, Mapping) and _num(r.get('n_distinct'))]
    if not ranges and not cats:
        return ''
    ranges.sort(key=lambda x: (x[1].get('column') not in transformed, x[0]))
    shares = [m.get('share') for _, m in missing.values() if _num(m.get('share'))]
    top_share = max(shares) if shares and max(shares) > 0 else 1.0
    skews = [abs(r['skewness']) for _, r in ranges if _num(r.get('skewness'))]
    top_skew = max(skews) if skews and max(skews) > 0 else 1.0
    ROWH, NAME, MISS, SMIN, S0, S1, SKZ = 24, 8, 112, 244, 250, 410, 520
    body = [f'<text x="{NAME}" y="{rc.TOP - 10}" class="note">{e(say("cv_col"))}</text>',
            f'<text x="{MISS}" y="{rc.TOP - 10}" class="note">{e(say("cv_missing"))}</text>',
            f'<text x="{S0}" y="{rc.TOP - 10}" class="note">{e(say("cv_range"))}</text>',
            f'<text x="{SKZ - 40}" y="{rc.TOP - 10}" class="note">{e(say("cv_skew"))}</text>']
    y = rc.TOP

    def miss_cells(column: str) -> str:
        found = missing.get(column)
        if not found:
            return ''
        i, m = found
        w = 44 * (m['share'] / top_share) if _num(m.get('share')) else 0
        out = (f'<rect class="bar s-base" x="{MISS}" y="{y + 6}" width="{max(0.0, w):.1f}" '
               f'height="10" rx="2"/>') if w > 0 else ''
        return out + citer.svg_num(rid, f'missing.{i}.n_missing', 'int', x=MISS + 50, y=y + 15)

    for i, r in ranges:
        column = str(r.get('column'))
        if column in transformed:
            body.append(f'<rect class="chosen-band" x="2" y="{y}" width="{rc.WIDTH - 4}" '
                        f'height="{ROWH - 2}" rx="3"/>')
        body.append(f'<text x="{NAME}" y="{y + 15}" data-literal="identifier"'
                    f'{" class=" + chr(34) + "lbl-chosen" + chr(34) if column in transformed else ""}>'
                    f'{e(rc.short(column, 15))}</text>')
        body.append(miss_cells(column))
        lo, hi = r['min'], r['max']
        span = (hi - lo) or 1.0
        px = (lambda v: S0 + (v - lo) / span * (S1 - S0))
        body.append(citer.svg_num(rid, f'ranges.{i}.min', 'auto', x=SMIN, y=y + 15, anchor='end',
                                  cls='axis'))
        body.append(f'<line class="whisker" x1="{S0}" y1="{y + 11}" x2="{S1}" y2="{y + 11}"/>')
        q = _mapping(r.get('quantiles'))
        if _num(q.get('0.01')) and _num(q.get('0.99')):
            body.append(f'<rect class="box" x="{px(q["0.01"]):.1f}" y="{y + 5}" '
                        f'width="{max(1.0, px(q["0.99"]) - px(q["0.01"])):.1f}" height="12" '
                        f'rx="2"/>')
        if _num(q.get('0.5')):
            body.append(f'<line class="median" x1="{px(q["0.5"]):.1f}" y1="{y + 3}" '
                        f'x2="{px(q["0.5"]):.1f}" y2="{y + 19}"/>')
        body.append(citer.svg_num(rid, f'ranges.{i}.max', 'auto', x=S1 + 4, y=y + 15,
                                  cls='axis'))
        if _num(r.get('skewness')):
            w = 52 * r['skewness'] / top_skew
            x = SKZ if w >= 0 else SKZ + w
            body.append(f'<line class="zero" x1="{SKZ}" y1="{y + 2}" x2="{SKZ}" y2="{y + 20}"/>')
            body.append(f'<rect class="bar s-{"ebm" if column in transformed else "lin"}" '
                        f'x="{x:.1f}" y="{y + 6}" width="{abs(w):.1f}" height="10" rx="2"/>')
            body.append(citer.svg_num(rid, f'ranges.{i}.skewness', 'f2', x=SKZ + 56, y=y + 15))
        y += ROWH
    for i, r in cats:
        column = str(r.get('column'))
        body.append(f'<text x="{NAME}" y="{y + 15}" data-literal="identifier">'
                    f'{e(rc.short(column, 15))}</text>')
        body.append(miss_cells(column))
        body.append(citer.svg_num(rid, f'cardinality.{i}.n_distinct', 'int', x=S0, y=y + 15,
                                  suffix=' ' + say('distinct')))
        y += ROWH
    svg = rc._svg(y + 8, ''.join(body), say('cv_view_label'))
    keys = [('box', say('key_band')), ('ci', say('key_median'))]
    if transformed:
        keys.append(('hl', say('key_transformed')))
    return rc.figure('column_view', say('column_question'), svg, _keys(keys),
                     e(say('column_note')))


def pipeline(view: Mapping, citer, fit_slot: str, quality_rid: str | None) -> str:
    """R53/R41: the preparation as a pipeline, from what the fit recorded
    (``preprocessing.fitted``): column, indicators, rare categories, caps, signed log, then
    imputation and scaling, then the model, learnt on the fitting rows of each fold; and each
    numeric column's verdict with its cited skewness."""
    rid = citer.slot_rid(fit_slot)
    if rid is None:
        return ''
    fv = _mapping(citer.results[rid].values)
    pre = _mapping(fv.get('preprocessing'))
    fitted = _mapping(pre.get('fitted'))
    if not fitted:
        return ''
    features = [str(f) for f in fv.get('features') or []]

    def names(items) -> str:
        items = [str(x) for x in items or []]
        if not items:
            return f'<span class="none">{e(say("pipe_none"))}</span>'
        return ' '.join(rh.lit('identifier', x, 'code') for x in items)
    stages = [('pipe_columns', names(features)),
              ('pipe_indicators', names(fitted.get('missing_indicators'))),
              ('pipe_rare', names(list(_mapping(fitted.get('rare_categories'))))),
              ('pipe_caps', names(list(_mapping(fitted.get('caps'))))),
              ('pipe_log', names(fitted.get('log_transform'))),
              ('pipe_scale', e(say('pipe_scale_detail'))),
              ('pipe_model', e(rh.capital(rh.model_name(fit_slot))))]
    flow = ''.join(f'<li data-stage="{key}"><b>{e(say(key))}</b><span>{detail}</span></li>'
                   for key, detail in stages)
    out = f'<ol class="pipe">{flow}</ol><p class="cap">{e(say("pipe_note"))}</p>'
    if quality_rid:
        qv = _mapping(citer.results[quality_rid].values)
        logs = set(str(x) for x in fitted.get('log_transform') or [])
        caps = set(str(x) for x in _mapping(fitted.get('caps')))
        missing = {str(_mapping(m).get('column')): j
                   for j, m in enumerate(qv.get('missing') or [])}
        rows = []
        for i, r in enumerate(qv.get('ranges') or []):
            column = str(_mapping(r).get('column'))
            if column not in features:
                continue
            checks = _checks(citer, quality_rid, i, _mapping(r), missing.get(column))
            if not checks:
                continue
            verdict = ('verdict_log' if column in logs else 'verdict_cap' if column in caps
                       else 'verdict_none')
            sep = ' : ' if texts.report_language() == 'fr' else ': '
            rows.append((verdict == 'verdict_none',
                         f'<li class="{"changed" if verdict != "verdict_none" else ""}">'
                         f'{rh.lit("identifier", column, "code")}{sep}<b>{e(say(verdict))}</b>'
                         f' — {" ; ".join(checks)}</li>'))
        if rows:
            rows.sort(key=lambda x: x[0])
            out += (f'<p class="sub-k">{e(say("verdicts"))}</p><ul class="verdicts">'
                    + ''.join(r for _, r in rows) + f'</ul><p class="cap">'
                    f'{e(say("thresholds_note"))}</p>')
    return out


def _setting(value, kind: str = 'auto') -> str:
    """A threshold of the engine's preparation rules (``drafts``): a setting, not a result."""
    return rh.lit('setting', cite.format_value(value, kind, texts.report_language()))


def _checks(citer, rid: str, i: int, r: Mapping, j: int | None) -> list[str]:
    """R41: what each preparation rule measured on one column against its threshold, the
    measure cited from the quality check, the threshold the engine's (``drafts``): the
    skewness against the signed-log minimum, the maximum against a multiple of the 99th
    percentile, the share of missing cells against the indicator minimum."""
    from . import drafts
    out = []
    if _num(r.get('skewness')) and citer.has(rid, f'ranges.{i}.skewness'):
        out.append(t('check_skew', value=citer.num(rid, f'ranges.{i}.skewness', 'f2'),
                     op='≥' if r['skewness'] >= drafts.SKEW_LOG_MIN else '<',
                     threshold=_setting(drafts.SKEW_LOG_MIN)))
    q99 = _mapping(r.get('quantiles')).get('0.99')
    if _num(q99) and q99 > 0 and _num(r.get('max')) and citer.has(rid, f'ranges.{i}.max'):
        out.append(t('check_tail', value=citer.num(rid, f'ranges.{i}.max', 'auto'),
                     op='>' if r['max'] > drafts.EXTREME_TAIL_RATIO * q99 else '≤',
                     ratio=_setting(drafts.EXTREME_TAIL_RATIO),
                     q99=citer.num(rid, cite.format_path(['ranges', str(i), 'quantiles', '0.99']),
                                   'auto')))
    if j is not None and citer.has(rid, f'missing.{j}.share'):
        share = citer.value(rid, f'missing.{j}.share')
        out.append(t('check_missing', value=citer.num(rid, f'missing.{j}.share', 'pct1'),
                     op='≥' if share >= drafts.MISSING_MIN_SHARE else '<',
                     threshold=_setting(drafts.MISSING_MIN_SHARE, 'pct0')))
    return out


def one_se(citer, rid: str, sel: Mapping) -> str:
    """R53: the one-standard-error rule: each configuration's mean over the folds with one
    standard error each side, the band from the best mean to the best plus one standard error
    (the bound cited), the configuration picked inside it marked."""
    configs = [(i, x) for i, x in enumerate(sel.get('configurations') or [])
               if isinstance(x, Mapping) and _num(x.get('mean'))]
    one = _mapping(sel.get('one_se'))
    if len(configs) < 2 or not _num(one.get('bound')):
        return ''
    best, pick = one.get('best'), one.get('pick')
    by_slot = {str(x.get('slot')): x for _, x in configs}
    if best not in by_slot:
        return ''
    fmt = 'f3' if sel.get('metric') == 'roc_auc' else 'f2'
    edges = [one['bound']]
    for _, x in configs:
        se = x.get('se') if _num(x.get('se')) else 0
        edges += [x['mean'] - se, x['mean'] + se]
    lo, hi = min(edges), max(edges)
    pad = (hi - lo) * 0.08 or 0.05
    scale = rc.Scale(lo - pad, hi + pad, x1=rc.WIDTH - rc.RIGHT - 16)
    y_end = rc.TOP + 4 + 30 * len(configs)
    lower = sel.get('direction', 'lower') == 'lower'
    xa, xb = sorted((scale(by_slot[best]['mean']), scale(one['bound'])))
    body = [scale.axis(rc.TOP - 6, y_end),
            f'<rect class="se-band" x="{xa:.1f}" y="{rc.TOP - 6}" width="{xb - xa:.1f}" '
            f'height="{y_end - rc.TOP + 6}"><title>{e(say("se_band"))}</title></rect>',
            f'<line class="thr" x1="{scale(one["bound"]):.1f}" y1="{rc.TOP - 10}" '
            f'x2="{scale(one["bound"]):.1f}" y2="{y_end}"/>',
            citer.svg_num(rid, 'model_selection.one_se.bound', fmt,
                          x=scale(one['bound']) + (4 if lower else -4), y=rc.TOP - 12,
                          anchor='start' if lower else 'end', cls='thr-t',
                          prefix=say('se_bound') + ' ')]
    y = rc.TOP + 4
    for i, x in configs:
        slot, cy = str(x.get('slot')), y + 10
        series = rc._series(slot)
        cls = ' class="lbl-chosen"' if slot == pick else ''
        body.append(f'<text x="{rc.LEFT - 8}" y="{cy + 4}" text-anchor="end" '
                    f'data-literal="identifier"{cls}>{e(rh.capital(rh.model_short(slot)))}</text>')
        if _num(x.get('se')):
            body.append(f'<line class="ci s-{series}" x1="{scale(x["mean"] - x["se"]):.1f}" '
                        f'y1="{cy}" x2="{scale(x["mean"] + x["se"]):.1f}" y2="{cy}"/>')
        if slot == pick:
            body.append(f'<circle class="pick-ring" cx="{scale(x["mean"]):.1f}" cy="{cy}" r="9">'
                        f'<title>{e(say("se_pick"))}</title></circle>')
        body.append(f'<circle class="dot s-{series}" cx="{scale(x["mean"]):.1f}" cy="{cy}" '
                    f'r="5"/>')
        body.append(citer.svg_num(rid, f'model_selection.configurations.{i}.mean', fmt,
                                  x=rc.WIDTH - rc.RIGHT + 2, y=cy + 4))
        y += 30
    svg = rc._svg(y_end + rc.AXIS, ''.join(body), say('se_label'))
    keys = [('dot', say('se_mean')), ('ci', say('se_ci')), ('seb', say('se_band')),
            ('ring', say('se_pick'))]
    return rc.figure('one_se', say('se_question'), svg, _keys(keys), e(say('se_note')))


EXPOSURE_LANES = ('structural', 'look', 'model', 'final')


def exposure_timeline(view: Mapping, slot_title) -> str:
    """R53: the exposure ledger as a timeline: each recorded result at the revision it started,
    on the lane of what it read (structure only, a look at the target, the models' fits and
    comparisons on the development rows, the final test), the opening of the final test drawn.
    Revisions are recorded literals of the study state."""
    looks = set((view.get('eda_looks') or {}).get('results') or [])
    events = []
    for slot, item in (view.get('results') or {}).items():
        rev = (item or {}).get('started_revision')
        if not isinstance(rev, int):
            continue
        if slot.startswith('final_test.'):
            lane = 'final'
        elif item.get('result_id') in looks:
            lane = 'look'
        elif slot.startswith(('fit.', 'evaluate.', 'diag.', 'policy.', 'predictor.')):
            lane = 'model'
        else:
            lane = 'structural'
        events.append((rev, lane, slot))
    if not events:
        return ''
    last = view.get('revision') if isinstance(view.get('revision'), int) else max(
        r for r, _, _ in events)
    scale = rc.Scale(1, max(2, last), x0=185, x1=rc.WIDTH - 24)
    lang = texts.report_language()
    body, y = [], rc.TOP
    lane_y = {}
    for lane in EXPOSURE_LANES:
        lane_y[lane] = y + 10
        body.append(f'<text x="177" y="{y + 14}" text-anchor="end" class="note">'
                    f'{e(say("lane_" + lane))}</text>')
        body.append(f'<line class="grid" x1="185" y1="{y + 10}" x2="{rc.WIDTH - 24}" '
                    f'y2="{y + 10}"/>')
        y += 26
    opening = ((view.get('final_test') or {}).get('opening') or {}).get('revision')
    if isinstance(opening, int):
        xo = scale(opening)
        body.append(f'<line class="thr" x1="{xo:.1f}" y1="{rc.TOP - 6}" x2="{xo:.1f}" '
                    f'y2="{y}"/>')
        body.append(f'<text x="{xo - 4:.1f}" y="{rc.TOP - 10}" text-anchor="end" '
                    f'class="thr-t">{e(say("opened_at"))}</text>')
    for rev, lane, slot in sorted(events):
        body.append(f'<circle class="ev-{lane}" cx="{scale(rev):.1f}" cy="{lane_y[lane]}" r="5">'
                    f'<title>{e(slot_title(slot))}</title></circle>')
    for tick in rc._ticks(1, max(2, last), 5):
        if abs(tick - round(tick)) > 1e-9:
            continue
        body.append(rc.lit('axis', cite.format_value(tick, 'int', lang), scale(tick), y + 14,
                           'middle', 'axis'))
    body.append(f'<text x="{rc.WIDTH - 24}" y="{y + 30}" text-anchor="end" class="note">'
                f'{e(say("revisions"))}</text>')
    svg = rc._svg(y + 38, ''.join(body), say('exposure_label'))
    keys = [(f'ev-{lane}', say('lane_' + lane)) for lane in EXPOSURE_LANES]
    return rc.figure('exposure_timeline', say('exposure_question'), svg, _keys(keys),
                     e(say('exposure_note')))


CSS = '''
table.evtab th[scope=row]{font-weight:600;text-align:left;text-transform:none;letter-spacing:0;font-size:13px}
table.evtab td{font-variant-numeric:tabular-nums}
table.evtab th.h-dev:before{content:"◐ ";color:var(--pen)}
table.evtab th.h-fin:before{content:"● ";color:var(--s-ok)}
table.evtab tr.chosen{background:var(--hl)}
table.evtab tr.chosen th,table.evtab tr.chosen td{border-top:2px solid var(--cardink);border-bottom:2px solid var(--cardink)}
table.evtab tr.sep th,table.evtab tr.sep td{border-top:2px solid var(--cardline);background:var(--cardsoft)}
table.evtab .chosen-mark{display:inline-block;font:700 10.5px var(--sans);letter-spacing:.05em;text-transform:uppercase;border:1.5px solid var(--cardink);border-radius:9px;padding:0 6px;margin-left:4px}
table.evtab .unmeasured{color:var(--cardmuted);font-style:italic}
table.evtab b.st-met{color:var(--s-ok)}table.evtab b.st-not_met,table.evtab b.st-uncertain{color:var(--red)}
svg.chart rect.chosen-band{fill:var(--hl);opacity:.55}
svg.chart text.lbl-chosen{font-weight:700}
svg.chart rect.cv-val{fill:var(--s-ok);opacity:.8}
svg.chart rect.cv-fit{fill:rgba(30,78,158,.16);stroke:var(--s-lin);stroke-width:1}
svg.chart text.cv-n{fill:#fff;stroke:none}
svg.chart rect.se-band{fill:var(--s-ok);opacity:.12}
svg.chart circle.pick-ring{fill:none;stroke:var(--cardink);stroke-width:2}
svg.chart circle.ev-structural{fill:var(--cardmuted)}
svg.chart circle.ev-look{fill:var(--ochre)}
svg.chart circle.ev-model{fill:var(--pen)}
svg.chart circle.ev-final{fill:var(--s-ok)}
svg.chart .s-ok{--sc:var(--s-ok)}
.keys i.sw.cvv{background:var(--s-ok)}.keys i.sw.cvf{background:rgba(30,78,158,.16);border:1px solid var(--s-lin)}
.keys i.sw.seb{background:var(--s-ok);opacity:.3;height:10px}
.keys i.sw.ring{width:10px;height:10px;border-radius:50%;background:none;border:2px solid var(--cardink)}
.keys i.sw.box{height:10px;background:rgba(30,78,158,.16);border:1px solid var(--s-lin)}
.keys i.sw.hl{height:10px;background:var(--hl)}
.keys i.sw.ev-structural{width:9px;height:9px;border-radius:50%;background:var(--cardmuted)}
.keys i.sw.ev-look{width:9px;height:9px;border-radius:50%;background:var(--ochre)}
.keys i.sw.ev-model{width:9px;height:9px;border-radius:50%;background:var(--pen)}
.keys i.sw.ev-final{width:9px;height:9px;border-radius:50%;background:var(--s-ok)}
ol.pipe{list-style:none;display:flex;flex-wrap:wrap;gap:8px 22px;padding:0;margin:8px 0;counter-reset:pipe}
ol.pipe li{position:relative;flex:1 1 150px;max-width:220px;background:var(--card);border:1.5px solid var(--cardline);border-radius:6px;padding:6px 9px;font-size:13px;color:var(--cardink)}
ol.pipe li b{display:block;font:600 11px var(--sans);letter-spacing:.05em;text-transform:uppercase;color:var(--cardmuted)}
ol.pipe li:not(:last-child):after{content:"→";position:absolute;right:-17px;top:50%;transform:translateY(-50%);color:var(--cardmuted);font-weight:700}
ol.pipe li .none{color:var(--cardmuted);font-style:italic}
ol.pipe li[data-stage=pipe_log],ol.pipe li[data-stage=pipe_caps],ol.pipe li[data-stage=pipe_rare],ol.pipe li[data-stage=pipe_indicators]{border-color:var(--s-ebm)}
ul.verdicts{margin:4px 0;padding-left:20px;font-size:13.5px}
ul.verdicts li.changed{font-weight:600}
p.sub-k{font:600 11px var(--sans);letter-spacing:.06em;text-transform:uppercase;color:var(--cardmuted);margin:10px 0 2px}
.concl-part{margin:18px 0 6px;font:600 13px var(--sans);letter-spacing:.06em;text-transform:uppercase;color:var(--yellow)}
.nochart{background:var(--card);color:var(--cardink);border:1.5px dashed var(--cardmuted);border-radius:6px;padding:8px 12px;margin:10px 0;font-size:13.5px}
.nochart ul{margin:4px 0;padding-left:20px}
'''
