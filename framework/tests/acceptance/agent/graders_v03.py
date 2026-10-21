"""v0.3 graders of the agent acceptance scenarios (WP-H). Claude Code acceptance only.

Text and transcript checks for what v0.3 changed in the junior's chat:

* guided adoption (WP-B, R14/R16/R27): a confirmation is the junior's reply verbatim; a
  short yes is accepted only as the answer to the closed question "Do you adopt this
  decision?" (``--adoption-question``) or as the adoption option of a choice
  (``--channel choice``); no reason or paraphrase is asked in guided mode;
* R32: when ``decide propose preprocessing`` returns ``data_contingent: true``, the reply
  says so before it shows the proposal;
* R28: the diagnostics run when the plan requires them (after the fits, before the
  variant; after the rule or model choice, before the final-test opening), and the
  binary confusion matrix is shown as a 2x2 table;
* ADR 0007: at most three variants, each with its question; a model family only when the
  engine's shortlist recommends comparing a non-linear family;
* R15/R30/R36/R37: replies in the study language (an engine text in English pasted into
  a French chat is a violation, quotations excepted), a French restatement for every
  proposal in a French study, no raw result, proposal, execution or request ids, the
  glossary's terms rather than home-made ones;
* smoothness metrics (plan section 2), measured per run from the transcript: junior turns
  to reach each pause, engine refusals and the refusals the junior saw, tool calls per
  pause, words per reply.

Every function reads plain data (events tagged by turn, the run record with its per-turn
snapshots, reply texts) so that it can be unit-tested on canned runs
(framework/tests/acceptance/test_graders.py).
"""
from __future__ import annotations

import json
import re
import shlex
import statistics

# --------------------------------------------------------------------------- transcript helpers


def tool_uses(events: list[dict]) -> list[dict]:
    """Every tool call, in order, with its turn and its result text."""
    results = {}
    for e in events:
        if e.get('type') != 'user':
            continue
        for c in (e.get('message') or {}).get('content') or []:
            if isinstance(c, dict) and c.get('type') == 'tool_result':
                content = c.get('content')
                if isinstance(content, list):
                    content = '\n'.join(x.get('text', '') for x in content if isinstance(x, dict))
                results[c.get('tool_use_id')] = content or ''
    out = []
    for e in events:
        if e.get('type') != 'assistant':
            continue
        for c in (e.get('message') or {}).get('content') or []:
            if isinstance(c, dict) and c.get('type') == 'tool_use':
                out.append({'turn': e.get('_turn'), 'name': c.get('name'), 'id': c.get('id'),
                            'input': c.get('input') or {}, 'result': results.get(c.get('id'), ''),
                            'order': len(out)})
    return out


def hypotrail_calls(events: list[dict]) -> list[dict]:
    """The Bash calls that run the hypotrail CLI, with ``ok`` (no ``"ok": false``)."""
    out = []
    for u in tool_uses(events):
        cmd = u['input'].get('command', '') if u['name'] == 'Bash' else ''
        if 'hypotrail' not in cmd and 'mlkit.study.cli' not in cmd:
            continue
        # A refusal may be printed compact (``{"ok":false,...}``).
        out.append({**u, 'command': cmd, 'ok': not re.search(r'"ok":\s*false', u['result'])
                    and 'Exit code 2' not in u['result']})
    return out


PROPOSE_RE = re.compile(r'\bdecide\s+propose\s+(\w+)')
RUN_RE = re.compile(r'\brun\s+([\w.:]+)')
CONFIRM_RE = re.compile(r'\bdecide\s+confirm\b')


def _arg(cmd: str, name: str) -> str | None:
    """The value of ``--name`` in a shell command (quoting resolved)."""
    for line in [cmd] + cmd.splitlines():
        if name not in line:
            continue
        try:
            tokens = shlex.split(line, posix=True)
        except ValueError:
            continue
        for i, t in enumerate(tokens):
            if t == name and i + 1 < len(tokens):
                return tokens[i + 1]
            if t.startswith(name + '='):
                return t.split('=', 1)[1]
    return None


