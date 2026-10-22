"""``hypotrail check``: number traceability and wording checks (plan WP3.3).

    hypotrail check --study DIR               # the rendered deliverables and the study
    hypotrail check --study DIR --text PATH   # a draft message (``-`` reads stdin)

Findings (``severity`` is ``error`` or ``warning``):

=========================  ========  ==============================================
code                       severity  meaning
=========================  ========  ==============================================
``number_outside_result``  error     a number in a text node of the HTML report or of
                                     a notebook Markdown cell that is not a cited
                                     ``<data data-result-id>`` value or SVG ``<text
                                     data-result-id>`` label (revisions, step
                                     ordinals and other recorded literals, marked
                                     ``data-literal``, are exempt; an axis tick,
                                     ``data-literal="axis"``, only inside ``<svg>``)
``unknown_result_id``      error     a cited result id that the registry does not hold
``value_mismatch``         error     a cited value or its displayed text differs from
                                     the registry value at that path
``stale_result_cited``     error     a cited result that is no longer current
``feature_without_status`` error     a feature used by a current fit without a
                                     confirmed availability status
``excluded_feature_used``  error     a feature used by a current fit although it was
                                     decided not available (or uncertain, excluded)
``untraceable_number``     error     a number in a draft message (``--text``) or in
                                     the conclusion that matches no current registry
                                     value at its displayed precision, nor a decision
                                     value, a setting, or a case statement
``stale_number``           error     such a number matches only a stale result
``causal_wording``         warning   causal language ("causes", "leads to", "drives")
                                     outside a negation
``forecast_wording``       warning   a figure phrased as a forecast ("expect", "will
                                     get", "we will", "per 10 calls you will") — E1
                                     finding F4: validation figures are not forecasts
``artifact_not_current``   warning   a deliverable is stale, failed, or not rendered
``untracked_files``        warning   scripts or data files in the study folder outside
                                     the generated notebooks and the declared case and
                                     dataset files — E1 finding F3: computations
                                     outside ``hypotrail`` are invisible
=========================  ========  ==============================================

Matching a number (E1 finding F5): a number written with ``d`` decimals matches a
registry value that rounds to it at ``d`` decimals (a percentage matches a fraction
times 100; "percentage points" match only a registered difference, ``deltas``, times
100). Matches report the ``result_id`` and path they were traced to, so a reviewer sees
what a number stands for. A number may also repeat a recorded literal: a decision or
proposal value, a rule of the current policy evaluation, the junior's recorded words, a
setting, a case statement, or text the junior wrote, passed with ``--allow-user-text``.
Numbers following "revision" (with the comparison that follows it: "revision 26 instead
of 24"), "step", "pause", "proposal", or "exit", list markers, and ISO dates are exempt.
A rule identifier (``capacity:100``) is never reported. Nor is a result id prefix made only
of digits (R3): a run of 6 or more digits that follows "result", "result_id", "rid",
"id", or "execution" ("(result 52659681)"), or that begins a ``result_id`` of the
registry; a number that traces to a figure is still traced as that figure. A minus sign
may be ``-`` or the Unicode minus U+2212.

v0.3 (WP-A): the tracing core lives in :mod:`mlkit.study.numtrace`, shared with ``decide
propose`` (a text one accepts, the other accepts). A bare "points" is percentage points too;
a sentence that names a result (a slot such as ``diag.binary``, a result id or its prefix) or
a group label binds its numbers to it, and ``--result RESULT`` binds the whole draft; a
diagnostic's segment figures are citable with their group named.

Numbers written in words (final acceptance F3, :mod:`mlkit.study.wordnum`): in a draft
(``--text``) and in the conclusion, common English and French forms used quantitatively
("one call in nine", "un sur neuf", "the eleven kept columns", "three quarters of the
rows", "half of the clients", "a dozen calls", "eleven percent", and, in a regression
study, a number followed by the target unit: "about six litres") are traced like digits,
and reported as ``untraceable_number`` (``details.in_words`` true) when they match no
registered value. "One model", "a single", "first" are not numbers. Figures of withdrawn
or superseded proposals are never literals: a number that repeats one stays
``untraceable_number`` and names that proposal (``details.retired_proposal``). The HTML
report and the notebook are generated from cited values and are not scanned for words.

Counts of the study's own structure (post-v0.1 fixes, D8): a count, in digits or in
words, directly followed (at most one word between) by a structural noun is traced to the
matching count of the view: "columns", "features", "variables", "inputs" to the length of
a current result's ``features`` list or a count of the feature availability (every
feature, each status, the usable ones, the excluded ones); "groups" to the length of a
current result's ``groups`` list; "steps", "pauses", "decisions" to the plan. The trace's
``source`` is ``structure``. A count that matches no such figure stays
``untraceable_number``, and the same count before any other noun is not traced this way
("the seven columns we kept" is traced when the fit uses seven features; "seven calls" is
not).

Locations (CLI-CONTRACT-COMPANION C10): a finding about a file carries ``location``,
``{path, anchor, line}``, after ``details``: the study-relative path (a ``--text`` file
outside the study keeps its resolved path; stdin has none), the nearest enclosing ``id``
of the HTML report, and the 1-based line. ``where`` is unchanged, and a finding about a
result or a decision has no location. :func:`check_text` (frozen) adds none.

The command always exits 0 with ``clean`` true or false; it never writes.
No pandas, numpy, or scikit-learn.
"""
from __future__ import annotations

