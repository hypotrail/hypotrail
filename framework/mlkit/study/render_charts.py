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

The charts (3 to 7, depending on what is registered):

1. the target: the count of each label (binary) or its distribution (regression);
2. the rate (binary) or mean (regression) by group of one column, with 95% intervals and
   the band chance alone draws (null band);
3. the single-feature signal, with the legitimacy flag;
4. binary: positives found by the model and by the baseline at each evaluated rule;
   regression: the residual distribution of each model on validation rows;
5. regression with a period column: the mean residual by period;
6. v0.3 (WP-J, R17): the distribution of one column, a skewed one first, with its exact
   zeros apart and its positive values on logarithmic bins, as the study panel draws it;
7. v0.3 (WP-J, R28): the predictor correlation matrix with its collinearity flags.

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
svg.chart rect.cpos{fill:var(--accent)}
svg.chart rect.cneg{fill:var(--amber)}
svg.chart rect.cflag{stroke:var(--ink);stroke-width:2}
svg.chart line.whisker{stroke:var(--ink);stroke-width:1.5}
svg.chart line.median{stroke:var(--ink);stroke-width:2.5}
svg.chart circle.mean{fill:var(--paper);stroke:var(--ink);stroke-width:2}
.legend{display:flex;gap:18px;font-size:12px;color:var(--muted);margin:4px 0 0}
.legend span:before{content:"";display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:6px;vertical-align:-2px;background:var(--accent)}
.legend span.b:before{background:var(--muted);opacity:.55}
.legend span.band:before{background:var(--muted);opacity:.18}
.legend span.flagged:before{background:var(--amber)}
.legend span.unused:before{opacity:.3}
.legend span.outline:before{background:none;border:2px solid var(--ink);width:9px;height:9px}
.legend span.box:before{opacity:.35}
.legend span.box.b:before{background:var(--muted);opacity:.35}
.legend span.final:before{background:var(--amber)}
.legend span.line:before{height:0;border-radius:0;background:none;border-top:3px solid var(--accent);vertical-align:3px}
.legend span.line.final:before{border-top-color:var(--amber)}
.legend span.diag:before{height:0;border-radius:0;background:none;border-top:2px dashed var(--muted);vertical-align:3px;opacity:1}
.legend span.bin:before{background:var(--paper);border:2px solid var(--ink);border-radius:50%;width:9px;height:9px}
.legend span.pt:before{border-radius:50%;opacity:.45}
.legend span.pt.final:before{background:var(--amber);opacity:.55}
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


def _rows() -> str:
    """B6c (M3): the rows the exploration reads: every development row under
    cross-validation, the training rows otherwise."""
    from . import texts
    return 'development rows' if texts.is_cv() else 'training rows'


