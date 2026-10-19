"""Inline SVG charts of the HTML report (v0.2a, WP-A6).

Every chart is drawn from registered results only, through a :class:`mlkit.study.cite.Citer`:

* a value label is a cited ``<text data-result-id data-path data-value>`` element
  (:meth:`~mlkit.study.cite.Citer.svg_num`), which ``hypotrail check`` verifies like a
  ``<data>`` element;
* an axis tick is a drawing scale, written ``<text data-literal="axis">``; ``check``
  accepts that exemption only inside an ``<svg>`` (CLI-CONTRACT §11, WP-A6);
* a group or feature name is a recorded literal (``data-literal="category"`` or
  ``"identifier"``).

No script, no external resource, no inline event handler: the charts are static SVG
styled by the report's CSS variables, so they follow the theme and stay CSP-safe. Each
chart sits in a ``<figure>`` whose caption states the question it answers. Hover shows
the mark's name (an SVG ``<title>``, never a number).

The charts (3 to 5, depending on what is registered):

1. the target: the count of each label (binary) or its distribution (regression);
2. the rate (binary) or mean (regression) by group of one column, with 95% intervals and
   the band chance alone draws (null band);
3. the single-feature signal, with the legitimacy flag;
4. binary: positives found by the model and by the baseline at each evaluated rule;
   regression: the residual distribution of each model on validation rows;
5. regression with a period column: the mean residual by period.

Pure: no pandas, numpy, or scikit-learn.
"""
from __future__ import annotations

import html
import math
from typing import Any, Mapping

from . import cite

e = html.escape

WIDTH = 640
LEFT = 170          # room for group and feature names
RIGHT = 70
ROW = 26
TOP = 30
AXIS = 34

CHART_CSS = '''
.charts figure{margin:18px 0 26px;padding:0;max-width:680px}
.charts figcaption{font-size:13px;color:var(--muted);margin:0 0 8px;max-width:680px}
.charts figcaption strong{color:var(--ink)}
.chart-frame{overflow-x:auto;max-width:680px}
svg.chart{display:block;width:100%;min-width:520px;max-width:680px;height:auto;overflow:visible}
svg.chart text{font-size:12px;fill:var(--ink);font-family:inherit}
svg.chart text.axis,svg.chart text.note{fill:var(--muted);font-size:11px}
svg.chart text.val{font-variant-numeric:tabular-nums;font-weight:650;paint-order:stroke;stroke:var(--paper);stroke-width:3px;stroke-linejoin:round}
svg.chart text.flag{fill:var(--amber);font-weight:700}
svg.chart line.grid{stroke:var(--line);stroke-width:1}
svg.chart line.ref{stroke:var(--muted);stroke-width:1.5;stroke-dasharray:4 3}
svg.chart line.zero{stroke:var(--muted);stroke-width:1.5}
svg.chart line.ci{stroke:var(--ink);stroke-width:2}
svg.chart rect.m,svg.chart circle.m{fill:var(--accent)}
svg.chart rect.b{fill:var(--muted);opacity:.55}
svg.chart rect.band{fill:var(--muted);opacity:.18}
svg.chart rect.box{fill:var(--accent);opacity:.35}
svg.chart rect.box.b{fill:var(--muted);opacity:.35}
svg.chart rect.flagged{fill:var(--amber)}
svg.chart rect.unused{fill:var(--muted);opacity:.3}
svg.chart line.whisker{stroke:var(--ink);stroke-width:1.5}
svg.chart line.median{stroke:var(--ink);stroke-width:2.5}
svg.chart circle.mean{fill:var(--paper);stroke:var(--ink);stroke-width:2}
.legend{display:flex;gap:18px;font-size:12px;color:var(--muted);margin:4px 0 0}
.legend span:before{content:"";display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:6px;vertical-align:-2px;background:var(--accent)}
.legend span.b:before{background:var(--muted);opacity:.55}
.legend span.band:before{background:var(--muted);opacity:.18}
.legend span.flagged:before{background:var(--amber)}
@media (forced-colors:active){svg.chart rect,svg.chart circle{forced-color-adjust:none}}
'''