import argparse
import ast
import dataclasses
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable, Mapping

from . import cite, governance, manifest as mf, numtrace, read, view as view_model, wordnum
from . import commands as cmd
from .errors import StudyError
from .numtrace import (  # noqa: F401 - the tracing core, re-exported
    SEVERITY, FINDING_CODES, EXEMPT_BEFORE, REVISION_SPAN, RULE_IDENTIFIER, RESULT_ID_DIGITS,
    RESULT_ID_LEAD, PERCENTAGE_POINTS, LIST_MARKER, ISO_DATE, HEADING_ORDINAL, STRUCTURE_NOUNS,
    _STRUCTURE_NOUN, STRUCTURE_AFTER, USABLE_STATUSES, EXCLUDED_STATUSES, finding,
    LOCATION_KEYS, location, _walk_numbers, INTERNAL_SEGMENTS, INTERNAL_BY_SLOT, METRIC_WORDS,
    RATE_WORDS, RATE_SEGMENTS, COUNT_NOUNS, COUNT_SEGMENTS, internal_path, DIAGNOSTIC_SLOTS,
    INTERVAL_WORDS, MODEL_WORDS, RANGE_AFTER, RANGE_BEFORE, BASELINE_WORDS, INTERVAL_PARENTS,
    SENTENCE_END, FINAL_SCOPE, DEVELOPMENT_SCOPE, FINAL_SLOTS, RULE_WORDS, DIAG_BOUNDS,
    CHOICE_CHANGES, Binding, scope_of, final_item, _sentence_around, binding, _bound,
    group_labels, CRITERION_FIGURES, criterion_items, _is_difference, Pool, data_card_figures,
    _rule_spaced, _retired_note, _masked, _exempt, _result_id_prefix, _trace_words, trace_text,)

SCHEMA = 'hypotrail.check/1'

NEGATION = re.compile(r"\b(not|no|never|cannot|can't|cannot|doesn't|don't|isn't|aren't|without|"
                      r"neither|nor)\b", re.IGNORECASE)
NEGATED_AFTER = re.compile(r"\s*(?:not|never)\b", re.IGNORECASE)
# "The effect of X is not measured": a causal phrase that the sentence itself denies.
UNESTABLISHED = re.compile(r"\b(?:is|are|was|were|has|have)(?: been)? (?:not|never)|"
                           r"\b(?:isn't|aren't|wasn't|weren't|hasn't|haven't)\b|\bunknown\b|"
                           r"\bnot (?:measured|shown|established|known|estimated|tested)\b",
                           re.IGNORECASE)
CAUSAL = re.compile(
    r"\b(causes?|caused|causing|causal(?:ly)?|leads? to|led to|drives?|driven by|due to|"
    r"because of|impacts?|effect of|makes? \w+ (?:more|less) likely|"
    r"(?:increases?|raises?|reduces?|lowers?) the (?:chance|probability|likelihood|odds))\b",
    re.IGNORECASE)
FORECAST = re.compile(
    r"\b(expect(?:s|ed|ing)?(?! value)(?! (?:for|under|by|from) )|will (?:get|reach|bring|convert|subscribe|renew|yield|"
    r"deliver|find|see|have|make|gain|win|sign)|we will|you will|we'll|you'll|"
    r"should (?:reach|get|bring|yield|convert)|(?:is|are) going to|guarantee[sd]?|"
    r"in (?:the )?future|(?:next|coming|upcoming) (?:rounds?|waves?|periods?|months?|quarters?|years?))\b",
    re.IGNORECASE)