def _scored() -> str:
    """B6c (M3): the rows a model comparison reads."""
    from . import texts
    return 'out-of-fold predictions' if texts.is_cv() else 'validation rows'


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
    svg = _svg(y + AXIS, ''.join(body), f'{_rows().capitalize()} by outcome')
    rate = citer.num(rid, 'rate', 'pct1')
    interval = ''
    if citer.has(rid, 'interval.low') and citer.has(rid, 'interval.high'):
        interval = (f' (<span data-literal="setting">95%</span> interval '
                    f'{citer.num(rid, "interval.low", "pct1")} to '
                    f'{citer.num(rid, "interval.high", "pct1")})')
    note = f'Positive rate on {_rows()}: {rate}{interval}.'
    return figure('target_balance', values.get('question') or
                  f'How often is the outcome positive among the {_rows()}?', svg,
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
            f'<title>Middle half of the {_rows()}</title></rect>',
            f'<line class="median" x1="{scale(values["median"]):.1f}" y1="{y + 4}" '
            f'x2="{scale(values["median"]):.1f}" y2="{y + 36}"/>']
    mi = values.get('mean_interval') or {}
    if _num(mi.get('low')) and _num(mi.get('high')):
        body.append(f'<line class="ci" x1="{scale(mi["low"]):.1f}" y1="{y + 46}" '
                    f'x2="{scale(mi["high"]):.1f}" y2="{y + 46}"/>')
    body.append(f'<circle class="mean" cx="{scale(values["mean"]):.1f}" cy="{y + 46}" r="5">'
                f'<title>Mean</title></circle>')
    body.append(lit('category', _rows().capitalize(), LEFT - 8, y + 24, 'end'))
    body.append(citer.svg_num(rid, 'min', 'auto', x=scale(lo), y=y - 2, anchor='middle'))
    body.append(citer.svg_num(rid, 'median', 'auto', x=scale(values['median']), y=y - 2,
                              anchor='middle'))
    body.append(citer.svg_num(rid, 'max', 'auto', x=scale(hi), y=y - 2, anchor='middle'))
    svg = _svg(y + 60 + AXIS, ''.join(body), f'Distribution of the target on {_rows()}')
    unit = values.get('unit') or ''
    note = (f'Box: the middle half of the {_rows()}; thick line: the median; circle: the '
            f'mean {citer.num(rid, "mean", "auto")}')
    if _num(mi.get('low')) and _num(mi.get('high')):
        note += (f' with its interval {citer.num(rid, "mean_interval.low", "auto")} to '
                 f'{citer.num(rid, "mean_interval.high", "auto")}')
    note += f'. Unit: <span data-literal="case">{e(unit)}</span>.' if unit else '.'
    return figure('target_distribution', values.get('question') or
                  f'How is the target distributed among the {_rows()}?', svg, note=note)


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
    note += (f'Dashed line: the overall value on {_rows()}. An association between groups, '
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
    note = (f'{name} of a model that sees one feature at a time, out of fold on {_rows()}. '
            'A strong signal raises one question only: is this feature truly known at the '
            'moment of prediction? It never selects features.')
    return figure('single_feature_signal', values.get('question') or
                  'Which feature alone carries a strong signal?', svg, lg, note)


# --- 4. binary: positives found at each rule -------------------------------------------------

SELECTION_LEGEND = {'fit.logistic': 'Model (logistic, the candidate)',
                    'fit.variant': 'Model (the variant, adopted with the rule)',
                    'fit.variant:2': 'Model (the second variant, adopted with the rule)',
                    'fit.variant:3': 'Model (the third variant, adopted with the rule)'}


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
    svg = _svg(y + AXIS - 4, ''.join(body), f'Residuals of each model on the {_scored()}')
    unit = values.get('unit')
    unit_note = f' Unit: <span data-literal="case">{e(unit)}</span>.' if unit else ''
    note = (f'Residual: observed minus predicted, on the {_scored()}. Line: from the '
            '<span data-literal="setting">5th</span> to the '
            '<span data-literal="setting">95th</span> percentile; box: the middle half; thick '
            'line: the median. A box away from the zero line means the model is biased on '
            'these rows.' + unit_note)
    return figure('residuals', 'How far from the observed value are the predictions of each '
                  f'model on the {_scored()}?', svg,
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
    note = (f'Mean residual (observed minus predicted) of the {_scored()} of each group; the '
            'value shown is the linear model\'s. Groups with few rows are noisy.')
    return figure(f'residuals_by:{column}', f'Does the error drift across the values of '
                  f'{column}?', svg, legend(('m', 'Linear model'), ('b', 'Mean baseline')),
                  note)


# --- v0.3 (WP-J, R17, R28): a column's distribution and the predictor correlations ---------

def distribution(citer: cite.Citer, rid: str, values: Mapping) -> str:
    """The distribution of one column (``eda.distribution``), as the study panel draws it:
    a skewed column of non-negative values shows its exact zeros as their own bar and its
    positive values on logarithmic bins (R17); otherwise the fixed-width bins, or the groups
    of a discrete or categorical column. Special values and missing cells are bars of their
    own. Bar length: the share of the rows read; label: the count of rows."""
    column = str(values.get('column', ''))
    numeric = values.get('numeric') if isinstance(values.get('numeric'), Mapping) else None
    rows = []          # (label parts, share path or None, count path, css class)
    if numeric:
        skewed = bool(numeric.get('skewed')) and bool(numeric.get('log_bins'))
        key = 'log_bins' if skewed else 'bins'
        zeros = numeric.get('zeros') or {}
        if skewed and _num(zeros.get('n_rows')) and zeros['n_rows'] > 0:
            rows.append((('lit', 'Exactly zero'), 'numeric.zeros.share', 'numeric.zeros.n_rows',
                         'flagged'))
        for i, b in enumerate(numeric.get(key) or []):
            if isinstance(b, Mapping) and _num(b.get('n_rows')):
                rows.append((('bin', f'numeric.{key}.{i}'), f'numeric.{key}.{i}.share',
                             f'numeric.{key}.{i}.n_rows', 'm'))
    else:
        skewed = False
        for i, g in enumerate(values.get('groups') or []):
            if isinstance(g, Mapping) and _num(g.get('n_rows')):
                rows.append((('lit', short(g.get('value', ''), 20)), f'groups.{i}.share',
                             f'groups.{i}.n_rows', 'unused' if g.get('small_count') else 'm'))
    for i, s in enumerate(values.get('special_values') or []):
        if isinstance(s, Mapping) and _num(s.get('n_rows')) and s['n_rows'] > 0:
            rows.append((('lit', short(f'{column} = {s.get("value")}', 20)),
                         f'special_values.{i}.share', f'special_values.{i}.n_rows', 'b'))
    if _num(values.get('n_missing')) and values['n_missing'] > 0:
        rows.append((('lit', 'Missing'), None, 'n_missing', 'b'))
    if not rows:
        return ''
    total = values.get('n_rows')
    if not _num(total) or total <= 0:
        return ''
    counts = [citer.value(rid, count) for _, _, count, _ in rows]
    scale = Scale(0, _nice_max(max(counts) / total), x1=WIDTH - RIGHT - 20)
    body, y = [], TOP
    for (label, _share, count, cls), n in zip(rows, counts):
        cy = y + 13
        kind, text = label
        if kind == 'bin':
            # The bin's edges, cited: "low to high".
            body.append(citer.svg_num(rid, f'{text}.low', 'auto', x=LEFT - 70, y=cy + 4,
                                      anchor='end', cls='axis', suffix=' to'))
            body.append(citer.svg_num(rid, f'{text}.high', 'auto', x=LEFT - 8, y=cy + 4,
                                      anchor='end', cls='axis'))
            name = 'Bin of the column'
        else:
            body.append(lit('category', text, LEFT - 8, cy + 4, 'end'))
            name = str(text)
        w = max(1.0, scale(n / total) - scale(0))
        body.append(f'<rect class="{cls}" x="{LEFT}" y="{y + 3}" width="{w:.1f}" height="18" '
                    f'rx="4"><title>{e(name)}</title></rect>')
        body.append(citer.svg_num(rid, count, 'int', x=LEFT + w + 6, y=cy + 4))
        y += ROW
    body.insert(0, scale.axis(TOP - 6, y + 2, percent=True))
    svg = _svg(y + AXIS, ''.join(body), f'Distribution of {column} on the {_rows()}')
    items = [('m', 'Rows in the bin or group')]
    if skewed:
        items.insert(0, ('flagged', 'Exact zeros, apart'))
    if any(cls == 'b' for *_, cls in rows):
        items.append(('b', 'Special values and missing cells'))
    if any(cls == 'unused' for *_, cls in rows):
        items.append(('unused', 'Group with few rows'))
    note = (f'Share of the {_rows()} ({citer.num(rid, "n_rows", "int")} rows read) on the '
            'axis; the count of rows at the end of each bar.')
    if skewed:
        note += (' The column is skewed: its exact zeros are counted apart and its positive '
                 'values are binned on a logarithmic scale, each bin closed on the left.')
    note += ' The outcome is not read.'
    return figure(f'distribution:{column}', values.get('question') or
                  f'How are the values of {column} distributed among the {_rows()}?', svg,
                  legend(*items), note)


MAX_MATRIX_LABELS = 30


def correlation(citer: cite.Citer, rid: str, values: Mapping) -> str:
    """The predictor association matrix (``eda.correlation``), as the study panel draws it:
    the features in the engine's clustered order, one cell per pair coloured by the sign
    and shaded by the size of the association, the pairs at or above the collinearity level
    outlined; the flagged pairs are listed with their cited value."""
    order = [str(n) for n in values.get('order') or []][:MAX_MATRIX_LABELS]
    pairs = [(i, p) for i, p in enumerate(values.get('pairs') or []) if isinstance(p, Mapping)]
    if len(order) < 2 or not pairs:
        return ''
    by_pair = {}
    for i, p in pairs:
        by_pair[(p.get('a'), p.get('b'))] = by_pair[(p.get('b'), p.get('a'))] = (i, p)
    k = len(order)
    cell = min(22.0, (WIDTH - RIGHT - LEFT) / k)
    body, top = [], TOP
    for r, a in enumerate(order):
        y = top + r * cell
        body.append(lit('identifier', short(a, 20), LEFT - 8, y + cell / 2 + 4, 'end'))
        for col, b in enumerate(order):
            x = LEFT + col * cell
            if a == b:
                body.append(f'<rect class="b" x="{x:.1f}" y="{y:.1f}" width="{cell - 1:.1f}" '
                            f'height="{cell - 1:.1f}" fill-opacity="0.15"><title>{e(a)}</title>'
                            f'</rect>')
                continue
            found = by_pair.get((a, b))
            if not found or not _num(found[1].get('value')):
                continue
            i, p = found
            v = citer.value(rid, f'pairs.{i}.value')
            cls = 'cpos' if v >= 0 else 'cneg'
            flag = ' cflag' if p.get('flag') else ''
            body.append(f'<rect class="{cls}{flag}" x="{x:.1f}" y="{y:.1f}" '
                        f'width="{cell - 1:.1f}" height="{cell - 1:.1f}" '
                        f'fill-opacity="{0.08 + 0.92 * min(1.0, abs(v)):.2f}">'
                        f'<title>{e(a)} and {e(b)}</title></rect>')
    height = top + k * cell + 12
    svg = _svg(height, ''.join(body), 'Association between each pair of predictors')
    lg = legend(('m', 'Positive association'), ('final', 'Negative association'),
                ('outline', 'At or above the collinearity level (outlined)'))
    flagged = [(i, p) for i, p in pairs if p.get('flag') and _num(p.get('value'))]
    flagged.sort(key=lambda ip: -abs(ip[1]['value']))
    level = citer.num(rid, 'level', 'f2') if citer.has(rid, 'level') else ''
    note = ('Columns are in the same order as the rows, grouped so that associated '
            'predictors sit together; a darker cell is a stronger association. ')
    if flagged:
        items = '; '.join(f'<code data-literal="identifier">{e(str(p.get("a")))}</code> and '
                          f'<code data-literal="identifier">{e(str(p.get("b")))}</code> '
                          f'{citer.num(rid, f"pairs.{i}.value", "f2")}'
                          for i, p in flagged[:8])
        note += f'Pairs at or above {level} in size: {items}. '
    else:
        note += f'No pair reaches {level} in size. '
    note += ('The target is not read: this is not a look at the outcome. A flagged pair only '
             'asks whether both predictors are needed.')
    return figure('correlation', values.get('question') or
                  'Which predictors carry nearly the same information?', svg, lg, note)


# --- L6 (R8): two charts of the narrative report, drawn from recorded values only ----------

def fold_scores(citer: cite.Citer, rid: str, selection: Mapping, names: list[str],
                words: Mapping) -> str:
    """The out-of-fold score of each fold, one row per configuration compared
    (``model_selection.configurations.<i>.per_fold``), with the mean of the folds cited.
    ``names`` are the configurations' names in the study language; ``words`` the labels of
    ``narrative.charts``. Empty when fewer than two configurations have their folds."""
    configs = [(i, c) for i, c in enumerate(selection.get('configurations') or [])
               if isinstance(c, Mapping) and isinstance(c.get('per_fold'), list)
               and c['per_fold'] and all(_num(v) for v in c['per_fold']) and _num(c.get('mean'))]
    if len(configs) < 2:
        return ''
    fmt = 'f3' if selection.get('metric') == 'roc_auc' else 'f2'
    every = [v for _, c in configs for v in c['per_fold']]
    pad = (max(every) - min(every)) * 0.08 or 0.01
    scale = Scale(min(every) - pad, max(every) + pad, x1=WIDTH - RIGHT - 10)
    body, y = [], TOP
    for row, (i, c) in enumerate(configs):
        cy = y + 11
        body.append(lit('category', short(names[row] if row < len(names) else c.get('slot')),
                        LEFT - 8, cy + 4, 'end'))
        for j, v in enumerate(c['per_fold']):
            cls = 'pt m' if row == 0 else 'pt'
            body.append(f'<circle class="{cls}" cx="{scale(v):.1f}" cy="{cy}" r="5"/>')
        mx = scale(c['mean'])
        body.append(f'<line class="median" x1="{mx:.1f}" y1="{cy - 11}" x2="{mx:.1f}" '
                    f'y2="{cy + 11}"/>')
        body.append(citer.svg_num(rid, f'model_selection.configurations.{i}.mean', fmt,
                                  x=WIDTH - RIGHT + 4, y=cy + 4))
        y += ROW + 8
    body.insert(0, scale.axis(TOP - 8, y + 2))
    svg = _svg(y + AXIS, ''.join(body), words['folds_label'])
    lg = legend(('pt', words['folds_point']), ('outline', words['folds_mean']))
    return figure('fold_scores', words['folds_question'], svg, lg, e(words['folds_note']))


def nonlinearity(citer: cite.Citer, rid: str, index: int, check: Mapping, words: Mapping,
                 *, binary: bool) -> str:
    """The gap between the observed outcome and the mean prediction in each range of one
    feature (``linear_checks.nonlinearity.<index>.bins``), with plus or minus two standard
    errors drawn: the shape a linear model does not follow. Binary gaps are shown in
    percentage points (``pts1``), regression gaps in the target's unit."""
    bins = [(j, b) for j, b in enumerate(check.get('bins') or [])
            if isinstance(b, Mapping) and _num(b.get('gap')) and _num(b.get('se'))]
    if len(bins) < 2:
        return ''
    k = 100 if binary else 1          # the binary gap is drawn in percentage points
    reach = max(abs(b['gap']) + 2 * b['se'] for _, b in bins) * k * 1.1 or 0.01
    scale = Scale(-reach, reach, x1=WIDTH - RIGHT - 10)
    fmt = 'pts1' if binary else 'f2'
    feature = str(check.get('feature', ''))
    body, y = [], TOP
    x0 = scale(0)
    for j, b in bins:
        cy = y + 11
        low, high = b.get('low'), b.get('high')
        label = (words['range'].format(low=_tick_text(low, False), high=_tick_text(high, False))
                 if _num(low) and _num(high) else str(b.get('bin', '')))
        body.append(lit('category', short(label), LEFT - 8, cy + 4, 'end'))
        gap, se = b['gap'] * k, b['se'] * k
        xa, xb = sorted((x0, scale(gap)))
        body.append(f'<rect class="m" x="{xa:.1f}" y="{cy - 7}" width="{max(1.0, xb - xa):.1f}" '
                    f'height="14" rx="3"/>')
        body.append(f'<line class="ci" x1="{scale(gap - 2 * se):.1f}" y1="{cy}" '
                    f'x2="{scale(gap + 2 * se):.1f}" y2="{cy}"/>')
        base = f'linear_checks.nonlinearity.{index}.bins.{j}.gap'
        body.append(citer.svg_num(rid, base, fmt, x=WIDTH - RIGHT + 4, y=cy + 4))
        y += ROW
    body.append(f'<line class="zero" x1="{x0:.1f}" y1="{TOP - 8}" x2="{x0:.1f}" y2="{y}"/>')
    body.insert(0, scale.axis(TOP - 8, y + 2))
    svg = _svg(y + AXIS, ''.join(body), words['nonlinearity_label'].format(feature=feature))
    bar = f'{words["nonlinearity_bar"]} ({words["points"]})' if binary \
        else words['nonlinearity_bar']
    lg = legend(('m', bar), ('ci', words['nonlinearity_ci']))
    return figure(f'nonlinearity:{feature}',
                  words['nonlinearity_question'].format(feature=feature), svg, lg,
                  e(words['nonlinearity_note']))