def lit(kind: str, text: Any, x: float, y: float, anchor: str = 'start',
        cls: str = '') -> str:
    klass = f' class="{cls}"' if cls else ''
    return (f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}"{klass} '
            f'data-literal="{kind}">{e(str(text))}</text>')


def _nice_max(value: float) -> float:
    if value <= 0:
        return 1.0
    exp = 10 ** math.floor(math.log10(value))
    for step in (1, 1.25, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10):
        if step * exp >= value:
            return step * exp
    return 10 * exp


def _ticks(lo: float, hi: float, n: int = 4) -> list[float]:
    span = hi - lo
    if span <= 0:
        return [lo]
    raw = span / n
    exp = 10 ** math.floor(math.log10(raw))
    step = next(s * exp for s in (1, 2, 2.5, 5, 10) if s * exp >= raw)
    start = math.ceil(lo / step - 1e-9) * step
    out, t = [], start
    while t <= hi + 1e-9:
        out.append(round(t, 10))
        t += step
    return out


def _tick_text(value: float, percent: bool) -> str:
    if percent:
        shown = 100 * value
        return f'{shown:.0f}%' if abs(shown - round(shown)) < 1e-9 else f'{shown:.1f}%'
    if abs(value - round(value)) < 1e-9:
        return f'{round(value):,}'
    return f'{value:.2f}'.rstrip('0').rstrip('.') if abs(value) < 10 else f'{value:.1f}'


class Scale:
    def __init__(self, lo: float, hi: float, x0: float = LEFT, x1: float = WIDTH - RIGHT):
        self.lo, self.hi, self.x0, self.x1 = lo, hi, x0, x1

    def __call__(self, v: float) -> float:
        if self.hi == self.lo:
            return self.x0
        return self.x0 + (v - self.lo) / (self.hi - self.lo) * (self.x1 - self.x0)

    def axis(self, y_top: float, y_bottom: float, percent: bool = False) -> str:
        out = []
        for t in _ticks(self.lo, self.hi):
            x = self(t)
            out.append(f'<line class="grid" x1="{x:.1f}" y1="{y_top:.1f}" x2="{x:.1f}" '
                       f'y2="{y_bottom:.1f}"/>')
            out.append(lit('axis', _tick_text(t, percent), x, y_bottom + 16, 'middle', 'axis'))
        return ''.join(out)


MAX_LABEL = 22


def short(text: Any, limit: int = MAX_LABEL) -> str:
    """A name cut to fit the label column (the full name stays in the mark's title)."""
    text = str(text)
    return text if len(text) <= limit else text[:limit - 1] + '…'


def _svg(height: float, body: str, label: str) -> str:
    return (f'<svg class="chart" viewBox="0 0 {WIDTH} {height:.0f}" role="img" '
            f'aria-label="{e(label)}">{body}</svg>')


def figure(chart_id: str, question: str, svg: str, legend: str = '', note: str = '') -> str:
    note_html = f'<p class="small">{note}</p>' if note else ''
    return (f'<figure data-chart="{e(chart_id)}"><figcaption><strong>Question.</strong> '
            f'{e(question)}</figcaption><div class="chart-frame">{svg}</div>{legend}'
            f'{note_html}</figure>')


def legend(*items: tuple[str, str]) -> str:
    return '<p class="legend">' + ''.join(f'<span class="{e(c)}">{e(t)}</span>'
                                         for c, t in items) + '</p>'


def _num(x: Any) -> bool:
    return cite.is_number(x)


# --- 1. the target ------------------------------------------------------------------------

