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
``gate_result`` for that explicit policy. A clean clone establishes public integrity; it
never concludes ``current`` on the private context nor resolves an opaque reference. Without
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
GIT_ENV = {'GIT_TERMINAL_PROMPT': '0', 'GIT_OPTIONAL_LOCKS': '0', 'LC_ALL': 'C'}


def git(repo: Path, *args: str, input_: bytes | None = None) -> bytes:
    """Run one Git plumbing command (no shell, no hook, no pager); bytes of stdout."""
    env = {**os.environ, **GIT_ENV}
    proc = subprocess.run(['git', '-C', str(repo), '-c', 'core.hooksPath=/dev/null',
                           '-c', 'core.fsmonitor=false', '--no-pager', *args], input=input_, capture_output=True, env=env,
                          timeout=120, check=False)
    if proc.returncode != 0:
        raise refuse('git_index_conflict', f'git {args[0]} failed.',
                     'Check that --repo is a Git repository and the target exists.',
                     command=args[0], stderr=proc.stderr.decode(errors='replace')[-300:])
    return proc.stdout


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
            base = self.repo / ex.EXPORT_DIR
            if not base.is_dir():
                return []
            for p in base.iterdir():
                if p.name.startswith('.rv-'):
                    self.problems.append(f'leftover temporary folder {p.name}')
                elif p.name.startswith('rv-'):
                    if p.is_symlink() or not p.is_dir():
                        self.problems.append(f'{p.name} is not a generation folder')
                    else:
                        names.add(p.name)
            return sorted(names)
        for path in self._entries:
            if path.startswith(prefix):
                rest = path[len(prefix):].split('/')
                if rest[0].startswith('.rv-'):
                    self.problems.append(f'leftover temporary folder {rest[0]}')
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


# The terms that decide what a review had to establish. The other fields (mode, milestones,
# what the verification requires of context and evidence, expiry, waivers, export, ids) are
# applied by the verifier itself, so a policy may differ on them.
REVIEW_TERMS = ('required_dimensions', 'responsibility_profiles', 'critical_dimensions',
                'peer_required_dimensions', 'minimum_assurance', 'assistance_rule',
                'team_coverage', 'role_policy')


def _review_terms(policy_doc: Mapping) -> str:
    return canonical.digest({k: policy_doc[k] for k in REVIEW_TERMS})


def _gate_on_export(doc: Mapping, policy_doc: Mapping, axes: Mapping,
                    today: str | None = None) -> dict:
    import datetime as _dt
    reasons = []
    if _review_terms(policy_doc) != _review_terms(doc['policy']):
        # The reviews were made under another policy (perhaps relaxed in the candidate):
        # they are not evidence for this one.
        reasons.append({'code': 'policy_differs'})
    rule = policy_doc['expiration_rule']
    today = today or _dt.datetime.now(_dt.timezone.utc).date().isoformat()
    if rule['kind'] == 'until' and today > rule['date']:
        reasons.append({'code': 'policy_expired'})
    critical = set(policy_doc['critical_dimensions'])
    actor = (doc['coverage_selection'] or {}).get('actor_alias')
    for d in doc['dimensions']:
        rule_ = policy_doc['assistance_rule']['critical' if d['id'] in critical else 'other']
        if rule_ == 'unaided_required' and d['assistance_summary'] != 'unaided':
            reasons.append({'code': 'assistance_not_admissible', 'dimension': d['id']})
        if d['id'] in critical and d['reviewer_alias'] and d['reviewer_alias'] == actor:
            reasons.append({'code': 'reviewer_not_distinct', 'dimension': d['id']})
    try:
        required = pol.author_dimensions(policy_doc, doc['coverage_selection']['profile']) \
            if doc['coverage_selection'] else []
    except Exception:          # noqa: BLE001
        required = []
        reasons.append({'code': 'profile_unknown'})
    if not doc['coverage_selection']:
        reasons.append({'code': 'no_selection'})
    dims = {d['id']: d for d in doc['dimensions']}
    for dim in required:
        d = dims.get(dim)
        if d is None or d['status'] != 'demonstrated':
            reasons.append({'code': 'dimension_not_demonstrated', 'dimension': dim})
        elif d['freshness_at_export'] != 'current':
            reasons.append({'code': 'dimension_not_current', 'dimension': dim})
    peers = {p['dimension_id']: p for p in doc['peer_coverage']}
    for dim in policy_doc['peer_required_dimensions']:
        if dim in required:
            p = peers.get(dim)
            if p is None or p['status'] != 'current' or \
                    p['people'] < policy_doc['team_coverage']['minimum_people']:
                reasons.append({'code': 'peer_coverage_missing', 'dimension': dim})
    if doc['privacy_review']['status'] != 'approved':
        reasons.append({'code': 'privacy_review_pending'})
    if axes['public_integrity'] != 'valid':
        reasons.append({'code': 'public_integrity_invalid'})
    if axes['public_source_freshness'] != 'current':
        reasons.append({'code': f'public_sources_{axes["public_source_freshness"]}'})
    if policy_doc['context_requirement'] == 'complete' and \
            axes['private_context_verification'] != 'verified':
        reasons.append({'code': 'private_context_unknown'})
    if policy_doc['evidence_requirement'] == 'payloads_available' and \
            axes['evidence_availability'] != 'available':
        reasons.append({'code': 'evidence_unavailable'})
    limitations = sorted(set(pol.limitations(policy_doc)) | set(doc['limitations']))
    if policy_doc['mode'] != 'required':
        return {'decision': 'not_applicable', 'reasons': reasons, 'limitations': limitations}
    return {'decision': 'blocked' if reasons else 'allowed', 'reasons': reasons,
            'limitations': limitations}


