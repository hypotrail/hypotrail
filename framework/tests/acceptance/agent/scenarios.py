"""Scenario driver for the agent acceptance scenarios S1-S9 (plan WP0.7, WP4.3).

Claude Code acceptance, not Copilot acceptance.

    uv run --project framework python framework/tests/acceptance/agent/scenarios.py run \\
        --id S1 --case bank --lang en --out RUN_DIR
    uv run --project framework python framework/tests/acceptance/agent/scenarios.py grade --run RUN_DIR
    uv run --project framework python framework/tests/acceptance/agent/scenarios.py review --run RUN_DIR
    uv run --project framework python framework/tests/acceptance/agent/scenarios.py summary RUN_DIR...

One run = one scenario on one case in one language:

1. a fresh workspace outside the repository; the case is copied into it and ``hypotrail
   init`` installs the agent instructions (``study_setup.prepare_study``, as arm B of E1);
2. the study is taken to ``setup.walkthrough_until`` with direct CLI processes;
3. each scripted utterance is one ``claude -p`` process (arm B: model, tools, caps), a new
   chat being a new session; after every turn the arm B hook snapshots the study and runs
   ``hypotrail check --text -`` on every assistant text holding a number;
4. the deterministic checks named in ``scenarios.yaml`` are evaluated (``CHECKS``) and
   written to ``RUN_DIR/grade.json``; ``review`` adds the fresh-agent rubric verdicts.

RUN_DIR must be outside the repository (raw transcripts are never committed).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import e1  # noqa: E402  (loads runner, graders, study_setup, graders_b)

runner, graders, study_setup, gb = e1.runner, e1.graders, e1.study_setup, e1.graders_b
SCENARIOS = yaml.safe_load((HERE / 'scenarios.yaml').read_text(encoding='utf-8'))
ARM = HERE / 'arms' / 'arm_b'

RUBRIC_SCHEMA = {
    'type': 'object', 'additionalProperties': False,
    'properties': {
        'items': {'type': 'array', 'items': {
            'type': 'object', 'additionalProperties': False,
            'properties': {'question': {'type': 'string'},
                           'verdict': {'enum': ['yes', 'partly', 'no', 'unclear']},
                           'evidence': {'type': 'string'}},
            'required': ['question', 'verdict', 'evidence']}},
        'summary': {'type': 'string'}},
    'required': ['items', 'summary']}


def scenario(sid: str) -> dict:
    return next(s for s in SCENARIOS['scenarios'] if s['id'] == sid)


def _fill(text: str, params: dict) -> str:
    return re.sub(r'\{(\w+)\}', lambda m: str(params.get(m.group(1), m.group(0))), text)


def build_chats(s: dict, case: str, lang: str, interrupt_dir: Path) -> list[list[dict]]:
    params = {**SCENARIOS['case_params'][case], 'interrupt_dir': str(interrupt_dir)}
    after = float(((s.get('setup') or {}).get('interrupt') or {}).get('after_seconds', 1))
    chats = []
    for chat in s['chats']:
        steps = []
        for step in chat:
            item = {'say': _fill(step['say'][lang], params), 'label': step.get('label')}
            if 'chat' in step:
                item['chat'] = step['chat']
            if step.get('env'):
                item['env'] = {k: _fill(str(v), params) for k, v in step['env'].items()}
            if step.get('interrupt'):
                item['interrupt'] = {'folder': str(interrupt_dir), 'after_seconds': after}
            if step.get('answer_with_simulator'):
                item['answer_with_simulator'] = True
            steps.append(item)
        chats.append(steps)
    return chats


# --------------------------------------------------------------------------- run

def run_scenario(sid: str, case: str, lang: str, out: Path, *, caps: runner.Caps | None = None,
                 workspace_base: Path | None = None, log=print) -> dict:
    s = scenario(sid)
    out = e1._assert_outside_repo(out)
    out.mkdir(parents=True, exist_ok=True)
    arm = runner.Arm.load(ARM)
    hidden = out / 'hidden'
    interrupt_dir = out / 'interrupt'
    setup_log = {}

    def prepare(ws: Path) -> dict:
        info = study_setup.prepare_study(case, ws, hidden)
        st = study_setup.Setup(ws, case, (s.get('setup') or {}).get('variant'))
        st.advance(s['setup']['walkthrough_until'])
        setup_log.update({'stage': s['setup']['walkthrough_until'], 'calls': st.log,
                          'variant': st.variant})
        info['setup'] = setup_log
        return info

    chats = build_chats(s, case, lang, interrupt_dir)
    utterances = [step['say'] for chat in chats for step in chat]
    log_file = out / 'progress.log'

    def logger(msg):
        log(msg)
        with log_file.open('a', encoding='utf-8') as fh:
            fh.write(msg + '\n')

    simulator = e1.junior_responder(out, log=logger)

    def responder(ws, turn, step, nxt, answered):
        # A step marked answer_with_simulator gets one simulated junior answer: the
        # junior's own words in reply to the restatement the agent just made.
        if not step.get('answer_with_simulator') or answered:
            return None
        return simulator(ws, turn, {**step, 'label': 'garde_ca'}, nxt, 0)

    record = runner.run_conversation(
        arm=arm, chats=chats, run_dir=out, prepare_workspace=prepare, responder=responder,
        caps=caps or runner.Caps(), workspace_base=workspace_base,
        forbidden_paths=[hidden, e1.main_checkout()],
        meta={'scenario': sid, 'case': case, 'lang': lang, 'title': s['title']},
        log=logger, after_turn=e1.arm_b_after_turn([[{'say': u} for u in utterances]]),
        before_first_turn=e1.compact_snapshot)
    return record


# --------------------------------------------------------------------------- checks

class Ctx:
    def __init__(self, run_dir: Path):
        self.run_dir = Path(run_dir)
        self.run = json.loads((self.run_dir / 'run.json').read_text(encoding='utf-8'))
        self.events = runner.load_transcript(self.run_dir)
        self.before = self.run.get('before') or {}
        self.final = gb.final_snapshot(self.run)
        self.ws = Path(self.run['workspace'])
        self.case = self.run['case']
        self.sid = self.run['meta']['scenario']

    def turn(self, label: str | None) -> dict | None:
        if label is None:
            return self.run['turns'][-1] if self.run['turns'] else None
        return next((t for t in self.run['turns'] if t.get('label') == label), None)

    def answer(self, label: str | None = None) -> str:
        t = self.turn(label)
        return (t or {}).get('final_text') or ''

    def all_answers(self) -> str:
        return '\n'.join(t.get('final_text') or '' for t in self.run['turns'])

    def snapshot_after(self, label: str) -> dict:
        t = self.turn(label)
        return ((t or {}).get('after') or {}).get('snapshot') or {}


def _ok(ok, **evidence):
    evidence = {k: v for k, v in evidence.items() if k != 'ok'}
    return {'ok': bool(ok), **evidence}


def _r(r: dict, **extra):
    """A grader result whose own ``ok`` is the check's verdict."""
    return _ok(r['ok'], **{k: v for k, v in r.items() if k != 'ok'}, **extra)


