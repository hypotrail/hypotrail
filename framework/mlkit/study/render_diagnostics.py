"""The "Model diagnostics" section of the HTML report (v0.2b, WP-B4, remark R9).

Fed by the view only, like the rest of the report (:mod:`mlkit.study.render_html`): every
number is a cited registry value (:class:`mlkit.study.cite.Citer`), every chart is an inline
SVG whose value labels are cited and whose ticks are ``axis`` literals
(:mod:`mlkit.study.render_charts`). The section has two parts, clearly labelled:

* **Development evidence** (``diag.binary`` or ``diag.regression``): computed on the
  predictions of the development rows on which the model and the rule were chosen; after
  the final test is opened it stays, labelled as computed before or after the opening;
* **Final evidence** (``diag.final_test``): only once the final test is opened; while it is
  sealed the part says so and shows nothing else.

Binary: a table of the models side by side, then for the model shown (the chosen or
proposed one, else the candidate) the confusion matrix at the rule, the gain curve, the
calibration plot and its bins, precision and recall by segment, the coefficients with their
bootstrap intervals, and example errors. Regression: the models side by side, then the
residuals against the prediction, the predicted against the observed values, the
quantile-quantile plot, the residual distribution, the heteroscedasticity indicator,
residuals by variable, the coefficients, and the largest errors.

Pure: no pandas, numpy, or scikit-learn.
"""
from __future__ import annotations

import html
import re
from typing import Any, Mapping

from . import audience, cite, render_charts, texts
from .render_charts import legend, lit as svg_lit, figure

e = html.escape

DEVELOPMENT_SLOTS = {'binary': 'diag.binary', 'regression': 'diag.regression'}
FINAL_SLOT = 'diag.final_test'
MAX_COEFFICIENTS = 12
W, H = 640, 320
L, R, T, B = 64, 24, 20, 46

CSS = '''
.diagnostics h3 .badge{vertical-align:2px}
.diagnostics table.confusion td,.diagnostics table.confusion th{text-align:center}
.diagnostics table.confusion th[scope=row]{text-align:left}
svg.chart polyline.m{fill:none;stroke:var(--accent);stroke-width:2.5}
svg.chart polyline.m.final{stroke:var(--amber)}
svg.chart polyline.b{fill:none;stroke:var(--muted);stroke-width:2;stroke-dasharray:5 4}
svg.chart line.diag{stroke:var(--muted);stroke-width:1.5;stroke-dasharray:4 3}
svg.chart circle.pt{fill:var(--accent);opacity:.45}
svg.chart circle.pt.final{fill:var(--amber);opacity:.55}
svg.chart circle.bin{fill:var(--paper);stroke:var(--ink);stroke-width:2}
.examples td{font-size:12px}
.examples td:first-child{white-space:nowrap}
details.diag-more{margin:14px 0}
'''


def _labels() -> dict:
    return texts.report()['diagnostics']


def _model_name(model: str) -> str:
    from .render_html import MODEL_NAMES_EXTRA      # v0.3 (WP-F1)
    names = texts.report().get('model_names') or {}
    return names.get(model, MODEL_NAMES_EXTRA.get(model, model))


def _concept(term_id: str) -> str:
    entry = texts.glossary(term_id)
    if not entry:
        return ''
    return f'<p><strong class="term">{e(entry["term"])}.</strong> {e(entry["definition"])}</p>'


def _lit(kind: str, text: Any, tag: str = 'span') -> str:
    return f'<{tag} data-literal="{kind}">{e(str(text))}</{tag}>'


def _num(citer: cite.Citer, rid: str, path: list, fmt: str = 'auto') -> str:
    p = cite.format_path(path)
    return citer.num(rid, p, fmt) if citer.has(rid, p) else ''


def _interval(citer: cite.Citer, rid: str, low: list, high: list, fmt: str) -> str:
    lo, hi = cite.format_path(low), cite.format_path(high)
    if citer.has(rid, lo) and citer.has(rid, hi):
        return f' <span class="small">[{citer.num(rid, lo, fmt)}, {citer.num(rid, hi, fmt)}]</span>'
    return ''


def _badge(kind: str, label: str) -> str:
    return f'<span class="badge {e(kind)}">{e(label)}</span>'


def _table(head: list[str], rows: list[str], cls: str = '') -> str:
    th = ''.join(f'<th>{e(h)}</th>' for h in head)
    klass = f' class="{cls}"' if cls else ''
    return (f'<div class="scroll"><table{klass}><thead><tr>{th}</tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>')


# --- a two-axis chart -----------------------------------------------------------------------