def target_balance(citer: cite.Citer, rid: str, values: Mapping) -> str:
    """Positive and negative training rows (binary ``eda.target_rate``)."""
    pos, neg = values.get('n_positive'), values.get('n_negative')
    if not (_num(pos) and _num(neg)):
        return ''
    scale = Scale(0, _nice_max(max(pos, neg)))
    label_pos = f'{values.get("positive_label")}'
    rows = [('n_positive', pos, f'Outcome {label_pos}', 'm'),
            ('n_negative', neg, 'Other outcome', 'b')]
    body, y = [], TOP
    for path, v, name, cls in rows:
        w = max(1.0, scale(v) - scale(0))
        body.append(lit('category', name, LEFT - 8, y + 15, 'end'))
        body.append(f'<rect class="{cls}" x="{LEFT}" y="{y + 2}" width="{w:.1f}" height="18" '
                    f'rx="4"><title>{e(name)}</title></rect>')
        body.append(citer.svg_num(rid, path, 'int', x=LEFT + w + 6, y=y + 15))
        y += ROW + 6
    # WP-A9 (M6): the grid is drawn first, under the bars and their labels.
    body.insert(0, scale.axis(TOP - 6, y + 2))
    svg = _svg(y + AXIS, ''.join(body), 'Training rows by outcome')
    rate = citer.num(rid, 'rate', 'pct1')
    interval = ''
    if citer.has(rid, 'interval.low') and citer.has(rid, 'interval.high'):
        interval = (f' (<span data-literal="setting">95%</span> interval '
                    f'{citer.num(rid, "interval.low", "pct1")} to '
                    f'{citer.num(rid, "interval.high", "pct1")})')
    note = f'Positive rate on training rows: {rate}{interval}.'
    return figure('target_balance', values.get('question') or
                  'How often is the outcome positive among the training rows?', svg,
                  note=note)


def target_distribution(citer: cite.Citer, rid: str, values: Mapping) -> str:
    """Minimum, quartiles, maximum and mean with its interval (regression target)."""
    keys = ('min', 'q25', 'median', 'q75', 'max', 'mean')
    if not all(_num(values.get(k)) for k in keys):
        return ''
    lo, hi = values['min'], values['max']
    pad = (hi - lo) * 0.05 or 1
    scale = Scale(lo - pad, hi + pad)
    y = TOP + 10
    body = [scale.axis(TOP - 6, y + 60),
            f'<line class="whisker" x1="{scale(lo):.1f}" y1="{y + 20}" x2="{scale(hi):.1f}" '
            f'y2="{y + 20}"/>',
            f'<rect class="box" x="{scale(values["q25"]):.1f}" y="{y + 6}" '
            f'width="{scale(values["q75"]) - scale(values["q25"]):.1f}" height="28" rx="4">'
            f'<title>Middle half of the training rows</title></rect>',
            f'<line class="median" x1="{scale(values["median"]):.1f}" y1="{y + 4}" '
            f'x2="{scale(values["median"]):.1f}" y2="{y + 36}"/>']
    mi = values.get('mean_interval') or {}
    if _num(mi.get('low')) and _num(mi.get('high')):
        body.append(f'<line class="ci" x1="{scale(mi["low"]):.1f}" y1="{y + 46}" '
                    f'x2="{scale(mi["high"]):.1f}" y2="{y + 46}"/>')
    body.append(f'<circle class="mean" cx="{scale(values["mean"]):.1f}" cy="{y + 46}" r="5">'
                f'<title>Mean</title></circle>')
    body.append(lit('category', 'Training rows', LEFT - 8, y + 24, 'end'))
    body.append(citer.svg_num(rid, 'min', 'auto', x=scale(lo), y=y - 2, anchor='middle'))
    body.append(citer.svg_num(rid, 'median', 'auto', x=scale(values['median']), y=y - 2,
                              anchor='middle'))
    body.append(citer.svg_num(rid, 'max', 'auto', x=scale(hi), y=y - 2, anchor='middle'))
    svg = _svg(y + 60 + AXIS, ''.join(body), 'Distribution of the target on training rows')
    unit = values.get('unit') or ''
    note = (f'Box: the middle half of the training rows; thick line: the median; circle: the '
            f'mean {citer.num(rid, "mean", "auto")}')
    if _num(mi.get('low')) and _num(mi.get('high')):
        note += (f' with its interval {citer.num(rid, "mean_interval.low", "auto")} to '
                 f'{citer.num(rid, "mean_interval.high", "auto")}')
    note += f'. Unit: <span data-literal="case">{e(unit)}</span>.' if unit else '.'
    return figure('target_distribution', values.get('question') or
                  'How is the target distributed among the training rows?', svg, note=note)


# --- 2. rate or mean by group ---------------------------------------------------------------