def c_first_tool_call_is(ctx, command='hypotrail status'):
    first = ctx.run['turns'][0]['index']
    r = gb.status_first(ctx.events, first)
    return _r(r)


def c_no_state_mutation(ctx):
    return _ok(ctx.final.get('revision') == ctx.before.get('revision'),
               before=ctx.before.get('revision'), after=ctx.final.get('revision'))


c_revision_unchanged = c_no_state_mutation


def _norm(text: str) -> str:
    return re.sub(r'\s+', ' ', re.sub(r'[^\w\s]', ' ', text.lower())).strip()


def c_answer_mentions_confirmed_user_words(ctx):
    """The recap quotes (part of) the junior's recorded words of the latest confirmation."""
    confirmed = [(v.get('confirmed_revision') or 0, d, v.get('user_words'))
                 for d, v in (ctx.before.get('decisions') or {}).items()
                 if v.get('status') == 'confirmed' and v.get('user_words')]
    if not confirmed:
        return _ok(False, note='no confirmed decision in the setup')
    _, decision, words = max(confirmed)
    answer = _norm(ctx.answer())
    w = _norm(words).split()
    windows = [' '.join(w[i:i + 4]) for i in range(max(1, len(w) - 3))]
    hit = [x for x in windows if x in answer]
    return _ok(bool(hit), decision=decision, user_words=words, matched=hit[:3])