class Plane:
    """Linear x and y scales of one chart, with gridlines and ``axis`` tick literals."""

    def __init__(self, x: tuple[float, float], y: tuple[float, float]):
        self.x0, self.x1 = x
        self.y0, self.y1 = y

    def px(self, v: float) -> float:
        span = (self.x1 - self.x0) or 1.0
        return L + (v - self.x0) / span * (W - L - R)

    def py(self, v: float) -> float:
        span = (self.y1 - self.y0) or 1.0
        return H - B - (v - self.y0) / span * (H - T - B)

    def axes(self, x_percent: bool = False, y_percent: bool = False) -> str:
        out = []
        for t in render_charts._ticks(self.x0, self.x1):
            x = self.px(t)
            out.append(f'<line class="grid" x1="{x:.1f}" y1="{T}" x2="{x:.1f}" y2="{H - B}"/>')
            out.append(svg_lit('axis', render_charts._tick_text(t, x_percent), x, H - B + 16,
                               'middle', 'axis'))
        for t in render_charts._ticks(self.y0, self.y1):
            y = self.py(t)
            out.append(f'<line class="grid" x1="{L}" y1="{y:.1f}" x2="{W - R}" y2="{y:.1f}"/>')
            out.append(svg_lit('axis', render_charts._tick_text(t, y_percent), L - 6, y + 4,
                               'end', 'axis'))
        return ''.join(out)

    def titles(self, x_title: str, y_title: str) -> str:
        return (f'<text x="{(L + W - R) / 2:.1f}" y="{H - 8}" text-anchor="middle" '
                f'class="note">{e(x_title)}</text>'
                f'<text x="14" y="{(T + H - B) / 2:.1f}" text-anchor="middle" class="note" '
                f'transform="rotate(-90 14 {(T + H - B) / 2:.1f})">{e(y_title)}</text>')

    def diagonal(self) -> str:
        lo = max(self.x0, self.y0)
        hi = min(self.x1, self.y1)
        return (f'<line class="diag" x1="{self.px(lo):.1f}" y1="{self.py(lo):.1f}" '
                f'x2="{self.px(hi):.1f}" y2="{self.py(hi):.1f}"/>')

    def zero(self) -> str:
        if not (self.y0 <= 0 <= self.y1):
            return ''
        return (f'<line class="zero" x1="{L}" y1="{self.py(0):.1f}" x2="{W - R}" '
                f'y2="{self.py(0):.1f}"/>')


def _svg(body: str, label: str) -> str:
    return (f'<svg class="chart" viewBox="0 0 {W} {H}" role="img" aria-label="{e(label)}">'
            f'{body}</svg>')


def _range(values, pad: float = 0.06) -> tuple[float, float]:
    vals = [float(v) for v in values if cite.is_number(v)]
    if not vals:
        return 0.0, 1.0
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or abs(hi) or 1.0
    return lo - pad * span, hi + pad * span


# --- binary ---------------------------------------------------------------------------------

def gain_chart(citer: cite.Citer, rid: str, base: list, curve: Mapping, rule_share,
               final: bool) -> str:
    points = [p for p in curve.get('points') or [] if cite.is_number(p.get('recall'))]
    if not points:
        return ''
    plane = Plane((0.0, 1.0), (0.0, 1.0))
    line = ' '.join([f'{plane.px(0):.1f},{plane.py(0):.1f}'] +
                    [f'{plane.px(p["share"]):.1f},{plane.py(p["recall"]):.1f}' for p in points])
    body = [plane.axes(True, True), plane.diagonal(),
            f'<polyline class="{"m final" if final else "m"}" points="{line}">'
            f'<title>Model</title></polyline>']
    for i, p in enumerate(points):
        if p['share'] in (0.1, 0.2, 0.5):
            x, y = plane.px(p['share']), plane.py(p['recall'])
            body.append(f'<circle class="m" cx="{x:.1f}" cy="{y:.1f}" r="4"/>')
            body.append(citer.svg_num(rid, cite.format_path(base + ['curve', 'points', str(i),
                                                                     'recall']),
                                      'pct0', x=x + 6, y=y + 14, suffix=' found'))
    if cite.is_number(rule_share) and 0 < rule_share <= 1:
        x = plane.px(rule_share)
        body.append(f'<line class="ref" x1="{x:.1f}" y1="{T}" x2="{x:.1f}" y2="{H - B}"/>')
        body.append(f'<text x="{x + 4:.1f}" y="{T + 12}" class="note">the rule</text>')
    body.append(plane.titles('Share of the rows acted on, best scores first',
                             'Share of the positive rows found'))
    svg = _svg(''.join(body), 'Gain curve')
    note = (f'Diagonal: acting at random. AUC {_num(citer, rid, base + ["roc_auc"], "f3")}, '
            f'average precision {_num(citer, rid, base + ["average_precision"], "f3")}.')
    return figure('diag_gain', 'If the team acts on the best-scored rows first, what share of '
                  'all positive rows does it find?', svg,
                  # B6c (Low): each swatch looks like its mark (a line, a dashed diagonal).
                  legend(('line final' if final else 'line', 'Model'),
                         ('diag', 'Acting at random')), note)