def by_group(citer: cite.Citer, rid: str, values: Mapping, *, rate: bool) -> str:
    """One row per group: the point, its 95% interval, and the null band (chance)."""
    groups = [g for g in values.get('groups') or [] if isinstance(g, Mapping)]
    key = 'rate' if rate else 'mean'
    groups = [(i, g) for i, g in enumerate(groups) if _num(g.get(key))]
    if not groups:
        return ''
    edges = []
    for _, g in groups:
        edges.append(g[key])
        for part in ('interval', 'null_band'):
            band = g.get(part) or {}
            edges += [v for v in (band.get('low'), band.get('high')) if _num(v)]
    overall = values.get('overall_rate' if rate else 'overall_mean')
    if _num(overall):
        edges.append(overall)
    lo = 0.0 if rate else min(edges)
    hi = max(edges)
    if rate:
        hi = min(1.0, _nice_max(hi * 1.05))
    else:
        pad = (hi - lo) * 0.08 or 1
        lo, hi = lo - pad, hi + pad
    scale = Scale(lo, hi, x1=WIDTH - RIGHT - 20)
    fmt = 'pct1' if rate else 'auto'
    body, y = [], TOP
    for i, g in groups:
        base = f'groups.{i}'
        cy = y + 11
        band = g.get('null_band') or {}
        if _num(band.get('low')) and _num(band.get('high')):
            body.append(f'<rect class="band" x="{scale(band["low"]):.1f}" y="{y}" '
                        f'width="{max(1.0, scale(band["high"]) - scale(band["low"])):.1f}" '
                        f'height="22" rx="3"><title>Range chance alone draws</title></rect>')
        ci = g.get('interval') or {}
        if _num(ci.get('low')) and _num(ci.get('high')):
            body.append(f'<line class="ci" x1="{scale(ci["low"]):.1f}" y1="{cy}" '
                        f'x2="{scale(ci["high"]):.1f}" y2="{cy}"/>')
        body.append(f'<circle class="m" cx="{scale(g[key]):.1f}" cy="{cy}" r="5">'
                    f'<title>{e(str(g.get("value")))}</title></circle>')
        body.append(lit('category', short(g.get('value', ''), 15), 0, cy + 4, 'start'))
        body.append(citer.svg_num(rid, f'{base}.n_rows', 'int', x=LEFT - 8, y=cy + 4,
                                  anchor='end', cls='axis', prefix='n '))
        body.append(citer.svg_num(rid, f'{base}.{key}', fmt, x=WIDTH - RIGHT + 4,
                                  y=cy + 4, anchor='start'))
        y += ROW
    if _num(overall):
        x = scale(overall)
        body.append(f'<line class="ref" x1="{x:.1f}" y1="{TOP - 8}" x2="{x:.1f}" y2="{y}"/>')
    body.insert(0, scale.axis(TOP - 8, y + 2, percent=rate))
    what = 'Positive rate' if rate else 'Mean of the target'
    svg = _svg(y + AXIS, ''.join(body), f'{what} by group of {values.get("column", "")}')
    lg = legend(('m', f'{what} with its interval'), ('band', 'Range chance alone draws'))
    chart = (values.get('null_band') or {}).get('chart') or {}
    note = ''
    if chart:
        if chart.get('outside'):
            note = ('The spread between groups is larger than every one of the shuffles of the '
                    'target: a pattern unlikely to be chance alone. ')
        else:
            note = ('The spread between groups stays within what shuffling the target draws: '
                    'it is not distinguishable from chance. ')
    note += ('Dashed line: the overall value on training rows. An association between groups, '
             'not an effect of the variable.')
    column = str(values.get('column', ''))
    question = values.get('question') or f'Does the outcome differ across the groups of {column}?'
    note += ' Intervals: <span data-literal="setting">95%</span> level.'
    return figure(f'by_group:{values.get("column", "")}', question, svg, lg, note)


# --- 3. single-feature signal --------------------------------------------------------------

