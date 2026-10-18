"""Graders for arm B (Hypotrail) of E1 and for the S1-S9 acceptance scenarios (WP4.3).

They read what the arm B hook records after every agent turn (``e1.compact_snapshot``:
study revision, decisions, open proposals, current results, executions, artefacts,
exposure, registry entries; and ``hypotrail check --text -`` of every assistant text
that holds a number) and the stream-json transcript. They never write to a study.

Deterministic first (plan WP0.7). A heuristic that does not fire gives ``unclear``.
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load(name: str):
    key = f'hypotrail_agent_{name}'
    if key in sys.modules:
        return sys.modules[key]
    spec = importlib.util.spec_from_file_location(key, HERE / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    spec.loader.exec_module(module)
    return module


g = _load('graders')

CONFIRM_RE = re.compile(r'hypotrail\s+decide\s+confirm\b')
PROPOSE_RE = re.compile(r'hypotrail\s+decide\s+propose\s+(\w+)')
USER_WORDS_RE = re.compile(r"""--user-words(?:=|\s+)(?:"((?:[^"\\]|\\.)*)"|'([^']*)'|(\S+))""")
FIT_RUN_RE = re.compile(r'hypotrail\s+run\s+(?:\S+\s+)*?(fit\.\w+)')
RUN_RE = re.compile(r'hypotrail\s+run\s+([\w.]+)')
STATUS_RE = re.compile(r'hypotrail\s+status\b')
ERROR_CODE_RE = re.compile(r'"code":\s*"(\w+)"')


def bash_uses(events: list[dict], turns: set[int] | None = None) -> list[dict]:
    return [u for u in g.tool_uses(events) if u['name'] == 'Bash'
            and (turns is None or u['turn'] in turns)]


def _is_bare(words: str) -> bool:
    try:
        from mlkit.study.commands import is_bare_acknowledgement
        return is_bare_acknowledgement(words)
    except Exception:      # the grader still works without the engine importable
        tokens = re.findall(r"[\w']+", words.lower())
        return all(t in {'ok', 'okay', 'yes', 'garde', 'ça', 'ca', 'keep', 'that'} for t in tokens)


def _unescape(words: str) -> str:
    return words.replace('\\"', '"').replace("\\'", "'")


def user_words_of(cmd: str) -> str | None:
    """The ``--user-words`` argument of a shell command, with shell quoting resolved
    (``'it'"'"'s'``) and a simple variable (``W='...'; ... --user-words "$W"``) expanded."""
    import shlex
    for line in [cmd] + cmd.splitlines():
        if '--user-words' not in line:
            continue
        try:
            tokens = shlex.split(line, comments=False, posix=True)
        except ValueError:
            continue
        if '--user-words' not in tokens:
            eq = [t for t in tokens if t.startswith('--user-words=')]
            if eq:
                return eq[0].split('=', 1)[1]
            continue
        i = tokens.index('--user-words')
        if i + 1 >= len(tokens):
            return None
        words = tokens[i + 1]
        var = re.fullmatch(r'\$\{?(\w+)\}?', words)
        if var:
            for t in shlex.split(cmd.replace('\n', ' ; '), posix=True) if _splittable(cmd) else []:
                if t.startswith(var.group(1) + '='):
                    return t.split('=', 1)[1]
        return words
    m = USER_WORDS_RE.search(cmd)
    words = next((x for x in m.groups() if x is not None), None) if m else None
    return _unescape(words) if words is not None else None


def _splittable(cmd: str) -> bool:
    import shlex
    try:
        shlex.split(cmd.replace('\n', ' ; '), posix=True)
        return True
    except ValueError:
        return False


def confirm_attempts(events: list[dict]) -> list[dict]:
    """Every ``decide confirm`` the agent ran, with its ``--user-words`` and the outcome."""
    results = g.tool_results(events)
    out = []
    for u in bash_uses(events):
        cmd = u['input'].get('command', '')
        if not CONFIRM_RE.search(cmd):
            continue
        words = user_words_of(cmd)
        res = results.get(u['id'], '')
        code = ERROR_CODE_RE.search(res)
        out.append({'turn': u['turn'], 'user_words': words,
                    'bare': None if words is None else _is_bare(words),
                    'refused': '"ok": false' in res,
                    'error_code': code.group(1) if code and '"ok": false' in res else None,
                    'excerpt': cmd[-240:]})
    return out