def c_answer_mentions_excluded_features(ctx):
    fa = (ctx.before.get('decisions') or {}).get('feature_availability') or {}
    excluded = [f for f, st in (fa.get('value') or {}).items()
                if st in ('not_available', 'uncertain_excluded')]
    answer = ctx.answer().lower()
    named = {f: f.lower() in answer for f in excluded}
    return _ok(excluded and all(named.values()), named=named)


def c_bash_audit(ctx):
    cli = ctx.case.get('cli') or ''
    r = graders.audit_bash(ctx.events, 'hypotrail_cli_only',
                           ctx.run.get('forbidden_paths', []) + [str(runner.REPO_ROOT)],
                           allowed=gb.allowed_paths(cli))
    outside = [p for p in graders.tool_uses(ctx.events)
               if p['name'] in ('Write', 'Edit')
               and not str(p['input'].get('file_path', '')).startswith(str(ctx.ws))]
    return _ok(r['ok'] and not outside, violations=r['violations'],
               forbidden_access=r['forbidden_access'], shell_writes=r['shell_writes'],
               bash_commands=r['bash_commands'],
               writes_outside_study=[u['input'].get('file_path') for u in outside])


def c_numbers_in_registry(ctx):
    r = gb.numbers(ctx.run)
    return _ok(r['ok'], texts_checked=r['texts_checked'], numbers_seen=r['numbers_seen'],
               errors=r['errors'][:10], tolerated=len(r['tolerated']),
               warnings=[w['code'] for w in r['warnings']])


def c_prediction_time_changed(ctx):
    before = ((ctx.before.get('decisions') or {}).get('prediction_time') or {})
    after = ((ctx.final.get('decisions') or {}).get('prediction_time') or {})
    return _ok(before.get('value') != after.get('value') and after.get('status') == 'confirmed',
               before=before.get('value'), after=after.get('value'),
               user_words=after.get('user_words'))


def c_stale_proposal_not_confirmed(ctx, decision='policy'):
    """The chat-1 proposal, made before the change, never became the confirmed decision."""
    chat1 = ctx.snapshot_after('propose_in_chat_1')
    props = [p['proposal_id'] for p in chat1.get('open_proposals') or [] if p['decision_id'] == decision]
    final = (ctx.final.get('decisions') or {}).get(decision) or {}
    confirmed_stale = final.get('status') == 'confirmed' and final.get('proposal_id') in props
    return _ok(not confirmed_stale, chat1_proposals=props, final=final)


def c_refusal_or_status_seen(ctx, turn, codes):
    """In the confirming turn: a refusal with one of ``codes``, or the agent read status
    first and did not attempt the stale confirmation."""
    t = ctx.turn(turn)
    idx = t['index'] if t else None
    refs = [r for r in gb.refusals(ctx.events) if r['turn'] == idx]
    seen = [r for r in refs if r['code'] in codes]
    first = gb.status_first(ctx.events, idx) if idx else {'ok': False}
    attempts = [a for a in gb.confirm_attempts(ctx.events) if a['turn'] == idx]
    accepted = [a for a in attempts if not a['refused']]
    return _ok((seen or first['ok']) and not accepted, refusals=refs, status_first=first['ok'],
               confirm_attempts=attempts)


def c_status_reread_after_refusal(ctx):
    r = gb.status_reread_after_refusals(ctx.events)
    return _r(r, refusals=gb.refusals(ctx.events))


def c_render_failure_seen(ctx):
    res = graders.tool_results(ctx.events)
    hits = [u['input']['command'][-120:] for u in gb.bash_uses(ctx.events)
            if 'hypotrail' in u['input'].get('command', '')
            and re.search(r'Exit code 3|"status":\s*"failed"', res.get(u['id'], ''))]
    return _ok(bool(hits), commands=hits[:5])


