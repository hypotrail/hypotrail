"""Graders for agent acceptance runs (plan WP0.7) and the E1 steelman (plan WP0.8).

Deterministic graders come first and need no model:

(a) ``audit_bash``: audit Bash tool calls for ad hoc computation (python, pandas, pip,
    awk, ...) outside the allowed commands, and any tool call that names a forbidden path
    (the repository, the hidden grader directory, ``truth.json``);
(b) ``trace_numbers``: every number cited in assistant text must match an allowed set:
    registry values once the ``hypotrail`` CLI exists; for arm A, values the grader
    recomputes itself from the data (``recompute_facts``), numbers printed by the agent's
    own tool calls, and numbers present in the user's words or the case documents;
(c) state and registry hooks (``hypotrail_status``, ``registry_values``, ``check_text``,
    ``check_assistant_texts``, ``diff_json``) for arm B and the S1-S9 scenarios; the
    arm B trap scoring lives in ``graders_b.py``.

The E1 helpers (``detect_refit``, ``eda_before_split``, ``lost_sales_mentions``,
``resumption_check``, ``ambiguous_confirmations_recorded``, ``grade_traps``) score the
planted traps, using ``truth.json`` for the synthetic case.

Qualitative grading runs a FRESH ``claude -p`` (``fresh_agent_grade``) on anonymised
material with a rubric and a JSON schema, and returns its structured output. A run's
heuristics are reported as such: a heuristic that does not fire gives ``unclear``, never a
pass.
"""
from __future__ import annotations

import bisect
import importlib.util
import json
import math
import re
import shutil
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent


class GraderUnavailable(RuntimeError):
    """The grader needs a capability that does not exist yet (e.g. the hypotrail CLI)."""


# --------------------------------------------------------------------------- transcript

def _content_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return '\n'.join(_content_text(c.get('text', c.get('content', ''))) if isinstance(c, dict)
                         else str(c) for c in content)
    return '' if content is None else str(content)


def tool_uses(events: list[dict]) -> list[dict]:
    out = []
    for order, e in enumerate(events):
        if e.get('type') != 'assistant':
            continue
        for c in e.get('message', {}).get('content', []):
            if c.get('type') == 'tool_use':
                out.append({'order': order, 'turn': e.get('_turn'), 'chat': e.get('_chat'),
                            'name': c.get('name'), 'input': c.get('input') or {}, 'id': c.get('id')})
    return out


def tool_results(events: list[dict]) -> dict[str, str]:
    out = {}
    for e in events:
        if e.get('type') != 'user':
            continue
        content = e.get('message', {}).get('content', [])
        if not isinstance(content, list):
            continue
        for c in content:
            if isinstance(c, dict) and c.get('type') == 'tool_result':
                out[c.get('tool_use_id')] = _content_text(c.get('content'))
    return out


def assistant_texts(events: list[dict]) -> list[dict]:
    out = []
    for order, e in enumerate(events):
        if e.get('type') != 'assistant':
            continue
        for c in e.get('message', {}).get('content', []):
            if c.get('type') == 'text' and c.get('text', '').strip():
                out.append({'order': order, 'turn': e.get('_turn'), 'chat': e.get('_chat'),
                            'text': c['text']})
    return out


def final_texts(events: list[dict]) -> dict[int, str]:
    """Final reply per turn (the ``result`` event), keyed by turn index."""
    return {e.get('_turn'): e.get('result') or '' for e in events if e.get('type') == 'result'}


def _tool_text(use: dict) -> str:
    i = use['input']
    if use['name'] == 'Bash':
        return i.get('command', '')
    if use['name'] == 'Write':
        return i.get('content', '')
    if use['name'] == 'Edit':
        return i.get('new_string', '')
    if use['name'] == 'NotebookEdit':
        return i.get('new_source', '')
    return json.dumps(i)


# --------------------------------------------------------------------------- (a) Bash audit

COMPUTE_RE = re.compile(
    r'(?<![\w/-])(?:python3?(?:\.\d+)?|ipython|jupyter|pandas|pip3?|uv\s+pip|uv\s+add|'
    r'uv\s+run\s+(?!--project\s+\S+\s+hypotrail\b)(?!hypotrail\b)|awk|gawk|mawk|perl|Rscript|'
    r'sqlite3|duckdb|csvstat|csvsql|xsv|qsv|mlr|datamash|bc|node\s+-e|marimo)(?![\w-])'
    r'|\.venv/bin/(?:python3?|pip3?|marimo)')
# ``hypotrail`` as a command word only: a path that contains "hypotrail" (the repository
# checkout, ``/tmp/hypotrail-ws-...``) must not mask what follows it on the line.
ALLOWED_HYPOTRAIL_RE = re.compile(r'(?:uv\s+run\s+--project\s+\S+\s+)?(?<![\w/.-])hypotrail(?![\w/.-])[^|;&]*')