def signal(citer: cite.Citer, rid: str, values: Mapping) -> str:
    signals = [(i, s) for i, s in enumerate(values.get('signals') or [])
               if isinstance(s, Mapping) and _num(s.get('score'))]
    if not signals:
        return ''
    auc = values.get('metric') == 'roc_auc'
    low = min(s['score'] for _, s in signals)
    # AUC: chance is 0.5, so the axis starts at 0.4 (or lower when a score is lower) and a
    # reference line marks chance; R²: the axis starts at 0 (or at the lowest score).
    lo = min(0.4, math.floor(low * 10) / 10) if auc else min(0.0, math.floor(low * 10) / 10)
    hi = 1.0 if auc else max(1.0, max(s['score'] for _, s in signals))
    scale = Scale(lo, hi, x1=WIDTH - RIGHT - 60)
    body, y = [], TOP
    chance = 0.5 if auc else 0.0
    xc = scale(chance)
    for i, s in signals:
        used = s.get('availability') in ('available_at_prediction', 'uncertain_included')
        cls = 'flagged' if s.get('flag') else ('m' if used else 'unused')
        x0, x1 = sorted((xc, scale(s['score'])))       # a bar starts at chance
        w = max(1.0, x1 - x0)
        body.append(lit('identifier', short(s.get('feature', '')), LEFT - 8, y + 15, 'end'))
        body.append(f'<rect class="{cls}" x="{x0:.1f}" y="{y + 3}" width="{w:.1f}" height="16" '
                    f'rx="4"><title>{e(str(s.get("feature", "")))}</title></rect>')
        body.append(citer.svg_num(rid, f'signals.{i}.score', 'f2', x=max(xc, x1) + 6, y=y + 15))
        if not used:
            # WP-A9 (M6): an excluded feature says so even when its signal is strong.
            body.append(f'<text x="{WIDTH - 4}" y="{y + 15}" text-anchor="end" class="note">'
                        f'Not used by the model</text>')
        elif s.get('flag'):
            body.append(f'<text x="{WIDTH - 4}" y="{y + 15}" text-anchor="end" class="flag">'
                        f'Check legitimacy</text>')
        y += ROW - 4
    body.append(f'<line class="ref" x1="{xc:.1f}" y1="{TOP - 6}" x2="{xc:.1f}" y2="{y + 2}"/>')
    body.append(f'<text x="{xc:.1f}" y="{TOP - 12}" text-anchor="middle" class="note">'
                f'chance</text>')
    body.insert(0, scale.axis(TOP - 6, y + 2))
    name = 'Area under the ROC curve' if auc else 'Share of variance explained'
    svg = _svg(y + AXIS, ''.join(body), f'{name} of each feature alone')
    lg = legend(('m', 'Used by the model'), ('flagged', 'Strong enough to question'),
                ('b', 'Not used by the model'))
    lg = lg.replace('<span class="b">', '<span class="b unused">')
    note = (f'{name} of a model that sees one feature at a time, out of fold on training rows. '
            'A strong signal raises one question only: is this feature truly known at the '
            'moment of prediction? It never selects features.')
    return figure('single_feature_signal', values.get('question') or
                  'Which feature alone carries a strong signal?', svg, lg, note)


# --- 4. binary: positives found at each rule -------------------------------------------------

SELECTION_LEGEND = {'fit.logistic': 'Model (logistic, the candidate)',
                    'fit.variant': 'Model (the variant, adopted with the rule)'}


