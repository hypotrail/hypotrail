"""``hypotrail check``: number traceability and wording checks (plan WP3.3).

    hypotrail check --study DIR               # the rendered deliverables and the study
    hypotrail check --study DIR --text PATH   # a draft message (``-`` reads stdin)

Findings (``severity`` is ``error`` or ``warning``):

=========================  ========  ==============================================
code                       severity  meaning
=========================  ========  ==============================================
``number_outside_result``  error     a number in a text node of the HTML report or of
                                     a notebook Markdown cell that is not a cited
                                     ``<data data-result-id>`` value (revisions, step
                                     ordinals and other recorded literals, marked
                                     ``data-literal``, are exempt)
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

from . import cite, manifest as mf, read, view as view_model, wordnum
from . import commands as cmd
from .errors import StudyError

SCHEMA = 'hypotrail.check/1'
SEVERITY = {'number_outside_result': 'error', 'unknown_result_id': 'error',
            'value_mismatch': 'error', 'stale_result_cited': 'error',
            'feature_without_status': 'error', 'excluded_feature_used': 'error',
            'untraceable_number': 'error', 'stale_number': 'error',
            'causal_wording': 'warning', 'forecast_wording': 'warning',
            'artifact_not_current': 'warning', 'untracked_files': 'warning',
            # Post-v0.1 (P7): a recommended default credited to the analyst.
            'misattributed_delegation': 'error'}
FINDING_CODES = tuple(SEVERITY)

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
EXEMPT_BEFORE = re.compile(r'(?:revision|revisions|rev\.?|step|steps|pause|pauses|proposal|p_|'
                           r'request|req-|expected-revision|section|§|row|'
                           r'exit|exit code|exit status|exited with|exited with code)'
                           r'\s*[#:=]?\s*$', re.IGNORECASE)
# "revision 26 instead of 24", "revision 24 to 26", "revisions 24 and 26": every number of
# the comparison that follows "revision" is a revision too (D4). "and" and "or" continue
# only after the plural, so "at revision 26 and 115 clients" still checks 115.
REVISION_SPAN = re.compile(
    r'\brevision\s*[#:=]?\s*\d+(?:\s*(?:instead of|rather than|not|vs\.?|versus|to|->|\u2192)'
    r'\s*(?:revision\s*)?\d+(?![.,]\d))+'
    r'|\brevisions\s*\d+(?:\s*(?:,|and|or|to|-|\u2013)\s*\d+(?![.,]\d))+', re.IGNORECASE)
# A rule written as an identifier ("capacity:100", "threshold:0.2") names a rule; it is
# traced when it can be and never reported as a claim (D4).
RULE_IDENTIFIER = re.compile(r'\b(?:threshold|capacity)\s*:\s*(-?\d+(?:\.\d+)?)', re.IGNORECASE)
# A result id prefix made only of digits ("(result 52659681)") is an identifier, not a
# figure (R3): at least this many digits, after one of these words or as the start of a
# registry ``result_id``.
RESULT_ID_DIGITS = re.compile(r'\d{6,}')
RESULT_ID_LEAD = re.compile(r'\b(?:results?(?:[ _-]?ids?)?|rids?|ids?|executions?(?:[ _-]?ids?)?)'
                            r'\s*[#:=]?\s*[`(\[]?\s*$', re.IGNORECASE)
# "29.5 percentage points": a difference of two rates, read as a percentage of a registered
# difference (``deltas``), never of a rate (D4).
PERCENTAGE_POINTS = re.compile(r'\s*(?:percentage[- ]points?|pp\b|p\.p\.|points? de pourcentage)',
                               re.IGNORECASE)
LIST_MARKER = re.compile(r'^\s*\d+[.)]\s', re.MULTILINE)
ISO_DATE = re.compile(r'\b\d{4}-\d{2}-\d{2}(?:[T ][\d:.]+(?:Z|[+-]\d{2}:?\d{2})?)?\b')
HEADING_ORDINAL = re.compile(r'^(\s*#{1,6}\s+)\d+\.', re.MULTILINE)
# D8: nouns that name the study's own structure, by the view count they refer to.
STRUCTURE_NOUNS = {
    'features': ('columns', 'column', 'features', 'feature', 'variables', 'variable', 'inputs',
                 'predictors', 'colonnes', 'colonne'),
    'groups': ('groups', 'groupes'),
    'steps': ('steps', 'étapes'),
    'pauses': ('pauses', 'decision points'),
    'decisions': ('decisions', 'décisions'),
}
_STRUCTURE_NOUN = '|'.join(re.escape(n) for nouns in STRUCTURE_NOUNS.values()
                           for n in sorted(nouns, key=len, reverse=True))
STRUCTURE_AFTER = re.compile(rf"\s+(?:[^\W\d_][\w'’-]*\s+)?(?P<noun>{_STRUCTURE_NOUN})(?![\w])",
                             re.IGNORECASE)
USABLE_STATUSES = ('available_at_prediction', 'uncertain_included')
EXCLUDED_STATUSES = ('not_available', 'uncertain_excluded')
SENTENCE = re.compile(r'(?<=[.!?])\s+|\n+')
INLINE_CODE = re.compile(r'`[^`\n]*`')
# The default folder of ``hypotrail export handoff`` (CLI-CONTRACT-COMPANION C7): its
# files are the engine's own output, not computations outside hypotrail.
HANDOFF_DIR = 'handoff'
SCRIPT_SUFFIXES = {'.py', '.ipynb', '.r', '.sql', '.csv', '.parquet', '.xlsx', '.json', '.pkl'}
OWN_NOTEBOOKS = re.compile(r'^notebooks/(study_generated(\.user-edits-[^/]+)?|workbench(\.candidate)?)\.py$')
IGNORED_DIRS = {'.hypotrail', '__marimo__', '__pycache__', '.claude', '.github', '.git',
                'reports', '.venv'}


def finding(code: str, where: str, message: str, *, location: dict | None = None,
            **details) -> dict:
    """One finding. ``location`` (CLI-CONTRACT-COMPANION C10, optional) is
    ``{path, anchor, line}``: the study-relative file, the nearest enclosing HTML ``id``, and
    the 1-based line; ``where`` is unchanged."""
    out = {'code': code, 'severity': SEVERITY[code], 'where': where, 'message': message}
    if details:
        out['details'] = details
    if location is not None:
        out['location'] = location
    return out


LOCATION_KEYS = ('path', 'anchor', 'line')


def location(path: str | None, anchor: str | None = None, line: int | None = None) -> dict:
    return {'path': path, 'anchor': anchor, 'line': line}


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


# --- number pools -----------------------------------------------------------------------

def _walk_numbers(value: Any) -> Iterable[float]:
    if cite.is_number(value):
        yield float(value)
    elif isinstance(value, str):
        for tok in cite.parse_numbers(value):
            yield tok.value / 100 if tok.percent else tok.value
        for word in wordnum.parse(value):         # F3: "one in ten" written by the junior
            yield word.value / 100 if word.kind in ('percent', 'points') else word.value
    elif isinstance(value, Mapping):
        for v in value.values():
            yield from _walk_numbers(v)
    elif isinstance(value, list):
        for v in value:
            yield from _walk_numbers(v)


def _is_difference(path: str) -> bool:
    """True when a value path addresses a registered difference (``deltas``)."""
    if not path or path in cite.META_PATHS:
        return False
    return any('delta' in seg or 'difference' in seg for seg in cite.parse_path(path))


class Pool:
    """Numbers a text may cite: current results, then literals, then stale results.

    Literals are recorded values a text may repeat: decision and proposal values, the
    rules evaluated by the current policy evaluation, the junior's recorded words, settings,
    case statements, and ``user_texts`` (text the junior wrote, passed with
    ``--allow-user-text``).
    """

    def __init__(self, view: Mapping, user_texts: Iterable[str] = (),
                 result_ids: Iterable[str] | None = None, retired: Iterable[Mapping] = ()):
        self.current, self.stale, self.literal = [], [], []
        # Withdrawn and superseded proposals (F3): never literals; only named in the
        # finding when an untraceable number repeats one of their figures.
        self.retired = []
        for p in retired:
            for v in _walk_numbers(_rule_spaced(p.get('value'))):
                self.retired.append({'proposal_id': p.get('proposal_id'),
                                     'status': p.get('status'), 'value': v})
        # Result ids a digit-only prefix may abbreviate (R3): the registry when known,
        # else the results of the view.
        self.result_ids = tuple(result_ids) if result_ids is not None else tuple(
            item['result_id'] for item in view['results'].values()
            if isinstance(item.get('result_id'), str))
        # Target units of the results (a regression study, M3): "about six litres" is read.
        self.units = wordnum.unit_nouns(sorted({
            item['values']['unit'] for item in view['results'].values()
            if isinstance(item.get('values'), Mapping)
            and isinstance(item['values'].get('unit'), str)}))
        for slot, item in sorted(view['results'].items()):
            if item['values'] is None:
                continue
            bucket = self.current if item['current'] and item['integrity'] == 'ok' else self.stale
            leaves = list(cite.leaves(item['values']))
            if cite.is_number(item['n_rows']):
                leaves.append((('@n_rows',), item['n_rows']))
            for segments, value in leaves:
                bucket.append({'result_id': item['result_id'], 'slot': slot,
                               'path': cite.format_path(segments), 'value': value})
        for d in view['decisions'].values():
            if d['value'] is not None and d['decision_id'] != 'conclusion':
                self._literal('decision', d['decision_id'], d['value'])
        for p in view['open_proposals']:
            if p['decision_id'] != 'conclusion':
                self._literal('proposal', p['proposal_id'], p['value'])
        for d in view['decisions'].values():
            conf = d.get('confirmation')
            if isinstance(conf, Mapping) and isinstance(conf.get('user_words'), str):
                self._literal('user_words', d['decision_id'], conf['user_words'])
        # P2: the junior's recorded conditions and the words that resolved them.
        for n in view.get('notes') or []:
            self._literal('user_words', n['note_id'], n['user_words'])
            if isinstance(n.get('resolution'), Mapping):
                self._literal('user_words', n['note_id'], n['resolution'].get('user_words'))
        for slot, item in sorted(view['results'].items()):
            if item.get('activity') == 'policy.evaluation' and item['current'] \
                    and isinstance(item.get('params'), Mapping):
                for rule in item['params'].get('rules') or []:
                    self._literal('rule', slot, rule)
        for i, text in enumerate(user_texts):
            self._literal('user_text', f'user_text:{i + 1}', text)
        # D8: counts of the study's own structure, matched only before a structural noun.
        self.structure: list[dict] = []

        def count(kind: str, source: str, value) -> None:
            if isinstance(value, int) and not isinstance(value, bool):
                self.structure.append({'kind': kind, 'id': source, 'value': value})
        for slot, item in sorted(view['results'].items()):
            values = item.get('values')
            if not (item['current'] and item['integrity'] == 'ok' and isinstance(values, Mapping)):
                continue
            if isinstance(values.get('features'), list):
                count('features', f'{slot}.features', len(values['features']))
            if isinstance(values.get('groups'), list):
                count('groups', f'{slot}.groups', len(values['groups']))
        availability = [('decision', view['decisions'].get('feature_availability', {})
                         .get('value'))]
        availability += [(p['proposal_id'], p['value']) for p in view['open_proposals']
                         if p['decision_id'] == 'feature_availability']
        for source, value in availability:
            if not isinstance(value, Mapping):
                continue
            count('features', f'feature_availability.{source}.all', len(value))
            count('features', f'feature_availability.{source}.usable',
                  sum(v in USABLE_STATUSES for v in value.values()))
            count('features', f'feature_availability.{source}.excluded',
                  sum(v in EXCLUDED_STATUSES for v in value.values()))
            for status in sorted(set(value.values())):
                count('features', f'feature_availability.{source}.{status}',
                      sum(v == status for v in value.values()))
        plan = view.get('plan') or []
        count('steps', 'plan.steps', len(plan))
        count('pauses', 'plan.pauses', len({s['pause'] for s in plan if s.get('pause')}))
        count('decisions', 'decisions', len(view['decisions']))
        self._literal('setting', 'settings', view['settings'])
        self._literal('case', 'dataset.rows', view['dataset'].get('rows'))
        for items in view['facts']['by_status'].values():
            for f in items:
                self._literal('case', f['id'], f['value'])

    def _literal(self, kind: str, source: str, value: Any) -> None:
        for v in _walk_numbers(_rule_spaced(value)):
            self.literal.append({'source': kind, 'id': source, 'value': v})

    def trace_words(self, word: wordnum.WordNumber) -> tuple[str, dict | None]:
        """Where a number written in words comes from (F3), like :meth:`trace`: a ratio
        or a fraction matches at its own precision (:meth:`wordnum.WordNumber.matches`),
        percentage points only a registered difference."""
        points = word.kind == 'points'
        for bucket, label in ((self.current, 'current'), (self.literal, 'literal'),
                              (self.stale, 'stale')):
            if points and label == 'literal':
                continue
            for item in bucket:
                if points and not _is_difference(item['path']):
                    continue
                if word.matches(item['value'], literal=label == 'literal'):
                    return label, item
        return 'none', None

    def structure_match(self, text: str, end: int, value: float) -> dict | None:
        """The structure count (D8) a number ending at ``end`` refers to, when a structural
        noun follows it and the count matches; None otherwise."""
        m = STRUCTURE_AFTER.match(text, end)
        if m is None or value != int(value):
            return None
        noun = m.group('noun').lower()
        kind = next(k for k, nouns in STRUCTURE_NOUNS.items() if noun in nouns)
        return next((item for item in self.structure
                     if item['kind'] == kind and item['value'] == int(value)), None)

    def retired_match(self, value: float, *, percent: bool = False) -> dict | None:
        """The withdrawn or superseded proposal whose figure ``value`` repeats, if any."""
        for item in self.retired:
            v = 100 * item['value'] if percent else item['value']
            if abs(v - value) < 1e-9:
                return item
        return None

    def trace(self, tok: cite.Token, *, difference: bool = False) -> tuple[str, dict | None]:
        """Where ``tok`` comes from. ``difference``: the token is written in percentage
        points, so only a registered difference (``deltas``) can match it."""
        for bucket, label in ((self.current, 'current'), (self.literal, 'literal'),
                              (self.stale, 'stale')):
            if difference and label == 'literal':
                continue
            for item in bucket:
                if difference and not _is_difference(item['path']):
                    continue
                if cite.shown_matches(tok, item['value']) or (
                        not tok.percent and label == 'literal'
                        and abs(item['value'] - tok.value) < 1e-9):
                    return label, item
        return 'none', None


def _rule_spaced(value: Any) -> Any:
    """A rule identifier with its colon spaced ("capacity 100"), so its figure is read."""
    if isinstance(value, str) and ':' in value:     # "capacity:100", "threshold:0.3"
        return value.replace(':', ' ')
    return value


def _retired_note(pool: 'Pool', value: float, percent: bool = False) -> tuple[str, dict]:
    item = pool.retired_match(value, percent=percent)
    if item is None:
        return '', {}
    return (f' It repeats a figure of the {item["status"]} proposal {item["proposal_id"]}, '
            'which is no longer on the table: name that proposal without its figure.',
            {'retired_proposal': item['proposal_id'], 'proposal_status': item['status']})


def _masked(text: str) -> str:
    """``text`` with exempt numbers (dates, list markers, revision comparisons) blanked,
    same length."""
    text = ISO_DATE.sub(lambda m: ' ' * len(m.group(0)), text)
    text = LIST_MARKER.sub(lambda m: re.sub(r'\d', ' ', m.group(0)), text)
    text = REVISION_SPAN.sub(lambda m: re.sub(r'\d', ' ', m.group(0)), text)
    return text


def _exempt(text: str, tok: cite.Token) -> bool:
    return bool(EXEMPT_BEFORE.search(text[max(0, tok.start - 24):tok.start]))


def _result_id_prefix(pool: Pool, text: str, tok: cite.Token) -> bool:
    """True when ``tok`` is an all-digit result id prefix (R3): 6 or more digits, no sign,
    decimals or percent, after "result" / "rid" / "id" / "execution", or the start of a
    registry ``result_id``."""
    body = text[tok.start:tok.end]
    if tok.percent or not RESULT_ID_DIGITS.fullmatch(body):
        return False
    if RESULT_ID_LEAD.search(text[max(0, tok.start - 24):tok.start]):
        return True
    return any(rid.startswith(body) for rid in pool.result_ids)


def _trace_words(pool: Pool, masked: str, word: wordnum.WordNumber, where: str,
                 findings: list, traced: list, locate=None) -> None:
    """Trace one number written in words (F3) and record a finding or a trace."""
    at = locate(word.start) if locate else None
    label, item = pool.trace_words(word)
    shown = word.text.strip()
    structure = (pool.structure_match(masked, word.end, word.value)
                 if label in ('none', 'stale') and word.kind == 'count' else None)
    if structure is not None:
        traced.append({'text': shown, 'source': 'structure', 'id': structure['id'],
                       'value': structure['value'], 'in_words': True})
        return
    if label == 'current':
        traced.append({'text': shown, 'result_id': item['result_id'], 'slot': item['slot'],
                       'path': item['path'], 'value': item['value'], 'in_words': True})
    elif label == 'literal':
        traced.append({'text': shown, 'source': item['source'], 'id': item['id'],
                       'value': item['value'], 'in_words': True})
    elif label == 'stale':
        findings.append(finding('stale_number', where,
                                f'"{shown}" (a number written in words) matches only a stale '
                                'result; recompute before citing it.', number=shown,
                                in_words=True, result_id=item['result_id'], path=item['path'],
                                location=at))
    else:
        note, extra = _retired_note(pool, word.value)
        findings.append(finding('untraceable_number', where,
                                f'"{shown}" is a number written in words ({word.kind}) that '
                                'matches no current registry value. Cite the registered figure '
                                'with its result_id instead of computing or rounding it into '
                                'words.' + note, number=shown, in_words=True, kind=word.kind,
                                value=word.value, location=at, **extra))


def trace_text(pool: Pool, text: str, where: str, locate=None) -> tuple[list[dict], list[dict]]:
    """Trace every number of ``text``. ``locate`` (optional) maps an offset of ``text`` to
    the ``location`` of a finding (C10)."""
    findings, traced = [], []
    masked = _masked(text)
    identifiers = {m.start(1) for m in RULE_IDENTIFIER.finditer(masked)}
    items = sorted([(t.start, 0, t) for t in cite.parse_numbers(masked)]
                   + [(w.start, 1, w) for w in wordnum.parse(masked, pool.units)],
                   key=lambda x: x[:2])
    for _, in_words, tok in items:
        if _exempt(masked, tok):
            continue
        if in_words:
            _trace_words(pool, masked, tok, where, findings, traced, locate)
            continue
        difference = not tok.percent and bool(PERCENTAGE_POINTS.match(masked, tok.end))
        if difference:
            tok = dataclasses.replace(tok, percent=True)
        label, item = pool.trace(tok, difference=difference)
        if label in ('none', 'stale') and tok.start in identifiers:
            traced.append({'text': tok.text.strip(), 'source': 'identifier', 'id': 'rule',
                           'value': tok.value})
            continue
        structure = (pool.structure_match(masked, tok.end, tok.value)
                     if label in ('none', 'stale') and not tok.percent else None)
        if structure is not None:
            traced.append({'text': tok.text.strip(), 'source': 'structure',
                           'id': structure['id'], 'value': structure['value']})
            continue
        if label in ('none', 'stale') and _result_id_prefix(pool, masked, tok):
            traced.append({'text': tok.text.strip(), 'source': 'identifier', 'id': 'result_id',
                           'value': tok.value})
            continue
        if label == 'current':
            traced.append({'text': tok.text.strip(), 'result_id': item['result_id'],
                           'slot': item['slot'], 'path': item['path'], 'value': item['value']})
        elif label == 'literal':
            traced.append({'text': tok.text.strip(), 'source': item['source'], 'id': item['id'],
                           'value': item['value']})
        elif label == 'stale':
            findings.append(finding('stale_number', where,
                                    f'{tok.text.strip()} matches only a stale result; recompute '
                                    'before citing it.', number=tok.text.strip(),
                                    result_id=item['result_id'], path=item['path'],
                                    location=locate(tok.start) if locate else None))
        else:
            note, extra = _retired_note(pool, tok.value, percent=tok.percent)
            findings.append(finding('untraceable_number', where,
                                    f'{tok.text.strip()} matches no current registry value at its '
                                    'displayed precision. Cite a result instead of computing.'
                                    + note, number=tok.text.strip(),
                                    location=locate(tok.start) if locate else None, **extra))
    return findings, traced


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
                retired: Iterable[Mapping] = (), locate=None) -> tuple[list[dict], list[dict]]:
    findings, traced = trace_text(Pool(view, user_texts, result_ids, retired), text, where,
                                  locate)
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
        if tag == 'data':
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
        in_data = any(t == 'data' and 'data-result-id' in a for t, a in self.stack)
        literal = any('data-literal' in a for _, a in self.stack)
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
                 shown: str, where: str) -> list[dict]:
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
    except (TypeError, ValueError):
        attr_ok = False
    if not attr_ok or len(toks) != 1 or not cite.shown_matches(toks[0], value):
        return [finding('value_mismatch', where,
                        f'The cited value {shown!r} differs from the registry value at {path!r}.',
                        result_id=rid, path=path, shown=shown, attribute=raw, registry=value)]
    return []


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
                                           a.get('data-path', ''), a.get('value'), d['text'],
                                           where)]
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


def run_check(study_dir, text: str | None = None, user_texts: Iterable[str] = (),
              text_path: str | None = None) -> dict:
    """The ``hypotrail.check/1`` payload. ``text_path`` names the file ``text`` was read
    from, for the ``location`` of its findings (C10; stdin and None give a null path)."""
    study_dir = Path(study_dir).resolve()
    if text is None:
        view, findings, traced = check_study(study_dir)
        target = 'study'
    else:
        study = read.open(study_dir)
        view = view_model.build(study)
        findings, traced = _check_text(view, text, user_texts=user_texts,
                                       result_ids=registry_ids(study),
                                       retired=retired_proposals(study),
                                       locate=_text_locator(
                                           text_location_path(study_dir, text_path), text))
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
    text = _read_text(args.text) if args.text is not None else None
    return cmd.Outcome(run_check(args.study, text, [_read_text(u) for u in user],
                                 text_path=args.text))
