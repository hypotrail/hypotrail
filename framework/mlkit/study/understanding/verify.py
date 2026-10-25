"""Standalone export verifier and Git reading (SPEC §16).

``verify-export --repo DIR --target worktree|index|<commit>`` reads the bytes of the tree it
names: the working tree, a coherent capture of the index (its identity is read before and
after; a change in between is ``git_index_conflict``), or the tree of a commit through Git
plumbing (``ls-tree``, ``cat-file``). It never runs code of the repository: no hook, no
notebook, no pickle, no configuration of the commit. Paths are checked (relative, no
traversal, no duplicate, no symbolic link, a size limit).

It answers on separate axes: ``public_integrity`` (valid, invalid), ``declared_conformity``
(conforming, nonconforming, unknown), ``public_source_freshness`` (current, stale,
unknown), ``private_context_verification`` (verified, unknown), ``evidence_availability``,
``assurance``, ``unresolved_private_refs`` and ``limitations``; with ``--policy-file``, a
``gate_result`` for that explicit policy. With ``--study`` (local mode), ``gate_result`` and
``declared_conformity`` are the study's own gate for the exported session (review round 5:
one judgement) plus the reasons the artefact establishes on the verified tree
(:func:`tree_reasons`, review round 6), compared with every session whose decisions the gate
judged (:func:`local_tree_reasons`, review round 7); without it, :func:`_gate_on_export` applies the
gate's rules to the exported content only (CLI-CONTRACT §16 lists what it cannot judge). A
clean clone establishes public integrity; it never concludes ``current`` on the private context nor resolves an opaque reference. Without
``--policy-file`` the result is a historical diagnostic, not an organisational
authorisation, and a policy relaxed only inside the candidate change is never read as an
authority (the embedded policy only gives ``declared_conformity``).
"""
from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path, PurePosixPath
from typing import Callable, Mapping

from . import canonical, export as ex, policy as pol, refuse, snapshot as snap

SCHEMA = 'hypotrail.understanding-verification/1'
MAX_FILE = 4 * 1024 * 1024
# GIT_NO_LAZY_FETCH: a partial clone never fetches a missing object (Git 2.44 and later);
# older Git is covered by refusing a partial clone (Tree).
# GIT_NO_REPLACE_OBJECTS: refs/replace never substitutes other bytes for the ones the tree
# names (a mirror clone or a refs/* fetch brings such refs).
GIT_ENV = {'GIT_TERMINAL_PROMPT': '0', 'GIT_OPTIONAL_LOCKS': '0', 'LC_ALL': 'C',
           'GIT_NO_LAZY_FETCH': '1', 'GIT_NO_REPLACE_OBJECTS': '1'}
NO_LAZY_FETCH_SINCE = (2, 44)


def git_env() -> dict:
    """The environment of every Git call: the caller's, without any inherited ``GIT_*``
    variable (``GIT_DIR``, ``GIT_INDEX_FILE``, ``GIT_WORK_TREE``, ``GIT_CONFIG_*``... set by
    a hook or a linked worktree would make Git read another repository than ``--repo``),
    plus :data:`GIT_ENV`."""
    env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
    env.update(GIT_ENV)
    return env


def git_version() -> tuple[int, int]:
    proc = subprocess.run(['git', '--version'], capture_output=True, env=git_env(),
                          check=False)
    import re
    m = re.search(rb'(\d+)\.(\d+)', proc.stdout)
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def git(repo: Path, *args: str, input_: bytes | None = None) -> bytes:
    """Run one Git plumbing command (no shell, no hook, no pager); bytes of stdout."""
    env = git_env()
    proc = subprocess.run(['git', '-C', str(repo), '-c', 'core.hooksPath=/dev/null',
                           '-c', 'core.fsmonitor=false', '--no-pager', *args], input=input_, capture_output=True, env=env,
                          timeout=120, check=False)
    if proc.returncode != 0:
        raise refuse('git_index_conflict', f'git {args[0]} failed.',
                     'Check that --repo is a Git repository and the target exists.',
                     command=args[0], stderr=proc.stderr.decode(errors='replace')[-300:])
    return proc.stdout


def _partial_clone(repo: Path) -> bool:
    """A promisor remote is configured (the repository may fetch objects on demand)."""
    proc = subprocess.run(['git', '-C', str(repo), 'config', '--get-regexp',
                           r'^(extensions\.partialclone|remote\..*\.promisor)$'],
                          capture_output=True, env=git_env(), check=False)
    return proc.returncode == 0 and bool(proc.stdout.strip())


def _case_variant(path: str) -> bool:
    """A path that a case-insensitive checkout would put under the export folder, but
    that is not spelt as it (it would be invisible to this verifier otherwise)."""
    folded, exact = path.casefold(), ex.EXPORT_DIR + '/'
    return folded.startswith(exact.casefold()) and not path.startswith(exact) or (
        path.startswith(exact) and path[len(exact):].casefold().startswith(('rv-', '.rv-'))
        and not path[len(exact):].startswith(('rv-', '.rv-')))