def calibration_chart(citer: cite.Citer, rid: str, base: list, cal: Mapping) -> str:
    bins = [b for b in cal.get('bins') or [] if cite.is_number(b.get('mean_predicted'))
            and cite.is_number(b.get('observed_rate'))]
    if not bins:
        return ''
    top = max([b['mean_predicted'] for b in bins] + [b.get('high') or 0 for b in bins])
    hi = min(1.0, render_charts._nice_max(top * 1.05))
    plane = Plane((0.0, hi), (0.0, hi))
    body = [plane.axes(True, True), plane.diagonal()]
    for b in bins:
        x = plane.px(b['mean_predicted'])
        if cite.is_number(b.get('low')) and cite.is_number(b.get('high')):
            body.append(f'<line class="ci" x1="{x:.1f}" y1="{plane.py(b["low"]):.1f}" '
                        f'x2="{x:.1f}" y2="{plane.py(min(b["high"], hi)):.1f}"/>')
        body.append(f'<circle class="bin" cx="{x:.1f}" cy="{plane.py(b["observed_rate"]):.1f}" '
                    f'r="4.5"><title>Bin</title></circle>')
    body.append(plane.titles('Mean score of the bin', 'Observed positive rate of the bin'))
    svg = _svg(''.join(body), 'Calibration')
    note = (f'One circle per bin of rows with similar scores, with the interval of its observed '
            f'rate. Diagonal: a score that reads as a probability. Brier score '
            f'{_num(citer, rid, base + ["calibration", "brier"], "f4")}, against '
            f'{_num(citer, rid, base + ["calibration", "brier_base_rate"], "f4")} for the '
            f'constant base rate (lower is better).')
    return figure('diag_calibration', 'When the model gives rows a score, do about that share '
                  'of them turn out positive?', svg, legend(('bin', 'Bin and its interval')),
                  note)


def _confusion(citer: cite.Citer, rid: str, base: list, conf: Mapping) -> str:
    lab = _labels()
    p = base + ['confusion']
    rows = [f'<tr><th scope="row">{e(lab["confusion_positive"])}</th>'
            f'<td>{_num(citer, rid, p + ["true_positives"])}</td>'
            f'<td>{_num(citer, rid, p + ["false_negatives"])}</td></tr>',
            f'<tr><th scope="row">{e(lab["confusion_negative"])}</th>'
            f'<td>{_num(citer, rid, p + ["false_positives"])}</td>'
            f'<td>{_num(citer, rid, p + ["true_negatives"])}</td></tr>']
    table = _table([lab['confusion_rows'], lab['confusion_selected'],
                    lab['confusion_not_selected']], rows, 'confusion')
    figures = (f'<p>Precision {_num(citer, rid, p + ["precision"], "pct1")}, recall '
               f'{_num(citer, rid, p + ["recall"], "pct1")}, specificity '
               f'{_num(citer, rid, p + ["specificity"], "pct1")}, on '
               f'{_num(citer, rid, p + ["n"], "int")} rows.</p>')
    expected = (f'<p class="small">{e(lab["confusion_expected"])}</p>'
                if conf.get('selection') == 'expected' else '')
    return (f'<h4>{e(lab["confusion_heading"])}</h4>{_concept("confusion_matrix")}{table}'
            f'{figures}{expected}')


def _calibration_table(citer: cite.Citer, rid: str, base: list, cal: Mapping) -> str:
    lab = _labels()
    rows = []
    for i, b in enumerate(cal.get('bins') or []):
        p = base + ['calibration', 'bins', str(i)]
        flag = 'no' if b.get('inside_interval') else 'yes'
        rows.append(f'<tr><td>{_num(citer, rid, p + ["bin"], "int")}</td>'
                    f'<td>{_num(citer, rid, p + ["n"], "int")}</td>'
                    f'<td>{_num(citer, rid, p + ["mean_predicted"], "pct1")}</td>'
                    f'<td>{_num(citer, rid, p + ["observed_rate"], "pct1")}'
                    f'{_interval(citer, rid, p + ["low"], p + ["high"], "pct1")}</td>'
                    f'<td>{_lit("category", flag)}</td></tr>')
    return (f'<details><summary>{e(lab["calibration_table"])}</summary>'
            + _table(['Bin', 'Rows', 'Mean score', 'Observed rate [interval]',
                      'Score outside the interval'], rows) + '</details>')