# --------------------------------------------------------------------------- language

FR_WORDS = frozenset('le la les des une est et que pour sur pas ce dans du au aux avec qui '
                     'nous vous tu ton ta tes sont cette ces mais ou donc plus être sans '
                     'aussi fait chaque lignes modèle réservations ligne entre comme '
                     'avant après très'.split())
EN_WORDS = frozenset('the is are and of to for on with this that not be it its which we you '
                     'your our from by an at as was were has have will would can each rows '
                     'model before after than or but'.split())
CODE_BLOCK_RE = re.compile(r'```.*?```', re.S)
INLINE_CODE_RE = re.compile(r'`[^`\n]*`')
QUOTED_RE = re.compile(r'«[^»]*»|“[^”]*”|"[^"\n]*"')


def strip_quoted(text: str) -> str:
    """The text without code, quoted blocks (``> ...``) and quotations: what the agent
    wrote in its own voice. Engine texts quote the case's statements as written (English
    in the shipped cases, WP-C C7), and the junior's words are quoted as said."""
    text = CODE_BLOCK_RE.sub(' ', text or '')
    text = '\n'.join(line for line in text.splitlines() if not line.lstrip().startswith('>'))
    text = INLINE_CODE_RE.sub(' ', text)
    return QUOTED_RE.sub(' ', text)


def language_counts(text: str) -> tuple[int, int]:
    words = re.findall(r"[a-zàâçéèêëîïôûùüÿœ]+", (text or '').lower())
    return sum(w in FR_WORDS for w in words), sum(w in EN_WORDS for w in words)


def reply_language(text: str) -> str | None:
    fr, en = language_counts(strip_quoted(text))
    if fr + en < 6:
        return None
    return 'fr' if fr > en else 'en'


SENTENCE_RE = re.compile(r'(?<=[.!?:])\s+|\n+')


def foreign_sentences(text: str, lang: str, min_words: int = 8) -> list[str]:
    """Sentences of at least ``min_words`` words written in the other language (an engine
    junior text left in English in a French chat, or the reverse), quotations excepted."""
    out = []
    for s in SENTENCE_RE.split(strip_quoted(text)):
        words = re.findall(r"[^\W\d_]+", s)
        if len(words) < min_words:
            continue
        fr, en = language_counts(s)
        own, other = (fr, en) if lang == 'fr' else (en, fr)
        if other >= 3 and other > 2 * own:
            out.append(s.strip()[:200])
    return out


def replies_in_language(texts: list[str], lang: str) -> dict:
    wrong, foreign = [], []
    for i, t in enumerate(texts):
        got = reply_language(t)
        if got is not None and got != lang:
            wrong.append({'reply': i + 1, 'detected': got, 'start': (t or '')[:120]})
        foreign += [{'reply': i + 1, 'sentence': s} for s in foreign_sentences(t, lang)]
    return {'ok': not wrong and not foreign, 'lang': lang, 'replies_in_other_language': wrong,
            'foreign_sentences': foreign[:10]}


def restatements_in_language(events: list[dict], lang: str) -> dict:
    """In a French study, every accepted proposal carries ``--restatement-fr`` (rule 11)."""
    if lang != 'fr':
        return {'ok': True, 'note': 'English study', 'proposals': 0}
    missing, n = [], 0
    for c in hypotrail_calls(events):
        if PROPOSE_RE.search(c['command']) and c['ok']:
            n += 1
            if '--restatement-fr' not in c['command'] and '--lang fr' not in c['command'] \
                    and '--lang=fr' not in c['command']:
                missing.append({'turn': c['turn'],
                                'decision': PROPOSE_RE.search(c['command']).group(1)})
    return {'ok': not missing, 'proposals': n, 'without_french_restatement': missing}


# --------------------------------------------------------------------------- raw ids