def _safe(path: str) -> bool:
    try:
        snap.safe_relative(path)
        return True
    except Exception:          # noqa: BLE001
        return False


class Tree:
    """Read access to one target: ``read(rel) -> bytes | None`` and ``list(prefix)``."""

    def __init__(self, repo: Path, target: str):
        self.repo = Path(repo)
        self.target = target
        self.problems: list[str] = []
        self._entries: dict[str, tuple[str, str]] | None = None    # path -> (mode, oid)
        if target == 'worktree':
            return
        if _partial_clone(self.repo) and git_version() < NO_LAZY_FETCH_SINCE:
            # Git 2.44 and later honour GIT_NO_LAZY_FETCH: a missing object is then an error,
            # never a fetch, and the local index and commit blobs read as usual.
            raise refuse('git_index_conflict', 'This is a partial clone and this Git (older '
                         'than 2.44) cannot be told not to fetch a missing object, which '
                         'would run the configured transport.',
                         'Use Git 2.44 or later, or a full clone (git clone without --filter).')
        if target == 'index':
            self.index_id = self._index_identity()
            self._entries = self._ls_index()
        else:
            commit = git(self.repo, 'rev-parse', '--verify', '--end-of-options',
                         f'{target}^{{commit}}').decode().strip()
            self.commit = commit
            self.tree = git(self.repo, 'rev-parse', f'{commit}^{{tree}}').decode().strip()
            self._entries = self._ls_tree(commit)

    def _index_identity(self) -> str:
        path = git(self.repo, 'rev-parse', '--git-path', 'index').decode().strip()
        p = Path(path) if os.path.isabs(path) else self.repo / path
        return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else 'none'

    def _ls_index(self) -> dict:
        out = {}
        for rec in git(self.repo, 'ls-files', '-s', '-z').split(b'\0'):
            if not rec:
                continue
            meta, path = rec.split(b'\t', 1)
            mode, oid, stage = meta.decode().split()
            p = path.decode('utf-8', 'replace')
            if stage != '0':
                self.problems.append(f'unmerged index entry {p}')
            if p in out:
                self.problems.append(f'duplicate path {p}')
            out[p] = (mode, oid)
        return out

    def _ls_tree(self, commit: str) -> dict:
        out = {}
        for rec in git(self.repo, 'ls-tree', '-r', '-z', '--full-tree', commit).split(b'\0'):
            if not rec:
                continue
            meta, path = rec.split(b'\t', 1)
            mode, kind, oid = meta.decode().split()
            p = path.decode('utf-8', 'replace')
            if p in out:
                self.problems.append(f'duplicate path {p}')    # a malformed tree
            out[p] = (mode, oid)
        return out

    def still_coherent(self) -> bool:
        return self.target != 'index' or self._index_identity() == self.index_id

    def read(self, rel: str) -> bytes | None:
        if not _safe(rel):
            self.problems.append(f'unsafe path {rel!r}')
            return None
        if self._entries is None:
            path = self.repo / rel
            if any((self.repo / PurePosixPath(*PurePosixPath(rel).parts[:i])).is_symlink()
                   for i in range(1, len(PurePosixPath(rel).parts) + 1)):
                self.problems.append(f'symbolic link {rel}')
                return None
            if not path.is_file():
                return None
            real = Path(os.path.realpath(path))
            if not real.is_relative_to(Path(os.path.realpath(self.repo))) \
                    or real.stat().st_size > MAX_FILE:
                self.problems.append(f'path outside limits {rel}')
                return None
            return real.read_bytes()
        entry = self._entries.get(rel)
        if entry is None:
            return None
        mode, oid = entry
        if mode == '120000':
            self.problems.append(f'symbolic link {rel}')
            return None
        if mode not in ('100644', '100755'):
            self.problems.append(f'not a regular file {rel}')
            return None
        size = int(git(self.repo, 'cat-file', '-s', oid).decode().strip())
        if size > MAX_FILE:
            self.problems.append(f'file over the limit {rel}')
            return None
        return git(self.repo, 'cat-file', 'blob', oid)

    def generations(self) -> list[str]:
        """The generation folders (``rv-*``), the same rule for every target. A leftover
        temporary folder (``.rv-*``), an ``rv-*`` entry that is not a folder of files, or a
        link is a problem; other names (a README, examples) are not generations."""
        prefix = ex.EXPORT_DIR + '/'
        names = set()
        if self._entries is None:
            parts = ex.EXPORT_DIR.split('/')
            for i, part in enumerate(parts):
                parent = self.repo.joinpath(*parts[:i])
                if parent.is_dir():
                    for p in parent.iterdir():
                        if p.name != part and p.name.casefold() == part.casefold():
                            self.problems.append('case variant of the export folder: '
                                                 + p.relative_to(self.repo).as_posix())
            base = self.repo / ex.EXPORT_DIR
            if not base.is_dir():
                return []
            for p in base.iterdir():
                if _case_variant(f'{ex.EXPORT_DIR}/{p.name}'):
                    self.problems.append(f'case variant of a generation: {p.name}')
                if p.name.startswith('.rv-'):
                    self.problems.append(f'leftover temporary folder {p.name} (an '
                                         'interrupted export: delete it)')
                elif p.name.startswith('rv-'):
                    if p.is_symlink() or not p.is_dir():
                        self.problems.append(f'{p.name} is not a generation folder')
                    else:
                        names.add(p.name)
            return sorted(names)
        for path in self._entries:
            if _case_variant(path):
                self.problems.append(f'case variant of the export folder: {path}')
            if path.startswith(prefix):
                rest = path[len(prefix):].split('/')
                if rest[0].startswith('.rv-'):
                    self.problems.append(f'leftover temporary folder {rest[0]} (an '
                                         'interrupted export: remove it from the tree)')
                elif rest[0].startswith('rv-'):
                    if len(rest) != 2:
                        self.problems.append(f'{rest[0]} is not a generation folder')
                    else:
                        names.add(rest[0])
        return sorted(names)

    def files_in(self, rid: str) -> list[str]:
        prefix = f'{ex.EXPORT_DIR}/{rid}/'
        if self._entries is None:
            base = self.repo / ex.EXPORT_DIR / rid
            return sorted(p.name for p in base.iterdir()) if base.is_dir() else []
        return sorted(p[len(prefix):] for p in self._entries if p.startswith(prefix))