def _segments(citer: cite.Citer, rid: str, base: list, segs: list) -> str:
    lab = _labels()
    out = []
    for i, seg in enumerate(segs):
        rows = []
        for j, g in enumerate(seg.get('groups') or []):
            p = base + ['segments', str(i), 'groups', str(j)]
            small = 'yes' if g.get('small_cell') else 'no'
            rows.append(
                f'<tr data-segment="{e(str(g.get("value")))}">'
                f'<td>{_lit("category", g.get("value", ""))}</td>'
                f'<td>{_num(citer, rid, p + ["n"], "int")}</td>'
                f'<td>{_num(citer, rid, p + ["n_positive"], "int")}</td>'
                f'<td>{_num(citer, rid, p + ["selected"], "auto")}</td>'
                f'<td>{_num(citer, rid, p + ["precision"], "pct1")}'
                f'{_interval(citer, rid, p + ["precision_low"], p + ["precision_high"], "pct1")}</td>'
                f'<td>{_num(citer, rid, p + ["recall"], "pct1")}'
                f'{_interval(citer, rid, p + ["recall_low"], p + ["recall_high"], "pct1")}</td>'
                f'<td>{_lit("category", small)}</td></tr>')
        out.append(f'<h5>{_lit("identifier", seg.get("column", ""), "code")}</h5>'
                   + _table(['Value', 'Rows', 'Positive rows', 'Selected', 'Precision [interval]',
                             'Recall [interval]', 'Too few rows to read alone'], rows,
                            'segments'))
    if not out:
        return ''
    return (f'<h4>{e(lab["segments_heading"])}</h4><p class="small">{e(lab["segments_note"])}'
            f'</p>{"".join(out)}')


def _coefficients(citer: cite.Citer, rid: str, base: list, coef: Mapping) -> str:
    if not isinstance(coef, Mapping) or not coef.get('terms'):
        return ''
    lab = _labels()
    rows = []
    for i, t in enumerate(coef['terms'][:MAX_COEFFICIENTS]):
        p = base + ['coefficients', 'terms', str(i)]
        excl = 'yes' if t.get('excludes_zero') else 'no'
        rows.append(f'<tr><td>{_lit("identifier", t.get("term", ""), "code")}</td>'
                    f'<td>{_num(citer, rid, p + ["value"], "f3")}'
                    f'{_interval(citer, rid, p + ["low"], p + ["high"], "f3")}</td>'
                    f'<td>{_lit("category", excl)}</td></tr>')
    meta = (f'<p class="small">{e(lab["coefficients_note"])} Scale: '
            f'{_lit("message", coef.get("scale") or "")}. '
            f'{_num(citer, rid, base + ["coefficients", "replicates"], "int")} bootstrap refits on '
            f'{_num(citer, rid, base + ["coefficients", "n_rows"], "int")} rows, '
            f'{_num(citer, rid, base + ["coefficients", "level"], "pct0")} percentile '
            f'intervals.</p>')
    check = coef.get('point_check')
    if isinstance(check, Mapping) and check.get('consistent') is False:
        # WP-B6a: the stored coefficients are not the refit the intervals describe.
        meta += f'<p class="small warn">{_lit("message", check.get("note") or "")}</p>'
    return (f'<details class="diag-more"><summary><strong>{e(lab["coefficients_heading"])}'
            f'</strong></summary>{meta}'
            + _table(['Term', 'Coefficient [interval]', 'Interval excludes zero'], rows)
            + '</details>')


def _example_rows(citer: cite.Citer, rid: str, path: list, items: list, features: list,
                  numbers: list[tuple[str, str]]) -> str:
    if not items:
        return f'<p class="muted">{e(_labels()["examples_none"])}</p>'
    rows = []
    for i, item in enumerate(items):
        p = path + [str(i)]
        cells = [f'<td>{_lit("identifier", item.get("row_key", ""), "code")}</td>']
        cells += [f'<td>{_num(citer, rid, p + [key], fmt)}</td>' for key, fmt in numbers]
        values = item.get('values') or {}
        cells += [f'<td>{_lit("data_row", "" if values.get(f) is None else values.get(f))}</td>'
                  for f in features]
        rows.append(f'<tr>{"".join(cells)}</tr>')
    head = ['Row'] + [_NUMBER_LABELS[k] for k, _ in numbers] + list(features)
    return _table(head, rows, 'examples')


