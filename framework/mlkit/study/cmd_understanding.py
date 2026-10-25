"""``hypotrail understanding``: the opt-in understanding and handover review (ADR 0008).

    hypotrail understanding policy show --study DIR
    hypotrail understanding policy set --file POLICY --author ID --reason TEXT  (mutation)
    hypotrail understanding plan --profile P --milestone M --actor ID [--repo DIR]
                                 [--sources-file FILE] [--write-plan FILE] --study DIR
    hypotrail understanding start --plan-file PLAN                              (mutation)
    hypotrail understanding status [--session ID] [--repo DIR] --study DIR
    hypotrail understanding task --session ID --study DIR
    hypotrail understanding submit --session ID --task ID --response-file F
                                   --assistance-file F [--cite REF ...]
                                   [--previous-attempt ID]                       (mutation)
    hypotrail understanding coach --attempt ID                                  (mutation)
    hypotrail understanding rectify --attempt ID --assistance-file F            (mutation)
    hypotrail understanding propose-review --session ID --file PROPOSAL         (mutation)
    hypotrail understanding review --session ID --file HUMAN_DECISIONS          (mutation)
    hypotrail understanding arbitrate --session ID --file ARBITRATION           (mutation)
    hypotrail understanding select --file COVERAGE_SELECTION                    (mutation)
    hypotrail understanding waive --file WAIVER                                 (mutation)
    hypotrail understanding handover set --session ID --file CONTENT            (mutation)
    hypotrail understanding transfer start --session ID --peer ID --task ID     (mutation)
    hypotrail understanding transfer submit --transfer ID --response-file F
                                   --assistance-file F --evidence-file F         (mutation)
    hypotrail understanding transfer review --transfer ID --file REVIEW         (mutation)
    hypotrail understanding close --session ID --to STATUS --reason TEXT        (mutation)
    hypotrail understanding check --milestone M [--policy-file F] [--repo DIR] --study DIR
    hypotrail understanding export preview --session ID --repo DIR --study DIR
    hypotrail understanding export approve --session ID --contributor ID
                                   --content-digest D                           (mutation)
    hypotrail understanding export write --session ID --repo DIR                (mutation)
    hypotrail understanding git-plan --session ID --repo DIR --study DIR
    hypotrail understanding git-stage --session ID --repo DIR --index-identity H --study DIR
    hypotrail understanding git-receipt --session ID --repo DIR --commit OID     (mutation)
    hypotrail understanding relocate --session ID --repo DIR --author ID --reason TEXT
                                                                                (mutation)
    hypotrail understanding verify-export --repo DIR --target worktree|index|COMMIT
                                   [--policy-file F] [--review-id ID] [--study DIR]

Mutations take ``--request-id`` and ``--expected-revision``. JSON by default, ``--format
text`` for a person. Answers, documents and decisions are read from files named
explicitly; they are stored as local blobs of the study and never printed back. ``check``
is informative, never a reusable authorisation: ``export handoff`` recomputes the gate
under the writer lock in a required policy. ``verify-export`` needs no study.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import commands as cmd
from .understanding import (actions, taskset as bk, canonical, evaluate as ev, export as ex,
                            model, policy as pol, refuse, service as sv, snapshot as snap,
                            verify as vf)

SCHEMA = 'hypotrail.understanding/1'
STUDY_OPTIONAL = ('verify-export',)
MUTATIONS = ('policy set', 'start', 'submit', 'coach', 'rectify', 'propose-review', 'review',
             'arbitrate', 'select', 'waive', 'handover set', 'transfer start',
             'transfer submit', 'transfer review', 'close', 'export approve', 'export write',
             'git-receipt', 'relocate')
PLAN_SCHEMA = 'hypotrail.understanding-plan/1'
ESTIMATE_MINUTES = {'explain': 4, 'predict_consequence': 5, 'diagnose': 6, 'transfer': 8}


def _mut(p):
    p.add_argument('--request-id', default=None)
    p.add_argument('--expected-revision', default=None, type=int)


def configure(parser: argparse.ArgumentParser) -> None:
    from .cli import Parser, _common
    common = _common(False)       # every leaf takes --study and --format (verify-export: no study)
    sub = parser.add_subparsers(dest='verb', required=True, parser_class=Parser)
    policy = sub.add_parser('policy')
    pv = policy.add_subparsers(dest='policy_verb', required=True, parser_class=Parser)
    pv.add_parser('show', parents=[common])
    p = pv.add_parser('set', parents=[common])
    p.add_argument('--file', required=True)
    p.add_argument('--author', required=True, help='declared alias of who applies it')
    p.add_argument('--reason', required=True)
    _mut(p)
    p = sub.add_parser('plan', parents=[common])
    p.add_argument('--profile', required=True)
    p.add_argument('--milestone', required=True)
    p.add_argument('--actor', required=True, help='declared alias of the person reviewed')
    p.add_argument('--repo', default=None, help='the target repository holding the sources')
    p.add_argument('--sources-file', default=None,
                   help='JSON list of {logical_key, path, role} relative to --repo')
    p.add_argument('--previous-session', default=None)
    p.add_argument('--write-plan', default=None, help='also write the plan to this file')
    p = sub.add_parser('start', parents=[common])
    p.add_argument('--plan-file', required=True)
    _mut(p)
    p = sub.add_parser('status', parents=[common])
    p.add_argument('--session', default=None)
    p.add_argument('--repo', default=None)
    p = sub.add_parser('task', parents=[common])
    p.add_argument('--session', required=True)
    p = sub.add_parser('submit', parents=[common])
    p.add_argument('--session', required=True)
    p.add_argument('--task', required=True)
    p.add_argument('--response-file', required=True)
    p.add_argument('--assistance-file', required=True)
    p.add_argument('--cite', action='append', default=[])
    p.add_argument('--previous-attempt', default=None)
    _mut(p)
    for name in ('coach', 'rectify'):
        p = sub.add_parser(name, parents=[common])
        p.add_argument('--attempt', required=True)
        if name == 'rectify':
            p.add_argument('--assistance-file', required=True)
        _mut(p)
    for name in ('propose-review', 'review', 'arbitrate'):
        p = sub.add_parser(name, parents=[common])
        p.add_argument('--session', required=True)
        p.add_argument('--file', required=True)
        _mut(p)
    for name in ('select', 'waive'):
        p = sub.add_parser(name, parents=[common])
        p.add_argument('--file', required=True)
        _mut(p)
    handover = sub.add_parser('handover')
    hv = handover.add_subparsers(dest='handover_verb', required=True, parser_class=Parser)
    p = hv.add_parser('set', parents=[common])
    p.add_argument('--session', required=True)
    p.add_argument('--file', required=True)
    _mut(p)
    transfer = sub.add_parser('transfer')
    tv = transfer.add_subparsers(dest='transfer_verb', required=True, parser_class=Parser)
    p = tv.add_parser('start', parents=[common])
    p.add_argument('--session', required=True)
    p.add_argument('--peer', required=True)
    p.add_argument('--task', required=True)
    _mut(p)
    p = tv.add_parser('submit', parents=[common])
    p.add_argument('--transfer', required=True)
    p.add_argument('--response-file', required=True)
    p.add_argument('--assistance-file', required=True)
    p.add_argument('--evidence-file', required=True)
    _mut(p)
    p = tv.add_parser('review', parents=[common])
    p.add_argument('--transfer', required=True)
    p.add_argument('--file', required=True)
    _mut(p)
    p = sub.add_parser('close', parents=[common])
    p.add_argument('--session', required=True)
    p.add_argument('--to', required=True, choices=('active', 'awaiting_review', 'completed',
                                                   'abandoned'))
    p.add_argument('--reason', required=True)
    _mut(p)
    p = sub.add_parser('check', parents=[common])
    p.add_argument('--milestone', required=True)
    p.add_argument('--policy-file', default=None)
    p.add_argument('--repo', default=None)
    export = sub.add_parser('export')
    xv = export.add_subparsers(dest='export_verb', required=True, parser_class=Parser)
    p = xv.add_parser('preview', parents=[common])
    p.add_argument('--session', required=True)
    p.add_argument('--repo', required=True)
    p = xv.add_parser('approve', parents=[common])
    p.add_argument('--session', required=True)
    p.add_argument('--contributor', required=True)
    p.add_argument('--content-digest', required=True)
    _mut(p)
    p = xv.add_parser('write', parents=[common])
    p.add_argument('--session', required=True)
    p.add_argument('--repo', required=True)
    p.add_argument('--latest', action='store_true', help='also update latest.json (an index)')
    _mut(p)
    p = sub.add_parser('git-plan', parents=[common])
    p.add_argument('--session', required=True)
    p.add_argument('--repo', required=True)
    p = sub.add_parser('git-stage', parents=[common])
    p.add_argument('--session', required=True)
    p.add_argument('--repo', required=True)
    p.add_argument('--index-identity', required=True)
    p = sub.add_parser('git-receipt', parents=[common])
    p.add_argument('--session', required=True)
    p.add_argument('--repo', required=True)
    p.add_argument('--commit', required=True)
    _mut(p)
    p = sub.add_parser('relocate', parents=[common])
    p.add_argument('--session', required=True)
    p.add_argument('--repo', required=True, help='the new place of the moved repository '
                   '(the top level of its Git work tree)')
    p.add_argument('--author', required=True, help='declared alias of who records the move')
    p.add_argument('--reason', required=True)
    _mut(p)
    p = sub.add_parser('verify-export', parents=[common])
    p.add_argument('--repo', required=True)
    p.add_argument('--target', required=True)
    p.add_argument('--policy-file', default=None)
    p.add_argument('--review-id', default=None)


def _verb(args) -> str:
    v = args.verb
    for k in ('policy_verb', 'handover_verb', 'transfer_verb', 'export_verb'):
        if getattr(args, k, None):
            return f'{v} {getattr(args, k)}'
    return v


def _need_mutation(args, verb: str) -> None:
    if args.request_id is None or args.expected_revision is None:
        from .cli import ArgumentError
        raise ArgumentError(f'understanding {verb} changes the study: give --request-id and '
                            '--expected-revision')


def _ok(verb: str, study, **payload) -> dict:
    return {'schema': SCHEMA, 'ok': True, 'command': f'understanding {verb}',
            'study': str(study) if study else None, **payload}


def _apply(args, action, params) -> dict:
    receipt = actions.apply(args.study, action, params, request_id=args.request_id,
                            expected_revision=args.expected_revision)
    return {'revision': receipt['revision'], 'replayed': bool(receipt.get('replayed')),
            'result': receipt['result']}


def _render_after(study) -> dict | None:
    """Re-render the deliverables after a mutation, as decisions do, so the report stays
    current and shows the review section; a failure never undoes the mutation."""
    try:
        return cmd.after_commit(Path(study), {'ok': True})
    except Exception:            # noqa: BLE001
        return None


def main(args: argparse.Namespace) -> cmd.Outcome:
    verb = _verb(args)
    if verb in MUTATIONS:
        _need_mutation(args, verb)
    if verb == 'verify-export':
        return cmd.Outcome(_verify_export(args))
    if args.study is None:
        from .cli import ArgumentError
        raise ArgumentError(f'understanding {verb} needs --study DIR')
    study = Path(args.study)
    handler = HANDLERS[verb]
    payload = handler(args)
    if verb in MUTATIONS and not payload.get('replayed'):
        artifacts = _render_after(study)
        if artifacts is not None:
            payload['artifacts'] = artifacts
    return cmd.Outcome(payload)


# --- read-only commands ---------------------------------------------------------------------

def _policy_show(args) -> dict:
    store = sv.open_store(args.study)
    state = sv.load_state(args.study)
    ext = model.of(state)
    doc = sv.policy_doc(store, ext) if ext else None
    return _ok('policy show', store.study_dir, mode=pol.mode(doc), policy=doc,
               policy_digest=pol.digest(doc) if doc else None,
               events=list(ext['policy_events']) if ext else [],
               limitations=pol.limitations(doc or {}) if doc else [])


def _sources(path) -> list:
    if path is None:
        return []
    return snap.validate_sources(model.read_json_input(path, 'sources-file'))


def _plan(args) -> dict:
    store = sv.open_store(args.study)
    state = sv.load_state(args.study)
    doc = sv.require_mode(store, state)
    if args.milestone not in pol.MILESTONES:
        raise refuse('policy_invalid', 'Only the handoff milestone exists.',
                     'Plan for --milestone handoff.', milestone=args.milestone)
    actor = model.actor(args.actor, 'actor')
    dims = pol.author_dimensions(doc, args.profile)
    taskset = sv.current_taskset(state)
    sources = _sources(args.sources_file)
    repo = str(Path(args.repo).resolve()) if args.repo else None
    ext = model.of(state)
    cap = sv.capture(state, ext, policy_digest=pol.digest(doc), taskset_doc=taskset, repo=repo,
                     sources=sources)
    refs = cap['refs']
    chosen, missing, uncovered = [], [], []
    for dim in dims:
        tasks = [t for t in taskset['tasks'] if dim in t['dimension_ids'] and t['kind'] != 'transfer']
        ready = [t for t in tasks if not bk.resolve(t['prompt_template'], refs, t['required_refs'])[1]]
        if not tasks:
            uncovered.append(dim)
        elif not ready:
            missing.append({'dimension_id': dim, 'missing_refs': sorted(
                {r for t in tasks for r in bk.resolve(t['prompt_template'], refs, t['required_refs'])[1]})})
        else:
            chosen.append(ready[0]['task_id'])
    transfer = [t['task_id'] for t in taskset['tasks'] if t['kind'] == 'transfer'
                and set(t['dimension_ids']) & set(doc['peer_required_dimensions'])]
    minutes = sum(ESTIMATE_MINUTES[bk.task(taskset, t)['kind']] for t in chosen)
    plan = {'schema': PLAN_SCHEMA, 'actor_declared_id': actor, 'profile': args.profile,
            'milestone': args.milestone, 'task_ids': chosen, 'transfer_task_ids': transfer,
            'sources': sources, 'repo': repo, 'previous_session_id': args.previous_session,
            'retention_notice': 'Answers stay in this study as local files (not encrypted, '
                                'not sent to any service); only a reviewed and approved '
                                'synthesis can be committed.'}
    if args.write_plan:
        Path(args.write_plan).write_text(json.dumps(plan, indent=2, ensure_ascii=False) + '\n',
                                         encoding='utf-8')
    return _ok('plan', store.study_dir, mode=doc['mode'], policy_digest=pol.digest(doc),
               plan=plan, dimensions=dims, critical_dimensions=doc['critical_dimensions'],
               peer_required_dimensions=[d for d in doc['peer_required_dimensions']
                                         if d in dims],
               prerequisites_missing=missing, dimensions_without_task=uncovered,
               estimate_minutes=minutes,
               taskset={'taskset_id': taskset['taskset_id'], 'qualification':
                     taskset['qualification']['status'],
                     'simulated_qualification': bk.simulated_qualification(taskset)},
               will_be_kept_locally=['answers', 'assistance declarations', 'proposals',
                                     'human review decisions'],
               may_be_committed=['an approved synthesis: understanding-review.json, '
                                 'understanding-review.md, export-manifest.json'],
               note='A plan is a preview; it validates nothing. A workshop session of 10 to 15 '
                    'minutes covers a few dimensions, not the whole policy.')


def _status(args) -> dict:
    store = sv.open_store(args.study)
    state = sv.load_state(args.study)
    ext = model.of(state)
    if ext is None:
        return _ok('status', store.study_dir, mode='off', sessions=[],
                   revision=state['revision'])
    from .understanding import STATE_SCHEMA
    if ext.get('schema') != STATE_SCHEMA:
        return _ok('status', store.study_dir, mode='unsupported', sessions=[],
                   revision=state['revision'], found=ext.get('schema'))
    doc = sv.policy_doc(store, ext)
    current = sv.current_for(store, state, ext, repo_override=args.repo)
    sessions = []
    for s in sorted(ext['sessions'].values(), key=lambda s: s['created_revision']):
        if args.session and s['session_id'] != args.session:
            continue
        snapdoc = sv.session_snapshot(store, s)
        taskset = sv.blob_json(store, s['taskset_blob'], 'taskset')
        dims = []
        for dim in s['dimensions']:
            v = ev.dimension_view(ext, s['actor_declared_id'], dim)
            d = ext['decisions'].get(v['decision_id']) if v['decision_id'] else None
            keys = ev.decision_dependency_keys(ext, d, taskset) if d else \
                ((bk.rubric_for(taskset, dim) or {}).get('dependency_keys') or [])
            fresh = snap.freshness(snapdoc['local'], current(s), keys)
            avail = ev.evidence_availability(ext, d['attempt_ids'],
                                             lambda sha: sv.blob_ok(store, sha)) if d else None
            dims.append({**v, 'freshness': fresh['status'], 'changed': fresh['changed'],
                         'unknown': fresh['unknown'], 'evidence_availability': avail,
                         'assistance': (ev.assistance_summary(ext, d['attempt_ids'])
                                        if d else None),
                         'assurance': pol.SUPPORTED_ASSURANCE})
        attempts = [a for a in ext['attempts'].values() if a['session_id'] == s['session_id']]
        sessions.append({
            'session_id': s['session_id'], 'status': s['status'],
            'actor_declared_id': s['actor_declared_id'], 'profile': s['profile'],
            'milestone': s['milestone'], 'dimensions': dims,
            'tasks_planned': len(s['task_ids']),
            'tasks_answered': len({a['task_ref']['task_id'] for a in attempts}),
            'attempts': len(attempts),
            'unavailable_answers': sum(1 for a in attempts
                                       if not sv.blob_ok(store, a['response_sha256'])),
            'taskset_qualified': s['taskset_qualified'], 'taskset_simulated': s['taskset_simulated'],
            'local_snapshot_digest': s['local_snapshot_digest'],
            'source_scope_digest': s['source_scope_digest'],
            'repository': sv.repository_of(store, s, repo_override=args.repo),
            'relocations': [{k: r[k] for k in ('from', 'to', 'author_declared_id', 'reason',
                                               'revision')}
                            for r in s.get('relocations') or []]})
    return _ok('status', store.study_dir, mode=pol.mode(doc), revision=state['revision'],
               policy_digest=pol.digest(doc) if doc else None, sessions=sessions,
               conflicts=ev.conflicts(ext),
               open_reservations=[r['reservation_id'] for r in ev.open_reservations(ext)],
               assurance=pol.SUPPORTED_ASSURANCE,
               limitations=pol.limitations(doc) if doc else [])


def _task(args) -> dict:
    store = sv.open_store(args.study)
    state = sv.load_state(args.study)
    sv.require_mode(store, state)
    ext = model.of(state)
    s = ext['sessions'].get(args.session)
    if s is None:
        raise refuse('invalid_transition', 'Unknown session.', 'Check the session id.')
    taskset = sv.blob_json(store, s['taskset_blob'], 'taskset')
    refs = sv.session_snapshot(store, s).get('refs') or {}
    answered = {a['task_ref']['task_id'] for a in ext['attempts'].values()
                if a['session_id'] == s['session_id']}
    pending = [t for t in s['task_ids'] if t not in answered]
    # A dimension with an open reservation asks a new variant (never the same question).
    for dim in s['dimensions']:
        for r in ev.open_reservations(ext, s['actor_declared_id'], dim):
            used = {ext['attempts'][a]['task_ref']['variant_id'] for a in r['attempt_ids']
                    if a in ext['attempts']}
            family = {ext['attempts'][a]['task_ref']['variant_family'] for a in r['attempt_ids']
                      if a in ext['attempts']}
            for t in taskset['tasks']:
                if t['variant_family'] in family and t['variant_id'] not in used \
                        and t['task_id'] not in answered and t['task_id'] not in pending:
                    if not bk.resolve(t['prompt_template'], refs, t['required_refs'])[1]:
                        pending.append(t['task_id'])
                        break
    if not pending:
        return _ok('task', store.study_dir, session_id=s['session_id'], task=None,
                   message='No admissible task is left in this session. A reservation without '
                           'a new qualified variant stays to_consolidate or needs_review.')
    t = bk.task(taskset, pending[0])
    text, missing = bk.resolve(t['prompt_template'], refs, t['required_refs'])
    if missing:
        raise refuse('prerequisite_missing', 'The next task cites a study element that does not '
                     'exist yet.', 'Take the study further first.', missing=missing)
    s_note = None if t['task_id'] in s['task_ids'] else \
        'A new variant of a task whose answer opened a reservation: the same question is ' \
        'never asked again to demonstrate anew.'
    return _ok('task', store.study_dir, session_id=s['session_id'], task={
        'task_id': t['task_id'], 'task_version': t['task_version'], 'kind': t['kind'],
        'dimension_ids': t['dimension_ids'], 'prompt': text,
        'permitted_resources': t['permitted_resources'],
        'prohibited_actions': t['prohibited_actions'], 'source_refs': t['source_refs'],
        'in_plan': t['task_id'] in s['task_ids']},
        instructions='Answer in your own words first, with the references you used. "I do not '
                     'know" is a valid answer. No hint or expected answer is shown before your '
                     'first submission; hints after it are recorded as help.', note=s_note)


def _check(args) -> dict:
    store = sv.open_store(args.study)
    state = sv.load_state(args.study)
    override, source = None, 'study'
    if args.policy_file:
        override = pol.validate(model.read_json_input(args.policy_file, 'policy-file'))
        source = 'file'
    result = sv.gate(store, state, args.milestone, policy_override=override,
                     policy_source=source, repo_override=args.repo)
    extra = {}
    if args.repo:
        extra['repo_note'] = ('--repo is a preview: the protected action reads the sources '
                              'from the repository recorded in each session. After a move, '
                              'record the new place with `understanding relocate`.')
    return _ok('check', store.study_dir, revision=state['revision'], gate=result,
               note='Informative only: it authorises nothing and is never reused. The '
                    'protected action recomputes it under the writer lock.', **extra)


def _preview(args) -> dict:
    store = sv.open_store(args.study)
    state = sv.load_state(args.study)
    sv.require_mode(store, state)
    ext = model.of(state)
    s = ext['sessions'].get(args.session)
    if s is None:
        raise refuse('invalid_transition', 'Unknown session.', 'Check the session id.')
    proj = ex.projection(store, state, s)
    digest = canonical.digest(proj)
    draft = ex.review(ext, s, proj, created_at='draft', base_commit=None)
    return _ok('export preview', store.study_dir, draft=True, content_digest=digest,
               review_id=ex.review_id(proj),
               required_contributors=sorted(set(ex.required_contributors(proj))
                                            | {s['actor_declared_id']}),
               missing_approvals=ex.missing_approvals(ext, s, proj),
               markdown=ex.markdown(draft), known_gaps=proj['known_gaps'],
               note='A draft: approving covers exactly content_digest. Any change of this '
                    'content invalidates every approval.')


def _published_intent(ext, session_id) -> dict:
    published = [x for x in (ext or {}).get('exports', {}).values()
                 if x['session_id'] == session_id and x['status'] == 'published']
    if not published:
        raise refuse('prerequisite_missing', 'No current export is published for this session.',
                     'Run export write first (a not_current export gets no Git plan).')
    return max(published, key=lambda x: x['recorded_revision'])


def _expected_files(repo: Path, intent) -> dict:
    """``{repo path: bytes}`` of the generation, checked against the hashes the intent
    announced (an artefact edited after the export is refused, never planned)."""
    files = {}
    for n in ex.FILES:
        path = repo / ex.EXPORT_DIR / intent['review_id'] / n
        data = path.read_bytes() if path.is_file() else None
        if data is None or canonical.sha256_hex(data) != intent['files'][n]:
            raise refuse('export_stale', f'{n} of the generation differs from the exported '
                         'bytes.', 'Restore the generation or export a new one.', file=n)
        files[f'{ex.EXPORT_DIR}/{intent["review_id"]}/{n}'] = data
    return files


def _git_plan(args) -> dict:
    store = sv.open_store(args.study)
    state = sv.load_state(args.study)
    ext = model.of(state)
    s = (ext or {}).get('sessions', {}).get(args.session)
    if s is None:
        raise refuse('invalid_transition', 'Unknown session.', 'Check the session id.')
    intent = _published_intent(ext, s['session_id'])
    repo = Path(args.repo).resolve()
    files = _expected_files(repo, intent)
    scope = sv.session_snapshot(store, s)['public']
    plan = vf.git_plan(repo, files, [e for e in scope['entries'] if e['path']])
    return _ok('git-plan', store.study_dir, review_id=intent['review_id'], **plan,
               consistent=not plan['source_conflicts'],
               next_steps=['stage exactly the artefacts (git add -- PATHS, or understanding '
                           'git-stage)', 'verify-export --target index',
                           'commit as usual', 'verify-export --target HEAD'])


def _git_stage(args) -> dict:
    plan = _git_plan(args)
    if plan['source_conflicts']:
        raise refuse('git_index_conflict', 'A mapped source differs between the snapshot, the '
                     'working tree and the index.', 'Regenerate or review the sources first.',
                     conflicts=plan['source_conflicts'])
    out = vf.stage(Path(args.repo).resolve(), [a['path'] for a in plan['artefacts']],
                   args.index_identity, {a['path']: a['sha256'] for a in plan['artefacts']})
    return _ok('git-stage', args.study, **out,
               note='Nothing else was staged or unstaged; commit with your usual git commit.')


# --- mutations --------------------------------------------------------------------------------

def _policy_set(args) -> dict:
    store = sv.open_store(args.study)
    doc = pol.validate(model.read_json_input(args.file, 'file'))
    sha = sv.put_json(store, doc)
    out = _apply(args, 'policy_set', {'policy_sha': sha, 'author_declared_id': args.author,
                                      'reason': args.reason})
    return _ok('policy set', store.study_dir, **out, source=str(Path(args.file).name),
               limitations=pol.limitations(doc))


def _start(args) -> dict:
    store = sv.open_store(args.study)
    plan = model.read_json_input(args.plan_file, 'plan-file')
    keys = {'schema', 'actor_declared_id', 'profile', 'milestone', 'task_ids',
            'transfer_task_ids', 'sources', 'repo', 'previous_session_id', 'retention_notice'}
    if not isinstance(plan, dict) or set(plan) != keys or plan['schema'] != PLAN_SCHEMA \
            or plan['milestone'] not in pol.MILESTONES \
            or not isinstance(plan['task_ids'], list) \
            or not all(isinstance(t, str) for t in plan['task_ids']) \
            or not (plan['previous_session_id'] is None
                    or isinstance(plan['previous_session_id'], str)) \
            or not (plan['repo'] is None or isinstance(plan['repo'], str)) \
            or not isinstance(plan['profile'], str):
        raise refuse('evidence_invalid', 'The plan file is the plan written by `understanding '
                     'plan`.', 'Make the plan again.')
    snap.validate_sources(plan['sources'])
    last = None
    for _ in range(3):              # a source moving during the capture: bounded retry
        state = sv.load_state(args.study)
        doc = sv.require_mode(store, state)
        taskset = sv.current_taskset(state)
        ext = model.of(state)
        for t in plan['task_ids']:
            if bk.task(taskset, t) is None:
                raise refuse('evidence_invalid', 'The plan names a task the taskset does not have.',
                             'Make the plan again.', task_id=t)
        cap = sv.capture(state, ext, policy_digest=pol.digest(doc), taskset_doc=taskset,
                         repo=plan['repo'], sources=plan['sources'])
        snap_sha = sv.put_json(store, {'local': cap['local'], 'public': cap['public'],
                                       'refs': cap['refs'], 'meta': {
                                           # the request's revision: a retry of the same
                                           # request stores the same snapshot (a replay)
                                           'capture_revision': args.expected_revision}})
        params = {'plan_sha': sv.put_json(store, plan), 'snapshot_sha': snap_sha,
                  'local_digest': cap['local_snapshot_digest'],
                  'scope_digest': cap['source_scope_digest'],
                  'taskset_digest': bk.digest(taskset), 'policy_digest': pol.digest(doc)}
        try:
            return _ok('start', store.study_dir, **_apply(args, 'start', params))
        except Exception as exc:          # noqa: BLE001
            if getattr(exc, 'code', None) != 'context_changed':
                raise
            last = exc
    raise last


def _store_text(store, path, field) -> tuple[str, int]:
    text = model.read_text_input(path, field)
    data = text.encode('utf-8')
    return sv.put_bytes(store, data), len(data)


def _submit(args) -> dict:
    store = sv.open_store(args.study)
    sha, size = _store_text(store, args.response_file, 'response-file')
    assistance = sv.put_json(store, model.read_json_input(args.assistance_file,
                                                          'assistance-file'))
    out = _apply(args, 'submit', {'session_id': args.session, 'task_id': args.task,
                                  'response_sha': sha, 'response_bytes': size,
                                  'assistance_sha': assistance, 'cited_refs': list(args.cite),
                                  'previous_attempt_id': args.previous_attempt})
    return _ok('submit', store.study_dir, **out,
               note='Your answer is stored locally and is not printed back.')


def _coach(args) -> dict:
    store = sv.open_store(args.study)
    out = _apply(args, 'coach', {'attempt_id': args.attempt})
    state = sv.load_state(args.study)
    ext = model.of(state)
    a = ext['attempts'][args.attempt]
    s = ext['sessions'][a['session_id']]
    rubric = bk.rubric(sv.blob_json(store, s['taskset_blob'], 'taskset'), a['task_ref']['rubric_id'])
    return _ok('coach', store.study_dir, **out, hints=list(rubric['hints']),
               expected_criteria=[c['text'] for c in rubric['criteria']],
               note='This help is recorded: a later answer to this task is an aided answer. '
                    'A new demonstration uses a new variant.')


def _rectify(args) -> dict:
    store = sv.open_store(args.study)
    sha = sv.put_json(store, model.read_json_input(args.assistance_file, 'assistance-file'))
    return _ok('rectify', store.study_dir, **_apply(args, 'rectify', {
        'attempt_id': args.attempt, 'assistance_sha': sha}))


def _file_action(name, action, key, extra=None):
    def run(args) -> dict:
        store = sv.open_store(args.study)
        sha = sv.put_json(store, model.read_json_input(args.file, 'file'))
        params = {key: sha, **({'session_id': args.session} if extra == 'session' else {})}
        return _ok(name, store.study_dir, **_apply(args, action, params))
    return run


def _handover_set(args) -> dict:
    store = sv.open_store(args.study)
    doc = actions.handover_content(model.read_json_input(args.file, 'file'))
    sha = sv.put_json(store, doc)
    return _ok('handover set', store.study_dir, **_apply(args, 'handover', {
        'session_id': args.session, 'content_sha': sha}))


def _transfer_start(args) -> dict:
    store = sv.open_store(args.study)
    return _ok('transfer start', store.study_dir, **_apply(args, 'transfer_start', {
        'session_id': args.session, 'peer_declared_id': args.peer, 'task_id': args.task}),
        note='Declared ids are distinct; this does not authenticate either person.')


def _transfer_submit(args) -> dict:
    store = sv.open_store(args.study)
    sha, size = _store_text(store, args.response_file, 'response-file')
    assistance = sv.put_json(store, model.read_json_input(args.assistance_file,
                                                          'assistance-file'))
    evidence = sv.put_json(store, model.read_json_input(args.evidence_file, 'evidence-file'))
    return _ok('transfer submit', store.study_dir, **_apply(args, 'transfer_submit', {
        'transfer_id': args.transfer, 'response_sha': sha, 'response_bytes': size,
        'assistance_sha': assistance, 'evidence_sha': evidence}))


def _transfer_review(args) -> dict:
    store = sv.open_store(args.study)
    sha = sv.put_json(store, model.read_json_input(args.file, 'file'))
    return _ok('transfer review', store.study_dir, **_apply(args, 'transfer_review', {
        'transfer_id': args.transfer, 'review_sha': sha}))


def _close(args) -> dict:
    store = sv.open_store(args.study)
    return _ok('close', store.study_dir, **_apply(args, 'close', {
        'session_id': args.session, 'to': args.to, 'reason': args.reason}))


def _approve(args) -> dict:
    store = sv.open_store(args.study)
    return _ok('export approve', store.study_dir, **_apply(args, 'approve', {
        'session_id': args.session, 'contributor': args.contributor,
        'content_digest': args.content_digest}),
        note='A declared approval of exactly this content; it does not authenticate anyone.')


def _export_write(args, *, fault=None) -> dict:
    """Intent in the study, files out of the lock, receipt in the study (SPEC §14)."""
    store = sv.open_store(args.study)
    state = sv.load_state(args.study)
    sv.require_mode(store, state)
    ext = model.of(state)
    s = ext['sessions'].get(args.session)
    if s is None:
        raise refuse('invalid_transition', 'Unknown session.', 'Check the session id.')
    repo = Path(args.repo).resolve()
    if not repo.is_dir():
        raise refuse('path_outside_scope', '--repo is not a directory.', 'Name the repository.')
    if (repo / ex.EXPORT_DIR).resolve().is_relative_to(store.home.resolve()):
        raise refuse('path_outside_scope', 'The export never goes inside the study state.',
                     'Name the target repository.')
    proj = ex.projection(store, state, s)
    digest = canonical.digest(proj)
    rid = ex.review_id(proj)
    prior = sorted((x for x in ext['exports'].values() if x['review_id'] == rid),
                   key=lambda x: x['recorded_revision'])
    if prior:
        # A retry of the same generation renders the same bytes (same time and base).
        created_at, base = prior[0]['created_at'], prior[0]['base_commit']
    else:
        created_at, base = sv.now(), None
        try:
            if vf._has_head(repo):
                base = vf.git(repo, 'rev-parse', 'HEAD').decode().strip()
        except Exception:          # noqa: BLE001 - not a Git repository: no base commit
            base = None
    doc = ex.review(ext, s, proj, created_at=created_at, base_commit=base)
    if doc['privacy_review']['status'] != 'approved':
        raise refuse('privacy_approval_required', 'Every contributor approves the exact '
                     'content before export.', 'Collect the missing approvals.',
                     missing=ex.missing_approvals(ext, s, proj))
    doc_files = ex.files_of(doc)
    hashes = {n: canonical.sha256_hex(d) for n, d in doc_files.items()}
    reserved = [x for x in prior if x['status'] == 'reserved']
    if reserved and reserved[0]['files'] == hashes:
        # A publication interrupted before its receipt: reconciled from the bytes the
        # intent announced, never under a new intent (A13, A31).
        intent = {'result': {'intent_id': reserved[0]['intent_id']},
                  'revision': reserved[0]['recorded_revision'], 'replayed': True}
    else:
        intent = _apply(args, 'export_intent', {
            'session_id': s['session_id'], 'review_id': rid, 'projection_digest': digest,
            'destination': f'{ex.EXPORT_DIR}/{rid}', 'files': hashes,
            'created_at': created_at, 'base_commit': base})
    outcome = ex.publish(repo, rid, doc_files, fault=fault)
    # Reconcile from the bytes announced by the intent, never from a new rendering.
    on_disk = {n: canonical.sha256_hex((repo / ex.EXPORT_DIR / rid / n).read_bytes())
               for n in ex.FILES}
    if on_disk != hashes:
        raise refuse('export_stale', 'The published generation does not hold the announced '
                     'bytes.', 'Inspect docs/understanding before any new attempt.')
    # The receipt revalidates the context under the writer lock (actions._export_receipt).
    # Its request is derived from the intent, so a full retry replays it.
    iid = intent['result']['intent_id']
    receipt = _receipt(args.study, iid, on_disk)
    _settle_interrupted(args.study, repo, s['session_id'], iid)
    if args.latest:
        ex.write_latest(repo, rid)
    return _ok('export write', store.study_dir, review_id=rid, publication=outcome,
               destination=f'{ex.EXPORT_DIR}/{rid}', files=hashes,
               receipt=receipt['result'], revision=receipt['revision'],
               replayed=intent['replayed'],
               next_steps=['understanding git-plan', 'stage the listed paths only',
                           'verify-export --target index', 'git commit',
                           'verify-export --target HEAD'])


def _settle_interrupted(study, repo: Path, session_id: str, done: str) -> None:
    """Earlier intents of the session left ``reserved`` by a publication interrupted before
    its receipt get their receipt now when their folder holds the announced bytes (the
    receipt revalidates them: ``published`` or ``not_current``). Others stay reserved."""
    ext = model.of(sv.load_state(study))
    for x in list(ext['exports'].values()):
        if x['session_id'] != session_id or x['status'] != 'reserved' or x['intent_id'] == done:
            continue
        folder = repo / x['destination']
        try:
            held = {n: canonical.sha256_hex((folder / n).read_bytes()) for n in ex.FILES}
        except OSError:
            continue
        if held == x['files'] and not folder.is_symlink():
            _receipt(study, x['intent_id'], held)


def _receipt(study, intent_id, files) -> dict:
    """The export receipt, idempotent per intent: replayed when already recorded."""
    state = sv.load_state(study)
    intent = model.of(state)['exports'][intent_id]
    if intent['status'] != 'reserved':
        return {'result': {'intent_id': intent_id, 'status': intent['status'], 'final': True},
                'revision': state['revision'], 'replayed': True}
    return actions.apply(study, 'export_receipt', {'intent_id': intent_id,
                                                   'verified_files': files},
                         request_id=f'receipt-{intent_id}', expected_revision=state['revision'])


def _git_toplevel(repo: Path) -> Path | None:
    """The top level of the Git work tree holding ``repo`` (None outside one)."""
    import os
    import subprocess
    env = {**os.environ, **vf.GIT_ENV}
    try:
        proc = subprocess.run(['git', '-C', str(repo), '-c', 'core.hooksPath=/dev/null',
                               '-c', 'core.fsmonitor=false', 'rev-parse', '--show-toplevel'],
                              capture_output=True, env=env, timeout=60, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    out = proc.stdout.decode(errors='replace').strip()
    return Path(out).resolve() if proc.returncode == 0 and out else None


def _relocate(args) -> dict:
    store = sv.open_store(args.study)
    repo = Path(args.repo).resolve()
    if not repo.is_dir():
        raise refuse('path_outside_scope', '--repo is not a directory.', 'Name the repository.')
    if _git_toplevel(repo) != repo:
        raise refuse('path_outside_scope', '--repo is not the top level of a Git work tree; '
                     'nothing was recorded.', 'Name the top level of the moved repository.')
    return _ok('relocate', store.study_dir, **_apply(args, 'relocate', {
        'session_id': args.session, 'repo': str(repo), 'author_declared_id': args.author,
        'reason': args.reason}),
        note='Freshness is read from this repository from now on; the digests are unchanged. '
             'A relocation records a move declared by a person; it does not authenticate the '
             'content of the new place.')


def _git_receipt(args) -> dict:
    store = sv.open_store(args.study)
    state = sv.load_state(args.study)
    ext = model.of(state)
    intent = _published_intent(ext, args.session)
    expected = {f'{ex.EXPORT_DIR}/{intent["review_id"]}/{n}': intent['files'][n]
                for n in ex.FILES}
    r = vf.commit_receipt(Path(args.repo).resolve(), args.commit, expected)
    return _ok('git-receipt', store.study_dir, **_apply(args, 'git_receipt', {
        'review_id': intent['review_id'], **r}), commit=r['commit'], tree=r['tree'])


def _verify_export(args) -> dict:
    if not Path(args.repo).is_dir():
        raise refuse('path_outside_scope', '--repo is not a directory; nothing was verified.',
                     'Name the repository to verify.')
    policy_doc = None
    if args.policy_file:
        policy_doc = pol.validate(model.read_json_input(args.policy_file, 'policy-file'))
    local = None
    if getattr(args, 'study', None):
        local = _local_checker(args.study, args.repo)
    out = vf.verify(Path(args.repo).resolve(), args.target, policy_doc=policy_doc, local=local,
                    review_id=args.review_id)
    out['command'] = 'understanding verify-export'
    out['policy_source'] = 'file' if policy_doc else 'embedded (diagnostic only)'
    return out


def _local_checker(study, repo):
    store = sv.open_store(study)
    state = sv.load_state(study)
    ext = model.of(state)

    def run(doc, file_hashes=None) -> dict:
        if not ext:
            # A study without the review exported nothing: the generation is not its own.
            return {'private_context_verification': 'unknown', 'study_binding': 'not_recorded',
                    'evidence_availability': 'unavailable'}
        session = next((s for s in ext['sessions'].values()
                        if ex._opaque(ext, 'session', s['session_id']) == doc['session_ref']),
                       None)
        if session is None:
            return {'private_context_verification': 'unknown', 'study_binding': 'not_recorded'}
        # The artefact must be one this study exported: same review id, same approved
        # projection and the very bytes a recorded export intent announced (a forged or an
        # edited generation is not). A reserved intent counts when its bytes are there: its
        # publication was interrupted before the receipt.
        digest = canonical.digest(ex.approval_projection(doc))
        recorded = any(x['review_id'] == doc['review_id'] and x['projection_digest'] == digest
                       and x['session_id'] == session['session_id']
                       and x['status'] in ('published', 'not_current', 'reserved')
                       and file_hashes is not None and x['files'] == file_hashes
                       for x in ext['exports'].values())
        if not recorded:
            return {'private_context_verification': 'unknown', 'study_binding': 'not_recorded',
                    'evidence_availability': 'unavailable'}
        # Private context only: the repository entries are public and checked against the
        # requested tree (index or commit), never the working tree here.
        def private(local):
            return [e for e in local['entries'] if e['origin'] != 'repo']
        current = sv.current_for(store, state, ext, repo_override=repo)(session)
        captured = sv.session_snapshot(store, session)['local']
        same = canonical.digest(private(current)) == canonical.digest(private(captured))
        ids = [d['human_review_ref'] for d in doc['dimensions'] if d['human_review_ref']]
        attempts = [a for i in ids for a in (ext['decisions'].get(i) or {}).get('attempt_ids', [])]
        avail = ev.evidence_availability(ext, attempts, lambda sha: sv.blob_ok(store, sha)) \
            if attempts else 'unavailable'
        return {'private_context_verification': 'verified' if same else 'unknown',
                'private_context_changed': not same, 'evidence_availability': avail,
                'study_binding': 'verified'}
    return run


HANDLERS = {
    'policy show': _policy_show, 'policy set': _policy_set, 'plan': _plan, 'start': _start,
    'status': _status, 'task': _task, 'submit': _submit, 'coach': _coach, 'rectify': _rectify,
    'propose-review': _file_action('propose-review', 'propose', 'proposal_sha', 'session'),
    'review': _file_action('review', 'review', 'decisions_sha', 'session'),
    'arbitrate': _file_action('arbitrate', 'arbitrate', 'arbitration_sha', 'session'),
    'select': _file_action('select', 'select', 'selection_sha'),
    'waive': _file_action('waive', 'waive', 'waiver_sha'),
    'handover set': _handover_set, 'transfer start': _transfer_start,
    'transfer submit': _transfer_submit, 'transfer review': _transfer_review,
    'close': _close, 'check': _check, 'export preview': _preview, 'export approve': _approve,
    'export write': _export_write, 'git-plan': _git_plan, 'git-stage': _git_stage,
    'git-receipt': _git_receipt, 'relocate': _relocate}


def text(payload: dict) -> str:
    """A short human summary of an understanding payload."""
    lines = [f'{payload.get("command")}: ok']
    if 'gate' in payload:
        g = payload['gate']
        lines.append(f'milestone {g["milestone"]}: {g["decision"]} (assurance {g["assurance"]})')
        lines += [f'  - {r["code"]}' + (f' [{r["dimension"]}]' if r.get('dimension') else '')
                  for r in g['reasons']]
    if 'sessions' in payload:
        lines.append(f'mode {payload.get("mode")}')
        for s in payload['sessions']:
            lines.append(f'session {s["session_id"]} ({s["status"]}) for {s["actor_declared_id"]}')
            lines += [f'  {d["dimension_id"]}: {d["status"]}, {d["freshness"]}'
                      for d in s['dimensions']]
    if payload.get('task'):
        t = payload['task']
        lines += [f'task {t["task_id"]} ({t["kind"]}, {", ".join(t["dimension_ids"])})',
                  t['prompt'], payload.get('instructions', '')]
    if 'markdown' in payload:
        lines += [f'content digest {payload["content_digest"]} (draft)', payload['markdown']]
    return '\n'.join(x for x in lines if x is not None)