# Gaps an export states that are not reasons of the gate: what only the export can say
# (``source_unreadable``, ``external_unverified``) and the limitations the gate counted
# (``private_context_unknown`` per dimension under ``public_only``).
# ``scope_does_not_cover_shown_decision`` (review round 7, R7-2) is one too: it is not a
# reason of the gate, it makes the export's public sources ``unknown`` (:func:`_verify_one`).
EXPORT_ONLY_GAPS = ('source_unreadable', 'external_unverified', ex.SCOPE_GAP)


def _gate_on_export(doc: Mapping, policy_doc: Mapping, axes: Mapping,
                    today: str | None = None) -> dict:
    """The standalone judgement (no study): the gate's rules (:func:`evaluate.gate`) applied
    to what the exported content states, for ``policy_doc`` (``--policy-file`` or the
    embedded policy). Review round 5: the same codes as the gate wherever the content has
    the information. A policy whose digest differs from the embedded one (the policy the
    export's gate applied) gives what the gate gives for decisions made under another
    policy: ``selection_policy_changed``, ``decision_policy_changed`` on every selected
    dimension and ``peer_coverage_missing`` on every peer dimension (the export does not
    record a policy per decision, so a decision made under that very policy is not told
    apart). With the same policy, every reason of the export's own gate (its ``known_gaps``)
    is a reason here too. What needs the study is listed in CLI-CONTRACT §16 (waivers,
    reservations, conflicts and arbitrations under another policy, the private context, the
    current taskset and the answers)."""
    import datetime as _dt
    from . import DIMENSIONS, evaluate as ev, taskset as bk
    reasons: list[dict] = []

    def add(code: str, dim: str | None = None) -> None:
        r = {'code': code, 'dimension': dim} if dim else {'code': code}
        if r not in reasons:
            reasons.append(r)
    limitations = set(pol.limitations(policy_doc)) | set(doc['limitations'])
    same = pol.digest(policy_doc) == doc['policy_digest']
    sel = doc['coverage_selection']
    gaps = [g for g in doc['known_gaps'] if isinstance(g, dict)]
    # The recorded status of each decision the export lists (its own session's); a decision
    # of another session is known only by the status shown (review round 6, R6-4).
    recorded = {x['decision_ref']: x['status'] for x in doc['decisions_summary']}
    status_reasons = {g.get('ref') for g in gaps
                      if g.get('kind') not in ev.STATUS_NEUTRAL_CODES + EXPORT_ONLY_GAPS
                      + ev.LIMITATION_GAPS + ('no_required_check',)}
    milestone = (sel or {}).get('milestone')
    applicable = policy_doc['mode'] == 'required' and (
        milestone is None or milestone in policy_doc['milestones'])
    if not sel:
        add('no_selection')
    else:
        if not same:
            add('selection_policy_changed')
        try:
            required = pol.author_dimensions(policy_doc, sel['profile'])
        except Exception:          # noqa: BLE001 - the profile is not in this policy
            required = None
            add('profile_unknown')
        if required is not None:
            critical = set(policy_doc['critical_dimensions'])
            actor = sel.get('actor_alias')
            rule = policy_doc['expiration_rule']
            now_ = today or _dt.datetime.now(_dt.timezone.utc).date().isoformat()
            expired = rule['kind'] == 'until' and now_ > rule['date']
            qualified = bk.qualified({'qualification': {'status': doc['provenance'].get(
                'taskset_qualification')}}) and 'taskset_not_qualified' not in doc['limitations']
            private_unknown = {g.get('ref') for g in gaps
                               if g.get('kind') in ev.LIMITATION_GAPS}
            dims = {d['id']: d for d in doc['dimensions']}
            for dim in required:
                d = dims.get(dim)
                if d is None or not d['human_review_ref']:
                    add('dimension_not_selected', dim)
                    continue
                if not same:
                    add('decision_policy_changed', dim)
                if not qualified:
                    add('taskset_not_qualified', dim)
                # The gate's rule: the selected decision is not recorded ``demonstrated``, or
                # it has a problem (another policy, a taskset not qualified). A dimension shown
                # ``needs_review`` or ``to_consolidate`` because of a reason that is not about
                # the decision (an open reservation, a conflict, a help or reviewer rule) is
                # not that (R6-4): the status shown counts only when no other reason of the
                # export's gate on the dimension explains it.
                status = recorded.get(d['human_review_ref'])
                if status is None:
                    explained = same and dim in status_reasons
                    status = 'demonstrated' if explained else d['status']
                if status != 'demonstrated' or not same or not qualified:
                    add('dimension_not_demonstrated', dim)
                if dim in critical and d['reviewer_alias'] == actor:
                    add('reviewer_not_distinct', dim)
                if ev.peer_rule(policy_doc, dim) == 'unaided_required' and \
                        d['assistance_summary'] != 'unaided':
                    add('assistance_not_admissible', dim)
                if d['evidence_availability'] != 'available':
                    if policy_doc['evidence_requirement'] == 'payloads_available':
                        add('evidence_unavailable', dim)
                    else:
                        limitations.add('evidence_not_reauditable')
                fresh = 'stale' if expired else d['freshness_at_export']
                if fresh == 'stale':
                    add('stale', dim)
                elif fresh == 'unknown':
                    if policy_doc['context_requirement'] == 'public_only' \
                            and dim in private_unknown:
                        limitations.add('private_context_unknown')
                    else:
                        add('freshness_unknown', dim)
            peers = {p['dimension_id']: p for p in doc['peer_coverage']}
            for dim in policy_doc['peer_required_dimensions']:
                if dim not in required:
                    continue
                p = peers.get(dim)
                if p is None or not same or ev.peer_gap(p, policy_doc):
                    add('peer_coverage_missing', dim)
    if same:
        # The reasons of the export's own gate under this very policy, with or without a
        # selection (an export without one records the reasons of the decisions it shows,
        # judged as a virtual selection; R6-4).
        for g in gaps:
            kind = g.get('kind')
            if kind in EXPORT_ONLY_GAPS or kind in ev.LIMITATION_GAPS \
                    or kind == 'no_required_check':
                continue
            add(kind, g.get('ref') if g.get('ref') in DIMENSIONS else None)
    # What the artefact itself establishes on the verified tree, or cannot without the study.
    for r in tree_reasons(doc, axes):
        add(r['code'])
    if policy_doc['context_requirement'] == 'complete' and \
            axes['private_context_verification'] != 'verified':
        add('private_context_unknown')
    if policy_doc['evidence_requirement'] == 'payloads_available' and \
            axes['evidence_availability'] != 'available':
        add('evidence_unavailable')
    if not applicable:
        return {'decision': 'not_applicable', 'reasons': reasons,
                'limitations': sorted(limitations), 'judgement': 'export'}
    return {'decision': 'blocked' if reasons else 'allowed', 'reasons': reasons,
            'limitations': sorted(limitations), 'judgement': 'export'}