PROPOSAL_ID_RE = re.compile(r'(?<![\w-])[pn]_\d+\b')
EXECUTION_ID_RE = re.compile(r'(?<![\w-])e_[0-9a-f]{6,}\b')
HEX_RE = re.compile(r'(?<![\w-])[0-9a-f]{8,64}(?![\w-])')
REVISION_RE = re.compile(r'\b(?:revision|révision|rev\.)\s*#?\d+', re.I)
STALE_SENTENCE_RE = re.compile(r'stale|périm|marked|marqué', re.I)


def raw_ids(texts: list[str], result_ids: set[str], request_ids: set[str] = frozenset()) -> dict:
    """Ids and revision numbers in junior-facing replies (rule 11). A hex token counts
    when it is a prefix of a registered result id, or 12+ characters mixing digits and
    letters; the stale-report sentence of rule 7 may name its revision."""
    found = []
    for i, t in enumerate(texts):
        text = CODE_BLOCK_RE.sub(' ', t or '')
        for m in PROPOSAL_ID_RE.finditer(text):
            found.append({'reply': i + 1, 'id': m.group(0), 'kind': 'proposal_or_note'})
        for m in EXECUTION_ID_RE.finditer(text):
            found.append({'reply': i + 1, 'id': m.group(0), 'kind': 'execution'})
        for m in HEX_RE.finditer(text):
            tok = m.group(0)
            known = any(r.startswith(tok) for r in result_ids)
            mixed = len(tok) >= 12 and re.search(r'\d', tok) and re.search(r'[a-f]', tok)
            if known or mixed:
                found.append({'reply': i + 1, 'id': tok, 'kind': 'result'})
        for rid in request_ids:
            if len(rid) >= 6 and rid in text:
                found.append({'reply': i + 1, 'id': rid, 'kind': 'request'})
        for s in SENTENCE_RE.split(text):
            if REVISION_RE.search(s) and not STALE_SENTENCE_RE.search(s):
                found.append({'reply': i + 1, 'id': REVISION_RE.search(s).group(0),
                              'kind': 'revision'})
    return {'ok': not found, 'found': found[:10]}


def request_ids(events: list[dict]) -> set[str]:
    out = set()
    for c in hypotrail_calls(events):
        rid = _arg(c['command'], '--request-id')
        if rid:
            out.add(rid)
    return out


# --------------------------------------------------------------------------- guided adoption

OPTIONAL_RE = re.compile(r'optional|optionnel|facultati|not required|not needed|no need|'
                         r"isn't required|is not required|pas obligatoire|pas besoin|"
                         r"pas nécessaire|n'est pas requis|if you (?:want|wish|like)|"
                         r'si tu (?:veux|le souhaites)|si vous (?:voulez|le souhaitez)', re.I)
ASK_REASON_RE = re.compile(
    r"\b(?:give|tell|add|include|need|want|state|explain)\w*\b[^.?!\n]{0,30}\b(?:a|your|one)"
    r"\s+reasons?\b|\bwhy (?:do|would|did|are) you\b|"
    r"\b(?:say|tell|answer|confirm|write|put|rephrase|restate|reply)\b[^.?!\n]{0,40}"
    r"\bin your own words\b|"
    r"\b(?:donne|dis|ajoute|indique|précise|besoin|explique)\w*\b[^.?!\n]{0,30}"
    r"\b(?:une|ta|votre|la) raison\b|\bpourquoi (?:tu|vous)\b|"
    # Own words are asked with a request verb ("réponds avec tes propres mots"); "j'ai
    # rédigé le critère avec tes mots" reports what the agent did (S14 smoke run).
    r"\b(?:réponds|répondez|dis|dites|reformule\w*|écris|écrivez|confirme|confirmez|redis)\b"
    r"[^.?!\n]{0,40}\b(?:avec|dans|en) (?:tes|vos) (?:propres )?mots\b|"
    r"\bparce que\s*(?:…|\.\.\.)", re.I)