def verify(repo, target: str, *, policy_doc: Mapping | None = None,
           local: Callable[[Mapping], Mapping] | None = None,
           review_id: str | None = None) -> dict:
    """Verify every generation (or ``review_id``) in ``target`` of ``repo``.

    ``local(review)`` (local mode, the study is accessible) returns
    ``{'private_context_verification', 'evidence_availability'}`` for a review."""
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
    approvers = {a['approver_alias'] for a in doc['privacy_review']['approvals']}
    if doc['privacy_review']['status'] == 'approved' and not need <= approvers:
        problems.append('approved without every contributor')
    if doc['privacy_review']['status'] == 'pending' and need <= approvers:
        problems.append('privacy review status contradicts its approvals')
    if problems:
        return axes
    axes['public_integrity'] = 'valid'
    fresh = snap.public_freshness(scope, tree.read)
    axes['public_source_freshness'] = fresh['status']
    axes['public_source_changes'] = fresh
    axes['unresolved_private_refs'] = [o['opaque_private_ref'] for o in scope['omitted_private']]
    if axes['unresolved_private_refs']:
        limitations.append('private_refs_not_resolvable_outside_the_study')
    if local is not None:
        axes.update(local(doc))
        if axes.get('study_binding') == 'not_recorded':
            problems.append('this generation was not exported by the given study')
            axes['public_integrity'] = 'invalid'
            return axes
    else:
        limitations.append('no_local_study: private context and answers not checked')
    try:
        embedded = pol.validate(doc['policy'])
        conf = _gate_on_export(doc, embedded, axes)
        unknowable = {'private_context_unknown', 'evidence_unavailable'}
        if not conf['reasons']:
            axes['declared_conformity'] = 'conforming'
        elif local is None and {r['code'] for r in conf['reasons']} <= unknowable:
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
    staged = git(repo, 'diff', '--cached', '--no-renames', '--name-only', '-z').split(b'\0') \
        if head else \
        git(repo, 'ls-files', '-z').split(b'\0')
    staged = sorted(p.decode() for p in staged if p)
    allowed = set(files) | {s['path'] for s in sources if s['path']}
    foreign = [p for p in staged if p not in allowed]
    return {'base_commit': head, 'artefacts': [{'path': p, 'sha256': hashlib.sha256(d)
                                                .hexdigest()} for p, d in sorted(files.items())],
            'source_conflicts': conflicts, 'staged_outside_plan': foreign,
            'index_identity': index.index_id}


def _has_head(repo: Path) -> bool:
    proc = subprocess.run(['git', '-C', str(repo), 'rev-parse', '--verify', '-q', 'HEAD'],
                          capture_output=True, env={**os.environ, **GIT_ENV}, check=False)
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
