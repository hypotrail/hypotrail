"""Cited numbers: every number a deliverable shows comes from a registry result.

``Citer.num(rid, path, fmt)`` returns one HTML element::

    <data value="0.1153" data-result-id="<rid>" data-path="rate"
          title="result <rid> · rate">11.5%</data>

It refuses (``untraceable_number``) a result id that is unknown, not current, or
failed its integrity check, a path absent from the result, and a value that is not a
number. Renderers never format a number any other way, so ``hypotrail check`` can
verify every number of the HTML report against the registry.

Paths address ``values`` of a result: segments separated by dots, list indices as
integers, and a segment that contains a dot in brackets
(``rules.[threshold:0.3].models.[fit.logistic].precision``). ``@n_rows`` addresses
the entry's ``n_rows``. A list of mappings may also be addressed by the ``rule`` or
``id`` of an item (``rules.[capacity:100]``).

Free-text templates (content files and rendered explanations)::

    {{r:<result_id>.<path>|<fmt>}}   a result by id
    {{slot:<slot>:<path>|<fmt>}}     the current result of a slot (eda.rate_by:<column> too)
    {{fact:<fact id>|<fallback>}}    a case statement, quoted as recorded

Formats: ``int``, ``pct0``-``pct2`` (a fraction shown as a percentage), ``pts0``-``pts2``
(a difference of fractions shown in percentage points), ``f1``-``f4``, ``auto``.

Charts (WP-A6): a value label inside an inline SVG is a ``<text>`` element with the same
``data-result-id``, ``data-path`` and ``data-value`` attributes (:meth:`Citer.svg_num`).
An axis tick is a drawing scale, not a result: it is a ``<text data-literal="axis">``
element, and ``check`` accepts that exemption only inside an ``<svg>`` element.
:func:`parse_numbers` reads numbers back from text for ``check``.

Pure: no file I/O, no pandas, numpy, or scikit-learn.
"""
from __future__ import annotations

import html
import json
import math
import re
from dataclasses import dataclass
from typing import Any, Iterator, Mapping

from .errors import StudyError

FORMATS = ('int', 'pct0', 'pct1', 'pct2', 'f1', 'f2', 'f3', 'f4', 'auto')
# ``pts<d>`` (WP-A6, the HTML report only; the companion mirrors :data:`FORMATS`): a
# difference of two fractions shown in percentage points, without a percent sign ("29.5"
# points for 0.295). The element carries ``data-scale="100"`` so ``check`` compares the
# shown text with the registry value times 100.
SCALED_FORMATS = {'pts0': 100, 'pts1': 100, 'pts2': 100}
REPORT_FORMATS = FORMATS + tuple(SCALED_FORMATS)
META_PATHS = ('@n_rows',)
TEMPLATE = re.compile(r'\{\{(r|slot|fact):([^{}|]+?)(?:\|([^{}]*))?\}\}')
_SEGMENT = re.compile(r'\[([^\]]+)\]|([^.\[\]]+)')

# A number in prose: thousands with comma groups ("3,164", and with decimals "3,842.8", as
# :func:`fmt_number` writes a value of 1,000 or more), a decimal with a dot or a
# comma ("0.115", "0,115"), an integer; an optional percent sign. A number glued to a
# letter or an underscore ("pct1", "x_2", "3f9a") is part of a word, not a number. A minus
# sign glued to the digits makes the number negative ("-1", a sentinel); "10-18" is two numbers.
# The minus may be the hyphen-minus or the Unicode minus sign U+2212 ("−0.99").
# WP-H3: French groups thousands with a space, a no-break space or a narrow no-break space
# ("37 062", "37 062,5"); such a group is one number, its decimals after a comma.
_SPACE = '[ \u00a0\u202f\u2009]'
NUMBER = re.compile(r'(?<![\w.])([-\u2212](?=\d))?([1-9]\d{0,2}(?:,\d{3})+(?:\.\d+)?|'
                    rf'[1-9]\d{{0,2}}(?:{_SPACE}\d{{3}})+(?!\d|\.\d|,\d{{3}})(?:,\d+)?|'
                    r'\d+(?:[.,]\d+)?)'
                    r'(?![\w])(\s?%)?')