_NUMBER_LABELS = {'score': 'Score', 'observed': 'Observed', 'prediction': 'Predicted',
                  'residual': 'Residual'}


def _examples(citer: cite.Citer, rid: str, base: list, ex: Mapping) -> str:
    lab = _labels()
    features = list(ex.get('features') or [])
    p = base + ['examples']
    return (f'<h4>{e(lab["examples_heading"])}</h4>{_concept("example_errors")}'
            f'<p class="small">{e(ex.get("note") or "")}</p>'
            f'<h5>{e(lab["false_positives"])}</h5>'
            + _example_rows(citer, rid, p + ['false_positives'], ex.get('false_positives') or [],
                            features, [('score', 'f3')])
            + f'<h5>{e(lab["false_negatives"])}</h5>'
            + _example_rows(citer, rid, p + ['false_negatives'], ex.get('false_negatives') or [],
                            features, [('score', 'f3')]))


def _binary_models_table(citer: cite.Citer, rid: str, models: Mapping) -> str:
    rows = []
    for m, d in models.items():
        p = ['models', m]
        rows.append(f'<tr data-model="{e(m)}"><td>{e(_model_name(m))}</td>'
                    f'<td>{_num(citer, rid, p + ["roc_auc"], "f3")}</td>'
                    f'<td>{_num(citer, rid, p + ["average_precision"], "f3")}</td>'
                    f'<td>{_num(citer, rid, p + ["calibration", "brier"], "f4")}</td>'
                    f'<td>{_num(citer, rid, p + ["confusion", "precision"], "pct1")}</td>'
                    f'<td>{_num(citer, rid, p + ["confusion", "recall"], "pct1")}</td></tr>')
    return (f'<h4>{e(_labels()["models_heading"])}</h4>'
            + _table(['Model', 'AUC', 'Average precision', 'Brier score',
                      'Precision at the rule', 'Recall at the rule'], rows))


def _binary_body(citer: cite.Citer, rid: str, values: Mapping, model: str,
                 final: bool) -> str:
    from .render_html import rule_words
    lab = _labels()
    d = (values.get('models') or {}).get(model) or {}
    base = ['models', model]
    rule = values.get('rule')
    source = values.get('rule_source')
    source_text = lab['rule_source'].get(source, '') if source else ''
    conf = d.get('confusion') or {}
    n = conf.get('n')
    share = (conf.get('selected') / n) if cite.is_number(conf.get('selected')) and n else None
    parts = [f'<p><strong>{e(lab["rule"])}:</strong> '
             f'{_lit("decision_value", rule_words(rule))}'
             f'{" (" + e(source_text) + ")" if source_text else ""}. '
             f'<strong>{e(lab["model"])}:</strong> {e(_model_name(model))}.</p>']
    if len(values.get('models') or {}) > 1:
        parts.append(_binary_models_table(citer, rid, values['models']))
    parts.append(_confusion(citer, rid, base, conf))
    parts.append(f'<h4>{e(lab["gain_heading"])}</h4>{_concept("gain_curve")}'
                 f'{_concept("roc_curve")}')
    parts.append(gain_chart(citer, rid, base, d.get('curve') or {}, share, final))
    parts.append(f'<h4>{e(lab["calibration_heading"])}</h4>{_concept("calibration")}'
                 f'{_concept("brier_score")}')
    parts.append(calibration_chart(citer, rid, base, d.get('calibration') or {}))
    parts.append(_calibration_table(citer, rid, base, d.get('calibration') or {}))
    parts.append(_segments(citer, rid, base, d.get('segments') or []))
    if not final:
        parts.append(_coefficients(citer, rid, base, d.get('coefficients') or {}))
    parts.append(_examples(citer, rid, base, d.get('examples') or {}))
    return ''.join(p for p in parts if p)


# --- regression -----------------------------------------------------------------------------