def tree_reasons(doc: Mapping, axes: Mapping, *, judged_by_study: bool = False) -> list[dict]:
    """The reasons the artefact itself establishes on the verified tree: its privacy review
    is not approved, its public integrity is not valid, or the public sources of the
    verified tree (``--target``) are not the snapshot's (``public_sources_stale``,
    ``public_sources_unknown``). The standalone verifier applies them all; local mode too
    (review round 6, R6-2), except the public sources when ``judged_by_study``: the verified
    tree holds the very bytes the study's gate read, which it judged dimension by dimension
    (``stale`` on the dimensions whose dependency keys changed, which a waiver may cover)."""
    out = []
    if doc['privacy_review']['status'] != 'approved':
        out.append({'code': 'privacy_review_pending'})
    if axes['public_integrity'] != 'valid':
        out.append({'code': 'public_integrity_invalid'})
    if axes['public_source_freshness'] != 'current' and not judged_by_study:
        out.append({'code': f'public_sources_{axes["public_source_freshness"]}'})
    return out


def _same_bytes(tree: 'Tree', scope: Mapping | None, where: str | None,
                verified: Path) -> bool:
    """Whether every public source ``scope`` maps has, in the verified tree, the bytes it has
    in the working tree of ``where`` (what the study's gate read for that session). False
    when that repository or scope is unknown or gone, when nothing is mapped, or when a byte
    differs."""
    if scope is None or not where or not Path(where).is_dir():
        return False
    paths = [e['path'] for e in scope['entries'] if e['path']]
    if not paths:
        return False
    if tree.target == 'worktree' and Path(where).resolve() == verified:
        return True
    other = Tree(Path(where), 'worktree')

    def digest(data):
        return None if data is None else hashlib.sha256(data).hexdigest()
    try:
        return all(digest(tree.read(p)) == digest(other.read(p)) for p in paths) \
            and not other.problems
    except Exception:          # noqa: BLE001 - an unreadable place is not the same bytes
        return False


