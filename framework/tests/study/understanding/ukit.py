"""Helpers of the understanding review tests: a synthetic study, a target Git repository,
policies, and a driver of ``hypotrail understanding`` through ``cli.run``.

The bank copied next to the synthetic case is ``framework/tests/fixtures/understanding``:
its qualification is a **simulated** review. Human decisions written by these helpers carry
``simulated: true`` and a declaration naming them as test fixtures.
"""
from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import flowkit as fk
from mlkit.study import case as c, cli, read

FIXTURES = fk.TESTS / 'fixtures' / 'understanding'


def _probe_temp_filesystem() -> tuple[bool, bool]:
    """Whether the temporary folder's filesystem keeps two names that differ only in case
    (Linux: yes; macOS and Windows by default: no), and accepts a file name that is not
    UTF-8 (APFS and NTFS refuse one). Some tests build such a tree on disk."""
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / 'a').write_bytes(b'')
        case_sensitive = not (Path(d) / 'A').exists()
        try:
            with open(os.path.join(os.fsencode(d), b'n-\xe9'), 'wb'):
                pass
            non_utf8 = True
        except (OSError, ValueError):
            non_utf8 = False
    return case_sensitive, non_utf8


CASE_SENSITIVE_FS, NON_UTF8_NAMES = _probe_temp_filesystem()


def rmtree(path) -> None:
    """``shutil.rmtree`` that also removes read-only files: Git writes its objects read-only,
    and Windows refuses to delete a read-only file."""
    import stat

    def clear(function, target, _exc):
        os.chmod(target, stat.S_IWRITE)
        function(target)
    shutil.rmtree(path, onexc=clear)
NEEDS_CASE_SENSITIVE = ('builds two names that differ only in case on disk: needs a '
                        'case-sensitive filesystem (not macOS or Windows by default)')
SIM = {'source': 'reviewer_file',
       'statement': 'SIMULATED test fixture: no person made this review.'}

POLICY = {
    'schema': 'hypotrail.understanding-policy/1', 'policy_id': 'team-default', 'version': 1,
    'mode': 'coaching', 'milestones': ['handoff'],
    'required_dimensions': ['D1', 'D2', 'D3', 'D4', 'D5', 'D6', 'D7', 'D8'],
    'responsibility_profiles': {'analyst': ['D1', 'D2', 'D3', 'D4', 'D7'],
                                'pipeline': ['D2', 'D3', 'D5', 'D6', 'D8']},
    'critical_dimensions': ['D2', 'D3'], 'peer_required_dimensions': ['D2'],
    'minimum_assurance': 'human_declared',
    'assistance_rule': {'critical': 'unaided_required', 'other': 'aided_allowed'},
    'expiration_rule': {'kind': 'none'}, 'evidence_retention': 'durable',
    'evidence_requirement': 'payloads_available', 'context_requirement': 'complete',
    'export_policy': {'include_excerpts': False, 'include_contacts': False,
                      'external_sources': 'allowed'},
    'exemptions_policy': {'waivers_allowed': False},
    'team_coverage': {'minimum_people': 2}, 'role_policy': {'arbiters': 'any_declared'}}

ASSIST = {'resources_used': ['repository'], 'ai_assistance_declared': False,
          'independence_claim': 'I wrote this answer myself.', 'limitations': []}
SOURCES = [{'logical_key': 'repo:src/pipeline.py', 'path': 'src/pipeline.py', 'role': 'code'},
           {'logical_key': 'repo:src/transforms.py', 'path': 'src/transforms.py',
            'role': 'transform_recipe'},
           {'logical_key': 'repo:SECURITY.md', 'path': 'SECURITY.md', 'role': 'security_rule'}]


def policy(**changes) -> dict:
    doc = copy.deepcopy(POLICY)
    doc.update(changes)
    return doc


def git(repo, *args, check=True) -> str:
    env = {**os.environ, 'GIT_AUTHOR_NAME': 'Test', 'GIT_AUTHOR_EMAIL': 'test@example.invalid',
           'GIT_COMMITTER_NAME': 'Test', 'GIT_COMMITTER_EMAIL': 'test@example.invalid'}
    p = subprocess.run(['git', '-C', str(repo), *args], capture_output=True, text=True,
                       env=env, check=False)
    if check:
        assert p.returncode == 0, p.stderr
    return p.stdout.strip()