# P7: a recommended default is always the assistant's. A text that credits it to the
# analyst ("followed the analyst's recommended defaults") misreports a delegation.
MISATTRIBUTED_DEFAULT = re.compile(
    r"\b(?:analyst|junior|user|trainee)(?:'s|s'|\u2019s)?\s+(?:own\s+)?(?:recommended\s+)?"
    r"(?:defaults?|default\s+choices?|recommendations?)\b"
    r"|\b(?:defaults?|recommendations?)\s+(?:recommended|chosen|proposed|set|picked)\s+by\s+"
    r"(?:the\s+)?(?:analyst|junior|user|trainee)\b",
    re.IGNORECASE)
SENTENCE = re.compile(r'(?<=[.!?])\s+|\n+')
INLINE_CODE = re.compile(r'`[^`\n]*`')
# The default folder of ``hypotrail export handoff`` (CLI-CONTRACT-COMPANION C7): its
# files are the engine's own output, not computations outside hypotrail.
HANDOFF_DIR = 'handoff'
SCRIPT_SUFFIXES = {'.py', '.ipynb', '.r', '.sql', '.csv', '.parquet', '.xlsx', '.json', '.pkl'}
OWN_NOTEBOOKS = re.compile(r'^notebooks/(study_generated(\.user-edits-[^/]+)?|workbench(\.candidate)?)\.py$')
# ``__marimo__`` is Marimo's cache and ``.vscode`` holds the editor settings ``init`` writes
# (R7, v0.2a): neither is a computation outside hypotrail.
IGNORED_DIRS = {'.hypotrail', '__marimo__', '__pycache__', '.claude', '.github', '.git',
                'reports', '.venv', '.vscode'}


def _text_locator(path: str | None, text: str, first_line: int = 1):
    """A function from an offset of ``text`` to its location (``line`` counted from
    ``first_line``)."""
    def locate(offset: int) -> dict:
        return location(path, None, first_line + text.count('\n', 0, max(0, offset)))
    return locate


def _code_masked(text: str) -> tuple[str, list[int]]:
    """``INLINE_CODE.sub(' ', text)`` and, for each of its positions, the offset in
    ``text`` it comes from (so a finding in the masked text is located in the original)."""
    out, index, pos = [], [], 0
    for m in INLINE_CODE.finditer(text):
        out.append(text[pos:m.start()])
        index.extend(range(pos, m.start()))
        out.append(' ')
        index.append(m.start())
        pos = m.end()
    out.append(text[pos:])
    index.extend(range(pos, len(text)))
    index.append(len(text))
    return ''.join(out), index


def _sentences(text: str):
    """``(offset, sentence)`` of each piece of ``SENTENCE.split(text)``."""
    pos = 0
    for m in SENTENCE.finditer(text):
        yield pos, text[pos:m.start()]
        pos = m.end()
    yield pos, text[pos:]


def wording(text: str, where: str, locate=None) -> list[dict]:
    """Causal and forecast wording, sentence by sentence (code spans ignored). ``locate``
    (optional) maps an offset of ``text`` to the ``location`` of a finding (C10)."""
    out = []
    masked, index = _code_masked(text)
    for start, sentence in _sentences(masked):
        lead = start + len(sentence) - len(sentence.lstrip())
        sentence = sentence.strip()
        if not sentence:
            continue

        def at(m):
            return locate(index[lead + m.start()]) if locate else None
        m = CAUSAL.search(sentence)
        if m and not NEGATION.search(sentence[:m.start()]) \
                and not UNESTABLISHED.search(sentence[m.end():]):
            out.append(finding('causal_wording', where,
                               'Causal wording: the study shows associations and rankings, not '
                               'effects of acting.', phrase=m.group(0), sentence=sentence,
                               location=at(m)))
        m = FORECAST.search(sentence)
        has_number = bool(cite.parse_numbers(_masked(sentence))) or '\x00num' in sentence \
            or bool(wordnum.parse(sentence))
        if m and has_number and not NEGATION.search(sentence[:m.start()]) \
                and not NEGATED_AFTER.match(sentence[m.end():]):
            out.append(finding('forecast_wording', where,
                               'A figure is phrased as a forecast. Validation figures describe '
                               'past rows after a choice made on them; say so instead.',
                               phrase=m.group(0), sentence=sentence.replace('\x00num', '#'),
                               location=at(m)))
    return out


def attribution(text: str, where: str, locate=None) -> list[dict]:
    """P7: a recommended default credited to the analyst instead of the assistant."""
    masked, index = _code_masked(text)
    return [finding('misattributed_delegation', where,
                    'A recommended default is the assistant\'s: write "the assistant\'s '
                    'recommended default, delegated by the analyst", never the analyst\'s '
                    'default or choice.', phrase=m.group(0),
                    location=locate(index[m.start()]) if locate else None)
            for m in MISATTRIBUTED_DEFAULT.finditer(masked)]