def judged_sessions(tree: 'Tree', sessions: list[Mapping], verified: Path) -> list[dict]:
    """One line per session whose decisions or context the study's gate judged (the
    exported session first, then every session of the gate's ``repositories``; review round
    7, R7-1): its repository, whether it is the verified one, whether the verified tree holds
    the bytes the gate read there for every public source of that session's snapshot scope
    (``same_bytes``), and the freshness of that scope on the verified tree
    (``tree_freshness``, ``unknown`` when the scope is unreadable). Local paths: this output
    is local, never public."""
    out = []
    for s in sessions:
        scope, where = s.get('scope'), s.get('repository')
        try:
            fresh = snap.public_freshness(scope, tree.read)['status'] if scope else 'unknown'
        except Exception:      # noqa: BLE001 - an unreadable tree is not current
            fresh = 'unknown'
        out.append({'session_id': s['session_id'], 'repository': where,
                    'is_verified_repository': None if not where
                    else Path(where).resolve() == verified,
                    'same_bytes': _same_bytes(tree, scope, where, verified),
                    'tree_freshness': fresh})
    return out


def local_tree_reasons(doc: Mapping, axes: Mapping, lines: list[Mapping]) -> tuple:
    """``(judged, extra, limitations)`` of local mode on the verified tree (review rounds 6
    and 7). ``judged``: the verified tree holds, for every session the study's gate judged,
    the bytes the gate read (``lines`` from :func:`judged_sessions`, none missing). Otherwise
    the export's own ``public_sources_stale|unknown`` is added (:func:`tree_reasons`), and
    each judged session's scope that is not ``current`` on the verified tree adds its own.
    A session read from another repository than the verified one adds
    ``verified_repository_not_the_session_one``: blocking when its scope or the export's is
    not ``current`` on the verified tree, a limitation otherwise. Nothing here relaxes the
    gate: the reasons are only added."""
    judged = bool(lines) and all(x['same_bytes'] for x in lines)
    extra = tree_reasons(doc, axes, judged_by_study=judged)
    lims: list = []

    def add(code):
        if {'code': code} not in extra:
            extra.append({'code': code})
    export_current = axes['public_source_freshness'] == 'current'
    for x in lines:
        if not judged and x['tree_freshness'] != 'current':
            add(f'public_sources_{x["tree_freshness"]}')
        if x['is_verified_repository'] is False:
            if x['tree_freshness'] != 'current' or not export_current:
                add(OTHER_REPOSITORY)
            elif OTHER_REPOSITORY not in lims:
                lims.append(OTHER_REPOSITORY)
    if {'code': OTHER_REPOSITORY} in extra and OTHER_REPOSITORY in lims:
        lims.remove(OTHER_REPOSITORY)
    return judged, extra, lims


def with_tree(result: Mapping | None, extra: list, limitations=()) -> dict | None:
    """The study's gate ``result`` (local mode) plus the reasons ``extra`` established on the
    verified tree: the gate's reasons are kept as they are (still ``check``'s), ``extra`` is
    appended, and an ``allowed`` or ``allowed_by_waiver`` decision becomes ``blocked`` when
    ``extra`` is not empty. A waiver covers what the study's gate judged, never bytes of the
    verified tree it did not read, so it is then not accepted (``waiver_not_accepted``, as the
    gate says of a waiver that does not cover every blocking reason). ``not_applicable`` stays
    (coaching: the reasons say what a required check would find)."""
    if result is None:
        return None
    out = dict(result)
    reasons = [dict(r) for r in result['reasons']]
    added = []
    for r in extra:
        if r not in reasons:
            reasons.append(dict(r))
            added.append(r['code'])
    lims = set(result['limitations']) | set(limitations)
    if added and result['decision'] in ('allowed', 'allowed_by_waiver'):
        if result['decision'] == 'allowed_by_waiver':
            reasons.append({'code': 'waiver_not_accepted',
                            'detail': 'the waiver covers what the study\'s gate judged, '
                                      'not the verified tree\'s reasons'})
            out['waiver_ref'] = None
            lims.discard('waived_requirements')
        out['decision'] = 'blocked'
    out['reasons'] = reasons
    out['limitations'] = sorted(lims)
    out['target_tree_reasons'] = added
    return out