def asks_for_reason(texts: list[str]) -> dict:
    """Guided mode (WP-B, R27): the agent never asks the junior for a reason or for their
    own words; a sentence saying a reason is optional is not a request."""
    hits = []
    for i, t in enumerate(texts):
        for s in SENTENCE_RE.split(t or ''):
            if ASK_REASON_RE.search(s) and not OPTIONAL_RE.search(s):
                hits.append({'reply': i + 1, 'sentence': s.strip()[:200]})
    return {'ok': not hits, 'requests': hits}


REASON_CODES = ('reason_required', 'needs_reason', 'paraphrase_required')


def refusal_codes(events: list[dict]) -> list[dict]:
    out = []
    for c in hypotrail_calls(events):
        if not c['ok']:
            m = re.search(r'"code":\s*"(\w+)"', c['result'])
            reason = re.search(r'"reason":\s*"(\w+)"', c['result'])
            out.append({'turn': c['turn'], 'order': c['order'],
                        'code': m.group(1) if m else None,
                        'reason': reason.group(1) if reason else None,
                        'command': c['command'][-160:]})
    return out


def guided_confirmations(run: dict, events: list[dict], attempts: list[dict],
                         allowed_codes=('stale_revision', 'proposal_stale')) -> dict:
    """Every confirmation the engine recorded holds the junior's reply of that turn
    verbatim; a bare reply was recorded only as the answer to the closed adoption question;
    no confirmation attempt was refused (a refusal is a lottery the junior sees), except
    for a stale proposal or revision (another chat moved the study)."""
    bad = []
    seen = {d: (v or {}).get('confirmed_revision')
            for d, v in ((run.get('before') or {}).get('decisions') or {}).items()}
    heard = set()
    for t in run['turns']:
        snap = (t.get('after') or {}).get('snapshot') or {}
        heard.add(_norm(t.get('utterance') or ''))
        for d, v in (snap.get('decisions') or {}).items():
            rev = (v or {}).get('confirmed_revision')
            if rev and rev != seen.get(d):
                words = _norm(v.get('user_words') or '')
                delegated = 'delegat' in str(v.get('basis') or '')
                # The words of this turn or of an earlier one (S10: "I keep my sentence"
                # confirms the sentence said the turn before).
                if words not in heard and not delegated:
                    bad.append({'turn': t['index'], 'decision': d, 'user_words': v.get('user_words'),
                                'said': t.get('utterance'), 'problem': 'not_verbatim'})
            seen[d] = rev
    refused = [a for a in attempts if a['refused'] and a.get('error_code') not in allowed_codes]
    flagged_unasked = [a for a in attempts if a.get('adoption') and not a.get('asked')
                       and not a['refused'] and '--channel' not in a['excerpt']]
    reason = [r for r in refusal_codes(events)
              if r['code'] in REASON_CODES or r['reason'] in REASON_CODES]
    return {'ok': not bad and not refused and not flagged_unasked and not reason,
            'not_verbatim': bad, 'refused_attempts': [
                {k: a[k] for k in ('turn', 'error_code', 'user_words')} for a in refused],
            'adoption_flag_without_question': [a['excerpt'][-160:] for a in flagged_unasked],
            'reason_or_paraphrase_refusals': reason}


def _norm(text: str) -> str:
    return re.sub(r'\s+', ' ', re.sub(r'[^\w\s]', ' ', (text or '').lower())).strip()


# --------------------------------------------------------------------------- R32

CONTINGENT_TALK_RE = re.compile(
    r'data[- ]contingent|dépend\w* des données|after (?:looking|seeing|we looked|having looked|'
    r'we saw|the look)|looked at the (?:target|outcome)|look(?:s|ed)? at the (?:target|outcome)|'
    r'après avoir (?:regardé|vu|examiné|observé)|regard\w* (?:à )?(?:la|le) (?:cible|résultat)|'
    r'vu la cible|optimis', re.I)