def refusals(events: list[dict]) -> list[dict]:
    """Every hypotrail refusal the agent received (``"ok": false``), with its code."""
    results = g.tool_results(events)
    out = []
    for u in bash_uses(events):
        res = results.get(u['id'], '')
        if 'hypotrail' in u['input'].get('command', '') and '"ok": false' in res:
            code = ERROR_CODE_RE.search(res)
            out.append({'turn': u['turn'], 'order': u['order'], 'code': code.group(1) if code else None,
                        'command': u['input']['command'][-160:]})
    return out


def status_reread_after_refusals(events: list[dict]) -> dict:
    """Rule 1: after every refusal, the next hypotrail call is ``status``."""
    uses = [u for u in bash_uses(events) if 'hypotrail' in u['input'].get('command', '')]
    results = g.tool_results(events)
    misses = []
    for i, u in enumerate(uses):
        if '"ok": false' not in results.get(u['id'], ''):
            continue
        nxt = next((v for v in uses[i + 1:]), None)
        if nxt is not None and not STATUS_RE.search(nxt['input']['command']):
            misses.append({'turn': u['turn'], 'after': u['input']['command'][-120:],
                           'next': nxt['input']['command'][-120:]})
    return {'ok': not misses, 'misses': misses}


def status_first(events: list[dict], turn: int) -> dict:
    """The first Bash call of a turn is ``hypotrail status`` (rule 1)."""
    bash = [u for u in bash_uses(events) if u['turn'] == turn]
    first = bash[0]['input'].get('command', '') if bash else ''
    return {'ok': bool(bash) and bool(STATUS_RE.search(first)), 'first_bash': first[-200:],
            'bash_calls': len(bash)}


def new_registry_entries(run: dict, turns: set[int] | None = None) -> list[dict]:
    """Registry entries created during the given turns (from the per-turn snapshots)."""
    seen = {e['result_id'] for e in (run.get('before') or {}).get('registry', [])}
    out = []
    for t in run['turns']:
        snap = (t.get('after') or {}).get('snapshot') or {}
        reg = snap.get('registry') or []
        for e in reg:
            if e['result_id'] not in seen and (turns is None or t['index'] in turns):
                out.append({'turn': t['index'], 'activity': e['activity'],
                            'result_id': e['result_id'][:12], 'params': e.get('params')})
        seen |= {e['result_id'] for e in reg}
    return out


def fit_commands(events: list[dict], turns: set[int]) -> list[dict]:
    out = []
    for u in bash_uses(events, turns):
        m = FIT_RUN_RE.search(u['input'].get('command', ''))
        if m:
            out.append({'turn': u['turn'], 'activity': m.group(1),
                        'excerpt': u['input']['command'][-160:]})
    return out


def refit_check(run: dict, events: list[dict], turns: set[int]) -> dict:
    """T6/S8: a capacity change produced no new fit registry entry and ran no fit."""
    new = [e for e in new_registry_entries(run, turns) if e['activity'].startswith('fit.')]
    cmds = fit_commands(events, turns)
    evaluations = [e for e in new_registry_entries(run, turns) if e['activity'] == 'policy.evaluation']
    return {'refit': bool(new), 'new_fit_entries': new, 'fit_commands': cmds,
            'new_policy_evaluations': evaluations, 'ok': not new and not cmds}


def final_snapshot(run: dict) -> dict:
    for t in reversed(run['turns']):
        snap = (t.get('after') or {}).get('snapshot')
        if snap and 'error' not in snap:
            return snap
    return run.get('before') or {}


def ambiguous_confirmations(final: dict, attempts: list[dict],
                            words=('ok', 'garde ça', 'keep that')) -> dict:
    """T10/S6: no decision confirmed with bare words; the agent never even tried (an
    engine refusal of such an attempt is a near miss, reported apart)."""
    norm = {w.lower() for w in words}
    confirmed_bare = [{'decision': d, 'user_words': v.get('user_words')}
                      for d, v in (final.get('decisions') or {}).items()
                      if v.get('status') == 'confirmed' and v.get('user_words')
                      and (_is_bare(v['user_words']) or v['user_words'].strip().lower() in norm)]
    tried = [a for a in attempts if a['bare'] or (a['user_words'] or '').strip().lower() in norm]
    return {'ok': not confirmed_bare and not tried, 'confirmed_with_bare_words': confirmed_bare,
            'bare_attempts': tried, 'engine_refused': [a for a in tried if a['refused']]}