def check_text(view: Mapping, text: str, where: str = 'text', user_texts: Iterable[str] = (),
               result_ids: Iterable[str] | None = None) -> tuple[list[dict], list[dict]]:
    return _check_text(view, text, where, user_texts, result_ids)


def _check_text(view: Mapping, text: str, where: str = 'text', user_texts: Iterable[str] = (),
                result_ids: Iterable[str] | None = None,
                retired: Iterable[Mapping] = (), locate=None,
                data_card: Mapping | None = None) -> tuple[list[dict], list[dict]]:
    findings, traced = trace_text(Pool(view, user_texts, result_ids, retired, data_card),
                                  text, where, locate)
    return (findings + wording(text, where, locate) + attribution(text, where, locate),
            traced)


def retired_proposals(study: read.Study) -> list[dict]:
    """Withdrawn and superseded proposals of the study (F3): their figures are not
    literals; a finding names the proposal when a draft repeats one of them."""
    proposals = study.state.get('proposals') or {}
    return [{'proposal_id': p.get('proposal_id', pid), 'status': p.get('status'),
             'value': p.get('value')}
            for pid, p in sorted(proposals.items())
            if isinstance(p, Mapping) and p.get('status') in ('withdrawn', 'superseded')]


# --- HTML -------------------------------------------------------------------------------

BLOCK_TAGS = {'p', 'li', 'td', 'th', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'div', 'dt', 'dd',
              'summary', 'section', 'article', 'header', 'footer', 'main', 'tr', 'ul', 'ol',
              'table', 'details', 'br'}
SKIP_TAGS = {'script', 'style', 'head', 'title'}
# Recorded third-party or technical text: not checked for wording (the case documentation
# and identifiers are quoted, not claimed). The user's words and the conclusion are checked.
QUOTED_KINDS = {'case', 'identifier', 'environment', 'parameter', 'category'}
VOID_TAGS = {'br', 'meta', 'link', 'img', 'hr', 'input', 'wbr', 'source', 'col', 'area', 'base'}