QUOTE_LINE_RE = re.compile(r'^\s*>', re.M)


def data_contingent_first(events: list[dict], final_texts: dict) -> dict:
    """R32: for each accepted preprocessing proposal the engine marked data-contingent, the
    reply of that turn says so before the proposal's quoted block (or before the adoption
    question when there is no block)."""
    cases = []
    for c in hypotrail_calls(events):
        m = PROPOSE_RE.search(c['command'])
        if not (m and m.group(1) == 'preprocessing' and c['ok']):
            continue
        contingent = re.search(r'"data_contingent":\s*true', c['result']) is not None
        if not contingent:
            cases.append({'turn': c['turn'], 'data_contingent': False})
            continue
        reply = final_texts.get(c['turn']) or ''
        said = CONTINGENT_TALK_RE.search(reply)
        quote = QUOTE_LINE_RE.search(reply)
        question = re.search(r'adopt\w*(?:-(?:vous|tu))?\s+(?:this|the|cette|la)\s+d[ée]cision', reply, re.I)
        anchor = quote or question
        ok = bool(said) and (anchor is None or said.start() < anchor.start())
        cases.append({'turn': c['turn'], 'data_contingent': True, 'said': bool(said),
                      'said_before_proposal': ok,
                      'excerpt': reply[max(0, (said.start() if said else 0) - 60):
                                       (said.end() if said else 0) + 80][:200]})
    exercised = [x for x in cases if x['data_contingent']]
    return {'ok': all(x['said_before_proposal'] for x in exercised), 'exercised': len(exercised),
            'proposals': cases}


# --------------------------------------------------------------------------- R28

FIT_RE = re.compile(r'\brun\s+fit\.(?:logistic|linear)\b')
DIAG_RE = re.compile(r'\brun\s+diag\.(?:binary|regression)\b')


# The engine's next action as the agent printed it (often through ``jq`` under another
# key): a ``run`` of the diagnostics requires them; a proposal means they are done or not
# required. The last one printed in an output counts (round 1: a diagnostic launched in
# the background and read when it finished, S14 Hotel en).
NEXT_DIAG_RE = re.compile(r'"kind"\s*:\s*"run"\s*,\s*(?:"step"\s*:\s*"\w+"\s*,\s*)?'
                          r'"activity"\s*:\s*"(diag\.(?:binary|regression))"')
NEXT_PROPOSE_RE = re.compile(r'"kind"\s*:\s*"(?:propose|await_user_words)"')


def diagnostics_when_required(events: list[dict], run: dict | None = None) -> dict:
    """R28: when the engine's ``next_action`` names the diagnostics (in any output the
    agent read, or in the study at the start of a turn), they run before the agent
    proposes anything. The engine decides when they are required (after the fits, and
    after a choice whose rule the current diagnostics were not computed at, R34); a choice
    adopted at the rule the diagnostics already used needs none (smoke run S14)."""
    start_required = {}
    if run is not None:
        prev = run.get('before') or {}
        for t in run['turns']:
            na = prev.get('next_action') or {}
            start_required[t['index']] = str(na.get('activity') or '').startswith('diag.')
            prev = (t.get('after') or {}).get('snapshot') or prev
    required, turn, misses, required_seen = None, None, [], 0
    calls = hypotrail_calls(events)
    # The output of a command the agent ran in the background, read from its task file.
    seen = {c['id'] for c in calls}
    calls += [{**u, 'command': '', 'ok': True} for u in tool_uses(events)
              if u['name'] == 'Read' and u['id'] not in seen
              and '/tasks/' in str(u['input'].get('file_path', ''))]
    calls.sort(key=lambda c: c['order'])
    for c in calls:
        if c['turn'] != turn:
            turn = c['turn']
            if start_required.get(turn):
                required = 'study at the start of the turn'
                required_seen += 1
        if c['ok'] and DIAG_RE.search(c['command']):
            required = None
            continue
        m = PROPOSE_RE.search(c['command'])
        if m and c['ok'] and required:
            misses.append({'turn': c['turn'], 'proposal': m.group(1), 'required_by': required})
            required = None
        if not c['ok']:
            continue
        signals = [(m.start(), m) for m in NEXT_DIAG_RE.finditer(c['result'] or '')] + \
            [(m.start(), None) for m in NEXT_PROPOSE_RE.finditer(c['result'] or '')]
        if signals:
            _, last = max(signals, key=lambda x: x[0])
            if last is not None:
                if not required:
                    required_seen += 1
                required = f'next_action {last.group(1)}'
            else:
                required = None
    return {'ok': not misses, 'exercised': required_seen, 'misses': misses}