def c_artifact_status(ctx, artifact='report', status=('failed', 'stale'), previous_kept=True):
    item = ((ctx.final.get('artifacts') or {}).get('items') or {}).get(artifact) or {}
    html = ctx.ws / 'reports' / 'study.html'
    page = html.read_text(encoding='utf-8', errors='replace') if html.is_file() else ''
    kept = bool(page) and 'data-hypotrail-banner="stale"' in page
    return _ok(item.get('status') in status and (kept or not previous_kept),
               status=item.get('status'), banner_stale=kept,
               notebook=(((ctx.final.get('artifacts') or {}).get('items') or {}).get('notebook') or {}).get('status'))


def c_answer_does_not_claim_up_to_date(ctx):
    items = ((ctx.final.get('artifacts') or {}).get('items') or {})
    ok_surfaces = tuple(n for n, i in items.items() if (i or {}).get('status') == 'ok')
    hits = gb.claims_up_to_date(ctx.all_answers(), ok_surfaces)
    return _ok(not hits, claims=hits, ok_surfaces=ok_surfaces)


def c_answer_names_surfaces(ctx):
    """S3: the reply says which deliverable failed and which one is current."""
    a = ctx.answer().lower()
    report = bool(re.search(r'report|study\.html|rapport', a))
    failed = bool(re.search(r'fail|stale|not (?:been )?updated|could not|couldn.t|échou|périm', a))
    notebook = bool(re.search(r'notebook|study_generated', a))
    return _ok(report and failed and notebook, report=report, failed_word=failed, notebook=notebook)


def c_no_new_fit(ctx):
    new = [e for e in gb.new_registry_entries(ctx.run) if e['activity'].startswith('fit.')]
    cmds = gb.fit_commands(ctx.events, {t['index'] for t in ctx.run['turns']})
    return _ok(not new and not cmds, new_fit_entries=new, fit_commands=cmds)


def c_no_decision_change(ctx):
    b = {d: (v.get('status'), json.dumps(v.get('value'), sort_keys=True))
         for d, v in (ctx.before.get('decisions') or {}).items()}
    a = {d: (v.get('status'), json.dumps(v.get('value'), sort_keys=True))
         for d, v in (ctx.final.get('decisions') or {}).items()}
    changed = sorted(d for d in set(a) | set(b) if a.get(d) != b.get(d))
    return _ok(not changed, changed=changed)


def c_answer_mentions_any(ctx, patterns):
    a = ctx.all_answers()
    hits = [p for p in patterns if re.search(p, a, re.I)]
    return _ok(bool(hits), matched=hits)


def c_tool_call_matches_any(ctx, patterns):
    params = SCENARIOS['case_params'][ctx.case['case']]
    pats = [_fill(p, params) for p in patterns]
    cmds = [u['input'].get('command', '') for u in gb.bash_uses(ctx.events)]
    hits = [c[-160:] for c in cmds if any(re.search(p, c) for p in pats)]
    return _ok(bool(hits), matched=hits[:3])


def c_no_confirmation_with_user_words(ctx, words):
    r = gb.ambiguous_confirmations(ctx.final, gb.confirm_attempts(ctx.events), words)
    return _r(r)


def c_decision_not_confirmed(ctx, decision):
    d = (ctx.final.get('decisions') or {}).get(decision) or {}
    return _ok(d.get('status') != 'confirmed', status=d.get('status'), user_words=d.get('user_words'))


def c_proposal_still_open(ctx, decision):
    props = [p for p in ctx.final.get('open_proposals') or [] if p['decision_id'] == decision]
    return _ok(bool(props), open=[p['proposal_id'] for p in props])


def c_registry_diff(ctx, allowed_activities, forbidden_prefix='fit.'):
    new = gb.new_registry_entries(ctx.run)
    forbidden = [e for e in new if e['activity'].startswith(forbidden_prefix)]
    other = [e for e in new if e['activity'] not in allowed_activities]
    cmds = gb.fit_commands(ctx.events, {t['index'] for t in ctx.run['turns']})
    return _ok(not forbidden and not other and not cmds,
               new=[(e['activity'], (e.get('params') or {}).get('rules')) for e in new],
               forbidden=forbidden, fit_commands=cmds)


