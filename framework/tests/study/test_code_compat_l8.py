"""The source attestations of lot L8 (owner session 2026-10-26) in ``mlkit.study.code_compat``.

L8 changes seven modules that activity fingerprints hold: ``governance`` and ``fit`` (R6, the
per-column rare grouping), ``eda`` (R5, the quantiles and skewness of the quality check), and
``fit``, ``families``, ``policy``, ``regression``, ``objective`` (R10 level 2, a
``progress.step`` call per fold, grid value or bootstrap replicate, a no-op without
``run --progress``). Without an attestation every result of every existing study would be
"code changed", including the one evaluation of an opened final test.

One set of exact, directed edges, from the digests the attested engines recorded (10c1e70,
whose fingerprinted bytes are those of ba4819c, and the earlier fit and families digests of
818995c and 506180a) to the L8 digests, each scoped to the activities whose fingerprint holds
the module, the capture excepted. They were added only after ``code_compat_evidence.py``
matched for each of the three engines (``docs/handoff/LIBRARIES-V1.md``, section "Owner
session 2026-10-26 (L8)"). ``predictor.capture`` is not attested: its ids hash the code
fingerprint and its recipe and runtime changed, so an existing capture is no longer current
(risk K3, accepted by the owner, D19); ``test_l8_existing_studies.py`` shows what the
junior then sees.

Without the old engines these tests check that the edges target the real bytes, that the
activity lists are explicit and complete, and that the edges stay exact, directed and scoped;
``test_byte_comparison_with_the_pre_l8_engine`` repeats the comparison when an old engine is
supplied (``HYPOTRAIL_COMPAT_OLD_PYTHON``, ``HYPOTRAIL_COMPAT_OLD_ROOT``).
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

REPO = Path(__file__).resolve().parents[3]
STUDY = 'framework/mlkit/study'
MODULES = ('governance', 'eda', 'fit', 'families', 'policy', 'regression', 'objective')
FILES = {f'mlkit.study.{m}': f'{STUDY}/{m}.py' for m in MODULES}
# The L8 bytes.
NEW = {'mlkit.study.governance':
       '9c86f512c9a3beafe0d37f477a71e669555eb639c4e97b78155223b833ed4c77',
       'mlkit.study.eda': '9d419bd785382586e5edd3f8cefbae3edbd6fd5506629a5173816aa884e2539b',
       'mlkit.study.fit': '49981afe99bb73270f2fd71cb2948b9d44eb22136e9b44b3120358a9656bec98',
       'mlkit.study.families':
       'cc9f13d151e5fe985707a968254bacfa46ba3e538ff7a82ff0d5dfe266833eda',
       'mlkit.study.policy': '6b1d050040a77235b8ce47886c863a0efd02400da7a887662d8bf87c66233c8a',
       'mlkit.study.regression':
       'c7e0677a68608ad21cb28764cae5dfafc396c5f3c07f6f3f2ff6420e105dfd07',
       'mlkit.study.objective':
       '917cd720307df2e0b61c1e5476ce91ff24df95995887bf123606921c0cc47a71'}
GOVERNANCE = '09af3783c18fd7947b6f979a24a5266cca85ca576e69c8ee6a233e6e2e6fa413'
EDA = '45d9aea4b6cb8e83f27025665734a93e0cecf30a37e8903c3ea4b711ce85157e'
POLICY = '5bd077037ff250399e8058780419caaa3f1488a3cd8025b5d8b3d948ab109ed1'
REGRESSION = '3d48d0912580fcd8cb0837da51c3bef5dbdc0092267bc9fa6f955e969915db21'
OBJECTIVE = '130a6184006f915880dfb1451437b5ebe5bf5cc0847105a02befa0f603794318'
# The digests each attested engine recorded, by commit (the activities digest too: its edges
# to the current activities bytes are earlier rounds', unchanged by L8).
ENGINES = {
    '10c1e70': {'mlkit.study.activities':
                '9f5e8c3fa79d7ebbfdb146bc2c556733998377fc023d4309e99964feac48175b',
                'mlkit.study.governance': GOVERNANCE, 'mlkit.study.eda': EDA,
                'mlkit.study.fit':
                '9ca62f79a0cb335374beb1c8047cd34047bd4456a192f300282e269f1979c8f7',
                'mlkit.study.families':
                '4e207920618b1a59da54d1a66066a22c771a276795012931a4aa74f9a78a3f00',
                'mlkit.study.policy': POLICY, 'mlkit.study.regression': REGRESSION,
                'mlkit.study.objective': OBJECTIVE},
    '818995c': {'mlkit.study.activities':
                'd6806ce3ff8f40c90eec7342c4ea2693a87c39a387a660dc1633364edd5c1f10',
                'mlkit.study.governance': GOVERNANCE, 'mlkit.study.eda': EDA,
                'mlkit.study.fit':
                'd39f3f5bfbc0927c79af7371b8358b9b4d72892b869c2ed726498a798a744579',
                'mlkit.study.families':
                '2d8748798498388525c94ef85f8d73779b2a0c5d3145270e32d67cbbfc860e85',
                'mlkit.study.policy': POLICY, 'mlkit.study.regression': REGRESSION,
                'mlkit.study.objective': OBJECTIVE},
    '506180a': {'mlkit.study.activities':
                '3065f4d623f1ea2346c43ef27c0dd0f9a948c8eb007355c9cb625967b17cc9e1',
                'mlkit.study.governance': GOVERNANCE, 'mlkit.study.eda': EDA,
                'mlkit.study.fit':
                '28c00840fe9f9a5c17d0e9a0d483cd7dbdc9ed2cc4d715a8f65073399d989161',
                'mlkit.study.families':
                '2d8748798498388525c94ef85f8d73779b2a0c5d3145270e32d67cbbfc860e85',
                'mlkit.study.policy': POLICY, 'mlkit.study.regression': REGRESSION,
                'mlkit.study.objective': OBJECTIVE},
}
# The attested lists, written out: every activity whose fingerprint holds the module, the
# capture excepted.
ATTESTED = {
    'mlkit.study.governance': ['fit.logistic', 'fit.linear', 'fit.variant',
                               'final_test.evaluation', 'diag.binary', 'diag.regression'],
    'mlkit.study.eda': ['eda.target_rate', 'eda.special_values', 'eda.rate_by',
                        'eda.target_summary', 'eda.mean_by', 'eda.distribution', 'eda.quality',
                        'eda.single_feature_signal'],
    'mlkit.study.fit': ['fit.baseline', 'fit.logistic', 'fit.linear',
                        'eda.single_feature_signal', 'fit.variant', 'final_test.evaluation',
                        'diag.binary', 'diag.regression'],
    'mlkit.study.families': ['fit.variant', 'final_test.evaluation'],
    'mlkit.study.policy': ['policy.evaluation', 'policy.inspect', 'final_test.evaluation',
                           'diag.binary', 'diag.final_test'],
    'mlkit.study.regression': ['fit.baseline', 'fit.linear', 'evaluate.regression',
                               'fit.variant', 'final_test.evaluation', 'diag.regression',
                               'diag.final_test'],
    'mlkit.study.objective': ['fit.baseline', 'fit.logistic', 'policy.evaluation',
                              'policy.inspect', 'fit.linear', 'evaluate.regression',
                              'fit.variant', 'final_test.evaluation'],
}
# The capture's own modules L8 changed (never attested).
CAPTURE_FILES = {'mlkit.contracts.recipe': 'framework/mlkit/contracts/recipe.py',
                 'hypotrail_runtime.preprocess':
                 'framework/runtime/src/hypotrail_runtime/preprocess.py'}
STALE = ('{path} changed again after L8: re-run framework/tests/study/code_compat_evidence.py '
         'against the new bytes and, only if it matches, add new edges from the L8 bytes and '
         'from every source below (keep these; they stop matching by themselves).')


def _sources(module: str) -> set[str]:
    return {digests[module] for digests in ENGINES.values()}


def _holding(module: str) -> set[str]:
    return {a for a in act.ACTIVITIES if module in act.MODULES[a]
            or module in act.REGRESSION_MODULES.get(a, ())}


def test_the_l8_edges_target_the_current_bytes():
    assert code_compat.integrity()
    for module, path in FILES.items():
        now = hashlib.sha256((REPO / path).read_bytes()).hexdigest()
        assert read._module_path(module).read_bytes() == (REPO / path).read_bytes()
        if now != NEW[module]:
            for source in _sources(module) | {NEW[module]}:
                covered = {a for r in code_compat.ATTESTATIONS if r['module'] == module
                           and r['from_sha256'] == source and r['to_sha256'] == now
                           for a in r['activities']}
                assert covered == set(ATTESTED[module]), STALE.format(path=path)
        assert set(ATTESTED[module]) == _holding(module) - {act.CAPTURE}
        assert len(set(ATTESTED[module])) == len(ATTESTED[module])
        for source in _sources(module):
            [record] = [r for r in code_compat.ATTESTATIONS if r['module'] == module
                        and r['from_sha256'] == source and r['to_sha256'] == NEW[module]]
            assert record['activities'] == ATTESTED[module]
            assert act.CAPTURE not in record['activities']
            assert act.POPULATION not in record['activities']
            assert record['reason'].strip()
            assert 'framework/tests/study/test_code_compat_l8.py' in record['evidence']
            assert 'framework/tests/study/code_compat_evidence.py' in record['evidence']
            assert any(e.startswith('docs/handoff/LIBRARIES-V1.md#owner-session-2026-10-26-l8')
                       for e in record['evidence'])
    # The activities module is not changed by L8: its earlier edges still target it.
    acts = 'mlkit.study.activities'
    assert hashlib.sha256((REPO / f'{STUDY}/activities.py').read_bytes()).hexdigest() == \
        ENGINES['10c1e70'][acts]


def test_the_l8_edges_start_at_the_recorded_bytes():
    for commit, digests in ENGINES.items():
        probe = subprocess.run(['git', '-C', str(REPO), 'cat-file', '-e', f'{commit}^{{commit}}'],
                               capture_output=True)
        if probe.returncode != 0:
            pytest.skip(f'{commit} is not in this clone')
        for module, digest in digests.items():
            path = f"{STUDY}/{module.rsplit('.', 1)[1]}.py"
            blob = subprocess.run(['git', '-C', str(REPO), 'show', f'{commit}:{path}'],
                                  capture_output=True, check=True).stdout
            assert hashlib.sha256(blob).hexdigest() == digest, (commit, module)


def _entry(activity: str, digests: dict) -> dict:
    modules = dict(registry.code_fingerprint(list(act.MODULES[activity]))['modules'])
    modules.update({m: d for m, d in digests.items() if m in modules})
    return {'activity': activity, 'code': {'modules': modules}}


def test_a_result_of_every_attested_engine_stays_current(tmp_path):
    """A result each engine recorded, for every activity but the capture and the population
    profile, is current at the L8 bytes; the capture is not."""
    case_dir = fk.make_case(tmp_path / 'case', n_rows=200)['case'].parent
    Flow(tmp_path / 'study', case_dir).init()
    study = read.open(tmp_path / 'study')
    every = set(act.ACTIVITIES) - {act.CAPTURE, act.POPULATION}
    for commit, digests in ENGINES.items():
        for activity in sorted(every):
            assert study.code_changed(_entry(activity, digests)) == [], (commit, activity)
        changed = study.code_changed(_entry(act.CAPTURE, digests))
        assert {'mlkit.study.fit', 'mlkit.study.governance'} <= set(changed), (commit, changed)
    # L8 changes no module of the population profile: a 10c1e70 one stays current.
    assert study.code_changed(_entry(act.POPULATION, ENGINES['10c1e70'])) == []


def test_the_l8_edges_stay_exact_directed_and_scoped(tmp_path):
    case_dir = fk.make_case(tmp_path / 'case', n_rows=200)['case'].parent
    Flow(tmp_path / 'study', case_dir).init()
    study = read.open(tmp_path / 'study')
    for module in FILES:
        for source in _sources(module):
            # Directed: the reverse edge does not exist.
            assert not code_compat.equivalent(module, NEW[module], source, ATTESTED[module][0])
            # Never the capture, never without an activity.
            assert not code_compat.equivalent(module, source, NEW[module], act.CAPTURE)
            assert not code_compat.equivalent(module, source, NEW[module], None)
            # Never an activity the module's fingerprint does not hold.
            for activity in sorted(set(act.ACTIVITIES) - set(ATTESTED[module])):
                assert not code_compat.equivalent(module, source, NEW[module], activity)
    # Not transitive and not merged across modules: an unknown digest stays unknown, and an
    # eda edge does not cover a fit module change.
    assert study.code_changed(_entry('fit.logistic', {'mlkit.study.fit': 'e' * 64})) == [
        'mlkit.study.fit']
    assert study.code_changed(_entry('eda.single_feature_signal', {
        'mlkit.study.eda': EDA, 'mlkit.study.fit': 'e' * 64})) == ['mlkit.study.fit']
    assert study.code_changed(_entry('eda.quality', {'mlkit.study.eda': 'd' * 64})) == [
        'mlkit.study.eda']


def test_the_capture_modules_changed_and_are_never_attested():
    """K3: the recipe (rare_category version 2) and the runtime's preparation (versions 1
    and 2) changed; no edge covers them, so a capture made before L8 is not current. The
    runtime's contracts module, which the population profile fingerprints too, is
    unchanged."""
    for module, path in CAPTURE_FILES.items():
        assert module in act.MODULES[act.CAPTURE]
        before = subprocess.run(['git', '-C', str(REPO), 'show', f'10c1e70:{path}'],
                                capture_output=True)
        if before.returncode != 0:
            pytest.skip('10c1e70 is not in this clone')
        assert hashlib.sha256(before.stdout).hexdigest() != hashlib.sha256(
            (REPO / path).read_bytes()).hexdigest(), module
        assert not any(r['module'] == module for r in code_compat.ATTESTATIONS), module
    assert not any(act.CAPTURE in r['activities'] for r in code_compat.ATTESTATIONS)
    contracts = 'framework/runtime/src/hypotrail_runtime/contracts.py'
    before = subprocess.run(['git', '-C', str(REPO), 'show', f'10c1e70:{contracts}'],
                            capture_output=True, check=True).stdout
    assert before == (REPO / contracts).read_bytes()


@pytest.mark.skipif(not (os.environ.get('HYPOTRAIL_COMPAT_OLD_PYTHON')
                         and os.environ.get('HYPOTRAIL_COMPAT_OLD_ROOT')),
                    reason='needs a pre-L8 engine (10c1e70, 818995c or 506180a) and a Python '
                           'with its dependencies (HYPOTRAIL_COMPAT_OLD_PYTHON, '
                           'HYPOTRAIL_COMPAT_OLD_ROOT)')
def test_byte_comparison_with_the_pre_l8_engine(tmp_path):
    """The evidence itself: the same flows on both engines, then leaf recomputation."""
    script = Path(__file__).with_name('code_compat_evidence.py')
    proc = subprocess.run([sys.executable, str(script), 'evidence',
                           os.environ['HYPOTRAIL_COMPAT_OLD_PYTHON'],
                           os.environ['HYPOTRAIL_COMPAT_OLD_ROOT'], str(tmp_path / 'work')],
                          capture_output=True, text=True, timeout=5400)
    assert proc.returncode == 0, proc.stdout[-4000:] + proc.stderr[-4000:]
    assert 'DIFFERENT' not in proc.stdout and proc.stdout.rstrip().endswith('MATCH')