def make_repo(root: Path) -> Path:
    """A project whose sources are LF bytes on every system (``newline``: Windows would write
    CRLF, and a test of Git's end-of-line conversion would then have nothing to convert)."""
    repo = root / 'project'
    (repo / 'src').mkdir(parents=True)
    for path, text in (('src/pipeline.py', 'def predict(row):\n    return score(select(row))\n'),
                       ('src/transforms.py', 'def fit_imputer(train):\n    return train.mean()\n'),
                       ('SECURITY.md', 'Every new dependency is reviewed before adoption.\n'),
                       ('README.md', 'Project.\n')):
        (repo / path).write_text(text, newline='\n')
    git(repo, 'init', '-q', '-b', 'main')
    # No automatic maintenance: Git detaches it after a commit (2.47+), and the tests copy
    # the repository while it may still hold .git/objects/maintenance.lock.
    git(repo, 'config', 'maintenance.auto', 'false')
    git(repo, 'config', 'gc.auto', '0')
    git(repo, 'add', '--', 'src/pipeline.py', 'src/transforms.py', 'SECURITY.md', 'README.md')
    git(repo, 'commit', '-q', '-m', 'project sources')
    return repo


def make_case_dir(root: Path, task='binary') -> Path:
    case_dir = fk.make_case(root / f'case-{task}', n_rows=400, task=task)['case'].parent
    case_id = c.load_case(case_dir, verify_data=False).document['id']
    text = (FIXTURES / f'bank-{task}.yaml').read_text().replace('__CASE_ID__', case_id)
    (case_dir / 'understanding.yaml').write_text(text)
    return case_dir


class U:
    """A study with the review, driven through ``cli.run`` like the real CLI."""

    def __init__(self, root: Path, task='binary', case_dir=None, repo=True, pauses=True):
        self.root = Path(root)
        self.case_dir = case_dir or make_case_dir(self.root, task)
        self.flow = fk.Flow(self.root / 'study', self.case_dir, prefix='u')
        self.flow.init()
        if pauses:
            self.flow.pauses()
        self.repo = make_repo(self.root) if repo else None
        self.n = 0

    @property
    def study(self) -> Path:
        return self.flow.study

    def file(self, name: str, content) -> Path:
        path = self.root / 'inputs' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, str):
            path.write_text(content, encoding='utf-8')
        else:
            path.write_text(json.dumps(content), encoding='utf-8')
        return path

    def rev(self) -> int:
        return read.load_state(self.study)['revision']

    def rid(self) -> str:
        self.n += 1
        return f'ur{self.n}'

    def call(self, *args, expect=0, mutation=False, request_id=None, revision=None):
        argv = ['understanding', *[str(a) for a in args], '--study', str(self.study)]
        if mutation:
            argv += ['--request-id', request_id or self.rid(), '--expected-revision',
                     str(self.rev() if revision is None else revision)]
        out = cli.run(argv)
        json.dumps(out.payload)
        if expect is not None:
            assert out.exit_code == expect, out.payload
        return out.payload

    def m(self, *args, **kw):
        return self.call(*args, mutation=True, **kw)

    def state(self) -> dict:
        return read.load_state(self.study)

    def ext(self) -> dict:
        return self.state()['understanding']

    # high-level steps

    def set_policy(self, doc=None, **kw):
        return self.m('policy', 'set', '--file', self.file('policy.json', doc or POLICY),
                      '--author', 'lead', '--reason', 'team agreement', **kw)

    def start(self, actor='alice', profile='pipeline', sources=SOURCES, **kw):
        args = ['plan', '--profile', profile, '--milestone', 'handoff', '--actor', actor,
                '--write-plan', self.root / 'inputs' / 'plan.json']
        if self.repo is not None:
            args += ['--repo', self.repo, '--sources-file', self.file('sources.json', sources)]
        (self.root / 'inputs').mkdir(exist_ok=True)
        plan = self.call(*args)
        out = self.m('start', '--plan-file', self.root / 'inputs' / 'plan.json', **kw)
        return plan, out

    def submit(self, sid, task_id, text='My own answer, with the reasons.', assist=None,
               cite=(), **kw):
        args = ['submit', '--session', sid, '--task', task_id, '--response-file',
                self.file(f'answer-{self.n}.txt', text), '--assistance-file',
                self.file(f'assist-{self.n}.json', assist or ASSIST)]
        for r in cite:
            args += ['--cite', r]
        return self.m(*args, **kw)

    def bank(self) -> dict:
        import yaml
        return yaml.safe_load((self.case_dir / 'understanding.yaml').read_text())

    def bank_task(self, task_id) -> dict:
        return next(t for t in self.bank()['tasks'] if t['task_id'] == task_id)

    def rubric(self, dim) -> dict:
        return next(r for r in self.bank()['rubrics'] if r['dimension_id'] == dim)

    def task_for(self, dim, variant='a', kind=None) -> str:
        return next(t['task_id'] for t in self.bank()['tasks'] if t['dimension_ids'][0] == dim
                    and t['variant_id'] == variant and (kind is None or t['kind'] == kind))

    def decision(self, dim, attempts, status='demonstrated', actor='alice', result=None,
                 **extra) -> dict:
        r = self.rubric(dim)
        res = {c['criterion_id']: (result or ('met' if status == 'demonstrated' else
                                              'not_met' if status == 'to_consolidate'
                                              else 'uncertain'))
               for c in r['criteria']}
        if status == 'demonstrated':
            res = {k: 'met' for k in res}
        d = {'dimension_id': dim, 'reviewed_actor_id': actor, 'attempt_ids': list(attempts),
             'criterion_results': [{'criterion_id': k, 'result': v, 'note': None}
                                   for k, v in res.items()],
             'status': status, 'rationale': f'Simulated reviewer rationale for {dim}.',
             'evidence_refs': [], 'supersedes_ids': [], 'resolves_reservation_ids': [],
             'proposal_ref': None, 'correction_of_review_error': False}
        d.update(extra)
        return d

    def review(self, sid, decisions, reviewer='bob', simulated=True, **kw):
        doc = {'reviewer_declared_id': reviewer, 'declaration': SIM, 'simulated': simulated,
               'decisions': decisions}
        return self.m('review', '--session', sid, '--file',
                      self.file(f'review-{self.n}.json', doc), **kw)


