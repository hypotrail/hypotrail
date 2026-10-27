"""Texts of the lesson-style report and the guided reading of each figure (owner decision
2026-10-27, R27 to R30).

Every text comes from ``content/lesson.yaml`` (:func:`mlkit.study.texts.lesson`), in the
language of the edition being written (:func:`mlkit.study.texts.report_language`); no prose is
written here. A text holds named placeholders (``{name}``) that the renderer fills with HTML
it built: cited registry values (:meth:`mlkit.study.cite.Citer.num`) or recorded literals
(``data-literal``). The text around them is escaped; ``<b>`` and ``<i>`` of the content file
are kept.

:func:`frame` wraps a figure or a table of the report in a graph-paper frame (R30): above it,
"Why this chart" with its frame line (development or final evidence, the rows, the model);
below it, "How to read it" step by step, "What we conclude" with the cited values, and "Watch
out" when a reading trap exists.

Pure: no pandas, numpy, or scikit-learn.
"""
from __future__ import annotations

import html
import re
from typing import Any, Iterable, Mapping

from . import cite, texts

e = html.escape
_PLACEHOLDER = re.compile(r'\{([a-z_][a-z0-9_]*)\}')
_KEPT_TAGS = (('&lt;b&gt;', '<b>'), ('&lt;/b&gt;', '</b>'), ('&lt;i&gt;', '<i>'),
              ('&lt;/i&gt;', '</i>'))


def _escape(text: str) -> str:
    out = e(text, quote=False)
    for escaped, tag in _KEPT_TAGS:
        out = out.replace(escaped, tag)
    return out


def fill(text: str, values: Mapping[str, str] | None = None) -> str:
    """``text`` escaped, each ``{name}`` replaced by ``values[name]`` (HTML, not escaped).
    KeyError for a placeholder without a value: a text never shows a raw placeholder."""
    values = values or {}
    out, pos = [], 0
    for m in _PLACEHOLDER.finditer(text):
        out.append(_escape(text[pos:m.start()]))
        out.append(str(values[m.group(1)]))
        pos = m.end()
    out.append(_escape(text[pos:]))
    return ''.join(out)


def language() -> str:
    return texts.report_language()


def say(path: str) -> str:
    """The plain text at ``path`` in the edition's language (not escaped)."""
    return texts.say(texts.lesson(path))


def has(path: str) -> bool:
    return texts.has_lesson(path)


def t(path: str, **values: str) -> str:
    """The HTML of the text at ``path``, filled with ``values``."""
    return fill(say(path), values)


def items(path: str) -> list[str]:
    """The texts of a list at ``path`` (each ``{en, fr}``), in the edition's language."""
    if not has(path):
        return []
    return [texts.say(node) for node in texts.lesson(path) or []]


def lit(kind: str, text: Any, tag: str = 'span') -> str:
    from .render_html import lit as html_lit
    return html_lit(kind, text, tag)


def count(kind: str, value: Any) -> str:
    """A recorded count (``structure``, ``decision_value``, ``ordinal``) in the edition's
    number format."""
    if cite.is_number(value):
        return lit(kind, cite.format_value(value, 'int', language()))
    return lit(kind, '' if value is None else value)


def ordinal(value: Any) -> str:
    return lit('ordinal', value)


def stamp(kind: str) -> str:
    return f'<span class="stamp {e(kind)}">{e(say("ui.stamps." + kind))}</span>'


def evidence_badge(kind: str) -> str:
    return (f'<span class="evb ev-{e(kind)}" data-evidence-label="{e(kind)}">'
            f'{e(say("ui.evidence." + kind))}</span>')


# --- figures -----------------------------------------------------------------------------------

class Numbering:
    """Figure numbers of one edition: ``<chapter>.<k>``, or ``V`` in the verdict."""

    def __init__(self):
        self.next: dict[str, int] = {}

    def take(self, chapter: str) -> str:
        if chapter == 'verdict':
            return 'V'
        k = self.next.get(chapter, 0) + 1
        self.next[chapter] = k
        return f'{chapter[2:]}.{k}'


def frame_line(evidence: str, rows: str = '', scored: str = '', model: str = '',
               final_note: bool = True) -> str:
    """The frame of a figure: the evidence class, the rows, how they were predicted, the
    model, and (development evidence) that the final test is not in it."""
    parts = [e(say(f'ui.frame_words.{evidence}'))]
    if rows:
        parts.append(rows)
    if scored:
        parts.append(e(scored))
    if model:
        parts.append(model)
    if evidence == 'development' and final_note:
        parts.append(e(say('ui.frame_words.no_final')))
    return ' · '.join(parts)