def selection(citer: cite.Citer, rid: str, values: Mapping, rule_words,
              model: str = 'fit.logistic') -> str:
    """Positive rows found at each evaluated rule by ``model`` (B6c, M4: the configuration
    the policy adopts, or proposes; the variant when the rule applies to it) and by the
    baseline. Under cross-validation the counts are out of fold (M3)."""
    rules = values.get('rules') if isinstance(values.get('rules'), Mapping) else {}
    items = []
    for key, item in rules.items():
        models = item.get('models') if isinstance(item, Mapping) else None
        if not isinstance(models, Mapping):
            continue
        if model not in models:
            model = 'fit.logistic'
        m, b = models.get(model) or {}, models.get('fit.baseline') or {}
        if _num(m.get('true_positives')) and _num(b.get('true_positives')) \
                and _num(m.get('selected')):
            items.append((key, m, b))
    if not items:
        return ''
    items.sort(key=lambda t: t[1]['selected'])
    total = values.get('n_positive')
    top = max([m['true_positives'] for _, m, _ in items] + ([total] if _num(total) else []))
    scale = Scale(0, _nice_max(top), x1=WIDTH - RIGHT - 10)
    body, y = [], TOP + 10
    slot = cite.format_path([model])
    for key, m, b in items:
        prefix = cite.format_path(['rules', key, 'models'])
        body.append(lit('decision_value', rule_words(key), 0, y + 4, 'start'))
        y += 12
        body.append(citer.svg_num(rid, f'{prefix}.{slot}.selected', 'auto',
                                  x=LEFT - 8, y=y + 15, anchor='end', cls='axis',
                                  suffix=' rows selected'))
        for cls, name, data, dy in (('m', model, m, 0), ('b', 'fit.baseline', b, 20)):
            w = max(1.0, scale(data['true_positives']) - scale(0))
            label = 'Model' if name != 'fit.baseline' else 'Baseline'
            body.append(f'<rect class="{cls}" x="{LEFT}" y="{y + dy + 2}" width="{w:.1f}" '
                        f'height="16" rx="4"><title>{label}</title></rect>')
            body.append(citer.svg_num(rid, f'{prefix}.{cite.format_path([name])}'
                                      '.true_positives', 'auto', x=LEFT + w + 6, y=y + dy + 15))
        y += 52
    if _num(total):
        x = scale(total)
        body.append(f'<line class="ref" x1="{x:.1f}" y1="{TOP - 8}" x2="{x:.1f}" y2="{y - 8}"/>')
        body.append(citer.svg_num(rid, 'n_positive', 'int', x=x, y=TOP - 12, anchor='middle',
                                  cls='axis', suffix=' positive rows in all'))
    body.insert(0, scale.axis(TOP - 4, y - 6))
    svg = _svg(y + AXIS - 8, ''.join(body), 'Positive rows found among the selected rows')
    lg = legend(('m', SELECTION_LEGEND.get(model, 'Model')),
                ('b', 'Baseline (no ranking, average count)'))
    if values.get('evaluation') == 'out_of_fold':
        within = any(isinstance(item, Mapping) and any(
            isinstance(v, Mapping) and v.get('selection_scope') == 'within_fold'
            for v in (item.get('models') or {}).values()) for item in rules.values())
        note = ('Out-of-fold predictions of the development rows'
                + (', each rule applied within each fold' if within else '')
                + '. The rule is chosen on these rows, so these counts are optimistic and are '
                  'not a forecast. The dashed line is every positive row of the development '
                  'rows.')
    else:
        note = ('Validation rows. The rule is chosen on these rows, so these counts are '
                'optimistic and are not a forecast. The dashed line is every positive row of '
                'the validation rows.')
    return figure('selection', 'Among the rows each rule selects, how many positive rows does '
                  'the model find, compared with the baseline?', svg, lg, note)


# --- 4. regression: residuals ---------------------------------------------------------------

MODEL_NAMES = {'fit.linear': 'Linear model', 'fit.baseline': 'Mean baseline'}


def residuals(citer: cite.Citer, rid: str, values: Mapping) -> str:
    res = values.get('residuals') if isinstance(values.get('residuals'), Mapping) else {}
    keys = ('q05', 'q25', 'median', 'q75', 'q95')
    models = [m for m in ('fit.linear', 'fit.baseline')
              if isinstance(res.get(m), Mapping) and all(_num(res[m].get(k)) for k in keys)]
    if not models:
        return ''
    edges = [res[m][k] for m in models for k in keys] + [0.0]
    lo, hi = min(edges), max(edges)
    pad = (hi - lo) * 0.08 or 1
    scale = Scale(lo - pad, hi + pad, x1=WIDTH - RIGHT - 10)
    body, y = [], TOP + 6
    for m in models:
        r = res[m]
        cls = 'box' if m == 'fit.linear' else 'box b'
        cy = y + 14
        base = cite.format_path(['residuals', m])
        body.append(lit('identifier', MODEL_NAMES[m], LEFT - 8, cy + 4, 'end'))
        body.append(f'<line class="whisker" x1="{scale(r["q05"]):.1f}" y1="{cy}" '
                    f'x2="{scale(r["q95"]):.1f}" y2="{cy}"/>')
        body.append(f'<rect class="{cls}" x="{scale(r["q25"]):.1f}" y="{cy - 11}" '
                    f'width="{max(1.0, scale(r["q75"]) - scale(r["q25"])):.1f}" height="22" '
                    f'rx="4"><title>{MODEL_NAMES[m]}</title></rect>')
        body.append(f'<line class="median" x1="{scale(r["median"]):.1f}" y1="{cy - 13}" '
                    f'x2="{scale(r["median"]):.1f}" y2="{cy + 13}"/>')
        body.append(citer.svg_num(rid, f'{base}.median', 'f2', x=WIDTH - RIGHT + 2,
                                  y=cy + 4, prefix='median '))
        y += 40
    x0 = scale(0)
    body.append(f'<line class="zero" x1="{x0:.1f}" y1="{TOP - 6}" x2="{x0:.1f}" y2="{y - 6}"/>')
    body.insert(0, scale.axis(TOP - 6, y - 4))
    svg = _svg(y + AXIS - 4, ''.join(body), 'Residuals of each model on validation rows')
    unit = values.get('unit')
    unit_note = f' Unit: <span data-literal="case">{e(unit)}</span>.' if unit else ''
    note = ('Residual: observed minus predicted, on validation rows. Line: from the '
            '<span data-literal="setting">5th</span> to the '
            '<span data-literal="setting">95th</span> percentile; box: the middle half; thick '
            'line: the median. A box away from the zero line means the model is biased on '
            'these rows.' + unit_note)
    return figure('residuals', 'How far from the observed value are the predictions of each '
                  'model on validation rows?', svg,
                  legend(('box', 'Linear model'), ('box b', 'Mean baseline')), note)