# Reasons the standalone verifier cannot settle without the study (``unknown``, not a
# failure, for ``declared_conformity``).
UNKNOWABLE = ('private_context_unknown', 'evidence_unavailable')
# Local mode (R6-2): the verified repository is not the one the session's freshness is read
# from. It blocks when the verified tree's public sources are not the snapshot's; otherwise
# it is a limitation (the study's gate read another place, whose public sources the verified
# tree holds unchanged).
OTHER_REPOSITORY = 'verified_repository_not_the_session_one'


def verify(repo, target: str, *, policy_doc: Mapping | None = None,
           local: Callable[[Mapping], Mapping] | None = None,
           review_id: str | None = None) -> dict:
    """Verify every generation (or ``review_id``) in ``target`` of ``repo``.

    ``local(review, file_hashes)`` (local mode, the study is accessible) returns, for a
    review whose three files have ``file_hashes``, ``study_binding`` and, when bound, the
    axes the study settles: ``private_context_verification``, ``evidence_availability``,
    ``declared_conformity`` and ``gate_result`` from the study's own gate
    (:func:`service.gate`), ``exported_content_current``, ``verified_repository``,
    ``judged_sessions`` (internal: every session the gate judged with its repository and
    snapshot scope, R7-1) and ``judgement: 'study'``; :func:`with_tree` then adds the
    verified tree's reasons (:func:`local_tree_reasons`)."""
    tree = Tree(Path(repo), target)
    generations = tree.generations()
    if review_id is not None:
        generations = [g for g in generations if g == review_id] or [review_id]
    results = []
    for rid in generations:
        try:
            results.append(_verify_one(tree, rid, policy_doc, local))
        except Exception as exc:      # noqa: BLE001 - untrusted content: invalid, not a crash
            results.append({'review_id': rid, 'public_integrity': 'invalid',
                            'declared_conformity': 'unknown',
                            'public_source_freshness': 'unknown',
                            'private_context_verification': 'unknown',
                            'evidence_availability': 'unavailable',
                            'assurance': pol.SUPPORTED_ASSURANCE,
                            'unresolved_private_refs': [], 'limitations': [],
                            'problems': [f'malformed artefact ({exc.__class__.__name__})'],
                            'gate_result': None})
    if not tree.still_coherent():
        raise refuse('git_index_conflict', 'The index changed during the verification; the '
                     'result is not usable.', 'Run verify-export again when nothing stages.')
    out = {'schema': SCHEMA, 'ok': True, 'target': target,
           'commit': getattr(tree, 'commit', None), 'tree': getattr(tree, 'tree', None),
           'generations': results, 'problems': sorted(set(tree.problems))}
    out['public_integrity'] = 'valid' if results and all(
        r['public_integrity'] == 'valid' for r in results) and not tree.problems else 'invalid'
    return out