TABLE_ROW_RE = re.compile(r'^\s*\|(.+)\|\s*$')
INT_CELL_RE = re.compile(r'^\s*\**\s*\d{1,3}(?:[ ,.  ]\d{3})*\s*\**\s*$|^\s*\**\d+\**\s*$')


def confusion_tables(text: str) -> list[list[str]]:
    """2x2 count tables in a reply: a markdown table (or a code-block grid) with at least
    two rows holding at least two integer cells."""
    found = []
    blocks, current = [], []
    for line in (text or '').splitlines():
        if TABLE_ROW_RE.match(line):
            current.append(line)
        else:
            if current:
                blocks.append(current)
            current = []
    if current:
        blocks.append(current)
    for block in blocks:
        rows = [r for r in block
                if sum(bool(INT_CELL_RE.match(c)) for c in r.strip().strip('|').split('|')) >= 2]
        if len(rows) >= 2:
            found.append(block)
    for code in re.findall(r'```(.*?)```', text or '', re.S):
        rows = [r for r in code.splitlines() if len(re.findall(r'\b\d[\d,  ]*\b', r)) >= 2]
        if len(rows) >= 2:
            found.append(rows)
    return found


def confusion_shown(events: list[dict], final_texts: dict) -> dict:
    """R28 (binary): after a turn that ran ``diag.binary``, a reply of that turn or a
    later one shows the confusion matrix as a 2x2 table."""
    turns = sorted({c['turn'] for c in hypotrail_calls(events)
                    if c['ok'] and re.search(r'\brun\s+diag\.binary\b', c['command'])})
    if not turns:
        return {'ok': True, 'exercised': False, 'note': 'no diag.binary run'}
    shown = [t for t, text in sorted(final_texts.items()) if t >= turns[0] and confusion_tables(text)]
    return {'ok': bool(shown), 'exercised': True, 'diag_turns': turns, 'table_turns': shown}


# --------------------------------------------------------------------------- ADR 0007

def _variant_values(cmd: str) -> list[dict]:
    raw = _arg(cmd, '--value-json')
    if raw is None:
        return []
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    if isinstance(value, dict) and isinstance(value.get('variants'), list):
        return [v for v in value['variants'] if isinstance(v, dict)]
    return [value] if isinstance(value, dict) else []