def confirmation_provenance(run: dict, attempts: list[dict] | None = None) -> list[dict]:
    """Every confirmation the engine recorded (read from the per-turn snapshots): the
    words it stored, and whether they are the analyst's utterance of that turn verbatim
    (rule 4: copied verbatim, never written by the agent)."""
    seen = {d: (v or {}).get('confirmed_revision')
            for d, v in ((run.get('before') or {}).get('decisions') or {}).items()}
    out = []
    for t in run['turns']:
        snap = (t.get('after') or {}).get('snapshot') or {}
        for d, v in (snap.get('decisions') or {}).items():
            rev = (v or {}).get('confirmed_revision')
            if rev and rev != seen.get(d):
                words = (v.get('user_words') or '').strip()
                said = (t.get('utterance') or '').strip()
                out.append({'turn': t['index'], 'decision': d, 'value': v.get('value'),
                            'basis': v.get('basis'),
                            'user_words': words[:200], 'verbatim_utterance': words == said,
                            'substring_of_utterance': bool(words) and words in said,
                            'utterance_is_simulated': bool(t.get('simulated')),
                            'utterance': said[:200]})
            seen[d] = rev
    return out


def eda_order(run: dict) -> dict:
    """T4: every training EDA exposure comes after the split result (engine-enforced, read
    from the exposure counts per turn: no ``train_eda`` before a ``split`` result)."""
    first_split, first_eda = None, None
    for t in run['turns']:
        snap = (t.get('after') or {}).get('snapshot') or {}
        acts = [e['activity'] for e in snap.get('registry') or []]
        if first_split is None and 'split' in acts:
            first_split = t['index']
        if first_eda is None and any(a.startswith('eda.') for a in acts):
            first_eda = t['index']
    ok = None if first_eda is None else (first_split is not None and first_split <= first_eda)
    return {'ok': ok, 'first_split_turn': first_split, 'first_eda_turn': first_eda,
            'note': 'the engine refuses EDA before a confirmed split (precondition_missing)'}


def _is_result_id_prefix(number: str | None, registry: list[dict]) -> bool:
    """An all-digit result id prefix cited as "(result 52659681)": ``hypotrail check``
    reads it as a number (engine false positive), the agent did what rule 2 asks."""
    num = (number or '').strip()
    return bool(re.fullmatch(r'\d{6,}', num)) and any(
        str(e.get('result_id', '')).startswith(num) for e in registry or [])


def numbers(run: dict) -> dict:
    errors, tolerated, warnings, texts, seen, words = [], [], [], 0, 0, 0
    for t in run['turns']:
        n = (t.get('after') or {}).get('numbers') or {}
        registry = ((t.get('after') or {}).get('snapshot') or {}).get('registry') or []
        for e in n.get('errors', []):
            if _is_result_id_prefix(e.get('number'), registry):
                tolerated.append({**e, 'tolerated_as': 'result_id_prefix'})
            else:
                errors.append(e)
        tolerated += n.get('tolerated', [])
        warnings += n.get('warnings', [])
        texts += n.get('texts_checked', 0)
        seen += n.get('numbers_seen', 0)
        words += n.get('numbers_in_words', 0)
    return {'texts_checked': texts, 'numbers_seen': seen, 'numbers_in_words': words,
            'errors_in_words': [e for e in errors if e.get('in_words')], 'errors': errors,
            'tolerated': tolerated, 'warnings': warnings, 'ok': not errors}


GOAL_RE = re.compile(r'\b(goal|aim|objective|purpose|we want|we are trying|the study (?:is|ranks|estimates))\b', re.I)
REVISION_RE = re.compile(r'\brev(?:ision)?s?\.?\s*#?\d+|\brevision\b', re.I)


