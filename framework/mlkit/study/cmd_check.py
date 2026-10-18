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
                                     the generated notebooks — E1 finding F3:
                                     computations outside ``hypotrail`` are invisible
=========================  ========  ==============================================

Matching a number (E1 finding F5): a number written with ``d`` decimals matches a
registry value that rounds to it at ``d`` decimals (a percentage matches a fraction
times 100). Matches report the ``result_id`` and path they were traced to, so a
reviewer sees what a number stands for. Numbers following "revision", "step",
"pause", or "proposal", list markers, and ISO dates are exempt.

The command always exits 0 with ``clean`` true or false; it never writes.
No pandas, numpy, or scikit-learn.
"""
from __future__ import annotations

import argparse
import ast
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable, Mapping

from . import cite, manifest as mf, read, view as view_model
from . import commands as cmd
from .errors import StudyError

SCHEMA = 'hypotrail.check/1'
SEVERITY = {'number_outside_result': 'error', 'unknown_result_id': 'error',
            'value_mismatch': 'error', 'stale_result_cited': 'error',
            'feature_without_status': 'error', 'excluded_feature_used': 'error',
            'untraceable_number': 'error', 'stale_number': 'error',
            'causal_wording': 'warning', 'forecast_wording': 'warning',
            'artifact_not_current': 'warning', 'untracked_files': 'warning'}
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
    r"\b(expect(?:s|ed|ing)?(?! value)|will (?:get|reach|bring|convert|subscribe|renew|yield|"
    r"deliver|find|see|have|make|gain|win|sign)|we will|you will|we'll|you'll|"
    r"should (?:reach|get|bring|yield|convert)|(?:is|are) going to|guarantee[sd]?|"
    r"in (?:the )?future|next campaign)\b", re.IGNORECASE)
EXEMPT_BEFORE = re.compile(r'(?:revision|revisions|rev\.?|step|steps|pause|pauses|proposal|p_|'
                           r'request|req-|expected-revision|section|§|row)\s*[#:=]?\s*$',
                           re.IGNORECASE)
LIST_MARKER = re.compile(r'^\s*\d+[.)]\s', re.MULTILINE)
ISO_DATE = re.compile(r'\b\d{4}-\d{2}-\d{2}(?:[T ][\d:.]+(?:Z|[+-]\d{2}:?\d{2})?)?\b')
HEADING_ORDINAL = re.compile(r'^(\s*#{1,6}\s+)\d+\.', re.MULTILINE)
SENTENCE = re.compile(r'(?<=[.!?])\s+|\n+')
INLINE_CODE = re.compile(r'`[^`\n]*`')
SCRIPT_SUFFIXES = {'.py', '.ipynb', '.r', '.sql', '.csv', '.parquet', '.xlsx', '.json', '.pkl'}
OWN_NOTEBOOKS = re.compile(r'^notebooks/(study_generated(\.user-edits-[^/]+)?|workbench(\.candidate)?)\.py$')
IGNORED_DIRS = {'.hypotrail', '__marimo__', '__pycache__', '.claude', '.github', '.git',
                'reports', '.venv'}


def finding(code: str, where: str, message: str, **details) -> dict:
    out = {'code': code, 'severity': SEVERITY[code], 'where': where, 'message': message}
    if details:
        out['details'] = details
    return out


# --- number pools -----------------------------------------------------------------------

def _walk_numbers(value: Any) -> Iterable[float]:
    if cite.is_number(value):
        yield float(value)
    elif isinstance(value, str):
        for tok in cite.parse_numbers(value):
            yield tok.value / 100 if tok.percent else tok.value
    elif isinstance(value, Mapping):
        for v in value.values():
            yield from _walk_numbers(v)
    elif isinstance(value, list):
        for v in value:
            yield from _walk_numbers(v)


class Pool:
    """Numbers a text may cite: current results, then stale results, then literals."""

    def __init__(self, view: Mapping):
        self.current, self.stale, self.literal = [], [], []
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
        self._literal('setting', 'settings', view['settings'])
        self._literal('case', 'dataset.rows', view['dataset'].get('rows'))
        for items in view['facts']['by_status'].values():
            for f in items:
                self._literal('case', f['id'], f['value'])

    def _literal(self, kind: str, source: str, value: Any) -> None:
        if isinstance(value, str) and ':' in value:     # "capacity:100", "threshold:0.3"
            value = value.replace(':', ' ')
        for v in _walk_numbers(value):
            self.literal.append({'source': kind, 'id': source, 'value': v})

    def trace(self, tok: cite.Token) -> tuple[str, dict | None]:
        for bucket, label in ((self.current, 'current'), (self.literal, 'literal'),
                              (self.stale, 'stale')):
            for item in bucket:
                if cite.shown_matches(tok, item['value']) or (
                        not tok.percent and label == 'literal'
                        and abs(item['value'] - tok.value) < 1e-9):
                    return label, item
        return 'none', None


def _masked(text: str) -> str:
    """``text`` with exempt numbers (dates, list markers) blanked, same length."""
    text = ISO_DATE.sub(lambda m: ' ' * len(m.group(0)), text)
    text = LIST_MARKER.sub(lambda m: re.sub(r'\d', ' ', m.group(0)), text)
    return text


def _exempt(text: str, tok: cite.Token) -> bool:
    return bool(EXEMPT_BEFORE.search(text[max(0, tok.start - 24):tok.start]))


def trace_text(pool: Pool, text: str, where: str) -> tuple[list[dict], list[dict]]:
    findings, traced = [], []
    masked = _masked(text)
    for tok in cite.parse_numbers(masked):
        if _exempt(masked, tok):
            continue
        label, item = pool.trace(tok)
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
                                    result_id=item['result_id'], path=item['path']))
        else:
            findings.append(finding('untraceable_number', where,
                                    f'{tok.text.strip()} matches no current registry value at its '
                                    'displayed precision. Cite a result instead of computing.',
                                    number=tok.text.strip()))
    return findings, traced


def wording(text: str, where: str) -> list[dict]:
    """Causal and forecast wording, sentence by sentence (code spans ignored)."""
    out = []
    for sentence in SENTENCE.split(INLINE_CODE.sub(' ', text)):
        sentence = sentence.strip()
        if not sentence:
            continue
        m = CAUSAL.search(sentence)
        if m and not NEGATION.search(sentence[:m.start()]) \
                and not UNESTABLISHED.search(sentence[m.end():]):
            out.append(finding('causal_wording', where,
                               'Causal wording: the study shows associations and rankings, not '
                               'effects of acting.', phrase=m.group(0), sentence=sentence))
        m = FORECAST.search(sentence)
        has_number = bool(cite.parse_numbers(_masked(sentence))) or '\x00num' in sentence
        if m and has_number and not NEGATION.search(sentence[:m.start()]) \
                and not NEGATED_AFTER.match(sentence[m.end():]):
            out.append(finding('forecast_wording', where,
                               'A figure is phrased as a forecast. Validation figures describe '
                               'past rows after a choice made on them; say so instead.',
                               phrase=m.group(0), sentence=sentence.replace('\x00num', '#')))
    return out


def check_text(view: Mapping, text: str, where: str = 'text') -> tuple[list[dict], list[dict]]:
    findings, traced = trace_text(Pool(view), text, where)
    return findings + wording(text, where), traced


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
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, dict]] = []
        self.texts: list[tuple[str, bool]] = []      # (text node, exempt)
        self.data: list[dict] = []
        self.blocks: list[str] = []
        self._block: list[str] = []

    def _flush(self):
        text = ''.join(self._block).strip()
        if text:
            self.blocks.append(text)
        self._block = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in BLOCK_TAGS:
            self._flush()
        if tag in VOID_TAGS:
            return
        self.stack.append((tag, attrs))
        if tag == 'data':
            self.data.append({'attrs': attrs, 'text': ''})

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
        quoted = any(a.get('data-literal') in QUOTED_KINDS for _, a in self.stack)
        if not quoted and not any(t in ('code', 'pre') for t in tags):
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
    for node, exempt in parser.texts:
        if exempt:
            continue
        for tok in cite.parse_numbers(_masked(node)):
            findings.append(finding('number_outside_result', where,
                                    f'{tok.text.strip()} is not a cited registry value.',
                                    number=tok.text.strip(), context=node.strip()[:160]))
    for d in parser.data:
        a = d['attrs']
        if 'data-result-id' not in a:
            continue
        findings += _check_cited(view, study, a['data-result-id'], a.get('data-path', ''),
                                 a.get('value'), d['text'], where)
    for block in parser.blocks:
        findings += wording(block, where)
    return findings


# --- notebook ---------------------------------------------------------------------------

def check_notebook(view: Mapping, study: read.Study, source: str, where: str) -> list[dict]:
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [finding('number_outside_result', where, f'The notebook does not parse: {exc}.')]
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
                for slot, rid in sorted(ids.items()):
                    findings += [f for f in _check_rid(view, study, rid, slot, where)]
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr in ('md', 'Html') and node.args \
                and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
            text = HEADING_ORDINAL.sub(lambda m: m.group(1), node.args[0].value)
            for tok in cite.parse_numbers(_masked(text)):
                findings.append(finding('number_outside_result', where,
                                        f'{tok.text.strip()} in a Markdown cell is not a cited '
                                        'registry value.', number=tok.text.strip(),
                                        line=node.lineno))
            findings += wording(INLINE_CODE.sub(' ', text), where)
    if generated is not None and generated != view['revision']:
        findings.append(finding('artifact_not_current', where,
                                f'The notebook was generated at an earlier revision; the study '
                                f'has moved on.', generated_revision=generated,
                                revision=view['revision']))
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
        params = item['params'] if isinstance(item['params'], dict) else {}
        values = item['values'] if isinstance(item['values'], dict) else {}
        features = params.get('features') or values.get('features') or []
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


def untracked_files(study_dir: Path) -> list[str]:
    out = []
    for path in sorted(study_dir.rglob('*')):
        rel = path.relative_to(study_dir)
        if not path.is_file() or set(rel.parts[:-1]) & IGNORED_DIRS or rel.parts[0] in IGNORED_DIRS:
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
        status = mf.effective_status(item, state)
        if status != 'ok':
            findings.append(finding('artifact_not_current', f'artifact:{name}',
                                    f'{path} is {status}.', status=status,
                                    error=(item or {}).get('error')))
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
        f, t = check_text(view, conclusion['text'], 'decision:conclusion')
        findings += f
        traced += t
    files = untracked_files(study.study_dir)
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


def _read_text(arg: str) -> str:
    if arg == '-':
        return sys.stdin.read()
    path = Path(arg)
    if not path.is_file():
        raise StudyError('invalid_arguments', f'--text: no such file {arg}',
                         details={'text': arg})
    return path.read_text(encoding='utf-8')


def run_check(study_dir, text: str | None = None) -> dict:
    study_dir = Path(study_dir).resolve()
    if text is None:
        view, findings, traced = check_study(study_dir)
        target = 'study'
    else:
        view = view_model.build(read.open(study_dir))
        findings, traced = check_text(view, text)
        target = 'text'
    counts = {'error': sum(f['severity'] == 'error' for f in findings),
              'warning': sum(f['severity'] == 'warning' for f in findings)}
    return {'schema': SCHEMA, 'ok': True, 'study': str(study_dir), 'revision': view['revision'],
            'target': target, 'clean': counts['error'] == 0, 'counts': counts,
            'findings': findings, 'traced': traced}


def main(args: argparse.Namespace) -> cmd.Outcome:
    text = _read_text(args.text) if args.text is not None else None
    return cmd.Outcome(run_check(args.study, text))