def _verify_one(tree: Tree, rid: str, policy_doc, local) -> dict:
    problems, limitations = [], ['assurance_human_declared',
                                 'no_proof_a_real_person_answered']
    base = f'{ex.EXPORT_DIR}/{rid}'
    axes = {'review_id': rid, 'public_integrity': 'invalid', 'declared_conformity': 'unknown',
            'public_source_freshness': 'unknown', 'private_context_verification': 'unknown',
            'evidence_availability': 'unavailable', 'assurance': pol.SUPPORTED_ASSURANCE,
            'unresolved_private_refs': [], 'limitations': limitations, 'problems': problems,
            'gate_result': None}
    if not rid.startswith('rv-') or not _safe(rid) or '/' in rid:
        problems.append('generation name is not a review id')
        return axes
    names = tree.files_in(rid)
    if sorted(names) != sorted(ex.FILES):
        problems.append('incomplete or extra files in the generation')
        return axes
    raw = {n: tree.read(f'{base}/{n}') for n in ex.FILES}
    if any(v is None for v in raw.values()):
        problems.append('unreadable file in the generation')
        return axes
    try:
        manifest = canonical.loads(raw[ex.MANIFEST_FILE])
        doc = canonical.loads(raw[ex.JSON_FILE])
    except canonical.CanonicalError as exc:
        problems.append(f'not canonical JSON: {exc.message}')
        return axes
    if not canonical.is_canonical(raw[ex.JSON_FILE]) or \
            not canonical.is_canonical(raw[ex.MANIFEST_FILE]):
        problems.append('JSON is not in canonical form')
    if not isinstance(manifest, dict) or not isinstance(manifest.get('files'), dict):
        problems.append('manifest is not an object with files')
        return axes
    if manifest.get('schema') != ex.MANIFEST_SCHEMA or manifest.get('review_id') != rid:
        problems.append('manifest identity')
    for name in (ex.JSON_FILE, ex.MD_FILE):
        f = (manifest.get('files') or {}).get(name) or {}
        if f.get('sha256') != canonical.sha256_hex(raw[name]) or f.get('bytes') != len(raw[name]):
            problems.append(f'manifest digest of {name}')
    shape = ex.validate_review(doc)
    problems += shape
    if shape:
        return axes
    if doc['review_id'] != rid or ex.review_id(ex.approval_projection(doc)) != rid:
        problems.append('review_id does not match the content')
    if ex.markdown(doc).encode('utf-8') != raw[ex.MD_FILE]:
        problems.append('Markdown is not the rendering of the JSON')
    if manifest.get('renderer_version') != doc['renderer_version']:
        problems.append('renderer version')
    if ex.files_of(doc)[ex.MANIFEST_FILE] != raw[ex.MANIFEST_FILE]:
        problems.append('manifest is not the one of the published JSON and Markdown')
    scope = doc['public_source_scope']
    if canonical.digest(scope) != doc['source_scope_digest']:
        problems.append('source_scope_digest does not match the public scope')
    if canonical.digest(doc['policy']) != doc['policy_digest']:
        problems.append('policy_digest')
    if doc['handover_content'] is not None and \
            canonical.digest(doc['handover_content']) != doc['handover_digest']:
        problems.append('handover_digest')
    digest = canonical.digest(ex.approval_projection(doc))
    for a in doc['privacy_review']['approvals']:
        if a['content_digest'] != digest:
            problems.append('an approval covers other content')
    # The people who must approve are recomputed from the published content, never read
    # from the list the export states about itself (spec §14, A29).
    need = set(ex.required_contributors(ex.approval_projection(doc)))
    if set(doc['privacy_review']['required_contributors']) != need:
        problems.append('required contributors do not match the published content')
    listed = [a['approver_alias'] for a in doc['privacy_review']['approvals']]
    approvers = set(listed)
    if len(listed) != len(approvers):
        problems.append('more than one approval by the same person')
    if not approvers <= need:
        problems.append('an approval by someone who is not a contributor')
    if doc['privacy_review']['status'] == 'approved' and not need <= approvers:
        problems.append('approved without every contributor')
    if doc['privacy_review']['status'] == 'pending' and need <= approvers:
        problems.append('privacy review status contradicts its approvals')
    if problems:
        return axes
    axes['public_integrity'] = 'valid'
    fresh = snap.public_freshness(scope, tree.read)
    if fresh['status'] == 'current' and any(
            isinstance(g, dict) and g.get('kind') == ex.SCOPE_GAP for g in doc['known_gaps']):
        # The scope does not cover a decision the export shows (R7-2): its sources were not
        # all checked, so they are never ``current``.
        fresh = {**fresh, 'status': 'unknown',
                 'missing': fresh['missing'] + ['a shown decision outside the public scope']}
    axes['public_source_freshness'] = fresh['status']
    axes['public_source_changes'] = fresh
    axes['unresolved_private_refs'] = [o['opaque_private_ref'] for o in scope['omitted_private']]
    if axes['unresolved_private_refs']:
        limitations.append('private_refs_not_resolvable_outside_the_study')
    if local is not None:
        # Local mode: the study's own gate is the judgement (review round 5), never a second
        # implementation; ``local`` gives it with the binding to a recorded export intent.
        axes.update(local(doc, {n: canonical.sha256_hex(raw[n]) for n in ex.FILES}))
        if axes.get('study_binding') == 'not_recorded':
            problems.append('this generation was not exported by the given study')
            axes['public_integrity'] = 'invalid'
            axes['gate_result'] = None
            return axes
        # The study's gate (unchanged: ``check``'s) plus what the artefact establishes on
        # the verified tree (R6-2): its public sources there when they are not the bytes the
        # study's gate read (the session's working tree, whose changes the gate judged per
        # dimension, waivable), its privacy review, and a verified repository that is not
        # the session's.
        # R7-1: every session whose decisions or context the gate judged is compared, each
        # with its own snapshot scope and repository working tree, not the exported one only.
        vr = axes.get('verified_repository') or {}
        sessions = axes.pop('judged_sessions', None) or []
        lines = judged_sessions(tree, sessions, tree.repo.resolve())
        if vr:
            vr['judged_sessions'] = lines
        judged, extra, lims = local_tree_reasons(doc, axes, lines)
        axes['public_sources_judged_by_study'] = judged
        limitations.extend(lims)
        axes['gate_result'] = with_tree(axes.get('gate_result'), extra, lims)
        if extra and axes.get('declared_conformity') == 'conforming':
            axes['declared_conformity'] = 'nonconforming'
        return axes
    limitations.append('no_local_study: private context and answers not checked')
    try:
        embedded = pol.validate(doc['policy'])
        conf = _gate_on_export(doc, embedded, axes)
        if not conf['reasons']:
            axes['declared_conformity'] = 'conforming'
        elif {r['code'] for r in conf['reasons']} <= set(UNKNOWABLE):
            axes['declared_conformity'] = 'unknown'      # needs the study, not a failure
        else:
            axes['declared_conformity'] = 'nonconforming'
    except Exception:          # noqa: BLE001
        axes['declared_conformity'] = 'unknown'
    if policy_doc is not None:
        axes['gate_result'] = _gate_on_export(doc, policy_doc, axes)
    return axes