def rows_words(n_html: str) -> str:
    return t('ui.frame_words.rows', n=n_html)


def _pick(kind: str, key: str, variant: str | None) -> str | None:
    """The path of ``figures.<kind>.<key>_<variant>`` when it exists, else of
    ``figures.<kind>.<key>``, else None."""
    if variant and has(f'figures.{kind}.{key}_{variant}'):
        return f'figures.{kind}.{key}_{variant}'
    if has(f'figures.{kind}.{key}'):
        return f'figures.{kind}.{key}'
    return None


def frame(numbering: Numbering, chapter: str, kind: str, body: str, *,
          values: Mapping[str, str] | None = None, frame_html: str = '',
          conclude: str | None = None, attention: str | None = None,
          extra_attention: str = '', stamp_kind: str = 'real', what: str = 'chart',
          slot: str | None = None, evidence: str | None = None, title_values=None,
          figure_id: str | None = None, variant: str | None = None) -> str:
    """A figure or a table of the report in its graph-paper frame, with its guided reading.

    ``values`` fill the ``conclude`` and ``attention`` texts of ``figures.<kind>`` (and its
    title); ``conclude`` and ``attention`` name a variant (``conclude_<variant>``), or
    ``'none'`` to leave the part out; ``variant`` picks ``title_<variant>`` and
    ``read_<variant>`` when they exist (the final test once opened). ``extra_attention`` is HTML appended to the "Watch
    out" block (the tension of the model choice). ``slot`` and ``evidence`` mark the frame
    with the result it draws (``data-for-slot``, ``data-evidence-class``)."""
    values = dict(values or {})
    number = numbering.take(chapter)
    label = say('ui.' + {'chart': 'figure', 'table': 'table', 'list': 'list'}[what])
    title = fill(say(_pick(kind, 'title', variant)), title_values or values)
    why_head = say('ui.' + {'chart': 'why_chart', 'table': 'why_table', 'list': 'why_list'}[what])
    fid = figure_id or f'fig-{number.replace(".", "-")}'
    attrs = f' id="{e(fid)}" data-figure="{e(kind)}"'
    if evidence:
        attrs += f' data-evidence-class="{e(evidence)}"'
    if slot:
        attrs += f' data-for-slot="{e(slot)}"'
    parts = [f'<div class="frame"{attrs}>',
             f'<div class="head"><div class="lbl">{e(label)} {ordinal(number)} — {title}</div>'
             f'{stamp(stamp_kind)}</div>',
             f'<div class="pq"><span class="k">{e(why_head)}</span>'
             f'<p>{t(f"figures.{kind}.why")}</p>']
    if frame_html:
        parts.append(f'<p class="fm"><b>{e(say("ui.frame_label"))}</b> : {frame_html}</p>'
                     if language() == 'fr' else
                     f'<p class="fm"><b>{e(say("ui.frame_label"))}</b>: {frame_html}</p>')
    parts.append('</div>')
    parts.append(f'<div class="fbody">{body}</div>')
    steps = items(_pick(kind, 'read', variant) or f'figures.{kind}.read')
    if steps:
        parts.append(f'<details class="f lire" open><summary>{e(say("ui.how_to_read"))} '
                     f'<small>{e(say("ui.step_by_step"))}</small></summary><div class="in"><ol>'
                     + ''.join(f'<li>{fill(s)}</li>' for s in steps) + '</ol></div></details>')
    if conclude != 'none':
        path = _pick(kind, 'conclude', conclude)
        if path:
            parts.append(f'<div class="concl"><span class="k">{e(say("ui.conclude"))}</span>'
                         f'<p>{fill(say(path), values)}</p></div>')
    attn = ''
    if attention != 'none':
        path = _pick(kind, 'attention', attention)
        if path:
            attn = f'<p>{fill(say(path), values)}</p>'
    if extra_attention:
        attn += extra_attention
    if attn:
        parts.append(f'<div class="attn"><span class="k">{e(say("ui.attention"))}</span>'
                     f'{attn}</div>')
    parts.append('</div>')
    return ''.join(parts)


def dl(rows: Iterable[tuple[str, str]], cls: str = '') -> str:
    rows = list(rows)
    if not rows:
        return ''
    klass = f' class="{cls}"' if cls else ''
    return (f'<dl{klass}>' + ''.join(f'<dt>{k}</dt><dd>{v}</dd>' for k, v in rows)
            + '</dl>')