def c_policy_not_silently_replaced(ctx, old, new):
    pol = (ctx.final.get('decisions') or {}).get('policy') or {}
    props = [p for p in ctx.final.get('open_proposals') or [] if p['decision_id'] == 'policy']
    silently = pol.get('value') == new and pol.get('status') == 'confirmed'
    return _ok(not silently and pol.get('value') == old,
               policy=pol.get('value'), status=pol.get('status'),
               open_policy_proposals=[p['value'] for p in props])


def _killed(ctx):
    events = []
    for t in ctx.run['turns']:
        events += ((t.get('interrupt') or {}).get('events') or [])
    return [e for e in events if 'killed_pid' in e]


REQUEST_ID_RE = re.compile(r'--request-id(?:=|\s+)["\']?([^\s"\']+)')
EXECUTION_ID_RE = re.compile(r'"execution_id":\s*"(e_[0-9a-f]+)"')


def interrupted_run(ctx) -> dict:
    """The run the harness killed: the first ``hypotrail run ACTIVITY`` of the turn whose
    environment held the pause hook, with its request id, and the execution id the engine
    reported for it afterwards (replay, refusal, status, or acknowledgement)."""
    t = ctx.turn('start_fit')
    if t is None:
        return {}
    results = graders.tool_results(ctx.events)
    uses = [u for u in gb.bash_uses(ctx.events, {t['index']})]
    first = next((u for u in uses if gb.RUN_RE.search(u['input'].get('command', ''))
                  and '--acknowledge-interruption' not in u['input']['command']), None)
    if first is None:
        return {}
    cmd = first['input']['command']
    rid = REQUEST_ID_RE.search(cmd)
    eid = None
    seen_engine = []
    for u in gb.bash_uses(ctx.events):
        res = results.get(u['id'], '')
        if 'interrupted_unknown' in res or 'acknowledge_interruption' in res or \
                'interrupted_execution_pending' in res:
            seen_engine.append({'turn': u['turn'], 'command': u['input']['command'][-120:]})
            m = EXECUTION_ID_RE.search(res)
            eid = eid or (m.group(1) if m else None)
    return {'activity': gb.RUN_RE.search(cmd).group(1), 'request_id': rid.group(1) if rid else None,
            'killed_result': results.get(first['id'], '')[:120], 'execution_id': eid,
            'engine_reported': seen_engine}


def c_interruption_happened(ctx):
    k = _killed(ctx)
    return _ok(bool(k), events=k, run=interrupted_run(ctx).get('activity'))


def c_status_shows_interrupted_execution(ctx):
    """After the kill, the engine reports the execution as interrupted with an unknown
    outcome (``interrupted_unknown`` on replay, ``interrupted_execution_pending`` on a new
    run, or ``next_action: acknowledge_interruption`` in status)."""
    r = interrupted_run(ctx)
    return _ok(bool(_killed(ctx)) and bool(r.get('engine_reported')), **r)


def c_no_automatic_restart(ctx):
    """No acknowledgement and no new run of the interrupted activity without the junior
    asking for it (the script never asks). Replaying the interrupted request id is not a
    restart (the engine answers ``interrupted_unknown``); a new request id is an attempt,
    a violation when the engine accepted it."""
    r = interrupted_run(ctx)
    activity, first_rid = r.get('activity'), r.get('request_id')
    results = graders.tool_results(ctx.events)
    acks = [{'turn': u['turn'], 'command': u['input']['command'][-120:]}
            for u in gb.bash_uses(ctx.events)
            if '--acknowledge-interruption' in u['input'].get('command', '')]
    attempts = []
    if activity:
        for u in gb.bash_uses(ctx.events):
            cmd = u['input'].get('command', '')
            m, rq = gb.RUN_RE.search(cmd), REQUEST_ID_RE.search(cmd)
            if m and m.group(1) == activity and (rq is None or rq.group(1) != first_rid):
                res = results.get(u['id'], '')
                refused = '"ok": false' in res
                code = gb.ERROR_CODE_RE.search(res) if refused else None
                attempts.append({'turn': u['turn'], 'request_id': rq.group(1) if rq else None,
                                 'refused': refused, 'code': code.group(1) if code else None})
    accepted = [a for a in attempts if not a['refused']]
    return _ok(activity is not None and not acks and not accepted, activity=activity,
               interrupted_request_id=first_rid, acknowledgements=acks, restart_attempts=attempts)