SPACE_GROUPED = re.compile(rf'[1-9]\d{{0,2}}(?:{_SPACE}\d{{3}})+(?:,(\d+))?')


def untraceable(message: str, **details) -> StudyError:
    return StudyError('untraceable_number', message, details=details)


# --- paths ------------------------------------------------------------------------------

def parse_path(path: str) -> list[str]:
    if not isinstance(path, str) or not path:
        raise untraceable('A cited number needs a value path.', path=path)
    if path in META_PATHS:
        return [path]
    segments, pos = [], 0
    for m in _SEGMENT.finditer(path):
        if m.start() != pos and path[pos:m.start()] != '.':
            raise untraceable(f'Malformed value path {path!r}.', path=path)
        segments.append(m.group(1) if m.group(1) is not None else m.group(2))
        pos = m.end()
    if pos != len(path) or not segments:
        raise untraceable(f'Malformed value path {path!r}.', path=path)
    return segments


def format_path(segments) -> str:
    out = []
    for s in segments:
        s = str(s)
        out.append(f'[{s}]' if ('.' in s or '[' in s or ']' in s) else s)
    return '.'.join(out)


def resolve(values: Any, segments: list[str], *, n_rows: Any = None) -> Any:
    """The value at ``segments`` inside ``values``; KeyError when absent."""
    if segments == ['@n_rows']:
        if n_rows is None:
            raise KeyError('@n_rows')
        return n_rows
    node = values
    for seg in segments:
        if isinstance(node, Mapping):
            if seg not in node:
                raise KeyError(seg)
            node = node[seg]
        elif isinstance(node, list):
            if seg.isdigit() and int(seg) < len(node):
                node = node[int(seg)]
                continue
            match = [item for item in node if isinstance(item, Mapping)
                     and seg in (str(item.get('rule')), str(item.get('id')))]
            if len(match) != 1:
                raise KeyError(seg)
            node = match[0]
        else:
            raise KeyError(seg)
    return node


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) \
        and math.isfinite(value)


def leaves(values: Any, prefix: tuple = ()) -> Iterator[tuple[tuple, float]]:
    """Every numeric leaf of ``values`` as ``(segments, value)``."""
    if is_number(values):
        yield prefix, values
    elif isinstance(values, Mapping):
        for k in sorted(values, key=str):
            yield from leaves(values[k], prefix + (str(k),))
    elif isinstance(values, list):
        for i, v in enumerate(values):
            yield from leaves(v, prefix + (str(i),))


# --- formatting -------------------------------------------------------------------------

def fmt_number(value: float, fmt: str = 'auto') -> str:
    if fmt not in REPORT_FORMATS:
        raise untraceable(f'Unknown number format {fmt!r}.', fmt=fmt,
                          formats=list(REPORT_FORMATS))
    if fmt == 'int':
        return f'{round(value):,}'
    if fmt.startswith('pct'):
        return f'{100 * value:.{int(fmt[3:])}f}%'
    if fmt.startswith('pts'):
        return f'{100 * value:.{int(fmt[3:])}f}'
    if fmt.startswith('f'):
        return f'{value:.{int(fmt[1:])}f}'
    if float(value).is_integer():
        return f'{int(value):,}'
    if abs(value) >= 100:
        return f'{value:,.1f}'
    if abs(value) >= 1:
        return f'{value:.2f}'
    return f'{value:.3f}'


@dataclass(frozen=True)
class Token:
    """A number read from text: its characters, value, decimals, and percent sign."""

    text: str
    value: float
    decimals: int
    percent: bool
    start: int
    end: int