def residual_chart(citer: cite.Citer, rid: str, base: list, d: Mapping, final: bool) -> str:
    pts = [p for p in (d.get('scatter') or {}).get('points') or []
           if cite.is_number(p.get('prediction')) and cite.is_number(p.get('residual'))]
    if not pts:
        return ''
    bins = [b for b in (d.get('by_prediction') or {}).get('bins') or []
            if cite.is_number(b.get('mean_prediction')) and cite.is_number(b.get('mean_residual'))]
    plane = Plane(_range([p['prediction'] for p in pts]),
                  _range([p['residual'] for p in pts] + [0.0]))
    cls = 'pt final' if final else 'pt'
    body = [plane.axes(), plane.zero()]
    body += [f'<circle class="{cls}" cx="{plane.px(p["prediction"]):.1f}" '
             f'cy="{plane.py(p["residual"]):.1f}" r="3"/>' for p in pts]
    if bins:
        line = ' '.join(f'{plane.px(b["mean_prediction"]):.1f},{plane.py(b["mean_residual"]):.1f}'
                        for b in bins)
        body.append(f'<polyline class="m" points="{line}"><title>Mean residual by bin'
                    f'</title></polyline>')
    body.append(plane.titles('Predicted value', 'Residual (observed minus predicted)'))
    svg = _svg(''.join(body), 'Residuals against the prediction')
    h = base + ['heteroscedasticity']
    note = (f'Points: rows ({_num(citer, rid, base + ["scatter", "n_shown"], "int")} shown of '
            f'{_num(citer, rid, base + ["scatter", "n_rows"], "int")}); line: the mean residual '
            f'of each bin of predictions. Rank correlation of the size of the residual with the '
            f'prediction: {_num(citer, rid, h + ["abs_residual_prediction_correlation"], "f2")}.')
    return figure('diag_residuals', 'Are the errors centred on zero across the range of the '
                  'predictions, and do they widen?', svg,
                  legend(('pt final' if final else 'pt', 'One row'),
                         ('line', 'Mean residual by bin of predictions')), note)


def observed_chart(citer: cite.Citer, rid: str, base: list, d: Mapping, final: bool) -> str:
    pts = [p for p in (d.get('scatter') or {}).get('points') or []
           if cite.is_number(p.get('prediction')) and cite.is_number(p.get('observed'))]
    if not pts:
        return ''
    lo, hi = _range([p['prediction'] for p in pts] + [p['observed'] for p in pts])
    plane = Plane((lo, hi), (lo, hi))
    cls = 'pt final' if final else 'pt'
    body = [plane.axes(), plane.diagonal()]
    body += [f'<circle class="{cls}" cx="{plane.px(p["prediction"]):.1f}" '
             f'cy="{plane.py(p["observed"]):.1f}" r="3"/>' for p in pts]
    body.append(plane.titles('Predicted value', 'Observed value'))
    svg = _svg(''.join(body), 'Predicted against observed values')
    note = (f'Diagonal: a perfect prediction. Mean absolute error '
            f'{_num(citer, rid, base + ["errors", "mae"], "f2")}.')
    return figure('diag_observed', 'How close are the predictions to the observed values?',
                  svg, '', note)


def qq_chart(citer: cite.Citer, rid: str, base: list, d: Mapping) -> str:
    pts = [p for p in (d.get('qq') or {}).get('points') or []
           if cite.is_number(p.get('theoretical')) and cite.is_number(p.get('sample'))]
    if not pts:
        return ''
    lo, hi = _range([p['theoretical'] for p in pts] + [p['sample'] for p in pts])
    plane = Plane((lo, hi), (lo, hi))
    body = [plane.axes(), plane.diagonal()]
    body += [f'<circle class="bin" cx="{plane.px(p["theoretical"]):.1f}" '
             f'cy="{plane.py(p["sample"]):.1f}" r="4"/>' for p in pts]
    body.append(plane.titles('Quantile of a normal distribution',
                             'Quantile of the standardised residuals'))
    svg = _svg(''.join(body), 'Quantile-quantile plot of the residuals')
    r = base + ['residuals']
    note = (f'Skewness {_num(citer, rid, r + ["skewness"], "f2")}, excess kurtosis '
            f'{_num(citer, rid, r + ["excess_kurtosis"], "f2")} (both near zero for normal '
            f'residuals).')
    return figure('diag_qq', 'Do the residuals look normal, as prediction intervals would '
                  'assume?', svg, '', note)


def _regression_models_table(citer: cite.Citer, rid: str, models: Mapping) -> str:
    rows = []
    for m in models:
        p = ['models', m]
        rows.append(f'<tr data-model="{e(m)}"><td>{e(_model_name(m))}</td>'
                    f'<td>{_num(citer, rid, p + ["errors", "mae"], "f2")}</td>'
                    f'<td>{_num(citer, rid, p + ["errors", "rmse"], "f2")}</td>'
                    f'<td>{_num(citer, rid, p + ["residuals", "mean"], "f2")}</td>'
                    f'<td>{_num(citer, rid, p + ["residuals", "sd"], "f2")}</td>'
                    f'<td>{_num(citer, rid, p + ["heteroscedasticity", "abs_residual_prediction_correlation"], "f2")}</td></tr>')
    return (f'<h4>{e(_labels()["models_heading"])}</h4>'
            + _table(['Model', 'MAE', 'RMSE', 'Mean residual', 'Residual standard deviation',
                      'Rank correlation of the error size with the prediction'], rows))


