"""Round-8 review probes (understanding, areas C and D), kept as regression tests:
F1 git-plan checks the generation's whole declared scope; F2 an exported session that maps
no source does not block local verification of the bytes check judged."""
import json
from advkit import U, ukit, gate, custom_flow
from mlkit.study import cli
from mlkit.study.understanding import export as ex

REQ = ukit.policy(mode='required')
NARROW = [s for s in ukit.SOURCES if s['path'] == 'src/pipeline.py']
DIRTY = 'def fit_imputer(train):\n    return train.median()\n'


def _verify(u, target, study=True, policy=None):
    args = ['understanding', 'verify-export', '--repo', str(u.repo), '--target', target]
    if study:
        args += ['--study', str(u.study)]
    if policy is not None:
        args += ['--policy-file', str(u.file(f'vp-{u.n}.json', policy))]
        u.n += 1
    return cli.run(args).payload


def test_gitplan_checks_the_shown_sessions_sources(tmp_path):
    u = U(tmp_path)
    # Alice reviews with an uncommitted imputer change in her working tree (S1 captures it).
    (u.repo / 'src/transforms.py').write_text(DIRTY)
    custom_flow(u, REQ)
    _, out = u.start(sources=NARROW)
    s2 = out['result']['session_id']
    assert gate(u)['decision'] == 'allowed'
    ukit.approve_all(u, s2)
    w = u.m('export', 'write', '--session', s2, '--repo', u.repo)
    doc = json.loads((u.repo / ex.EXPORT_DIR / w['review_id'] / ex.JSON_FILE).read_text())
    assert 'src/transforms.py' in [e['path'] for e in doc['public_source_scope']['entries']]
    plan = u.call('git-plan', '--session', s2, '--repo', u.repo)
    print('PLAN', json.dumps({k: plan[k] for k in ('consistent', 'source_conflicts',
                                                   'staged_outside_plan')}))
    # Fixed (round 8, F1): git-plan checks the generation's whole declared scope, including
    # the sources of the session whose decisions it shows: the conflict is reported and
    # git-stage refuses, instead of staging what verification then blocks.
    assert plan['consistent'] is False
    assert 'src/transforms.py' in [c['path'] for c in plan['source_conflicts']]
    refused = u.call('git-stage', '--session', s2, '--repo', u.repo, '--index-identity',
                     plan['index_identity'], expect=2)
    assert refused['error']['code'] == 'git_index_conflict'


def test_gitplan_reports_own_source(tmp_path):
    """Control: the same situation on a source the exported session maps is a conflict."""
    u = U(tmp_path)
    (u.repo / 'src/transforms.py').write_text(DIRTY)
    s1 = custom_flow(u, REQ)
    ukit.approve_all(u, s1)
    u.m('export', 'write', '--session', s1, '--repo', u.repo)
    plan = u.call('git-plan', '--session', s1, '--repo', u.repo)
    print('PLAN-OWN', plan['consistent'], plan['source_conflicts'])
    assert plan['consistent'] is False

def test_empty_scope_second_session(tmp_path):
    u = U(tmp_path)
    custom_flow(u, REQ)
    plan, out = u.start(sources=[], expect=None)
    print('START', json.dumps(out)[:400])
    s2 = out['result']['session_id']
    g = gate(u)
    print('CHECK', g['decision'], [r['code'] for r in g['reasons']])
    ukit.approve_all(u, s2)
    w = u.m('export', 'write', '--session', s2, '--repo', u.repo)
    doc = json.loads((u.repo / ex.EXPORT_DIR / w['review_id'] / ex.JSON_FILE).read_text())
    print('SCOPE', [e['path'] for e in doc['public_source_scope']['entries']])
    print('GAPS', doc['known_gaps'])
    gen = _verify(u, 'worktree')['generations'][0]
    print('LOCAL', gen['public_source_freshness'], gen['public_sources_judged_by_study'],
          gen['gate_result']['decision'], gen['gate_result']['target_tree_reasons'])
    print('LINES', gen['verified_repository']['judged_sessions'])
    sa = _verify(u, 'worktree', study=False, policy=doc['policy'])['generations'][0]
    print('STANDALONE', sa['public_source_freshness'], sa['gate_result']['decision'],
          sa['declared_conformity'])
    assert gen['gate_result']['decision'] == g['decision'], 'local differs from check on its own bytes'
