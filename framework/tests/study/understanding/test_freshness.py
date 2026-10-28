"""A09, A10, A11, A15 (digests): freshness by dependency, no circularity, no ML effect."""
from __future__ import annotations

import pytest

import flowkit as fk
import ukit
from mlkit.study.understanding import canonical, snapshot as snap


@pytest.fixture
def u(tmp_path):
    u = ukit.U(tmp_path)
    ukit.full_flow(u)
    return u


def dims(u):
    return {d['dimension_id']: d for d in u.call('status')['sessions'][0]['dimensions']}


def test_relevant_source_change_stales_only_linked_dimensions(u):
    """A09: a code change stales D6 (code) but not D3 (protocol); a transformation change
    stales D5; a security rule change stales D8."""
    assert {k: v['freshness'] for k, v in dims(u).items()} == {
        k: 'current' for k in dims(u)}
    (u.repo / 'src/pipeline.py').write_text('def predict(row):\n    return 1\n')
    d = dims(u)
    assert d['D6']['freshness'] == 'stale' and 'repo:src/pipeline.py' in d['D6']['changed']
    assert d['D3']['freshness'] == 'current' and d['D5']['freshness'] == 'current'
    (u.repo / 'SECURITY.md').write_text('Rules changed.\n')
    assert dims(u)['D8']['freshness'] == 'stale'


def test_a_new_scientific_decision_stales_its_dimension(u):
    """A09: changing the protocol (a decision) stales the dimensions that depend on it."""
    before = dims(u)
    assert before['D3']['freshness'] == 'current'
    u.flow.decide('split', {'method': 'stratified_random', 'validation_fraction': 0.25,
                            'seed': 7})
    assert dims(u)['D3']['freshness'] == 'stale'


def test_missing_source_is_unknown_not_current(u):
    """A10: a source that disappears is unknown, and blocks a complete policy."""
    (u.repo / 'SECURITY.md').unlink()
    d = dims(u)
    assert d['D8']['freshness'] == 'unknown'
    gate = u.call('check', '--milestone', 'handoff')['gate']
    assert gate['decision'] == 'blocked'
    assert any(r['code'] == 'freshness_unknown' for r in gate['reasons'])


def test_review_activity_never_changes_the_source_digests(u):
    """A15, A10: same sources plus more review give the same source digests; capture and
    render times and revisions are outside them."""
    state = u.state()
    ext = state['understanding']
    session = next(iter(ext['sessions'].values()))
    first = session['source_scope_digest'], session['local_snapshot_digest']
    sid = session['session_id']
    ukit.approve_all(u, sid)
    u.m('export', 'write', '--session', sid, '--repo', u.repo)
    from mlkit.study.understanding import service as sv
    plan = sv.session_plan(sv.open_store(u.study), session)
    again = snap.capture_context(u.state(), policy_digest=session['policy_digest'],
                                 taskset_doc=sv.current_taskset(u.state()), repo=u.repo,
                                 sources=plan['sources'], salt=ext['salt'])
    assert (again['source_scope_digest'], again['local_snapshot_digest']) == first
    for k in ('capture_revision', 'captured_at', 'revision'):
        assert k not in canonical.dumps(again['local']).decode()


def test_the_review_changes_no_scientific_record(tmp_path):
    """A11: no decision, partition, exposure record, registry entry or result changes."""
    u = ukit.U(tmp_path)
    before = u.state()
    exposure = fk.exposure_records(u.study)
    registry = fk.registry_entries(u.study)
    ukit.full_flow(u)
    after = u.state()
    for key in ('decisions', 'partition', 'current', 'stale', 'prior_exposure', 'proposals'):
        assert after.get(key) == before.get(key), key
    assert fk.exposure_records(u.study) == exposure
    assert fk.registry_entries(u.study) == registry


def test_public_scope_has_no_private_value(u):
    """The public projection lists only repository entries and contracts; private entries
    are opaque refs, never a digest of a private value."""
    ext = u.ext()
    session = next(iter(ext['sessions'].values()))
    from mlkit.study.understanding import service as sv
    doc = sv.session_snapshot(sv.open_store(u.study), session)
    public = doc['public']
    private_shas = {e['sha256'] for e in doc['local']['entries'] if e['origin'] in
                    ('study', 'case', 'engine')}
    text = canonical.dumps(public).decode()
    assert not any(sha in text for sha in private_shas)
    assert all(o['opaque_private_ref'].startswith('opq-') for o in public['omitted_private'])
    assert {e['path'] for e in public['entries'] if e['path']} == {
        'src/pipeline.py', 'src/transforms.py', 'SECURITY.md'}


@pytest.mark.parametrize('path', ['../outside.py', '/etc/passwd', 'a//b', './x', 'a\\b'])
def test_source_paths_are_confined(tmp_path, path):
    with pytest.raises(Exception) as e:
        snap.safe_relative(path)
    assert e.value.code == 'path_outside_scope'


def test_symlink_leaving_the_repository_is_refused(tmp_path):
    repo = tmp_path / 'r'
    repo.mkdir()
    (tmp_path / 'secret').write_text('x')
    (repo / 'link.py').symlink_to(tmp_path / 'secret')
    with pytest.raises(Exception) as e:
        snap.read_repo_file(repo, 'link.py')
    assert e.value.code == 'path_outside_scope'