SUMMARY_KEYS = (('mean', 'Mean (bias)'), ('sd', 'Standard deviation'), ('q05', '5th percentile'),
                ('median', 'Median'), ('q95', '95th percentile'), ('skewness', 'Skewness'),
                ('excess_kurtosis', 'Excess kurtosis'))


def _residual_summary(citer: cite.Citer, rid: str, base: list) -> str:
    cells = ''.join(f'<td>{_num(citer, rid, base + ["residuals", k], "f2")}</td>'
                    for k, _ in SUMMARY_KEYS)
    return (f'<h4>{e(_labels()["residual_summary"])}</h4>'
            + _table([label for _, label in SUMMARY_KEYS], [f'<tr>{cells}</tr>']))


def _hetero(citer: cite.Citer, rid: str, base: list, h: Mapping) -> str:
    lab = _labels()
    p = base + ['heteroscedasticity']
    flag = lab['hetero_yes'] if h.get('flag') else lab['hetero_no']
    return (f'<h4>{e(lab["hetero_heading"])}</h4>{_concept("heteroscedasticity")}'
            f'<p>{_badge("uncertain" if h.get("flag") else "met", flag)} Rank correlation '
            f'{_num(citer, rid, p + ["abs_residual_prediction_correlation"], "f2")}; spread of '
            f'the residuals in the top third of the predictions over the bottom third: '
            f'{_num(citer, rid, p + ["spread_ratio_top_bottom"], "f2")}.</p>'
            f'<p class="small">{_lit("message", h.get("rule") or "")}. '
            f'{e(h.get("meaning") or "")}</p>')


def _by_feature(citer: cite.Citer, rid: str, base: list, blocks: list) -> str:
    out = []
    for i, block in enumerate(blocks):
        rows = []
        for j, g in enumerate(block.get('groups') or []):
            p = base + ['by_feature', str(i), 'groups', str(j)]
            small = 'yes' if g.get('small_cell') else 'no'
            rows.append(f'<tr><td>{_lit("category", g.get("value", ""))}</td>'
                        f'<td>{_num(citer, rid, p + ["n"], "int")}</td>'
                        f'<td>{_num(citer, rid, p + ["mean_residual"], "f2")}</td>'
                        f'<td>{_num(citer, rid, p + ["mae"], "f2")}</td>'
                        f'<td>{_lit("category", small)}</td></tr>')
        out.append(f'<h5>{_lit("identifier", block.get("column", ""), "code")}</h5>'
                   + _table(['Value or bin', 'Rows', 'Mean residual', 'MAE',
                             'Too few rows to read alone'], rows))
    if not out:
        return ''
    return (f'<details class="diag-more"><summary><strong>{e(_labels()["by_feature_heading"])}'
            f'</strong></summary>{"".join(out)}</details>')


def _largest(citer: cite.Citer, rid: str, base: list, ex: Mapping) -> str:
    lab = _labels()
    features = list(ex.get('features') or [])
    return (f'<h4>{e(lab["largest_heading"])}</h4>{_concept("example_errors")}'
            + _example_rows(citer, rid, base + ['examples', 'largest_errors'],
                            ex.get('largest_errors') or [], features,
                            [('observed', 'f2'), ('prediction', 'f2'), ('residual', 'f2')]))


def _regression_body(citer: cite.Citer, rid: str, values: Mapping, model: str,
                     final: bool) -> str:
    lab = _labels()
    d = (values.get('models') or {}).get(model) or {}
    base = ['models', model]
    unit = values.get('unit')
    parts = [f'<p><strong>{e(lab["model"])}:</strong> {e(_model_name(model))}.'
             f'{" Unit: " + _lit("case", unit) + "." if unit else ""}</p>']
    if len(values.get('models') or {}) > 1:
        parts.append(_regression_models_table(citer, rid, values['models']))
    parts.append(f'<h4>{e(lab["residuals_heading"])}</h4>{_concept("residual")}')
    parts.append(residual_chart(citer, rid, base, d, final))
    parts.append(observed_chart(citer, rid, base, d, final))
    parts.append(f'{_concept("qq_plot")}<p class="small">{_lit("message", values.get("normality_note") or "")}'
                 f'</p>')
    parts.append(qq_chart(citer, rid, base, d))
    parts.append(_residual_summary(citer, rid, base))
    parts.append(_hetero(citer, rid, base, d.get('heteroscedasticity') or {}))
    parts.append(_by_feature(citer, rid, base, d.get('by_feature') or []))
    if not final:
        parts.append(_coefficients(citer, rid, base, d.get('coefficients') or {}))
    parts.append(_largest(citer, rid, base, d.get('examples') or {}))
    smearing = values.get('smearing') or {}
    parts.append(f'<h4>{e(lab["smearing"])}</h4>{_concept("smearing")}'
                 f'<p class="small">{_lit("message", smearing.get("note") or "")}</p>')
    return ''.join(p for p in parts if p)


