"""``hypotrail session-report``: a content-free timeline of a study, for observed sessions.

    hypotrail session-report --study DIR [--since REV] [--gap-minutes M]
    hypotrail session-report --study DIR --format text     # the same as Markdown

Read-only (it never writes, and works in a read-only process). It is meant for the
facilitator of an observed junior session (``docs/research/OBSERVATION-PROTOCOL.md``),
after the session, and is never logged itself. It joins three records:

* ``revisions.jsonl``: every committed change (always present);
* ``events.jsonl``: operational events (interrupted executions, failed renders, ...);
* ``session-log.jsonl``: the opt-in log of every CLI invocation, refusals and read-only
  commands included (:mod:`mlkit.study.sessionlog`); absent unless enabled, and the
  report then says that refusals, ``status`` reads, ``check`` runs and previews were not
  recorded.

Privacy: the report holds no conversation content. From the revision records it keeps
only identifiers (action, decision and proposal ids, basis, delegation scope, activity,
rule identifiers, column names, slots, the first 8 characters of result ids, the kind of
invalidation and how many results it made stale). It never copies ``user_words``,
restatements, rationales, proposed values, reasons, or text checked by ``check``.

Payload (``hypotrail.session_report/1``): ``schema``, ``ok``, ``study``, ``revision``,
``since``, ``sources``, ``span``, ``commands``, ``refusals``, ``decisions``, ``pauses``,
``runs``, ``renders``, ``checks``, ``gaps``, ``timeline``, ``privacy``. See
``docs/specs/CLI-CONTRACT.md``.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
from typing import Any, Iterable, Mapping

from . import commands as cmd
from . import read, sessionlog
from . import state as st

SCHEMA = 'hypotrail.session_report/1'
PAYLOAD_KEYS = ('schema', 'ok', 'study', 'revision', 'since', 'sources', 'span', 'commands',
                'refusals', 'decisions', 'pauses', 'runs', 'renders', 'checks', 'gaps',
                'timeline', 'privacy')
EVENTS_FILE = 'events.jsonl'
# The plan's three pauses (CLAUDE.md rule 3) and the decisions each one holds, per task:
# a regression study's third pause is the model choice (M3), not a policy.
PAUSES = {1: ('prediction_time', 'feature_availability'), 2: ('split',),
          3: ('policy', 'conclusion')}
TASK_PAUSES = {'binary': PAUSES,
               'regression': {**PAUSES, 3: ('model_choice', 'conclusion')}}
DEFAULT_GAP_MINUTES = 20
# Operational events worth a line in the timeline; ``command_committed`` repeats a revision.
EVENT_KINDS = ('study_created', 'interrupted_execution', 'render_failed',
               'nondeterministic_result', 'transaction_rolled_back',
               'commit_completed_after_interruption')
PRIVACY = ('No conversation content: user words, restatements, rationales, proposed values, '
           'reasons, and checked text are never copied. Identifiers, codes, counts, and times '
           'only.')


def configure(parser: argparse.ArgumentParser) -> None:
    parser.description = ('Read-only, content-free timeline of the study for an observed '
                           'session (never writes, never logged).')
    parser.add_argument('--since', type=int, default=None,
                        help='only what happened after revision REV')
    parser.add_argument('--gap-minutes', type=int, default=DEFAULT_GAP_MINUTES,
                        help=f'idle gaps longer than this are listed (default '
                             f'{DEFAULT_GAP_MINUTES})')


def _time(value) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _seconds(start, end) -> float | None:
    a, b = _time(start), _time(end)
    return round((b - a).total_seconds(), 1) if a and b else None


def _short(rid) -> str | None:
    return rid[:8] if isinstance(rid, str) else None


def _revision_line(r: Mapping) -> dict:
    """The content-free line of one revision record."""
    action = r.get('action')
    params = r.get('params') if isinstance(r.get('params'), Mapping) else {}
    result = r.get('result') if isinstance(r.get('result'), Mapping) else {}
    line = {'time': r.get('time'), 'source': 'revision', 'revision': r.get('revision'),
            'action': action}
    if action in ('decide.propose', 'decide.confirm', 'decide.withdraw'):
        for key in ('decision_id', 'proposal_id'):
            value = result.get(key, params.get(key))
            if value is not None:
                line[key] = value
        if action == 'decide.propose':
            line['superseded'] = list(result.get('superseded') or [])
        if action == 'decide.confirm':
            line['basis'] = result.get('basis', params.get('basis'))
            line['delegation_scope'] = result.get('delegation_scope',
                                                  params.get('delegation_scope'))
            inv = result.get('invalidation')
            if isinstance(inv, Mapping):
                line['invalidation'] = {'mutation': inv.get('mutation'),
                                        'stale_results': len(inv.get('stale_results') or [])}
    elif action and action.startswith('run.'):
        options = params.get('options') if isinstance(params.get('options'), Mapping) else {}
        for key in ('activity', 'execution_id', 'slot', 'status'):
            value = result.get(key, params.get(key))
            if value is not None:
                line[key] = value
        if options.get('rules'):
            line['rules'] = list(options['rules'])
        if options.get('column'):
            line['column'] = options['column']
        if result.get('result_id') or params.get('result_id'):
            line['result_id'] = _short(result.get('result_id') or params.get('result_id'))
    return line


def _log_line(entry: Mapping) -> dict:
    """A session-log line for the timeline (already content-free; re-filtered by key)."""
    keep = ('time', 'command', 'verb', 'exit_code', 'ok', 'revision', 'options', 'decision_id',
            'proposal_id', 'activity', 'refusal', 'replayed', 'status', 'basis',
            'delegation_scope', 'invalidation', 'artifacts', 'slot', 'result_id', 'check',
            'current_step', 'next_action', 'rules')
    return {'source': 'session_log', **{k: entry[k] for k in keep if k in entry}}


def _decisions(revisions: list[dict], log: list[dict]) -> list[dict]:
    """One item per proposal: when it was proposed, how it closed, and the time between."""
    out: dict[str, dict] = {}
    for r in revisions:
        action = r['action']
        pid = r.get('proposal_id')
        if action == 'decide.propose' and pid:
            out[pid] = {'proposal_id': pid, 'decision_id': r.get('decision_id'),
                        'proposed_at': r['time'], 'proposed_revision': r['revision'],
                        'outcome': 'open', 'closed_at': None, 'seconds_open': None,
                        'basis': None, 'delegation_scope': None, 'refused_confirmations': 0,
                        'refusal_reasons': {}}
            for old in r.get('superseded') or []:
                if old in out and out[old]['outcome'] == 'open':
                    out[old].update(outcome='superseded', closed_at=r['time'],
                                    seconds_open=_seconds(out[old]['proposed_at'], r['time']))
        elif action in ('decide.confirm', 'decide.withdraw') and pid in out:
            item = out[pid]
            item.update(outcome='confirmed' if action == 'decide.confirm' else 'withdrawn',
                        closed_at=r['time'], seconds_open=_seconds(item['proposed_at'], r['time']))
            if action == 'decide.confirm':
                item.update(basis=r.get('basis'), delegation_scope=r.get('delegation_scope'))
    for entry in log:
        if entry.get('command') == 'decide' and entry.get('verb') == 'confirm' \
                and not entry.get('ok') and entry.get('proposal_id') in out:
            item = out[entry['proposal_id']]
            item['refused_confirmations'] += 1
            reason = (entry.get('refusal') or {}).get('reason') or \
                (entry.get('refusal') or {}).get('code')
            item['refusal_reasons'][reason] = item['refusal_reasons'].get(reason, 0) + 1
    return sorted(out.values(), key=lambda d: (d['proposed_revision'], d['proposal_id']))


def _pauses(decisions: list[dict], task: str = 'binary') -> list[dict]:
    """Each pause of the study's task: from its first proposal to the confirmation that
    closed it."""
    out = []
    for number, ids in TASK_PAUSES.get(task, PAUSES).items():
        items = [d for d in decisions if d['decision_id'] in ids]
        if not items:
            out.append({'pause': number, 'decisions': list(ids), 'opened_at': None,
                        'closed_at': None, 'seconds': None, 'proposals': 0,
                        'confirmed': [], 'delegated': [], 'refused_confirmations': 0})
            continue
        confirmed = [d for d in items if d['outcome'] == 'confirmed']
        closed = all(any(d['decision_id'] == i and d['outcome'] == 'confirmed' for d in items)
                     for i in ids)
        opened = min(d['proposed_at'] for d in items)
        closed_at = max(d['closed_at'] for d in confirmed) if closed and confirmed else None
        out.append({'pause': number, 'decisions': list(ids), 'opened_at': opened,
                    'closed_at': closed_at,
                    'seconds': _seconds(opened, closed_at) if closed_at else None,
                    'proposals': len(items),
                    'confirmed': sorted({d['decision_id'] for d in confirmed}),
                    'delegated': sorted({d['decision_id'] for d in confirmed
                                         if d['basis'] == 'delegated_default'}),
                    'refused_confirmations': sum(d['refused_confirmations'] for d in items)})
    return out


def _runs(revisions: list[dict]) -> list[dict]:
    reserved: dict[str, dict] = {}
    for r in revisions:
        eid = r.get('execution_id')
        if r['action'] == 'run.reserve' and eid:
            reserved[eid] = {'execution_id': eid, 'activity': r.get('activity'),
                             'rules': r.get('rules'), 'column': r.get('column'),
                             'started_at': r['time'], 'outcome': 'running', 'ended_at': None,
                             'seconds': None, 'slot': None, 'result_id': None}
        elif r['action'] in ('run.promote', 'run.fail', 'run.recover', 'run.acknowledge') \
                and eid in reserved:
            item = reserved[eid]
            item.update(outcome={'run.promote': r.get('status') or 'promoted',
                                 'run.fail': 'failed', 'run.recover': 'interrupted',
                                 'run.acknowledge': 'acknowledged'}[r['action']],
                        ended_at=r['time'], seconds=_seconds(item['started_at'], r['time']))
            if r['action'] == 'run.promote':
                item.update(slot=r.get('slot'), result_id=r.get('result_id'))
    return list(reserved.values())


def _gaps(times: Iterable[str], minutes: int) -> list[dict]:
    stamps = sorted(t for t in (_time(x) for x in times) if t is not None)
    out = []
    for a, b in zip(stamps, stamps[1:]):
        gap = (b - a).total_seconds() / 60
        if gap > minutes:
            out.append({'from': a.isoformat(), 'to': b.isoformat(), 'minutes': round(gap, 1)})
    return out


def report(study_dir, since: int | None = None,
           gap_minutes: int = DEFAULT_GAP_MINUTES) -> dict:
    """The session report of the study at ``study_dir`` (read-only)."""
    study = read.open(study_dir)
    every = study.revisions(0)
    revisions = [_revision_line(r) for r in every if since is None or r.get('revision', 0) > since]
    # --since: the log and the events from the moment revision ``since`` was committed.
    cutoff = next((str(r.get('time')) for r in every if r.get('revision') == since), '') \
        if since is not None else ''
    events = [e for e in read._jsonl(study.home / EVENTS_FILE)
              if e.get('kind') in EVENT_KINDS and str(e.get('time', '')) > cutoff]
    log_path = sessionlog.path(study.study_dir)
    log_enabled = log_path.is_file()
    log = [e for e in read._jsonl(log_path) if str(e.get('time', '')) >= cutoff]
    event_lines = [{'time': e.get('time'), 'source': 'event', 'kind': e.get('kind'),
                    **{k: e[k] for k in ('revision', 'execution_id', 'activity', 'artifacts')
                       if k in e}} for e in events]
    log_lines = [_log_line(e) for e in log]
    timeline = sorted(revisions + event_lines + log_lines,
                      key=lambda x: (str(x.get('time') or ''), x['source'] != 'revision'))
    decisions = _decisions(revisions, log)
    commands = Counter(' '.join(x for x in (e.get('command'), e.get('verb')) if x) for e in log)
    refusals = [{'time': e.get('time'), 'command': ' '.join(
        x for x in (e.get('command'), e.get('verb')) if x), 'code': e['refusal'].get('code'),
        'reason': e['refusal'].get('reason'), 'revision': e.get('revision'),
        'proposal_id': e.get('proposal_id'), 'activity': e.get('activity')}
        for e in log if isinstance(e.get('refusal'), Mapping)]
    renders = ([{'time': e.get('time'), 'command': e.get('command'),
                 'revision': e.get('revision'), 'artifacts': e.get('artifacts')}
                for e in log if e.get('artifacts')]
               + [{'time': e.get('time'), 'command': None, 'revision': e.get('revision'),
                   'failed': e.get('artifacts')} for e in events
                  if e.get('kind') == 'render_failed'])
    checks = [{'time': e.get('time'), 'revision': e.get('revision'), **e['check']}
              for e in log if isinstance(e.get('check'), Mapping)]
    times = [x.get('time') for x in timeline if x.get('time')]
    manifest = study.artifacts() or {}
    span = {'first': min(times) if times else None, 'last': max(times) if times else None,
            'seconds': _seconds(min(times), max(times)) if times else None,
            'revisions': len(revisions)}
    return {
        'schema': SCHEMA, 'ok': True, 'study': str(study.study_dir), 'revision': study.revision,
        'since': since,
        'sources': {'revisions': len(revisions), 'events': len(events),
                    'session_log': {'enabled': log_enabled, 'entries': len(log),
                                    'path': f'{read.HOME}/{sessionlog.LOG_FILE}',
                                    'note': None if log_enabled else
                                    'The session log is off: refusals, status reads, check '
                                    'runs, and previews were not recorded. Enable it before '
                                    'a session with HYPOTRAIL_SESSION_LOG=1.'},
                    'artifacts_status': manifest.get('status')
                    if isinstance(manifest, Mapping) else None},
        'span': span,
        'commands': dict(sorted(commands.items())),
        'refusals': refusals,
        'decisions': decisions,
        'pauses': _pauses(decisions, st.task_of(study.state)),
        'runs': _runs(revisions),
        'renders': renders,
        'checks': checks,
        'gaps': _gaps(times, gap_minutes),
        'timeline': timeline,
        'privacy': PRIVACY,
    }


def main(args: argparse.Namespace) -> cmd.Outcome:
    from .errors import StudyError

    if args.gap_minutes < 1:
        raise StudyError('invalid_arguments', '--gap-minutes must be at least 1.')
    return cmd.Outcome(report(args.study, since=args.since, gap_minutes=args.gap_minutes))


# --- Markdown -----------------------------------------------------------------------------

def _dur(seconds: Any) -> str:
    if not isinstance(seconds, (int, float)):
        return '-'
    seconds = int(seconds)
    if seconds < 60:
        return f'{seconds}s'
    if seconds < 3600:
        return f'{seconds // 60}m{seconds % 60:02d}s'
    return f'{seconds // 3600}h{(seconds % 3600) // 60:02d}m'


def _clock(value: Any) -> str:
    t = _time(value)
    return t.strftime('%Y-%m-%d %H:%M:%S') if t else '-'


def _describe(x: Mapping) -> str:
    if x['source'] == 'revision':
        bits = [x.get('action') or '']
        for key in ('decision_id', 'proposal_id', 'activity', 'slot', 'status', 'basis',
                    'delegation_scope', 'result_id', 'column'):
            if x.get(key):
                bits.append(f'{key}={x[key]}')
        if x.get('rules'):
            bits.append('rules=' + ','.join(x['rules']))
        if x.get('invalidation'):
            bits.append(f'invalidation={x["invalidation"]["mutation"]}'
                        f' (stale {x["invalidation"]["stale_results"]})')
        return ' '.join(bits)
    if x['source'] == 'event':
        return f'event {x.get("kind")}' + (f' {x["activity"]}' if x.get('activity') else '')
    bits = [' '.join(b for b in (x.get('command'), x.get('verb')) if b), f'exit {x.get("exit_code")}']
    if x.get('refusal'):
        bits.append(f'REFUSED {x["refusal"].get("code")}'
                    + (f'/{x["refusal"]["reason"]}' if x['refusal'].get('reason') else ''))
    for key in ('decision_id', 'proposal_id', 'activity', 'next_action'):
        if x.get(key):
            bits.append(f'{key}={x[key]}')
    if x.get('check'):
        c = x['check']
        bits.append(f'check {c.get("target")} clean={c.get("clean")} '
                    f'errors={(c.get("counts") or {}).get("error")} '
                    f'warnings={(c.get("counts") or {}).get("warning")}')
    if x.get('options'):
        bits.append(' '.join(f'{k}={v}' for k, v in sorted(x['options'].items())))
    return ' · '.join(bits)


def markdown(payload: Mapping) -> str:
    """The report as Markdown, for the facilitator's analysis notes."""
    src = payload['sources']
    out = [f'# Session report', '',
           f'- Study: `{payload["study"]}` at revision {payload["revision"]}'
           + (f', since revision {payload["since"]}' if payload['since'] is not None else ''),
           f'- Span: {_clock(payload["span"]["first"])} to {_clock(payload["span"]["last"])} '
           f'({_dur(payload["span"]["seconds"])}), {payload["span"]["revisions"]} revisions',
           f'- Session log: {"on" if src["session_log"]["enabled"] else "off"}, '
           f'{src["session_log"]["entries"]} entries'
           + (f'. {src["session_log"]["note"]}' if src['session_log']['note'] else ''),
           f'- Privacy: {payload["privacy"]}', '', '## Pauses', '',
           '| Pause | Decisions | Opened | Closed | Elapsed | Proposals | Delegated | '
           'Refused confirmations |', '|---|---|---|---|---|---|---|---|']
    for p in payload['pauses']:
        out.append(f'| {p["pause"]} | {", ".join(p["decisions"])} | {_clock(p["opened_at"])} | '
                   f'{_clock(p["closed_at"])} | {_dur(p["seconds"])} | {p["proposals"]} | '
                   f'{", ".join(p["delegated"]) or "-"} | {p["refused_confirmations"]} |')
    out += ['', '## Decisions', '', '| Proposal | Decision | Outcome | Open for | Basis | '
            'Scope | Refused confirmations |', '|---|---|---|---|---|---|---|']
    for d in payload['decisions']:
        reasons = ', '.join(f'{k} x{v}' for k, v in d['refusal_reasons'].items())
        out.append(f'| {d["proposal_id"]} | {d["decision_id"]} | {d["outcome"]} | '
                   f'{_dur(d["seconds_open"])} | {d["basis"] or "-"} | '
                   f'{d["delegation_scope"] or "-"} | {d["refused_confirmations"]}'
                   + (f' ({reasons})' if reasons else '') + ' |')
    out += ['', '## Refusals', '']
    out += [f'- {_clock(r["time"])} `{r["command"]}`: {r["code"]}'
            + (f' ({r["reason"]})' if r['reason'] else '') for r in payload['refusals']] \
        or ['- none recorded' + ('' if src['session_log']['enabled'] else ' (session log off)')]
    out += ['', '## Checks', '']
    out += [f'- {_clock(c["time"])} {c.get("target")}: clean={c.get("clean")}, '
            f'codes={c.get("codes")}, traced={c.get("traced")}, in words={c.get("in_words")}'
            for c in payload['checks']] or ['- none recorded']
    out += ['', '## Runs', '']
    out += [f'- {_clock(r["started_at"])} {r["activity"]}'
            + (f' {",".join(r["rules"])}' if r.get('rules') else '')
            + f': {r["outcome"]} in {_dur(r["seconds"])}' for r in payload['runs']] \
        or ['- none']
    out += ['', '## Idle gaps', '']
    out += [f'- {_clock(g["from"])} to {_clock(g["to"])}: {g["minutes"]} min'
            for g in payload['gaps']] or ['- none']
    out += ['', '## Commands', '']
    out += [f'- `{k}`: {v}' for k, v in payload['commands'].items()] or ['- none recorded']
    out += ['', '## Timeline', '', '| Time | Source | Revision | What |', '|---|---|---|---|']
    for x in payload['timeline']:
        out.append(f'| {_clock(x.get("time"))} | {x["source"]} | {x.get("revision", "")} | '
                   f'{_describe(x)} |')
    return '\n'.join(out)
