"""Area C probes: a study without the extension exports the same handoff bytes as the
engine before the review existed (410a67e~1), and the review leaves scientific state
untouched."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import advkit as rkit  # noqa: E402,F401
from advkit import U, ukit, custom_flow  # noqa: E402
import flowkit as fk  # noqa: E402

import pytest  # noqa: E402

PY = sys.executable
REPO = Path(__file__).resolve().parents[4]
BEFORE_REVIEW = '410a67e~1'        # the engine before the understanding review existed
OLD = None


@pytest.fixture(scope='module', autouse=True)
def old_engine(tmp_path_factory):
    """The engine of BEFORE_REVIEW, extracted from Git (skipped in a shallow clone)."""
    global OLD
    root = tmp_path_factory.mktemp('old')
    archive = subprocess.run(['git', '-C', str(REPO), 'archive', BEFORE_REVIEW, 'framework'],
                             capture_output=True)
    if archive.returncode != 0:
        pytest.skip(f'{BEFORE_REVIEW} is not in this clone')
    subprocess.run(['tar', '-x', '-C', str(root)], input=archive.stdout, check=True)
    OLD = root / 'framework'
    yield OLD


def export_with(study, out, old: bool, extra_env=None):
    env = dict(os.environ)
    if old:
        env['PYTHONPATH'] = str(OLD)
    env.update(extra_env or {})
    p = subprocess.run([PY, '-c', 'import sys,json; from mlkit.study import cli; '
                        'o = cli.run(sys.argv[1:]); print(json.dumps(o.payload)); '
                        'import mlkit; print(mlkit.__file__, file=sys.stderr)',
                        'export', 'handoff', '--study', str(study), '--out', str(out)],
                       capture_output=True, text=True, env=env, cwd='/tmp')
    assert p.returncode == 0, p.stderr[-3000:]
    assert (str(OLD) in p.stderr) == old, p.stderr[-500:]
    return json.loads(p.stdout)


def tree(d: Path) -> dict:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(d.iterdir())}


def run_pair(u, tmp_path, label):
    study = u.study
    backup = tmp_path / f'{label}-backup'
    shutil.copytree(study, backup, symlinks=True)
    new = export_with(study, tmp_path / f'{label}-new', old=False)
    shutil.rmtree(study)
    shutil.copytree(backup, study, symlinks=True)
    old = export_with(study, tmp_path / f'{label}-old', old=True)
    a, b = tree(tmp_path / f'{label}-new'), tree(tmp_path / f'{label}-old')
    if a != b:
        for name in a:
            if a[name] != b.get(name):
                x = (tmp_path / f'{label}-new' / name).read_text(errors='replace').splitlines()
                y = (tmp_path / f'{label}-old' / name).read_text(errors='replace').splitlines()
                import difflib
                print(name, '\n'.join(list(difflib.unified_diff(y, x, lineterm=''))[:40]))
    new.pop('out'), old.pop('out')
    return a, b, new, old


def test_no_extension_same_handoff_bytes_as_before(tmp_path):
    u = U(tmp_path, repo=False)
    assert 'understanding' not in u.state()
    # The reference engine predates the structural-first plan generation (owner session
    # 2026-10-26, L5), whose ``exploration_order`` key it refuses as outside its schema (an
    # older engine refusing a newer state is correct). Both engines therefore export a study
    # of the previous generation, as ``init`` wrote it before L5 (``flowkit``).
    fk.previous_generation(u.study)
    assert 'exploration_order' not in u.state()
    a, b, new, old = run_pair(u, tmp_path, 'plain')
    assert new == old
    assert a == b


def test_review_never_changes_scientific_state(tmp_path):
    u = U(tmp_path)
    before = u.state()
    reg = u.study / '.hypotrail'
    def files():
        return {str(p.relative_to(reg)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in reg.rglob('*') if p.is_file() and 'blobs' not in p.parts
                and p.name not in ('state.json', 'revisions.jsonl', 'events.jsonl')
                and 'lock' not in p.name}
    fb = files()
    custom_flow(u, ukit.policy(mode='required'))
    after = u.state()
    skip = {'understanding', 'revision', 'receipts', 'updated'}
    for k in set(before) | set(after):
        if k in skip:
            continue
        assert before.get(k) == after.get(k), k
    fa = files()
    changed = {k for k in fa if fb.get(k) != fa[k]}
    print('changed non-state files:', sorted(changed))
    # revisions log: every new entry is an understanding action
    rows = [json.loads(l) for l in (reg / 'revisions.jsonl').read_text().splitlines()]
    new_rows = [r for r in rows if r.get('revision', 0) > before['revision']]
    actions = {r.get('action') or (r.get('change') or {}).get('action') for r in new_rows}
    print(actions)
    assert all(a and a.startswith('understanding.') for a in actions)
    # no answer text in logs
    text = (reg / 'revisions.jsonl').read_text() + (reg / 'events.jsonl').read_text()
    assert 'My own answer' not in text and 'imputer in src' not in text