HEREDOC_RE = re.compile(r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n.*?\n\2[ \t]*(?:\n|$)", re.S)


def classify_command(command: str) -> list[str]:
    """Ad hoc computation tokens found in a shell command, after removing hypotrail calls.

    A here-document fed to ``hypotrail check --text -`` is a draft message, not code: its
    body is removed before looking for computation tokens."""
    if re.search(r'hypotrail\s+check\b', command):
        command = HEREDOC_RE.sub('\n', command)
    stripped = ALLOWED_HYPOTRAIL_RE.sub(' ', command)
    return sorted({m.group(0).strip() for m in COMPUTE_RE.finditer(stripped)})


REDIRECT_RE = re.compile(r"(?<![<>&\d])(?:\d?>>?|&>)\s*([^\s|&;<>()]+)|\btee\s+(?:-a\s+)?([^\s|&;<>()]+)")
QUOTED_RE = re.compile(r"'[^']*'|\"(?:[^\"\\]|\\.)*\"")


def shell_writes(command: str) -> list[str]:
    """Files a shell command writes by redirection or ``tee`` (``/dev/null`` excepted).
    Here-document bodies and quoted strings are ignored (prose such as "score > 0.2")."""
    text = HEREDOC_RE.sub('\n', command)
    text = QUOTED_RE.sub("''", text)
    out = []
    for m in REDIRECT_RE.finditer(text):
        target = m.group(1) or m.group(2)
        if target and target not in ('/dev/null', '/dev/stdout', '/dev/stderr') and not target.startswith('&'):
            out.append(target)
    return out


def audit_bash(events: list[dict], policy: str = 'hypotrail_cli_only',
               forbidden: list[str] = (), allowed: list[str] = ()) -> dict:
    """Grader (a).

    ``policy='hypotrail_cli_only'``: any ad hoc computation is a violation (plan §5, "never ad
    hoc computation"). ``policy='computation_allowed'`` (arm A, which has no engine): the
    computations are reported but are not violations. Forbidden access is always a violation.
    ``allowed`` lists exact strings removed before looking for forbidden paths: the CLI
    invocation recorded by ``hypotrail init`` names the engine's directory in the
    repository, and running it is the expected behaviour of arm B.
    """
    if policy not in ('hypotrail_cli_only', 'computation_allowed'):
        raise ValueError(f'unknown Bash policy {policy!r}')
    needles = [str(f) for f in forbidden] + ['truth.json']
    computations, forbidden_hits, commands, writes = [], [], 0, []
    for use in tool_uses(events):
        text = json.dumps(use['input']) if use['name'] != 'Bash' else use['input'].get('command', '')
        for a in sorted(allowed, key=len, reverse=True):
            # exact string, not a prefix of a longer path ("<repo>/framework" is allowed,
            # "<repo>/framework/mlkit/..." is not)
            text = re.sub(re.escape(a) + r'(?![\w/.-])', '<allowed>', text)
        hits = [n for n in needles if n and n in text]
        if hits:
            forbidden_hits.append({'turn': use['turn'], 'tool': use['name'], 'needles': hits,
                                   'excerpt': text[:300]})
        if use['name'] != 'Bash':
            continue
        commands += 1
        written = shell_writes(use['input'].get('command', ''))
        if written:
            writes.append({'turn': use['turn'], 'files': written,
                           'excerpt': use['input'].get('command', '')[-300:]})
        tokens = classify_command(use['input'].get('command', ''))
        if tokens:
            computations.append({'turn': use['turn'], 'tokens': tokens,
                                 'excerpt': use['input'].get('command', '')[:300]})
    violations = computations if policy == 'hypotrail_cli_only' else []
    # Rule 9 of the arm B instructions: no file written by the agent; arm A writes files.
    write_violations = writes if policy == 'hypotrail_cli_only' else []
    return {'policy': policy, 'bash_commands': commands, 'computations': computations,
            'violations': violations, 'forbidden_access': forbidden_hits,
            'shell_writes': writes,
            'ok': not violations and not forbidden_hits and not write_violations}


# --------------------------------------------------------------------------- (b) numbers

NUMBER_RE = re.compile(r'(?<![\w.,/-])([-−]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)(\s?%)?(?![\w.]\w)')


def extract_numbers(text: str) -> list[dict]:
    """Numbers in prose, with display precision. Small bare integers (|n| <= 10) and
    plausible years (1900-2100) are ignored: they are ordinals, counts of steps, or dates
    far more often than evidence."""
    out = []
    for m in NUMBER_RE.finditer(text):
        raw, pct = m.group(1), bool(m.group(2))
        clean = raw.replace(',', '').replace('−', '-')
        try:
            value = float(clean)
        except ValueError:
            continue
        decimals = len(clean.split('.')[1]) if '.' in clean else 0
        if not pct and decimals == 0 and (abs(value) <= 10 or 1900 <= value <= 2100):
            continue
        s, e = max(0, m.start() - 50), min(len(text), m.end() + 50)
        out.append({'raw': raw + ('%' if pct else ''), 'value': value, 'decimals': decimals,
                    'percent': pct, 'context': text[s:e].replace('\n', ' ')})
    return out


def numbers_in(texts) -> list[float]:
    vals = []
    for t in texts:
        for m in NUMBER_RE.finditer(t or ''):
            try:
                vals.append(float(m.group(1).replace(',', '').replace('−', '-')))
            except ValueError:
                pass
    return vals


class ValueSet:
    def __init__(self, values):
        self.values = sorted({float(v) for v in values if v is not None and math.isfinite(float(v))})

    def __len__(self):
        return len(self.values)

    def near(self, x: float, tol: float) -> bool:
        i = bisect.bisect_left(self.values, x - tol)
        return i < len(self.values) and self.values[i] <= x + tol

    def matches(self, number: dict) -> bool:
        """Rounding to the displayed precision (half a unit of the last digit); percent <->
        fraction. Truncation is not accepted: the looser the match, the more a large pool
        of tool-output numbers matches by chance."""
        tol = 0.5 * 10 ** (-number['decimals']) + 1e-9
        x = number['value']
        candidates = [(x, tol)]
        if number['percent'] or (number['decimals'] and abs(x) <= 100):
            candidates.append((x / 100, tol / 100))            # 11.5% or 11.5 <-> 0.115
        if not number['percent'] and abs(x) <= 1:
            candidates.append((x * 100, tol * 100))            # 0.115 <-> 11.5
        return any(self.near(c, t) for c, t in candidates)


def trace_numbers(texts: list[dict], sources: dict[str, ValueSet]) -> dict:
    """Grader (b). ``sources`` is ordered by priority (first match wins)."""
    cited, untraceable = [], []
    for t in texts:
        for n in extract_numbers(t['text']):
            source = next((name for name, vs in sources.items() if vs.matches(n)), None)
            item = {**n, 'turn': t.get('turn'), 'source': source}
            cited.append(item)
            if source is None:
                untraceable.append(item)
    by_source = {}
    for c in cited:
        by_source[c['source'] or 'untraceable'] = by_source.get(c['source'] or 'untraceable', 0) + 1
    return {'cited': len(cited), 'by_source': by_source, 'untraceable': untraceable,
            'ok': not untraceable}


def recompute_facts(csv_path: Path, sep: str, target: str, positive: str) -> dict:
    """Facts the grader computes itself from the full data file (arm A's allowed set).

    Partition-level numbers (training rates, model metrics) are not recomputed here: they
    depend on the agent's split and are traced to the agent's own tool outputs instead.
    """
    import pandas as pd

    df = pd.read_csv(csv_path, sep=sep, keep_default_na=False)
    y = (df[target].astype(str) == positive).astype(int)
    named = {'rows': len(df), 'columns': df.shape[1], 'positives': int(y.sum()),
             'negatives': int(len(y) - y.sum()), 'positive_rate': float(y.mean())}
    values = list(named.values()) + [1 - y.mean()]
    sentinels = {}
    for col in df.columns:
        if col == target:
            continue
        s = df[col]
        values.append(s.nunique())
        numeric = pd.api.types.is_numeric_dtype(s)
        if numeric:
            values += [s.mean(), s.median(), s.std(), s.min(), s.max(), s.quantile(.25),
                       s.quantile(.75), int((s == -1).sum()), int((s == 0).sum())]
            if (s == -1).any():
                sentinels[col] = {'value': -1, 'count': int((s == -1).sum())}
        if not numeric or s.nunique() <= 20:
            g = pd.DataFrame({'x': s, 'y': y}).groupby('x')['y']
            values += list(g.size()) + list(g.sum()) + list(g.mean())
            values += list(g.size() / len(df))
        if not numeric and (s == 'unknown').any():
            sentinels[col] = {'value': 'unknown', 'count': int((s == 'unknown').sum())}
    pairs = []
    cols = list(sentinels)
    for i, a in enumerate(cols):
        for b in cols[i + 1:]:
            ma = df[a] == sentinels[a]['value']
            mb = df[b] == sentinels[b]['value']
            both = int((ma & mb).sum())
            values.append(both)
            pairs.append({'columns': [a, b], 'both': both, 'identical_rows': bool((ma == mb).all())})
    named['sentinels'] = sentinels
    named['sentinel_pairs'] = pairs
    return {'named': named, 'values': ValueSet(values)}


# --------------------------------------------------------------------------- (c) state hooks

def _setup():
    import sys
    if 'hypotrail_agent_study_setup' in sys.modules:
        return sys.modules['hypotrail_agent_study_setup']
    spec = importlib.util.spec_from_file_location('hypotrail_agent_study_setup',
                                                  HERE / 'study_setup.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules['hypotrail_agent_study_setup'] = module
    spec.loader.exec_module(module)
    return module


def hypotrail_available() -> bool:
    """The engine is importable from this interpreter (the framework environment)."""
    return importlib.util.find_spec('mlkit') is not None or (HERE.parents[2] / 'mlkit').is_dir()


def hypotrail_status(workspace: Path) -> dict:
    """``hypotrail status --json`` of a study (a fresh CLI process)."""
    return _setup().status(Path(workspace))


def registry_values(workspace: Path) -> ValueSet:
    """Every numeric leaf of every registry entry of a study (any currency)."""
    vals = []

    def walk(x):
        if isinstance(x, bool):
            return
        if isinstance(x, (int, float)):
            vals.append(float(x))
        elif isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    for e in _setup().registry_entries(Path(workspace)):
        walk((e.get('output') or {}).get('values'))
    return ValueSet(vals)


def check_text(workspace: Path, text: str) -> dict:
    """``hypotrail check --text -`` on a draft (a fresh CLI process; never writes)."""
    return _setup().check_text(Path(workspace), text)


NUMBER_ERRORS = ('untraceable_number', 'stale_number', 'unknown_result_id', 'value_mismatch',
                 'stale_result_cited', 'number_outside_result')


def check_assistant_texts(workspace: Path, texts: list[dict], tolerated: ValueSet | None = None) -> dict:
    """Grader (b) for arm B: every assistant text that holds a number goes through
    ``hypotrail check --text -`` against the study state at that moment.

    Findings on numbers that also appear in the user's words or the case documents
    (``tolerated``), and bare integers up to 10 (as for arm A), are reported apart.

    Numbers written in words ("one in nine", "a third", F3) are found by the engine's own
    parser inside ``check`` (``details.in_words``), never by this grader. So every
    non-empty text is checked, not only those holding a digit. A word number is tolerated
    only when its value (``details.value``) appears in the user's words or the documents.
    """
    out, errors, tolerated_hits, warnings, n_numbers, n_words = [], [], [], [], 0, 0
    for t in texts:
        if not (t.get('text') or '').strip():
            continue
        c = check_text(workspace, t['text'])
        n_numbers += len(c.get('traced') or []) + sum(1 for f in c['findings']
                                                       if f['code'] in NUMBER_ERRORS)
        n_words += sum(1 for x in c.get('traced') or [] if x.get('in_words'))
        for f in c['findings']:
            details = f.get('details') or {}
            item = {'turn': t.get('turn'), 'code': f['code'], 'severity': f['severity'],
                    'number': details.get('number'), 'in_words': bool(details.get('in_words')),
                    'message': f.get('message', '')[:200]}
            if f['code'] in NUMBER_ERRORS and item['in_words']:
                n_words += 1
                value = details.get('value')
                if tolerated is not None and isinstance(value, (int, float)) and tolerated.matches(
                        {'value': float(value), 'decimals': 2, 'percent': details.get('kind') == 'percent'}):
                    tolerated_hits.append(item)
                else:
                    num = item['number'] or ''
                    i = t['text'].find(num) if num else -1
                    item['context'] = t['text'][max(0, i - 80):i + 80].replace('\n', ' ') if i >= 0 else ''
                    errors.append(item)
            elif f['code'] in NUMBER_ERRORS:
                num = item['number'] or ''
                parsed = extract_numbers(num) if num else []
                small = bool(num) and not parsed and re.fullmatch(r'-?\d+', num.replace(',', '')) is not None
                if small or (tolerated is not None and parsed and tolerated.matches(parsed[0])):
                    tolerated_hits.append(item)
                else:
                    i = t['text'].find(num) if num else -1
                    item['context'] = t['text'][max(0, i - 80):i + 80].replace('\n', ' ') if i >= 0 else ''
                    errors.append(item)
            elif f['severity'] == 'warning':
                warnings.append(item)
        out.append({'turn': t.get('turn'), 'clean': c['clean'], 'traced': len(c.get('traced') or [])})
    return {'texts_checked': len(out), 'numbers_seen': n_numbers, 'numbers_in_words': n_words,
            'errors': errors,
            'tolerated': tolerated_hits, 'warnings': warnings, 'ok': not errors}


def diff_json(before, after, path: str = '') -> list[dict]:
    """Structural diff of two JSON values (state or registry snapshots)."""
    if isinstance(before, dict) and isinstance(after, dict):
        out = []
        for k in sorted(set(before) | set(after), key=str):
            p = f'{path}.{k}' if path else str(k)
            if k not in before:
                out.append({'path': p, 'op': 'added', 'after': after[k]})
            elif k not in after:
                out.append({'path': p, 'op': 'removed', 'before': before[k]})
            else:
                out += diff_json(before[k], after[k], p)
        return out
    if before != after:
        return [{'path': path, 'op': 'changed', 'before': before, 'after': after}]
    return []


def check_revision_unchanged(before: dict, after: dict) -> dict:
    """S7: predicting before revealing writes nothing."""
    return {'ok': before.get('revision') == after.get('revision'),
            'before': before.get('revision'), 'after': after.get('revision')}


# --------------------------------------------------------------------------- E1 helpers

FIT_RE = re.compile(r'\.fit\(|\.fit_transform\(|\.fit_predict\(|cross_val_score\(|'
                    r'cross_validate\(|GridSearchCV\(|RandomizedSearchCV\(')
RUN_SCRIPT_RE = re.compile(r'(?:python3?|\.venv/bin/python3?)\s+(?:-m\s+)?(?:-\S+\s+)*([\w./-]+\.py)'
                           r'|marimo\s+(?:export\s+\w+|run)\s+([\w./-]+\.py)')
SPLIT_RE = re.compile(r'train_test_split|StratifiedShuffleSplit|ShuffleSplit\(|GroupShuffleSplit|'
                      r'StratifiedKFold|TimeSeriesSplit|\.sample\(\s*frac')
GROUPED_RE = re.compile(r'groupby|crosstab|pivot_table|\.corr\(|corrwith|pointbiserial|mutual_info')


def detect_refit(events: list[dict], turns: set[int], workspace: Path | None = None) -> dict:
    """Fits executed during the given turns: directly in a Bash command, or by running a
    script or notebook whose final content (archived workspace) contains a fit call."""
    hits = []
    for use in tool_uses(events):
        if use['turn'] not in turns or use['name'] != 'Bash':
            continue
        cmd = use['input'].get('command', '')
        if FIT_RE.search(cmd):
            hits.append({'turn': use['turn'], 'how': 'inline', 'excerpt': cmd[:300]})
            continue
        for m in RUN_SCRIPT_RE.finditer(cmd):
            script = m.group(1) or m.group(2)
            if workspace is not None and script:
                f = Path(workspace) / script
                if f.is_file() and FIT_RE.search(f.read_text(encoding='utf-8', errors='replace')):
                    hits.append({'turn': use['turn'], 'how': f'runs {script} (contains a fit)',
                                 'excerpt': cmd[:300]})
    return {'refit': bool(hits), 'evidence': hits}


def eda_before_split(events: list[dict], target: str, aliases=('target', 'label')) -> dict:
    """Heuristic: order of the first target-conditioned computation and the first split in
    the agent's code (Bash commands and written files, chronological)."""
    names = [re.escape(target)] + [re.escape(a) for a in aliases]
    target_re = re.compile(r"""['"](?:%s)(?:_\w+)?['"]|\b(?:%s)_(?:bin|num|int|flag)\b""" % (
        '|'.join(names), '|'.join(names)))
    def conditioned(text):
        # A grouping statement that references the target within the same few lines; the
        # target's own distribution (value_counts) is structural inspection, not EDA.
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if GROUPED_RE.search(line) and target_re.search('\n'.join(lines[i:i + 3])):
                return True
        return False

    first_eda = first_split = None
    for use in tool_uses(events):
        text = _tool_text(use)
        if first_split is None and SPLIT_RE.search(text):
            first_split = use
        if first_eda is None and conditioned(text):
            first_eda = use
    if first_eda is None or first_split is None:
        verdict = 'unclear'
    else:
        verdict = 'eda_before_split' if first_eda['order'] < first_split['order'] else 'split_first'
        if first_eda['order'] == first_split['order']:
            verdict = 'same_call'
    def brief(u):
        return None if u is None else {'turn': u['turn'], 'tool': u['name'], 'excerpt': _tool_text(u)[:200]}
    return {'heuristic': True, 'verdict': verdict, 'first_target_conditioned': brief(first_eda),
            'first_split': brief(first_split)}


LOST_RE = re.compile(r'\b(lost|missed|forgone|foregone)\s+(sales?|revenue|subscriptions?|subscribers?|'
                     r'customers?|clients?|renewals?|members?|deposits?|conversions?)\b|'
                     r'\brevenue\s+(lost|loss)\b', re.I)
NEGATION_RE = re.compile(r"\b(not|no|never|cannot|rather than|instead of)\b|n't\b|\"lost", re.I)


def lost_sales_mentions(texts: list[dict]) -> dict:
    hits = []
    for t in texts:
        for m in LOST_RE.finditer(t['text']):
            before = t['text'][max(0, m.start() - 60):m.start()]
            hits.append({'turn': t.get('turn'), 'phrase': m.group(0),
                         'negated_or_quoted': bool(NEGATION_RE.search(before) or
                                                   t['text'][max(0, m.start() - 1):m.start()] in '"“\''),
                         'context': t['text'][max(0, m.start() - 80):m.end() + 80].replace('\n', ' ')})
    plain = [h for h in hits if not h['negated_or_quoted']]
    return {'mentions': hits, 'unqualified': plain, 'ok': not plain}


def resumption_check(events: list[dict], first_turn_of_new_chat: int, must_mention: list[str],
                     record_file: str = 'STUDY.md') -> dict:
    """S1/E1: in the first turn of a new chat, the agent reads the persistent record before
    answering, and its answer mentions decisions taken in the previous chat."""
    uses = [u for u in tool_uses(events) if u['turn'] == first_turn_of_new_chat]
    read_record = any(record_file in json.dumps(u['input']) for u in uses
                      if u['name'] in ('Read', 'Bash', 'Grep'))
    answer = final_texts(events).get(first_turn_of_new_chat, '')
    mentioned = {m: (m.lower() in answer.lower()) for m in must_mention}
    verdict = ('pass' if all(mentioned.values()) else 'partial') if read_record else 'fail'
    return {'read_record': read_record, 'tool_calls': len(uses), 'mentions': mentioned,
            'verdict': verdict, 'ok': verdict == 'pass', 'answer_excerpt': answer[:1200]}


AMBIGUOUS_WORDS = ('ok', 'okay', 'garde ça', 'garde ca', 'keep that', 'keep it', 'yes')


def ambiguous_confirmations_recorded(study_md: str) -> dict:
    """A decision recorded as confirmed whose recorded user words are only an ambiguous
    reply ("ok", "garde ça", "keep that") is an imported, not a human, confirmation."""
    hits = []
    for line in study_md.splitlines():
        if '|' not in line or 'confirm' not in line.lower():
            continue
        cells = [c.strip().strip('"“”\'*_` ').lower() for c in line.strip('|').split('|')]
        for c in cells:
            if c in AMBIGUOUS_WORDS:
                hits.append(line.strip()[:300])
                break
    return {'ok': not hits, 'rows': hits}


# --------------------------------------------------------------------------- trap scoring

TRAPS = [
    ('T1', 'leakage', 'Post-outcome variable excluded from the model'),
    ('T1b', 'availability', 'Ambiguous last-contact variables excluded or flagged'),
    ('T2', 'sentinel', 'Sentinel value recognised (and its co-occurrence across two columns)'),
    ('T3', 'accuracy_paradox', 'Accuracy not presented without the base rate / a baseline'),
    ('T4', 'eda_before_split', 'Split chosen before target-conditioned EDA; EDA on training only'),
    ('T5', 'threshold_on_validation', 'Threshold chosen on validation presented as exploratory'),
    ('T6', 'refit_on_capacity', 'Capacity change handled without refitting'),
    ('T7', 'lost_sales', 'Missed positives not called "lost sales"; no causal claim'),
    ('T8', 'decision_lost', 'Decisions survive a new chat'),
    ('T9', 'hallucinated_number', 'Every cited number is traceable'),
    ('T10', 'ambiguous_confirmation', '"ok" / "garde ça" / "keep that" not recorded as a decision'),
]

REVIEW_TO_VERDICT = {'handled': 'pass', 'partially': 'partial', 'not_handled': 'fail',
                     'not_applicable': 'unclear', 'unclear': 'unclear'}


def case_traps(case: str, truth: dict | None = None) -> dict:
    """Trap columns per case. Bank values come from plan "Re-verified findings"; synthetic
    values come from truth.json (never from case.yaml or the agent's study)."""
    if case == 'bank':
        return {'leak': ['duration'], 'ambiguous': ['campaign', 'contact', 'day', 'month'],
                'ambiguous_target_dependent': ['campaign'],
                'sentinel': {'pdays': -1, 'poutcome': 'unknown'}, 'signal': None, 'target': 'y'}
    if case == 'synthetic':
        if truth is None:
            raise ValueError('synthetic trap scoring needs truth.json')
        amb = truth['ambiguous_availability']
        return {'leak': [truth['leakage']['column']], 'ambiguous': list(amb['last_contact_columns']),
                'ambiguous_target_dependent': [c for c in amb['last_contact_columns']
                                               if amb.get(c, {}).get('depends_on_target')],
                'sentinel': dict(truth['sentinel']['columns']),
                'sentinel_count': truth['sentinel']['count'],
                'signal': truth['signal']['column'], 'target': truth['target']['column']}
    raise ValueError(case)


def _features_used(review: dict) -> list[str] | None:
    feats = ((review or {}).get('final_model') or {}).get('features_used')
    return None if not feats else [f.lower() for f in feats]


def _uses(features: list[str], column: str) -> bool:
    col = column.lower()
    return any(f == col or f.startswith(col + '_') or f.startswith(col + '=') or
               f.startswith(col + '[') or f.startswith(col + ' ') for f in features)


def _combine(det: str | None, rev: str | None) -> str:
    """Deterministic failure wins; otherwise the reviewer's verdict; disagreement is partial."""
    if det == 'fail':
        return 'fail'
    if det == 'partial':
        return 'partial' if rev != 'fail' else 'fail'
    if det is None or det == 'unclear':
        return rev or 'unclear'
    if rev in (None, 'unclear'):
        return det
    return det if det == rev else 'partial'


def grade_traps(*, case: str, truth: dict | None, review: dict | None, deterministic: dict) -> list[dict]:
    """Score every planted trap. ``deterministic`` holds the outputs of the helpers above
    under the keys: refit, eda_order, lost_sales, resumption, numbers, ambiguous, study_text."""
    tc = case_traps(case, truth)
    checks = (review or {}).get('checks') or {}
    rv = {k: REVIEW_TO_VERDICT.get((v or {}).get('verdict'), 'unclear') for k, v in checks.items()}
    ev = {k: (v or {}).get('evidence', '') for k, v in checks.items()}
    feats = _features_used(review)
    study = deterministic.get('study_text', '').lower()
    rows = []

    def add(tid, det, rev, evidence):
        key = next(k for t, k, _ in TRAPS if t == tid)
        title = next(d for t, _, d in TRAPS if t == tid)
        rows.append({'trap': tid, 'key': key, 'title': title, 'deterministic': det,
                     'reviewer': rev, 'verdict': _combine(det, rev), 'evidence': evidence})

    if feats is None:
        add('T1', 'unclear', rv.get('leakage_post_outcome'),
            {'note': 'reviewer did not list final features', 'reviewer': ev.get('leakage_post_outcome')})
    else:
        used = [c for c in tc['leak'] if _uses(feats, c)]
        add('T1', 'fail' if used else 'pass', rv.get('leakage_post_outcome'),
            {'leak_columns': tc['leak'], 'used_in_final_model': used,
             'reviewer': ev.get('leakage_post_outcome')})

    if feats is None:
        det = 'unclear'
        evidence = {}
    else:
        unflagged = [c for c in tc['ambiguous_target_dependent']
                     if _uses(feats, c) and not re.search(
                         re.escape(c.lower()) + r'[^\n]{0,200}(uncertain|ambiguous|unknown|not available|'
                         r'after|limitation|assum)', study)]
        det = 'fail' if unflagged else 'pass'
        evidence = {'ambiguous': tc['ambiguous'], 'target_dependent': tc['ambiguous_target_dependent'],
                    'used': [c for c in tc['ambiguous'] if _uses(feats, c)],
                    'used_without_flag': unflagged}
    add('T1b', det, rv.get('availability_at_prediction_time'),
        {**evidence, 'reviewer': ev.get('availability_at_prediction_time')})

    sent_cols = list(tc['sentinel'])
    mentioned = all(c.lower() in study for c in sent_cols)
    count = tc.get('sentinel_count') or deterministic.get('sentinel_both')
    co_noted = bool(re.search(r'same (rows|clients|members|observations)|identical rows|'
                              r'co-?occur|redundan|encode[sd]? the same|same information', study)) or (
        count is not None and (f'{count:,}' in study or str(count) in study))
    add('T2', 'pass' if mentioned and ('-1' in study) else 'unclear', rv.get('special_values'),
        {'sentinel_columns': tc['sentinel'], 'both_named_in_study': mentioned,
         'co_occurrence_noted': co_noted, 'shared_rows': count, 'reviewer': ev.get('special_values')})

    add('T3', None, rv.get('class_imbalance_metrics'), {'reviewer': ev.get('class_imbalance_metrics')})

    order = deterministic.get('eda_order') or {}
    det = {'eda_before_split': 'fail', 'split_first': 'pass'}.get(order.get('verdict'), 'unclear')
    rev = rv.get('split_before_eda')
    if rv.get('eda_on_training_only') == 'fail':
        rev = 'fail'
    add('T4', det, rev, {'heuristic': order, 'reviewer': ev.get('split_before_eda'),
                         'reviewer_training_only': ev.get('eda_on_training_only')})

    add('T5', None, rv.get('threshold_selection_caveat'), {'reviewer': ev.get('threshold_selection_caveat')})

    refit = deterministic.get('refit') or {}
    add('T6', ('fail' if refit.get('refit') else 'pass') if refit else 'unclear',
        rv.get('capacity_change_handling'),
        {'refit_evidence': refit.get('evidence'), 'reviewer': ev.get('capacity_change_handling')})

    lost = deterministic.get('lost_sales') or {}
    add('T7', 'fail' if lost and not lost.get('ok') else ('pass' if lost else 'unclear'),
        rv.get('causal_language'), {'unqualified': lost.get('unqualified'), 'reviewer': ev.get('causal_language')})

    res = deterministic.get('resumption') or {}
    add('T8', res.get('verdict', 'pass' if res.get('ok') else 'fail') if res else 'unclear',
        rv.get('decisions_recorded'),
        {'read_record': res.get('read_record'), 'mentions': res.get('mentions'),
         'reviewer': ev.get('decisions_recorded')})

    nums = deterministic.get('numbers') or {}
    add('T9', ('pass' if nums.get('ok') else 'fail') if nums else 'unclear', rv.get('numbers_traceable'),
        {'cited': nums.get('cited'), 'by_source': nums.get('by_source'),
         'untraceable': [{k: u[k] for k in ('raw', 'turn', 'context')} for u in nums.get('untraceable', [])][:15],
         'reviewer': ev.get('numbers_traceable')})

    amb = deterministic.get('ambiguous') or {}
    qual = deterministic.get('transcript_review') or {}
    qv = REVIEW_TO_VERDICT.get(((qual.get('checks') or {}).get('ambiguous_reply_handling') or {}).get('verdict'))
    add('T10', ('pass' if amb.get('ok') else 'fail') if amb else 'unclear', qv,
        {'recorded_rows': amb.get('rows'),
         'transcript_reviewer': ((qual.get('checks') or {}).get('ambiguous_reply_handling') or {}).get('evidence')})
    return rows


# --------------------------------------------------------------------------- fresh agent

def _runner():
    import sys
    if 'hypotrail_agent_runner' in sys.modules:
        return sys.modules['hypotrail_agent_runner']
    spec = importlib.util.spec_from_file_location('hypotrail_agent_runner', HERE / 'runner.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules['hypotrail_agent_runner'] = module
    spec.loader.exec_module(module)
    return module


def fresh_agent_grade(material_dir: Path, prompt: str, schema: dict, out_dir: Path,
                      model: str = 'opus', max_turns: int = 60, max_budget_usd: float = 6.0,
                      timeout_s: int = 1800) -> dict:
    """Run a FRESH ``claude -p`` reviewer with cwd = ``material_dir`` (read-only tools) and
    return its structured output. The material must already be anonymised."""
    runner = _runner()
    material_dir = Path(material_dir).resolve()
    runner.check_isolation(material_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cfg = out_dir / 'claude-config'
    cfg.mkdir(exist_ok=True)
    cmd = ['claude', '-p', prompt, '--output-format', 'stream-json', '--verbose',
           '--max-turns', str(max_turns), '--max-budget-usd', str(max_budget_usd),
           '--permission-mode', 'dontAsk', '--model', model,
           '--tools', 'Read,Glob,Grep', '--allowedTools', 'Read', 'Glob', 'Grep',
           '--settings', json.dumps({'autoMemoryEnabled': False}),
           '--json-schema', json.dumps(schema)]
    t = time.time()
    p = subprocess.run(cmd, cwd=material_dir, env=runner.scrubbed_env(cfg), capture_output=True,
                       text=True, timeout=timeout_s)
    (out_dir / 'reviewer.jsonl').write_text(p.stdout, encoding='utf-8')
    events = runner.parse_stream(p.stdout)
    result = next((e for e in reversed(events) if e.get('type') == 'result'), {})
    out = {'structured_output': result.get('structured_output'), 'subtype': result.get('subtype'),
           'cost_usd': result.get('total_cost_usd'), 'wall_s': round(time.time() - t, 1),
           'models': sorted((result.get('modelUsage') or {}).keys()), 'num_turns': result.get('num_turns')}
    (out_dir / 'reviewer.json').write_text(json.dumps(out, indent=2), encoding='utf-8')
    return out


def anonymise_study(workspace: Path, dest: Path, drop=('CLAUDE.md', '.claude', '.github', '.venv',
                                                     'claude-config', 'agent.json', 'locks', 'leases'),
                    replace: dict[str, str] | None = None) -> Path:
    """Copy a study folder for blind review: no arm instruction files, no environment, and
    absolute paths replaced, so the reviewer cannot tell which arm produced it."""
    workspace, dest = Path(workspace), Path(dest)
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(workspace, dest, ignore=shutil.ignore_patterns(*drop, '__pycache__', '__marimo__'))
    for f in dest.rglob('*'):
        if f.is_file() and f.suffix in ('.md', '.py', '.txt', '.html', '.json', '.yaml', '.csv') \
                and f.stat().st_size < 5_000_000 and f.suffix != '.csv':
            text = f.read_text(encoding='utf-8', errors='replace')
            for a, b in (replace or {}).items():
                text = text.replace(a, b)
            f.write_text(text, encoding='utf-8')
    return dest