def parse_numbers(text: str) -> list[Token]:
    out = []
    for m in NUMBER.finditer(text):
        sign, body, pct = (-1.0 if m.group(1) else 1.0), m.group(2), bool(m.group(3))
        grouped = re.fullmatch(r"[1-9]\d{0,2}(?:,\d{3})+(?:\.(\d+))?", body)
        spaced = SPACE_GROUPED.fullmatch(body)
        if grouped:
            value = float(body.replace(',', ''))
            decimals = len(grouped.group(1) or '')
        elif spaced:
            value = float(re.sub(_SPACE, '', body).replace(',', '.'))
            decimals = len(spaced.group(1) or '')
        else:
            norm = body.replace(',', '.')
            value = float(norm)
            decimals = len(norm.split('.')[1]) if '.' in norm else 0
        value *= sign
        out.append(Token(m.group(0), value, decimals, pct, m.start(), m.end()))
    return out


def shown_matches(token: Token, value: float, scale: float = 1) -> bool:
    """True when ``token`` is ``value`` (times ``scale``) written at the token's precision."""
    if not is_number(value):
        return False
    value = value * scale
    scaled = 100 * value if token.percent else value
    return abs(round(scaled, token.decimals) - token.value) < 10 ** -(token.decimals + 6) \
        or abs(scaled - token.value) <= 0.5 * 10 ** -token.decimals + 1e-12


# --- citing -----------------------------------------------------------------------------

@dataclass(frozen=True)
class Cited:
    result_id: str
    slot: str | None
    values: Any
    n_rows: Any
    current: bool
    integrity: str