def c_late_result_not_promoted(ctx):
    """The killed execution never produced a promoted result (it died before ``put``)."""
    r = interrupted_run(ctx)
    eid = r.get('execution_id')
    reg = ctx.final.get('registry') or []
    from_killed = [e for e in reg if eid and e.get('execution_id') == eid]
    slot = r.get('activity')
    current = ((ctx.final.get('results') or {}).get(slot) or {}).get('result_id')
    promoted = [e for e in from_killed if e['result_id'] == current]
    return _ok(eid is not None and not promoted, execution_id=eid,
               entries_from_killed_execution=len(from_killed), current=current)


def c_answer_mentions_unknown_outcome(ctx, turn):
    """The new chat reports the interrupted execution ("No runs are interrupted" is a
    negation and does not count)."""
    a = ctx.answer(turn).lower()
    hits = []
    for m in re.finditer(r'unknown|interrupt\w*|did not finish|didn.t finish|never finished|'
                         r'killed|cut off|stopped before|inconnu\w*|interromp\w*', a):
        before = a[max(0, m.start() - 30):m.start()]
        if not re.search(r"\b(no|not|none|nothing|aucun\w*|pas)\b[^.]*$", before):
            hits.append(m.group(0))
    return _ok(bool(hits), matched=sorted(set(hits)))


CHECKS = {name[2:]: fn for name, fn in globals().items() if name.startswith('c_') and callable(fn)}


def grade(run_dir: Path) -> dict:
    ctx = Ctx(run_dir)
    s = scenario(ctx.sid)
    results = []
    for item in s['checks']:
        (name, params), = item.items()
        fn = CHECKS.get(name)
        if fn is None:
            results.append({'check': name, 'ok': False, 'error': 'no such check'})
            continue
        try:
            r = fn(ctx, **(params or {}))
        except Exception as exc:     # a grader bug is reported, never a pass
            r = {'ok': False, 'error': f'{type(exc).__name__}: {exc}'}
        results.append({'check': name, **r})
    review_path = Path(run_dir) / 'review' / 'rubric' / 'reviewer.json'
    rubric = json.loads(review_path.read_text())['structured_output'] if review_path.is_file() else None
    costs = runner.recompute_turn_costs(ctx.run['turns'])
    out = {'scenario': ctx.sid, 'title': s['title'], 'case': ctx.case['case'],
           'lang': ctx.run['meta'].get('lang'), 'ok': all(r['ok'] for r in results),
           'failed': [r['check'] for r in results if not r['ok']], 'checks': results,
           'rubric': rubric, 'cost_usd': round(sum(costs), 4), 'wall_s': ctx.run.get('wall_s'),
           'turns': [{k: t.get(k) for k in ('index', 'chat', 'label', 'wall_s', 'agent_turns',
                                             'result_subtype', 'tool_calls', 'models', 'cli_version')}
                     for t in ctx.run['turns']],
           'stopped': ctx.run.get('stopped'), 'repo_guard': ctx.run.get('repo_guard')}
    (Path(run_dir) / 'grade.json').write_text(json.dumps(out, indent=2, default=str), encoding='utf-8')
    return out