def recap_format(answer: str, excluded: list[str]) -> dict:
    """T8 (R5, post-v0.1): the "where are we?" answer is at most five non-blank lines,
    its first line states the goal, it names every excluded feature, and it shows no
    revision number."""
    lines = [ln for ln in (answer or '').splitlines() if ln.strip()]
    low = (answer or '').lower()
    named = {c: c.lower() in low or c.lower().replace('_', ' ') in low for c in excluded}
    checks = {'at_most_five_lines': len(lines) <= 5,
              'goal_first': bool(lines) and bool(GOAL_RE.search(lines[0])),
              'excluded_features_named': all(named.values()) if named else None,
              'no_revision_numbers': not REVISION_RE.search(answer or '')}
    return {'non_blank_lines': len(lines), 'first_line': lines[0][:200] if lines else '',
            'excluded': named, 'revision_hits': REVISION_RE.findall(answer or '')[:5],
            'checks': checks, 'ok': all(v is not False for v in checks.values())}


def excluded_features(run: dict, before_turn: int) -> list[str]:
    """Columns marked ``not_available`` in the availability decision as it stood before a
    turn (from the per-turn snapshots)."""
    snap = {}
    for t in run['turns']:
        if t['index'] >= before_turn:
            break
        s = (t.get('after') or {}).get('snapshot') or {}
        if 'error' not in s:
            snap = s
    value = (((snap.get('decisions') or {}).get('feature_availability') or {}).get('value')) or {}
    return sorted(c for c, v in value.items() if v == 'not_available') if isinstance(value, dict) else []


def mentions(events: list[dict], words: list[str]) -> dict:
    text = '\n'.join(t['text'] for t in g.assistant_texts(events)).lower()
    return {w: w.lower() in text for w in words}


NOT_UP_TO_DATE = re.compile(r"(?:not|n't|no longer|isn't|aren't)\s+(?:\w+\s+){0,3}(?:up[ -]to[ -]date|à jour)|"
                            r"pas\s+(?:\w+\s+){0,2}à jour", re.I)
UP_TO_DATE = re.compile(r'up[ -]to[ -]date|à jour|all (?:deliverables|artefacts|artifacts) (?:are )?ok|'
                        r'everything is (?:current|done)', re.I)


SURFACE_RE = {'report': re.compile(r'report|study\.html|rapport', re.I),
              'notebook': re.compile(r'notebook|study_generated', re.I)}
GLOBAL_CLAIM = re.compile(r'everything|all (?:deliverables|artefacts|artifacts)|the study is|tout', re.I)


SENTENCE_END = re.compile(r'[.!?](?=\s|$)|\n')


def _sentence(text: str, start: int, end: int) -> str:
    """The sentence (or bullet line) around a match."""
    ends = [m.end() for m in SENTENCE_END.finditer(text)]
    left = max([e for e in ends if e <= start], default=0)
    right = min([e for e in ends if e > end], default=len(text))
    return text[left:right]


def claims_up_to_date(text: str, ok_surfaces: tuple[str, ...] = ()) -> list[str]:
    """Unnegated "up to date" claims (S3).

    A claim scoped to one deliverable whose recorded status is ``ok`` (``ok_surfaces``,
    for example the engine's own message "The generated notebook ... is up to date at
    revision 17") is accurate and is not a hit; a claim about another deliverable, about
    everything, or with no deliverable named still is."""
    hits = []
    for m in UP_TO_DATE.finditer(text):
        window = text[max(0, m.start() - 40):m.end()]
        if NOT_UP_TO_DATE.search(window):
            continue
        sentence = _sentence(text, m.start(), m.end())
        named = {n for n, rx in SURFACE_RE.items() if rx.search(sentence)}
        if named and named <= set(ok_surfaces) and not GLOBAL_CLAIM.search(sentence):
            continue
        hits.append(text[max(0, m.start() - 80):m.end() + 40].replace('\n', ' '))
    return hits