def residuals_by(citer: cite.Citer, rid: str, values: Mapping) -> str:
    blocks = values.get('residuals_by') or []
    if not blocks or not isinstance(blocks[0], Mapping):
        return ''
    block = blocks[0]
    groups = [(j, g) for j, g in enumerate(block.get('groups') or [])
              if isinstance(g, Mapping)
              and _num(((g.get('models') or {}).get('fit.linear') or {}).get('mean_residual'))]
    if not groups:
        return ''
    vals = [0.0] + [g['models'][m]['mean_residual'] for _, g in groups
                    for m in ('fit.linear', 'fit.baseline')
                    if _num((g['models'].get(m) or {}).get('mean_residual'))]
    lo, hi = min(vals), max(vals)
    pad = (hi - lo) * 0.08 or 1
    scale = Scale(lo - pad, hi + pad, x1=WIDTH - RIGHT - 10)
    body, y = [], TOP
    for j, g in groups:
        cy = y + 11
        body.append(lit('category', g.get('value', ''), LEFT - 60, cy + 4, 'end'))
        body.append(citer.svg_num(rid, f'residuals_by.0.groups.{j}.n_rows', 'int', x=LEFT - 8,
                                  y=cy + 4, anchor='end', cls='axis', prefix='n '))
        for m, cls, dy in (('fit.linear', 'm', -4), ('fit.baseline', 'b', 6)):
            v = (g['models'].get(m) or {}).get('mean_residual')
            if not _num(v):
                continue
            x0, x1 = sorted((scale(0), scale(v)))
            body.append(f'<rect class="{cls}" x="{x0:.1f}" y="{cy + dy - 4}" '
                        f'width="{max(1.0, x1 - x0):.1f}" height="8" rx="3">'
                        f'<title>{MODEL_NAMES[m]}</title></rect>')
        body.append(citer.svg_num(rid, f'residuals_by.0.groups.{j}.models.[fit.linear].'
                                       f'mean_residual', 'f2', x=WIDTH - RIGHT + 2, y=cy + 4))
        y += ROW
    x0 = scale(0)
    body.append(f'<line class="zero" x1="{x0:.1f}" y1="{TOP - 6}" x2="{x0:.1f}" y2="{y}"/>')
    body.insert(0, scale.axis(TOP - 6, y + 2))
    column = str(block.get('column', ''))
    svg = _svg(y + AXIS, ''.join(body), f'Mean residual by {column}')
    note = ('Mean residual (observed minus predicted) of the validation rows of each group; the '
            'value shown is the linear model\'s. Groups with few rows are noisy.')
    return figure(f'residuals_by:{column}', f'Does the error drift across the values of '
                  f'{column}?', svg, legend(('m', 'Linear model'), ('b', 'Mean baseline')),
                  note)