def variant_budget(run: dict, events: list[dict]) -> dict:
    """ADR 0007: every variant proposal names at most three variants, each with its
    question; a family variant only when the engine's shortlist (read in the snapshot
    before the turn) recommends ``compare_nonlinear``; never more than three distinct
    variants confirmed."""
    snaps = {0: run.get('before') or {}}
    for t in run['turns']:
        snaps[t['index']] = (t.get('after') or {}).get('snapshot') or {}
    proposals, problems = [], []
    for c in hypotrail_calls(events):
        m = PROPOSE_RE.search(c['command'])
        if not (m and m.group(1) == 'model_variant' and c['ok']):
            continue
        variants = _variant_values(c['command'])
        before = snaps.get((c['turn'] or 1) - 1) or {}
        rec = (before.get('model_families') or {}).get('recommendation') or \
            ((snaps.get(c['turn']) or {}).get('model_families') or {}).get('recommendation')
        families = [v for v in variants if v.get('kind') == 'family']
        no_question = [v for v in variants if not str(v.get('question') or '').strip()
                       and v.get('kind') != 'tuned']
        proposals.append({'turn': c['turn'], 'kinds': [v.get('kind') for v in variants],
                          'recommendation': rec})
        if len(variants) > 3:
            problems.append({'turn': c['turn'], 'problem': 'more_than_three', 'n': len(variants)})
        if families and rec != 'compare_nonlinear':
            problems.append({'turn': c['turn'], 'problem': 'family_without_recommendation',
                             'recommendation': rec})
        if no_question:
            problems.append({'turn': c['turn'], 'problem': 'variant_without_question',
                             'kinds': [v.get('kind') for v in no_question]})
    final = {}
    for t in reversed(run['turns']):
        final = (t.get('after') or {}).get('snapshot') or {}
        if final:
            break
    value = ((final.get('decisions') or {}).get('model_variant') or {}).get('value')
    confirmed = len(value.get('variants', [])) if isinstance(value, dict) and 'variants' in value \
        else (1 if value else 0)
    if confirmed > 3:
        problems.append({'problem': 'more_than_three_confirmed', 'n': confirmed})
    return {'ok': not problems, 'exercised': bool(proposals), 'proposals': proposals,
            'confirmed_variants': confirmed, 'problems': problems}


# --------------------------------------------------------------------------- glossary

HOME_MADE_TERMS = {
    'en': [r'\bvalidation rows\b', r'\btraining rows\b', r'\bmean precision\b', r'\btest set\b'],
    'fr': [r'précision moyenne', r'lignes de validation', r"lignes d.entra[îi]nement",
           r'\bjeu de test\b', r'\bensemble de test\b'],
}
STEP0_TERMS = {
    'en': [r'development (?:set|rows)', r'holdout|final test'],
    'fr': [r'développement', r'test final|holdout'],
}


def glossary_vocabulary(texts: list[str], lang: str, step0_text: str | None = None) -> dict:
    """R15/R30: the glossary's terms, never a home-made one (under cross-validation the
    engine says "validation fold"/"training folds", WP-C C9; the French AP term follows
    R15, C8); step 0 introduces the development set and the holdout (final test)."""
    used = []
    for i, t in enumerate(texts):
        clean = strip_quoted(t)
        for p in HOME_MADE_TERMS.get(lang, []):
            m = re.search(p, clean, re.I)
            if m:
                used.append({'reply': i + 1, 'term': m.group(0)})
    missing = []
    if step0_text is not None:
        missing = [p for p in STEP0_TERMS.get(lang, []) if not re.search(p, step0_text, re.I)]
    return {'ok': not used and not missing, 'home_made_terms': used[:10],
            'step0_terms_missing': missing}


# --------------------------------------------------------------------------- smoothness metrics

REFUSAL_TALK_RE = re.compile(
    r"refus|rejet|reject|n'a (?:rien|pas) (?:été )?(?:enregistr|accept)|rien n'a été enregistré|"
    r"nothing (?:was |has been |got )?recorded|(?:was|were|has been) not recorded|"
    r"wasn't recorded|(?:didn't|did not) (?:record|accept|go through|take)|"
    # WP-H3: « le moteur » alone is no refusal (« Le moteur signale aussi une forme… »,
    # S14 Hotel fr round 3); as in English, only with a refusing verb.
    r"l'outil (?:a|n'a)|le moteur (?:a refusé|refuse|n'a pas|ne peut pas|demande|exige)|"
    r"the engine (?:refused|did not|didn't|would not|won't|"
    r"rejected|asks|needs|requires)|the tool (?:refused|did not|didn't)", re.I)