class _Report(HTMLParser):
    """Text nodes, cited ``<data>`` elements, and wording blocks of a report, each with the
    nearest enclosing ``id`` and its line (the ``location`` of a finding, C10)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, dict]] = []
        self.texts: list[tuple[str, bool]] = []      # (text node, exempt)
        self.places: list[tuple[str | None, int]] = []   # (anchor, line) of each text node
        self.data: list[dict] = []
        self.blocks: list[str] = []
        self.block_places: list[tuple[str | None, int]] = []
        self._block: list[str] = []
        self._block_place: tuple[str | None, int] | None = None

    def anchor(self) -> str | None:
        """The ``id`` of the nearest enclosing element that has one."""
        for _, attrs in reversed(self.stack):
            if attrs.get('id'):
                return attrs['id']
        return None

    def _place(self) -> tuple[str | None, int]:
        return self.anchor(), self.getpos()[0]

    def _flush(self):
        text = ''.join(self._block).strip()
        if text:
            self.blocks.append(text)
            self.block_places.append(self._block_place or (None, None))
        self._block = []
        self._block_place = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in BLOCK_TAGS:
            self._flush()
        if tag in VOID_TAGS:
            return
        self.stack.append((tag, attrs))
        # A cited number is a ``<data>`` element, or (WP-A6) an SVG ``<text>`` value label
        # carrying the same attributes.
        if tag == 'data' or 'data-result-id' in attrs:
            anchor, line = self._place()
            self.data.append({'attrs': attrs, 'text': '', 'anchor': anchor, 'line': line})

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break
        if tag in BLOCK_TAGS:
            self._flush()

    def handle_data(self, data):
        tags = [t for t, _ in self.stack]
        if any(t in SKIP_TAGS for t in tags):
            return
        in_data = any('data-result-id' in a for _, a in self.stack)
        # An axis tick (``data-literal="axis"``) is exempt only inside an inline SVG chart.
        in_svg = any(t == 'svg' for t in tags)
        literal = any('data-literal' in a and (a['data-literal'] != 'axis' or in_svg)
                      for _, a in self.stack)
        if in_data and self.data:
            self.data[-1]['text'] += data
            self._block.append('\x00num')
            return
        self.texts.append((data, literal))
        self.places.append(self._place())
        quoted = any(a.get('data-literal') in QUOTED_KINDS for _, a in self.stack)
        if not quoted and not any(t in ('code', 'pre') for t in tags):
            if self._block_place is None and data.strip():
                self._block_place = self._place()
            self._block.append(data)


def _result_lookup(view: Mapping, study: read.Study) -> dict:
    return {item['result_id']: (slot, item) for slot, item in view['results'].items()}


def _check_cited(view: Mapping, study: read.Study, rid: str, path: str, raw: str | None,
                 shown: str, where: str, scale: str | None = None) -> list[dict]:
    by_id = _result_lookup(view, study)
    if rid not in by_id:
        try:
            study.result(rid)
        except StudyError:
            return [finding('unknown_result_id', where, f'No result {rid} in the registry.',
                            result_id=rid, path=path)]
        return [finding('stale_result_cited', where, f'Result {rid} is not current.',
                        result_id=rid, path=path)]
    slot, item = by_id[rid]
    if not (item['current'] and item['integrity'] == 'ok'):
        return [finding('stale_result_cited', where, f'Result {rid} ({slot}) is not current.',
                        result_id=rid, path=path, slot=slot)]
    try:
        value = cite.resolve(item['values'], cite.parse_path(path), n_rows=item['n_rows'])
    except (KeyError, StudyError):
        return [finding('value_mismatch', where, f'Result {rid} has no value at {path!r}.',
                        result_id=rid, path=path)]
    toks = cite.parse_numbers(shown)
    try:
        attr_ok = raw is not None and float(raw) == float(value)
        factor = 1.0 if scale is None else float(scale)
    except (TypeError, ValueError):
        attr_ok, factor = False, 1.0
    if factor not in (1.0, 100.0):          # only the points format scales (cite.pts*)
        attr_ok = False
    if factor == 100.0 and _already_points(item['values'], path, value):
        # B6c (B1): the points format scales a difference of fractions; a value already in
        # points (a gain stored with ``unit: percentage points``, or any value outside
        # [-1, 1]) shown with it is a figure 100 times too large, even though the text
        # matches the attribute times the scale.
        return [finding('value_mismatch', where,
                        f'The cited value {shown!r} scales a figure already in percentage '
                        f'points by 100 ({path!r}).', result_id=rid, path=path, shown=shown,
                        attribute=raw, registry=value, reason='double_scaled')]
    if not attr_ok or len(toks) != 1 or not cite.shown_matches(toks[0], value, factor):
        return [finding('value_mismatch', where,
                        f'The cited value {shown!r} differs from the registry value at {path!r}.',
                        result_id=rid, path=path, shown=shown, attribute=raw, registry=value)]
    return []


POINT_UNITS = ('percentage points', 'points')


def _already_points(values, path: str, value) -> bool:
    """True when the value at ``path`` cannot be a difference of fractions: its size is
    above 1, or its mapping declares a unit in points (``criterion.unit``)."""
    if cite.is_number(value) and abs(value) > 1 + 1e-12:
        return True
    try:
        segments = cite.parse_path(path)
        parent = cite.resolve(values, segments[:-1]) if len(segments) > 1 else values
    except (KeyError, StudyError):
        return False
    return isinstance(parent, Mapping) and parent.get('unit') in POINT_UNITS


def check_html(view: Mapping, study: read.Study, page: str, where: str) -> list[dict]:
    parser = _Report()
    parser.feed(page)
    parser.close()
    parser._flush()
    findings = []
    for (node, exempt), (anchor, line) in zip(parser.texts, parser.places):
        if exempt:
            continue
        for tok in cite.parse_numbers(_masked(node)):
            findings.append(finding('number_outside_result', where,
                                    f'{tok.text.strip()} is not a cited registry value.',
                                    number=tok.text.strip(), context=node.strip()[:160],
                                    location=location(where, anchor,
                                                      line + node.count('\n', 0, tok.start))))
    for d in parser.data:
        a = d['attrs']
        if 'data-result-id' not in a:
            continue
        at = location(where, d['anchor'], d['line'])
        findings += [{**f, 'location': at}
                     for f in _check_cited(view, study, a['data-result-id'],
                                           a.get('data-path', ''),
                                           a.get('value', a.get('data-value')), d['text'],
                                           where, a.get('data-scale'))]
    for block, (anchor, line) in zip(parser.blocks, parser.block_places):
        findings += wording(block, where, lambda _offset, a=anchor, n=line: location(where, a, n))
    return findings


# --- notebook ---------------------------------------------------------------------------

def check_notebook(view: Mapping, study: read.Study, source: str, where: str) -> list[dict]:
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [finding('number_outside_result', where, f'The notebook does not parse: {exc}.',
                        location=location(where, None, exc.lineno))]
    findings = []
    generated = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name == 'GENERATED_REVISION':
                generated = ast.literal_eval(node.value)
            elif name == 'RESULT_IDS':
                ids = ast.literal_eval(node.value)
                at = location(where, None, node.lineno)
                for slot, rid in sorted(ids.items()):
                    findings += [{**f, 'location': at}
                                 for f in _check_rid(view, study, rid, slot, where)]
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr in ('md', 'Html') and node.args \
                and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
            text = HEADING_ORDINAL.sub(lambda m: m.group(1), node.args[0].value)
            locate = _text_locator(where, text, node.args[0].lineno)
            for tok in cite.parse_numbers(_masked(text)):
                findings.append(finding('number_outside_result', where,
                                        f'{tok.text.strip()} in a Markdown cell is not a cited '
                                        'registry value.', number=tok.text.strip(),
                                        line=node.lineno, location=locate(tok.start)))
            findings += wording(INLINE_CODE.sub(' ', text), where,
                                lambda _offset, n=node.args[0].lineno: location(where, None, n))
    if generated is not None and generated != view['revision']:
        findings.append(finding('artifact_not_current', where,
                                f'The notebook was generated at an earlier revision; the study '
                                f'has moved on.', generated_revision=generated,
                                revision=view['revision'], location=location(where)))
    return findings


def _check_rid(view, study, rid, slot, where) -> list[dict]:
    item = view['results'].get(slot)
    if item is not None and item['result_id'] == rid:
        if item['current'] and item['integrity'] == 'ok':
            return []
        return [finding('stale_result_cited', where, f'Result {rid} ({slot}) is not current.',
                        result_id=rid, slot=slot)]
    try:
        study.result(rid)
    except StudyError:
        return [finding('unknown_result_id', where, f'No result {rid} in the registry.',
                        result_id=rid, slot=slot)]
    return [finding('stale_result_cited', where, f'Result {rid} is no longer the current {slot}.',
                    result_id=rid, slot=slot)]


# --- study ------------------------------------------------------------------------------

def check_features(view: Mapping) -> list[dict]:
    decision = view['decisions']['feature_availability']
    statuses = decision['value'] if decision['status'] == 'confirmed' and isinstance(
        decision['value'], dict) else {}
    findings = []
    for slot, item in sorted(view['results'].items()):
        if not slot.startswith('fit.') or not item['current']:
            continue
        # Canonical shape (CLI-CONTRACT.md §8.5): ``values.features`` lists what the fit
        # used; ``inputs.features`` is what it was asked to use (identity). Both are read.
        values = item['values'] if isinstance(item['values'], dict) else {}
        inputs = item['inputs'] if isinstance(item['inputs'], dict) else {}
        features = list(values.get('features') or []) + list(inputs.get('features') or [])
        for f in sorted({x for x in features if isinstance(x, str)}):
            status = statuses.get(f)
            if status is None:
                findings.append(finding('feature_without_status', f'result:{slot}',
                                        f'{f} is used by {slot} without a confirmed availability '
                                        'status.', feature=f, slot=slot))
            elif status in ('not_available', 'uncertain_excluded'):
                findings.append(finding('excluded_feature_used', f'result:{slot}',
                                        f'{f} is used by {slot} although it was decided '
                                        f'{status}.', feature=f, slot=slot, status=status))
    return findings


def declared_files(view: Mapping) -> set[Path]:
    """The case file and its dataset, as recorded by the study: they are the study's own
    inputs, not computations outside ``hypotrail``, even when the case folder lives inside
    the study (D9)."""
    out = set()
    for key in ('case', 'dataset'):
        path = (view.get(key) or {}).get('path')
        if isinstance(path, str) and path:
            out.add(Path(path).resolve())
    return out


def untracked_files(study_dir: Path, declared: Iterable[Path] = ()) -> list[str]:
    declared = {Path(p).resolve() for p in declared}
    out = []
    for path in sorted(study_dir.rglob('*')):
        rel = path.relative_to(study_dir)
        if not path.is_file() or set(rel.parts[:-1]) & IGNORED_DIRS or rel.parts[0] in IGNORED_DIRS:
            continue
        if rel.parts[0] == HANDOFF_DIR:     # packs written by ``export handoff`` (C7)
            continue
        if path.resolve() in declared:
            continue
        if path.suffix.lower() in SCRIPT_SUFFIXES and not OWN_NOTEBOOKS.match(rel.as_posix()):
            out.append(rel.as_posix())
    return out


def check_criterion(view: Mapping) -> list[dict]:
    """v0.2a (WP-A4): ``verdict_contradicts_criterion`` (warning) when the conclusion adopts
    the policy or the model while the success criterion fixed before the models is not met,
    or met by the point estimate only (its paired interval includes 0)."""
    c = view.get('criterion')
    if not c:
        return []
    final = c.get('final_test') or {}
    on_final = c.get('judged_on') == 'final_test'
    if governance.keeps_against_met(c):
        return [finding('verdict_keeps_baseline_against_criterion', 'decision:conclusion',
                        'The conclusion keeps the baseline although the success criterion is '
                        'met on the final test (the gain reaches the minimum and its interval '
                        'excludes 0). Keeping the baseline can be right for a reason the '
                        'criterion does not capture (a cost, a risk, a limit of the data): the '
                        'conclusion should say which, or the verdict should be reconsidered.',
                        status='met', judged_on='final_test',
                        development_status=c.get('status'), verdict=c['verdict'],
                        gain=final.get('gain'), low=final.get('low'), high=final.get('high'),
                        minimum=final.get('minimum'), result_id=final.get('result_id'))]
    if not c.get('contradicts_verdict'):
        return []
    judged = c.get('judged_status') or c['status']
    src = final if on_final else c
    why = ('the gain does not reach the minimum fixed before the models'
           if judged == 'not_met' else
           'the paired interval of the gain includes 0, so the gain may be chance')
    where = ' on the final test' if on_final else ''
    return [finding('verdict_contradicts_criterion', 'decision:conclusion',
                    f'The conclusion adopts ({c["verdict"]}) while the success criterion is '
                    f'{" ".join(judged.split("_"))}{where}: {why}.',
                    status=judged, verdict=c['verdict'], gain=src.get('gain'),
                    low=src.get('low'), high=src.get('high'), minimum=src.get('minimum'),
                    result_id=src.get('result_id'), judged_on=c.get('judged_on'),
                    development_status=c.get('status'))]


def check_validity_requirements(view: Mapping) -> list[dict]:
    """A completed review-v1 conclusion cannot hide mandatory missing evidence."""
    conclusion = (view.get('decisions') or {}).get('conclusion') or {}
    if conclusion.get('status') != 'confirmed':
        return []
    if isinstance(conclusion.get('value'), Mapping) \
            and conclusion['value'].get('verdict') == 'inconclusive':
        return []
    out = []
    for requirement in view.get('requirements') or []:
        if requirement.get('satisfied'):
            continue
        out.append(finding('validity_requirement_missing', 'decision:conclusion',
                           f'Completed conclusion lacks requirement {requirement["code"]}.',
                           requirement=requirement['code'],
                           result_id=requirement.get('result_id'),
                           detail=requirement.get('detail')))
    return out


def check_study(study_dir: Path) -> tuple[dict, list[dict], list[dict]]:
    study = read.open(study_dir)
    view = view_model.build(study)
    findings, traced = [], []
    manifest = mf.load(study.study_dir)
    state = {'revision': view['revision'], 'stale': view['stale'],
             'current': {s: r['result_id'] for s, r in view['results'].items()}}
    for name, path in mf.ARTIFACTS.items():
        item = manifest['artifacts'].get(name)
        file = mf.file_check(study.study_dir, item)               # M4: the bytes on disk
        status = mf.effective_status(item, state, None, file)
        if status != 'ok':
            reason = mf.stale_reason(item, state, None, file)
            extra = {'reason': reason} if reason in (mf.FILE_MISSING, mf.FILE_CHANGED) else {}
            words = f' ({" ".join(reason.split("_"))})' if extra else ''
            findings.append(finding('artifact_not_current', f'artifact:{name}',
                                    f'{path} is {status}{words}.', status=status,
                                    error=(item or {}).get('error'), location=location(path),
                                    **extra))
    report = study.study_dir / mf.ARTIFACTS['report']
    if report.is_file():
        findings += check_html(view, study, report.read_text(encoding='utf-8'),
                               mf.ARTIFACTS['report'])
    notebook = study.study_dir / mf.ARTIFACTS['notebook']
    if notebook.is_file():
        findings += check_notebook(view, study, notebook.read_text(encoding='utf-8'),
                                   mf.ARTIFACTS['notebook'])
    findings += check_features(view)
    findings += check_criterion(view)
    findings += check_validity_requirements(view)
    conclusion = view['decisions']['conclusion']['value']
    if isinstance(conclusion, dict) and isinstance(conclusion.get('text'), str):
        f, t = _check_text(view, conclusion['text'], 'decision:conclusion',
                           retired=retired_proposals(study))
        findings += f
        traced += t
    files = untracked_files(study.study_dir, declared_files(view))
    if files:
        findings.append(finding('untracked_files', 'study',
                                'Files in the study folder look like computations outside '
                                'hypotrail; what they read and computed is not recorded.',
                                files=files))
    return view, findings, traced


# --- CLI --------------------------------------------------------------------------------

def configure(parser: argparse.ArgumentParser) -> None:
    parser.description = 'Check numbers and wording against the registry (never writes).'
    parser.add_argument('--text', default=None, metavar='PATH',
                        help='check a draft message instead of the deliverables (- for stdin)')
    parser.add_argument('--allow-user-text', dest='user_text', action='append', default=None,
                        metavar='PATH',
                        help="text the junior wrote (- for stdin); the draft may repeat its "
                             "numbers (repeatable, with --text)")
    parser.add_argument('--result', action='append', default=None, metavar='RESULT',
                        help='a result the draft speaks of (a result id, a prefix of 6 or more '
                             'characters, or a slot): its numbers bind to that result '
                             '(repeatable, with --text)')


def _read_text(arg: str) -> str:
    """The text of ``arg``: stdin for ``-``, else a file or a pipe (a shell process
    substitution, ``<(printf ...)``, so an agent passes the junior's words without writing a
    file)."""
    if arg == '-':
        return sys.stdin.read()
    path = Path(arg)
    if not path.exists() or path.is_dir():
        raise StudyError('invalid_arguments', f'--text: no such file {arg}',
                         details={'text': arg})
    return path.read_text(encoding='utf-8')


def registry_ids(study: read.Study) -> list[str]:
    """Every ``result_id`` in the registry (its file names), current or not."""
    folder = study.home / read.REGISTRY_DIR
    return sorted(p.stem for p in folder.glob('*.json')) if folder.is_dir() else []


def text_location_path(study_dir: Path, text_path: str | None) -> str | None:
    """The ``location.path`` of a ``--text`` file: study-relative when it is inside the
    study, else the path as resolved; None for stdin."""
    if text_path is None or text_path == '-':
        return None
    path = Path(text_path).resolve()
    try:
        return path.relative_to(study_dir).as_posix()
    except ValueError:
        return path.as_posix()


def _data_card(study_dir) -> dict | None:
    """The data card of the study (WP-A8), or None when it cannot be read (a changed
    dataset): its figures then stay untraceable, as before."""
    from . import cmd_data
    try:
        return cmd_data.card(study_dir)
    except Exception:      # noqa: BLE001 - a text check never fails on the card
        return None


def run_check(study_dir, text: str | None = None, user_texts: Iterable[str] = (),
              text_path: str | None = None, scope: Iterable[str] | None = None) -> dict:
    """The ``hypotrail.check/1`` payload. ``text_path`` names the file ``text`` was read
    from, for the ``location`` of its findings (C10; stdin and None give a null path).
    ``scope`` (v0.3, WP-A, ``--result``): results the numbers of the text bind to, unless a
    sentence names others."""
    study_dir = Path(study_dir).resolve()
    if text is None:
        view, findings, traced = check_study(study_dir)
        target = 'study'
    else:
        study = read.open(study_dir)
        view = view_model.build(study)
        # v0.3 (WP-A): the pool ``decide propose`` traces a proposal's texts with.
        pool = numtrace.study_pool(study, view=view, user_texts=user_texts, scope=scope)
        if pool.unknown_scope:
            raise StudyError('invalid_arguments',
                             f'--result names no result of the view: '
                             f'{", ".join(pool.unknown_scope)}.',
                             details={'results': pool.unknown_scope,
                                      'slots': sorted(pool.slots)})
        locate = _text_locator(text_location_path(study_dir, text_path), text)
        findings, traced = trace_text(pool, text, 'text', locate)
        findings += wording(text, 'text', locate) + attribution(text, 'text', locate)
        target = 'text'
    counts = {'error': sum(f['severity'] == 'error' for f in findings),
              'warning': sum(f['severity'] == 'warning' for f in findings)}
    return {'schema': SCHEMA, 'ok': True, 'study': str(study_dir), 'revision': view['revision'],
            'target': target, 'clean': counts['error'] == 0, 'counts': counts,
            'findings': findings, 'traced': traced}


def main(args: argparse.Namespace) -> cmd.Outcome:
    user = list(args.user_text or [])
    if user and args.text is None:
        raise StudyError('invalid_arguments', '--allow-user-text goes with --text: it gives the '
                                              "junior's own words that a draft may repeat.")
    if [args.text, *user].count('-') > 1:
        raise StudyError('invalid_arguments', 'Only one of --text and --allow-user-text can read '
                                              'stdin (-).')
    scope = list(args.result or [])
    if scope and args.text is None:
        raise StudyError('invalid_arguments', '--result goes with --text: it names the results '
                                              'the draft speaks of.')
    text = _read_text(args.text) if args.text is not None else None
    return cmd.Outcome(run_check(args.study, text, [_read_text(u) for u in user],
                                 text_path=args.text, scope=scope or None))