HANDOVER = {
    'purpose': 'Rank the members to remind first when the desk can call only some of them.',
    'decisions_with_reasons': ['Inputs known before the reminder only, because the desk '
                               'acts before the outcome.'],
    'result_interpretation': 'A development comparison only; the final test is sealed.',
    'limits': ['Retrospective data of one network.'],
    'source_refs': ['src/transforms.py', 'src/pipeline.py'],
    'environment_and_reproduction': 'uv sync, then run the pipeline on a copy of the data.',
    'change_locations': ['src/transforms.py for the imputation'],
    'safety_rules': ['SECURITY.md applies to every new dependency.'],
    'next_actions': ['Open the final test once the rule is fixed.']}


def full_flow(u: U, *, required=True, peer=True):
    """A completed session for the analyst profile with every dimension demonstrated by a
    simulated reviewer, a reviewed handover, and a selection; returns the session id."""
    u.set_policy(policy(mode='required') if required else POLICY)
    plan, out = u.start()
    sid = out['result']['session_id']
    dims = out['result']['dimensions']
    tasks = {t: u.bank_task(t) for t in plan['plan']['task_ids']}
    decisions = []
    for dim in dims:
        tid = next(t for t, spec in tasks.items() if spec['dimension_ids'][0] == dim)
        r = u.submit(sid, tid, f'My own answer for {dim}, with the reasons.')
        decisions.append(u.decision(dim, [r['result']['attempt_id']],
                                    evidence_refs=['src/pipeline.py']))
    u.review(sid, decisions)
    u.m('handover', 'set', '--session', sid, '--file', u.file('handover.json', HANDOVER))
    transfer_dm = {}
    if peer:
        task = next(t['task_id'] for t in u.bank()['tasks'] if t['kind'] == 'transfer')
        t = u.m('transfer', 'start', '--session', sid, '--peer', 'carol', '--task', task)
        tid = t['result']['transfer_id']
        u.m('transfer', 'submit', '--transfer', tid, '--response-file',
            u.file('peer.txt', 'The imputer in src/transforms.py learns a mean.'),
            '--assistance-file', u.file('peer-assist.json', ASSIST), '--evidence-file',
            u.file('peer-evidence.json', {'evidence_refs': ['src/transforms.py'],
                                          'difficulty_or_blockers': []}))
        rv = u.m('transfer', 'review', '--transfer', tid, '--file', u.file(
            'peer-review.json', {'reviewer_declared_id': 'alice', 'declaration': SIM,
                                 'simulated': True, 'dimension_ids': ['D2'],
                                 'status': 'demonstrated',
                                 'rationale': 'Simulated: the peer found the imputer.'}))
        transfer_dm = {'D2': rv['result']['decision_id']}
    u.m('close', '--session', sid, '--to', 'completed', '--reason', 'review done')
    ext = u.ext()
    dm = {d['dimension_id']: d['decision_id'] for d in ext['decisions'].values()
          if d['kind'] == 'attempt' and d['session_id'] == sid}
    u.m('select', '--file', u.file('selection.json', {
        'milestone': 'handoff', 'actor_scope': {'actor_declared_id': 'alice',
                                                'profile': 'pipeline'},
        'dimension_decision_map': dm, 'transfer_decision_map': transfer_dm,
        'reservation_resolution_refs': []}))
    return sid


def approve_all(u: U, sid: str) -> dict:
    prev = u.call('export', 'preview', '--session', sid, '--repo', u.repo)
    for who in prev['required_contributors']:
        u.m('export', 'approve', '--session', sid, '--contributor', who, '--content-digest',
            prev['content_digest'])
    return prev


def copy_tree(src: Path, dst: Path) -> Path:
    shutil.copytree(src, dst)
    return dst