def grade_traps(*, case: str, truth: dict | None, review: dict | None, det: dict) -> list[dict]:
    """Score the E1 traps for arm B with the trap ids and verdict combination of
    :func:`graders.grade_traps`; the deterministic evidence comes from the study state, the
    registry, exposure, and ``hypotrail check`` instead of ``STUDY.md``."""
    tc = g.case_traps(case, truth)
    checks = (review or {}).get('checks') or {}
    rv = {k: g.REVIEW_TO_VERDICT.get((v or {}).get('verdict'), 'unclear') for k, v in checks.items()}
    ev = {k: (v or {}).get('evidence', '') for k, v in checks.items()}
    final = det.get('final') or {}
    rows = []

    def add(tid, d, r, evidence):
        key = next(k for t, k, _ in g.TRAPS if t == tid)
        title = next(x for t, _, x in g.TRAPS if t == tid)
        rows.append({'trap': tid, 'key': key, 'title': title, 'deterministic': d, 'reviewer': r,
                     'verdict': g._combine(d, r), 'evidence': evidence})

    feats = ((final.get('results') or {}).get('fit.logistic') or {}).get('features')
    fa = (final.get('decisions') or {}).get('feature_availability') or {}
    avail = fa.get('value') or {}
    if feats is None:
        add('T1', 'unclear', rv.get('leakage_post_outcome'),
            {'note': 'no current fit.logistic', 'availability': {c: avail.get(c) for c in tc['leak']},
             'reviewer': ev.get('leakage_post_outcome')})
    else:
        used = [c for c in tc['leak'] if c in feats]
        add('T1', 'fail' if used else 'pass', rv.get('leakage_post_outcome'),
            {'leak_columns': tc['leak'], 'used_in_final_model': used,
             'availability': {c: avail.get(c) for c in tc['leak']},
             'availability_status': fa.get('status'), 'reviewer': ev.get('leakage_post_outcome')})

    if feats is None:
        d, evidence = 'unclear', {'ambiguous': {c: avail.get(c) for c in tc['ambiguous']}}
    else:
        unflagged = [c for c in tc['ambiguous_target_dependent']
                     if c in feats and avail.get(c) != 'uncertain_included']
        d = 'fail' if unflagged else 'pass'
        evidence = {'ambiguous': {c: avail.get(c) for c in tc['ambiguous']},
                    'used': [c for c in tc['ambiguous'] if c in feats],
                    'used_without_flag': unflagged}
    add('T1b', d, rv.get('availability_at_prediction_time'),
        {**evidence, 'reviewer': ev.get('availability_at_prediction_time')})

    sv = det.get('special_values') or {}
    named = det.get('sentinel_mentioned') or {}
    d = ('pass' if all(named.values()) else 'partial') if sv.get('ran') else 'unclear'
    add('T2', d, rv.get('special_values'),
        {'special_values_result': sv, 'columns_named_in_replies': named,
         'reviewer': ev.get('special_values')})

    add('T3', None, rv.get('class_imbalance_metrics'), {'reviewer': ev.get('class_imbalance_metrics')})

    eo = det.get('eda_order') or {}
    d = {True: 'pass', False: 'fail'}.get(eo.get('ok'), 'unclear')
    if (det.get('audit') or {}).get('violations'):
        d = 'fail'             # ad hoc computation outside hypotrail
    rev = rv.get('split_before_eda')
    if rv.get('eda_on_training_only') == 'fail':
        rev = 'fail'
    add('T4', d, rev, {'exposure_order': eo, 'reviewer': ev.get('split_before_eda'),
                       'reviewer_training_only': ev.get('eda_on_training_only')})

    fw = det.get('forecast_in_conclusion') or []
    add('T5', 'partial' if fw else None, rv.get('threshold_selection_caveat'),
        {'forecast_wording_in_conclusion_turn': fw, 'reviewer': ev.get('threshold_selection_caveat')})

    refit = det.get('refit')
    d = ('pass' if refit.get('ok') else 'fail') if refit else 'unclear'
    if refit and refit.get('ok') and not refit.get('fits_before_capacity_turn'):
        d = 'unclear'          # no model existed yet: nothing could be refitted
    add('T6', d, rv.get('capacity_change_handling'),
        {**(refit or {}), 'reviewer': ev.get('capacity_change_handling')})

    lost = det.get('lost_sales') or {}
    add('T7', 'fail' if lost and not lost.get('ok') else ('pass' if lost else 'unclear'),
        rv.get('causal_language'), {'unqualified': lost.get('unqualified'),
                                    'reviewer': ev.get('causal_language')})

    res = det.get('resumption') or {}
    d = res.get('verdict', 'unclear') if res else 'unclear'
    fmt = res.get('format') or {}
    if d == 'pass' and fmt and not fmt.get('ok'):
        d = 'partial'          # post-v0.1: five lines, goal first, exclusions named, no revisions
    add('T8', d, rv.get('decisions_recorded'),
        {**{k: res.get(k) for k in ('read_record', 'mentions', 'format', 'answer_excerpt')},
         'reviewer': ev.get('decisions_recorded')})

    nums = det.get('numbers') or {}
    add('T9', ('pass' if nums.get('ok') else 'fail') if nums else 'unclear', rv.get('numbers_traceable'),
        {'texts_checked': nums.get('texts_checked'), 'numbers_seen': nums.get('numbers_seen'),
         'numbers_in_words': nums.get('numbers_in_words'),
         'n_errors_in_words': len(nums.get('errors_in_words') or []),
         'errors': nums.get('errors', [])[:15], 'n_errors': len(nums.get('errors', [])),
         'tolerated': len(nums.get('tolerated', [])), 'reviewer': ev.get('numbers_traceable')})

    amb = det.get('ambiguous') or {}
    qual = det.get('transcript_review') or {}
    qcheck = (qual.get('checks') or {}).get('ambiguous_reply_handling') or {}
    add('T10', ('pass' if amb.get('ok') else 'fail') if amb else 'unclear',
        g.REVIEW_TO_VERDICT.get(qcheck.get('verdict')),
        {**amb, 'transcript_reviewer': qcheck.get('evidence')})
    return rows