# The closed question, with the final-test opening's form ("Do you adopt the opening of the
# final test?", WP-H3), as graders_b.ADOPTION_QUESTION_RE.
ADOPTION_RE = re.compile(
    r"adopt\w*(?:-(?:vous|tu))?\s+(?:(?:this|the|cette|la)\s+d[ée]cision|"
    r"(?:the\s+opening|l['’]\s*ouverture)\b)", re.I)


def _words(text: str) -> int:
    return len(re.findall(r"[^\W_]+(?:['’-][^\W_]+)*", text or ''))


def smoothness(run: dict, events: list[dict]) -> dict:
    """Plan section 2, measured on one run: junior turns to reach each pause (the turn
    whose snapshot first shows the decision's proposal) and to confirm it, engine refusals
    (all, and those in a turn whose reply talks about a refusal: seen by the junior), tool
    calls per pause (a pause = a turn that ends with an open proposal or the closed
    adoption question; tool calls since the previous pause are charged to it), and words
    per reply."""
    turns = run['turns']
    proposed, confirmed = {}, {}
    seen_conf = {d: (v or {}).get('confirmed_revision')
                 for d, v in ((run.get('before') or {}).get('decisions') or {}).items()}
    before_open = {p['decision_id'] for p in (run.get('before') or {}).get('open_proposals') or []}
    for n, t in enumerate(turns, start=1):
        snap = (t.get('after') or {}).get('snapshot') or {}
        for p in snap.get('open_proposals') or []:
            if p['decision_id'] not in before_open:
                proposed.setdefault(p['decision_id'], n)
        for d, v in (snap.get('decisions') or {}).items():
            rev = (v or {}).get('confirmed_revision')
            if rev and rev != seen_conf.get(d):
                confirmed.setdefault(d, n)
                proposed.setdefault(d, n)      # proposed and confirmed in the same turn
            seen_conf[d] = rev
    refusals = refusal_codes(events)
    replies = {t['index']: t.get('final_text') or '' for t in turns}
    visible = [r for r in refusals if REFUSAL_TALK_RE.search(replies.get(r['turn'], ''))]
    calls_by_turn = {t['index']: t.get('tool_calls') or 0 for t in turns}
    pauses, pending = [], 0
    for t in turns:
        pending += calls_by_turn[t['index']]
        snap = (t.get('after') or {}).get('snapshot') or {}
        at_pause = bool(snap.get('open_proposals')) or bool(ADOPTION_RE.search(replies[t['index']]))
        if at_pause:
            pauses.append({'turn': t['index'], 'tool_calls': pending})
            pending = 0
    words = [_words(replies[t['index']]) for t in turns]
    per_pause = [p['tool_calls'] for p in pauses]
    conclusion = confirmed.get('conclusion')
    return {
        'junior_turns': len(turns),
        'turns_to_pause': proposed, 'turns_to_confirm': confirmed,
        'junior_turns_to_conclusion': conclusion,
        'refusals': len(refusals), 'refusals_visible': len(visible),
        'refusal_codes': [r['code'] for r in refusals],
        'visible_refusals': [{k: r[k] for k in ('turn', 'code')} for r in visible],
        'tool_calls': sum(calls_by_turn.values()), 'pauses': len(pauses),
        'tool_calls_per_pause_mean': round(statistics.mean(per_pause), 2) if per_pause else None,
        'tool_calls_per_pause_max': max(per_pause) if per_pause else None,
        'tool_calls_per_pause': per_pause,
        'words_per_reply_mean': round(statistics.mean(words), 1) if words else None,
        'words_per_reply_median': statistics.median(words) if words else None,
        'words_per_reply_max': max(words) if words else None,
    }


TARGETS = {'junior_turns_to_conclusion': 12, 'refusals_visible': 0, 'tool_calls_per_pause_mean': 4}


def targets(metrics: dict) -> dict:
    """Plan section 2 targets on one full-study run (S14)."""
    out = {}
    for key, limit in TARGETS.items():
        value = metrics.get(key)
        out[key] = {'value': value, 'target': limit,
                    'met': value is not None and value <= limit}
    return out
