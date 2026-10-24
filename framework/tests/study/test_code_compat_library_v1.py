"""The library-v1 source attestations of ``mlkit.study.code_compat`` (review E1).

The library integration changed ``mlkit/study/activities.py`` (in every activity's code
fingerprint) and ``mlkit/study/fit.py``. Studies made by the engine of 506180a lost every
current result until these edges were added; each edge is exact (one source digest, one
destination digest, named activities) and was added only after the byte comparison of
``code_compat_evidence.py`` matched (see ``docs/handoff/LIBRARIES-V1.md``).

Without the old engine these tests check that the edges target the real bytes, that the
activity lists are explicit and complete, and what the edges make current and what they do
not. ``test_byte_comparison_with_the_base_engine`` repeats the comparison itself when an old
engine is supplied (``HYPOTRAIL_COMPAT_OLD_PYTHON``, ``HYPOTRAIL_COMPAT_OLD_ROOT``).
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

from mlkit.study import activities as act, code_compat, read, registry

import flowkit as fk
from flowkit import Flow

BASE_COMMIT = '506180a'
LIBRARY_COMMIT = '621d607'
BASE = {'mlkit.study.activities':
        '3065f4d623f1ea2346c43ef27c0dd0f9a948c8eb007355c9cb625967b17cc9e1',
        'mlkit.study.fit': '28c00840fe9f9a5c17d0e9a0d483cd7dbdc9ed2cc4d715a8f65073399d989161'}
LIBRARY = {'mlkit.study.activities':
           'd6806ce3ff8f40c90eec7342c4ea2693a87c39a387a660dc1633364edd5c1f10',
           'mlkit.study.fit': 'd39f3f5bfbc0927c79af7371b8358b9b4d72892b869c2ed726498a798a744579'}
FILES = {'mlkit.study.activities': 'framework/mlkit/study/activities.py',
         'mlkit.study.fit': 'framework/mlkit/study/fit.py'}
# The activities of the 506180a engine (its ``activities.ACTIVITIES``), written out.
BASE_ACTIVITIES = ('split', 'eda.target_rate', 'eda.special_values', 'eda.rate_by',
                   'fit.baseline', 'fit.logistic', 'policy.evaluation', 'policy.inspect',
                   'eda.target_summary', 'eda.mean_by', 'fit.linear', 'evaluate.regression',
                   'eda.distribution', 'eda.quality', 'eda.single_feature_signal',
                   'fit.variant', 'final_test.evaluation', 'diag.binary', 'diag.regression',
                   'diag.final_test', 'eda.correlation')
# The attested lists, written out (no wildcard, no derivation from the engine).
ATTESTED = {
    'mlkit.study.activities': ['split', 'eda.target_rate', 'eda.special_values', 'eda.rate_by',
                               'eda.target_summary', 'eda.mean_by', 'eda.distribution',
                               'eda.quality', 'eda.single_feature_signal', 'eda.correlation',
                               'fit.baseline', 'fit.logistic', 'fit.linear', 'fit.variant',
                               'policy.evaluation', 'policy.inspect', 'evaluate.regression',
                               'diag.binary', 'diag.regression', 'final_test.evaluation'],
    'mlkit.study.fit': ['fit.baseline', 'fit.logistic', 'fit.linear', 'fit.variant',
                        'eda.single_feature_signal', 'diag.binary', 'diag.regression',
                        'final_test.evaluation'],
}
REPO = Path(__file__).resolve().parents[3]
STALE_EDGE = ('{module} no longer has the bytes its library-v1 attestation targets. Studies '
              'made by 506180a lose their current results again: re-run '
              'framework/tests/study/code_compat_evidence.py against the new bytes and, only '
              'if it matches, add a new edge from the 506180a digest to the new one (keep this '
              'one; it stops matching by itself).')


def _edges() -> dict:
    """The edges of this review, by module: from the base to the library bytes, other than
    the reviewed ``diag.final_test`` edge that existed before."""
    out = {}
    for record in code_compat.ATTESTATIONS:
        module = record['module']
        if module in BASE and record['from_sha256'] == BASE[module] \
                and record['to_sha256'] == LIBRARY[module] \
                and record['activities'] != ['diag.final_test']:
            out.setdefault(module, []).append(record)
    return out


def test_the_library_v1_edges_target_the_current_bytes():
    edges = _edges()
    assert set(edges) == set(BASE)
    for module, path in FILES.items():
        now = hashlib.sha256((REPO / path).read_bytes()).hexdigest()
        assert now == LIBRARY[module], STALE_EDGE.format(module=module)
        assert read._module_path(module).read_bytes() == (REPO / path).read_bytes()


def test_the_library_v1_edges_start_at_the_506180a_bytes():
    probe = subprocess.run(['git', '-C', str(REPO), 'cat-file', '-e', f'{BASE_COMMIT}^{{commit}}'],
                           capture_output=True)
    if probe.returncode != 0:
        pytest.skip(f'{BASE_COMMIT} is not in this clone')
    for commit, digests in ((BASE_COMMIT, BASE), (LIBRARY_COMMIT, LIBRARY)):
        for module, path in FILES.items():
            blob = subprocess.run(['git', '-C', str(REPO), 'show', f'{commit}:{path}'],
                                  capture_output=True, check=True).stdout
            assert hashlib.sha256(blob).hexdigest() == digests[module], (commit, module)


def test_the_activity_lists_are_explicit_and_complete():
    assert code_compat.integrity()
    edges = _edges()
    for module, records in edges.items():
        [record] = records                              # one edge per module, no duplicate
        assert record['activities'] == ATTESTED[module]
        assert len(set(record['activities'])) == len(record['activities'])
        assert all(a in BASE_ACTIVITIES and a in act.ACTIVITIES for a in record['activities'])
        assert not {act.CAPTURE, act.POPULATION} & set(record['activities'])
        assert record['reason'].strip() and record['evidence']
        assert 'framework/tests/study/test_code_compat_library_v1.py' in record['evidence']
        assert 'framework/tests/study/code_compat_evidence.py' in record['evidence']
        for activity in record['activities']:
            modules = set(act.MODULES[activity]) | set(act.REGRESSION_MODULES.get(activity, ()))
            assert module in modules, (module, activity)
    # Every base activity is covered by an activities edge from the base digest: these, plus
    # the reviewed diag.final_test edge that was already there.
    covered = {a for r in code_compat.ATTESTATIONS
               if r['module'] == 'mlkit.study.activities'
               and r['from_sha256'] == BASE['mlkit.study.activities']
               and r['to_sha256'] == LIBRARY['mlkit.study.activities'] for a in r['activities']}
    assert covered == set(BASE_ACTIVITIES)
    # The fit edge names exactly the base activities whose fingerprint holds the fit module.
    with_fit = {a for a in BASE_ACTIVITIES
                if 'mlkit.study.fit' in act.MODULES[a]
                or 'mlkit.study.fit' in act.REGRESSION_MODULES.get(a, ())}
    assert set(ATTESTED['mlkit.study.fit']) == with_fit


def _entry(activity: str, **digests) -> dict:
    modules = dict(registry.code_fingerprint(list(act.MODULES[activity]))['modules'])
    modules.update({m: d for m, d in digests.items() if m in modules})
    return {'activity': activity, 'code': {'modules': modules}}


def test_a_result_of_the_506180a_engine_is_current_for_every_base_activity(tmp_path):
    case_dir = fk.make_case(tmp_path / 'case', n_rows=200)['case'].parent
    Flow(tmp_path / 'study', case_dir).init()
    study = read.open(tmp_path / 'study')
    for activity in BASE_ACTIVITIES:
        assert study.code_changed(_entry(activity, **BASE)) == [], activity


def test_the_edges_stay_exact_directed_and_scoped(tmp_path):
    case_dir = fk.make_case(tmp_path / 'case', n_rows=200)['case'].parent
    Flow(tmp_path / 'study', case_dir).init()
    study = read.open(tmp_path / 'study')
    acts, fit = 'mlkit.study.activities', 'mlkit.study.fit'
    # Not for an activity that did not exist at the base (none of its results can be old).
    assert study.code_changed(_entry(act.CAPTURE, **BASE)) == [acts, fit]
    assert study.code_changed(_entry(act.POPULATION, **BASE)) == [acts]
    # Not from an older engine: the pre-WP-J digest is attested for diag.final_test only.
    pre_j = code_compat.ATTESTATIONS[0]
    assert pre_j['module'] == acts and pre_j['activities'] == ['diag.final_test']
    assert study.code_changed(_entry('split', **{acts: pre_j['from_sha256']})) == [acts]
    # Not transitive and not merged across modules: a fit edge does not cover the activities
    # module, and an unknown fit digest is not covered by the activities edge.
    assert study.code_changed(_entry('fit.logistic', **{acts: pre_j['from_sha256'],
                                                        fit: BASE[fit]})) == [acts]
    assert study.code_changed(_entry('fit.logistic', **{acts: BASE[acts],
                                                        fit: 'f' * 64})) == [fit]
    # Directed: the reverse edge does not exist.
    assert not code_compat.equivalent(acts, LIBRARY[acts], BASE[acts], 'split')
    assert not code_compat.equivalent(fit, LIBRARY[fit], BASE[fit], 'fit.baseline')
    # A module edge never covers an activity it does not name.
    assert not code_compat.equivalent(fit, BASE[fit], LIBRARY[fit], 'policy.evaluation')
    assert not code_compat.equivalent(acts, BASE[acts], LIBRARY[acts], None)


@pytest.mark.skipif(not (os.environ.get('HYPOTRAIL_COMPAT_OLD_PYTHON')
                         and os.environ.get('HYPOTRAIL_COMPAT_OLD_ROOT')),
                    reason='needs a 506180a checkout with its environment '
                           '(HYPOTRAIL_COMPAT_OLD_PYTHON, HYPOTRAIL_COMPAT_OLD_ROOT)')
def test_byte_comparison_with_the_base_engine(tmp_path):
    """The evidence itself: the same flows on both engines, then leaf recomputation."""
    script = Path(__file__).with_name('code_compat_evidence.py')
    proc = subprocess.run([sys.executable, str(script), 'evidence',
                           os.environ['HYPOTRAIL_COMPAT_OLD_PYTHON'],
                           os.environ['HYPOTRAIL_COMPAT_OLD_ROOT'], str(tmp_path / 'work')],
                          capture_output=True, text=True, timeout=3000)
    assert proc.returncode == 0, proc.stdout[-4000:] + proc.stderr[-4000:]
    assert 'DIFFERENT' not in proc.stdout and proc.stdout.rstrip().endswith('MATCH')