def git_plan(repo, files: Mapping[str, bytes], sources: list[Mapping]) -> dict:
    """The exact artefact paths and hashes to stage, and the inconsistencies: a mapped
    source whose worktree and index bytes differ, or differ from the snapshot; staged
    changes outside the plan (reported, never unstaged)."""
    repo = Path(repo)
    head = git(repo, 'rev-parse', '--verify', '-q', 'HEAD').decode().strip() \
        if _has_head(repo) else None
    index = Tree(repo, 'index')
    work = Tree(repo, 'worktree')
    conflicts = []
    for s in sources:
        if s['path'] is None:
            continue
        w, i = work.read(s['path']), index.read(s['path'])
        ws = hashlib.sha256(w).hexdigest() if w is not None else None
        is_ = hashlib.sha256(i).hexdigest() if i is not None else None
        if ws != s['sha256'] or is_ != s['sha256']:
            conflicts.append({'path': s['path'], 'snapshot': s['sha256'], 'worktree': ws,
                              'index': is_})       # an untracked source is a conflict too
    staged = git(repo, 'diff', '--cached', '--no-renames', '--ignore-submodules=none',
                 '--name-only', '-z').split(b'\0') if head else \
        git(repo, 'ls-files', '-z').split(b'\0')
    # A path that is not UTF-8 is reported with its bytes escaped, never a crash.
    staged = sorted(p.decode('utf-8', 'backslashreplace') for p in staged if p)
    allowed = set(files) | {s['path'] for s in sources if s['path']}
    foreign = [p for p in staged if p not in allowed]
    return {'base_commit': head, 'artefacts': [{'path': p, 'sha256': hashlib.sha256(d)
                                                .hexdigest()} for p, d in sorted(files.items())],
            'source_conflicts': conflicts, 'staged_outside_plan': foreign,
            'index_identity': index.index_id}


def _has_head(repo: Path) -> bool:
    proc = subprocess.run(['git', '-C', str(repo), 'rev-parse', '--verify', '-q', 'HEAD'],
                          capture_output=True, env=git_env(), check=False)
    return proc.returncode == 0


def stage(repo, paths: list[str], expected_index: str, expected: Mapping | None = None) -> dict:
    """Stage exactly ``paths`` (artefacts of the plan), after checking the index has not
    changed since the plan; nothing already staged is removed."""
    repo = Path(repo)
    for p in paths:
        if not _safe(p) or not p.startswith(ex.EXPORT_DIR + '/'):
            raise refuse('path_outside_scope', 'Only the review artefacts are staged by this '
                         'helper.', 'Stage other files yourself.', path=p)
    before = Tree(repo, 'index')
    if before.index_id != expected_index:
        raise refuse('git_index_conflict', 'The index changed since git-plan; nothing was '
                     'staged.', 'Run git-plan again.')
    snapshot_before = dict(before._entries)
    git(repo, 'add', '--', *paths)
    after = Tree(repo, 'index')
    changed = sorted(p for p in set(after._entries) | set(snapshot_before)
                     if after._entries.get(p) != snapshot_before.get(p))
    foreign = [p for p in changed if p not in paths]
    differ = [p for p, sha in (expected or {}).items()
              if hashlib.sha256(after.read(p) or b'').hexdigest() != sha]
    if differ:
        raise refuse('git_index_conflict', 'The staged bytes differ from the exported ones (a '
                     'clean filter or a concurrent change?). The index was left as is.',
                     'Check your Git filters, then stage the files again yourself.',
                     paths=differ)
    return {'staged': sorted(paths), 'unexpected_index_changes': foreign,
            'index_identity': after.index_id}


def commit_receipt(repo, commit: str, expected: Mapping[str, str]) -> dict:
    """``{commit, tree, paths}`` once ``commit`` is identified and contains exactly the
    announced artefact bytes (``{path: sha256}`` of the export intent); ``git_index_conflict``
    otherwise. It never creates a commit."""
    tree = Tree(Path(repo), commit)
    for path, sha in expected.items():
        data = tree.read(path)
        if data is None or hashlib.sha256(data).hexdigest() != sha:
            raise refuse('git_index_conflict', 'The commit does not contain the exported bytes.',
                         'Inspect the commit before any new attempt; no commit is created '
                         'automatically.', path=path)
    return {'commit': tree.commit, 'tree': tree.tree, 'paths': dict(sorted(expected.items()))}


def posix(path: str) -> str:
    return PurePosixPath(path).as_posix()