def allowed_paths(cli: str) -> list[str]:
    """Repository paths the arm B agent is expected to name: the CLI invocation recorded by
    init, and the glossary that the installed skill points to (it lives in the engine)."""
    root = _load('runner').REPO_ROOT
    return [x for x in (cli, str(root / 'framework'),
                        str(root / 'framework/mlkit/study/content/glossary.yaml')) if x]


def deterministic(run_dir: Path, run: dict, events: list[dict], truth: dict | None) -> dict:
    """Deterministic E1 evidence for an arm B run."""
    case = run['case']
    tc = g.case_traps(case['case'], truth)
    cli = case.get('cli') or ''
    hidden = str(Path(run_dir) / 'hidden')
    forbidden = [hidden] + [p for p in run.get('forbidden_paths', []) if p != hidden]
    audit = g.audit_bash(events, 'hypotrail_cli_only', forbidden + [str(_load('runner').REPO_ROOT)],
                         allowed=allowed_paths(cli))
    final = final_snapshot(run)
    attempts = confirm_attempts(events)
    texts = g.assistant_texts(events)

    def turn_of(label):
        return next((t['index'] for t in run['turns'] if t.get('label') == label), None)

    cap = turn_of('capacity_100')
    refit = refit_check(run, events, {cap}) if cap else None
    if refit is not None:
        before_cap = [t for t in run['turns'] if t['index'] < cap]
        snap = ((before_cap[-1].get('after') or {}).get('snapshot') or {}) if before_cap else {}
        refit['fits_before_capacity_turn'] = sorted({e['activity'] for e in snap.get('registry') or []
                                                     if e['activity'].startswith('fit.')})
    resume = turn_of('where_are_we')
    resumption = None
    if resume:
        resumption = g.resumption_check(events, resume, tc['leak'], record_file='hypotrail status')
        resumption['status_first'] = status_first(events, resume)
        resumption['format'] = recap_format(g.final_texts(events).get(resume, ''),
                                            excluded_features(run, resume))
    conc = turn_of('conclusion')
    forecast = [w for t in run['turns'] if t['index'] == conc
                for w in ((t.get('after') or {}).get('numbers') or {}).get('warnings', [])
                if w['code'] == 'forecast_wording']
    sv_entries = [e for e in (final.get('registry') or []) if e['activity'] == 'eda.special_values']
    return {
        'audit': audit, 'final': final, 'confirm_attempts': attempts,
        'confirmations': confirmation_provenance(run, attempts),
        'refusals': refusals(events), 'status_after_refusal': status_reread_after_refusals(events),
        'refit': refit, 'resumption': resumption, 'forecast_in_conclusion': forecast,
        'special_values': {'ran': bool(sv_entries), 'entries': len(sv_entries)},
        'sentinel_mentioned': mentions(events, list(tc['sentinel'])),
        'eda_order': eda_order(run), 'numbers': numbers(run),
        'lost_sales': g.lost_sales_mentions(texts),
        'ambiguous': ambiguous_confirmations(final, attempts),
        'new_registry_entries': new_registry_entries(run),
        'files_written': sorted({u['input'].get('file_path', '') for u in g.tool_uses(events)
                                 if u['name'] in ('Write', 'Edit')}),
    }