class Citer:
    """Cites numbers from a fixed set of results (a view, or frozen registry entries)."""

    def __init__(self, results: Mapping[str, Cited], facts: Mapping[str, str] | None = None):
        self.results = dict(results)
        self.by_slot = {c.slot: rid for rid, c in self.results.items() if c.slot}
        self.facts = dict(facts or {})
        self.cited: list[dict] = []

    @classmethod
    def from_view(cls, view: Mapping) -> 'Citer':
        results = {}
        for slot, item in view['results'].items():
            results[item['result_id']] = Cited(item['result_id'], slot, item['values'],
                                               item['n_rows'], bool(item['current']),
                                               item['integrity'])
        facts = {f['id']: f['value'] for items in view['facts']['by_status'].values()
                 for f in items}
        return cls(results, facts)

    def citable(self, rid: str | None) -> bool:
        c = self.results.get(rid) if rid else None
        return c is not None and c.current and c.integrity == 'ok'

    def slot_rid(self, slot: str) -> str | None:
        rid = self.by_slot.get(slot)
        return rid if self.citable(rid) else None

    def has(self, rid: str, path: str) -> bool:
        try:
            self.lookup(rid, path)
        except StudyError:
            return False
        return True

    def lookup(self, rid: str, path: str) -> float:
        c = self.results.get(rid)
        if c is None:
            raise untraceable(f'Result {rid} is not part of this view; its numbers cannot be cited.',
                              result_id=rid, path=path)
        if not (c.current and c.integrity == 'ok'):
            raise untraceable(f'Result {rid} is not current (or failed its integrity check); its '
                              f'numbers cannot be cited.', result_id=rid, path=path,
                              integrity=c.integrity)
        try:
            value = resolve(c.values, parse_path(path), n_rows=c.n_rows)
        except KeyError:
            raise untraceable(f'Result {rid} has no value at {path!r}.', result_id=rid,
                              path=path) from None
        if not is_number(value):
            raise untraceable(f'The value at {path!r} of result {rid} is not a number.',
                              result_id=rid, path=path)
        return value

    def num(self, rid: str, path: str, fmt: str = 'auto') -> str:
        value = self.lookup(rid, path)
        text = fmt_number(value, fmt)
        self.cited.append({'result_id': rid, 'path': path, 'value': value, 'text': text})
        scale = (f' data-scale="{SCALED_FORMATS[fmt]}"' if fmt in SCALED_FORMATS else '')
        return (f'<data value="{html.escape(json.dumps(value))}" '
                f'data-result-id="{html.escape(rid)}" data-path="{html.escape(path)}"{scale} '
                f'title="result {html.escape(rid)} · {html.escape(path)}">{html.escape(text)}</data>')

    def value(self, rid: str, path: str) -> float:
        """The number at ``path`` (for drawing a mark; a shown number goes through
        :meth:`num` or :meth:`svg_num`)."""
        return self.lookup(rid, path)

    def svg_num(self, rid: str, path: str, fmt: str = 'auto', *, x: float, y: float,
                anchor: str = 'start', cls: str = 'val', prefix: str = '',
                suffix: str = '') -> str:
        """A cited value label of an inline SVG chart: a ``<text>`` element with
        ``data-result-id``, ``data-path`` and ``data-value``. ``prefix`` and ``suffix`` are
        words without digits."""
        value = self.lookup(rid, path)
        text = fmt_number(value, fmt)
        self.cited.append({'result_id': rid, 'path': path, 'value': value, 'text': text})
        scale = (f' data-scale="{SCALED_FORMATS[fmt]}"' if fmt in SCALED_FORMATS else '')
        return (f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" class="{cls}" '
                f'data-value="{html.escape(json.dumps(value))}" '
                f'data-result-id="{html.escape(rid)}" data-path="{html.escape(path)}"{scale}>'
                f'{html.escape(prefix)}<tspan>{html.escape(text)}</tspan>'
                f'{html.escape(suffix)}</text>')

    def fact(self, fact_id: str, fallback: str) -> str:
        value = self.facts.get(fact_id)
        if value is None:
            return html.escape(fallback)
        return f'<q data-literal="case" data-fact="{html.escape(fact_id)}">{html.escape(str(value))}</q>'

    def expand(self, template: str) -> str:
        """HTML of a free-text template: text escaped, references cited (or refused)."""
        out, pos = [], 0
        for m in TEMPLATE.finditer(template):
            out.append(html.escape(template[pos:m.start()]))
            kind, ref, arg = m.group(1), m.group(2).strip(), m.group(3)
            if kind == 'fact':
                out.append(self.fact(ref, arg or ''))
            elif kind == 'r':
                rid, _, path = ref.partition('.')
                out.append(self.num(rid, path, arg or 'auto'))
            else:
                slot, path = self.split_slot_ref(ref)
                rid = self.slot_rid(slot)
                if rid is None:
                    raise untraceable(f'No current result in slot {slot!r} to cite.', slot=slot,
                                      path=path)
                out.append(self.num(rid, path, arg or 'auto'))
            pos = m.end()
        out.append(html.escape(template[pos:]))
        return ''.join(out)

    def ready(self, template: str) -> bool:
        """True when every ``{{slot:...}}`` of ``template`` names a citable slot.

        A template whose slots are not computed yet is shown as pending. Any other
        problem (an unknown result id, a missing path, a bad format) is not hidden:
        :meth:`expand` refuses it with ``untraceable_number``.
        """
        return all(self.slot_rid(self.split_slot_ref(m.group(2).strip())[0]) is not None
                   for m in TEMPLATE.finditer(template) if m.group(1) == 'slot')

    def split_slot_ref(self, ref: str) -> tuple[str, str]:
        """``(slot, path)`` of a ``{{slot:...}}`` reference. A slot may itself hold a colon
        (``eda.rate_by:<column>``): the longest known slot that prefixes ``ref`` wins."""
        for slot in sorted((s for s in self.by_slot if s), key=len, reverse=True):
            if ref.startswith(slot + ':'):
                return slot, ref[len(slot) + 1:]
        slot, _, path = ref.partition(':')
        return slot, path