# --- the section ----------------------------------------------------------------------------

def _focus(view: Mapping, values: Mapping, task: str) -> str:
    """The model shown in detail: the chosen (or proposed) one, else the candidate."""
    models = list((values.get('models') or {}))
    if task == 'regression':
        choice = (view['decisions'].get('model_choice') or {})
        wanted = choice.get('value') if choice.get('status') in ('confirmed',
                                                                  'reconfirm_required') else None
        wanted = wanted or (view.get('criterion') or {}).get('model')
    else:
        wanted = (view.get('criterion') or {}).get('model')
    if wanted in models:
        return wanted
    for m in ('fit.logistic', 'fit.linear'):
        if m in models:
            return m
    return models[0] if models else ''


_TERM = re.compile(r'<p><strong class="term">.*?</p>', re.S)


def _part(view: Mapping, citer: cite.Citer, slot: str, task: str, final: bool) -> str:
    lab = _labels()
    item = view['results'].get(slot)
    if item is None:
        return ''
    rid = item['result_id']
    if not citer.citable(rid):
        reason = (item.get('stale_reason') or {}).get('reason') or item.get('integrity') or ''
        return (f'<div data-slot="{e(slot)}" data-state="stale"><p>'
                f'{_badge("stale", texts.load("steps")["stale"])} {e(lab["stale"])} '
                f'{_lit("message", audience.reason_words(reason))}</p></div>')
    values = item['values']
    model = values.get('model') if final else _focus(view, values, task)
    body = (_regression_body if task == 'regression' else _binary_body)(
        citer, rid, values, model, final)
    if final:
        # The terms are defined once, in the development part.
        body = _TERM.sub('', body)
    question = values.get('question') or ''
    return (f'<div data-slot="{e(slot)}" data-state="current" data-result="{e(rid)}" '
            f'data-evidence="{e(str(values.get("evidence")))}">'
            f'<p><strong>Question.</strong> {_lit("message", question)}</p>{body}</div>')


def _opening_note(view: Mapping, item: Mapping | None) -> str:
    lab = _labels()
    final = view.get('final_test') or {}
    opening = final.get('opening') or {}
    if final.get('status') != 'opened' or not item:
        return ''
    after = isinstance(item.get('started_revision'), int) and \
        isinstance(opening.get('revision'), int) and \
        item['started_revision'] > opening['revision']
    return (f'<p class="notice" data-opening="{"after" if after else "before"}">'
            f'{e(lab["after_opening"] if after else lab["before_opening"])}</p>')


def section(view: Mapping, citer: cite.Citer) -> str:
    """The "Model diagnostics" section (empty parts say what is missing)."""
    labels = texts.report()
    lab = _labels()
    task = view.get('task') or 'binary'
    slot = DEVELOPMENT_SLOTS[task]
    dev_item = view['results'].get(slot)
    dev = _part(view, citer, slot, task, final=False)
    if not dev:
        dev = f'<p class="muted">{e(lab["pending"])}</p>'
    parts = [f'<section class="card diagnostics" id="diagnostics">'
             f'<h2>{e(labels["sections"]["diagnostics"])}</h2><p>{e(lab["intro"])}</p>',
             f'<h3 id="diagnostics-development">{_badge("confirmed", lab["development"])}</h3>'
             f'<p class="notice">{e(lab["development_note"])}</p>'
             f'{_opening_note(view, dev_item)}{dev}']
    final = view.get('final_test') or {}
    status = final.get('status')
    parts.append(f'<h3 id="diagnostics-final">{_badge("final", lab["final"])}</h3>')
    if status in (None, 'absent'):
        parts.append(f'<p class="muted">{e(lab["final_absent"])}</p>')
    elif status == 'sealed':
        parts.append(f'<p class="muted" data-final="sealed">{e(lab["final_sealed"])}</p>')
    else:
        body = _part(view, citer, FINAL_SLOT, task, final=True)
        parts.append(f'<p class="notice">{e(lab["final_note"])}</p>' + body if body else
                     f'<p class="muted" data-final="pending">{e(lab["final_pending"])}</p>')
    parts.append('</section>')
    return ''.join(parts)