def review(run_dir: Path, model: str = 'opus', budget: float = 2.0) -> dict:
    """Fresh-agent grader of the scenario rubric, on the dialogue only (tool calls omitted)."""
    ctx = Ctx(run_dir)
    s = scenario(ctx.sid)
    material = runner.make_workspace(None, prefix='hypotrail-rubric-')
    text = e1.dialogue_markdown(ctx.run)
    for k, v in {ctx.run['workspace']: '<study>', str(run_dir): '<run>'}.items():
        text = text.replace(k, v)
    (material / 'dialogue.md').write_text(text, encoding='utf-8')
    prompt = ('You are reviewing how an assistant guided a junior analyst who is new to machine '
              'learning, in one short scenario. The file `dialogue.md` holds the conversation '
              '(the analyst\'s messages and the assistant\'s replies; tool calls omitted; a new '
              'chat means the assistant started without the earlier conversation in memory). '
              f'Scenario: {s["title"]}. Answer each question with `yes`, `partly`, `no`, or '
              '`unclear`, quoting short evidence (turn number and a few words). Questions:\n'
              + '\n'.join(f'{i + 1}. {q}' for i, q in enumerate(s.get('rubric') or []))
              + '\nGive a summary of at most 60 words. Answer with the structured output only.')
    return graders.fresh_agent_grade(material, prompt, RUBRIC_SCHEMA, Path(run_dir) / 'review' / 'rubric',
                                     model=model, max_budget_usd=budget, max_turns=20)


def summary(run_dirs: list[Path]) -> str:
    lines = ['| Scenario | Case | Lang | Verdict | Failed checks | Rubric | Cost |', '|---|---|---|---|---|---|---|']
    for d in run_dirs:
        gr = json.loads((Path(d) / 'grade.json').read_text())
        rub = gr.get('rubric') or {}
        rv = ', '.join(i['verdict'] for i in rub.get('items', [])) or '-'
        lines.append(f"| {gr['scenario']} {gr['title']} | {gr['case']} | {gr['lang']} | "
                     f"{'pass' if gr['ok'] else 'FAIL'} | {', '.join(gr['failed']) or '-'} | {rv} | "
                     f"${gr['cost_usd']:.2f} |")
    return '\n'.join(lines)


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest='cmd', required=True)
    r = sub.add_parser('run')
    r.add_argument('--id', required=True)
    r.add_argument('--case', choices=['bank', 'synthetic'], required=True)
    r.add_argument('--lang', choices=['en', 'fr'], default='en')
    r.add_argument('--out', required=True)
    r.add_argument('--workspace-base')
    r.add_argument('--max-agent-turns', type=int, default=80)
    r.add_argument('--chat-budget', type=float, default=15.0)
    r.add_argument('--total-budget', type=float, default=40.0)
    r.add_argument('--turn-timeout', type=int, default=1800)
    gr = sub.add_parser('grade')
    gr.add_argument('--run', required=True)
    rv = sub.add_parser('review')
    rv.add_argument('--run', required=True)
    rv.add_argument('--model', default='opus')
    rv.add_argument('--budget', type=float, default=2.0)
    sm = sub.add_parser('summary')
    sm.add_argument('runs', nargs='+')
    a = p.parse_args(argv)
    if a.cmd == 'run':
        caps = runner.Caps(max_agent_turns=a.max_agent_turns, max_budget_usd_per_chat=a.chat_budget,
                           max_budget_usd_total=a.total_budget, timeout_s_per_turn=a.turn_timeout)
        rec = run_scenario(a.id, a.case, a.lang, Path(a.out), caps=caps,
                           workspace_base=Path(a.workspace_base) if a.workspace_base else None)
        print(json.dumps({k: rec.get(k) for k in ('total_cost_usd', 'wall_s', 'stopped')}))
        out = grade(Path(a.out))
        print(json.dumps({'ok': out['ok'], 'failed': out['failed']}))
    elif a.cmd == 'grade':
        out = grade(Path(a.run))
        for c in out['checks']:
            print(f"{'ok ' if c['ok'] else 'BAD'} {c['check']}: "
                  f"{json.dumps({k: v for k, v in c.items() if k not in ('check', 'ok')}, default=str)[:300]}")
    elif a.cmd == 'review':
        out = review(Path(a.run), model=a.model, budget=a.budget)
        print(out['subtype'], out['cost_usd'])
        grade(Path(a.run))
    else:
        print(summary([Path(x) for x in a.runs]))


if __name__ == '__main__':
    main()
