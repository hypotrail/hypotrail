"""Exact, reviewable source-compatibility attestations (reliability roadmap J4).

Compatibility is a directed edge from one source digest to one *current* digest, scoped to
named activities. There are deliberately no wildcards and no transitive closure. The table
is data; :func:`integrity` validates it without performing I/O.
"""
from __future__ import annotations

import re
from typing import Iterable, Mapping

SCHEMA = 'hypotrail.code_compat/1'
ATTESTATION_KEYS = ('module', 'from_sha256', 'to_sha256', 'activities', 'reason', 'evidence')
_SHA256 = re.compile(r'^[0-9a-f]{64}$')

# Destination digests are added only after the complete change is reviewed. A declaration
# that no longer targets the current bytes is harmless: it simply stops matching.
ATTESTATIONS: tuple[dict, ...] = (
    {
        'module': 'mlkit.study.activities',
        'from_sha256': 'b04e5fad6c3ae1e9d563d086a879422cce372e79593bec2b31eaebb098d3f30e',
        'to_sha256': 'd6806ce3ff8f40c90eec7342c4ea2693a87c39a387a660dc1633364edd5c1f10',
        'activities': ['diag.final_test'],
        'reason': ('The intervening activity changes add inspection and development-only '
                   'metadata, then (library integration v1) the predictor.capture and '
                   'diagnostics.population dispatch; final-test diagnostic dispatch and values '
                   'are unchanged.'),
        'evidence': ['framework/tests/study/test_v03_wp_j_engine.py',
                     'framework/tests/study/test_reliability_j4_j7.py',
                     'framework/tests/study/libraries/test_capture_final.py'],
    },
    {
        'module': 'mlkit.study.activities',
        'from_sha256': '3065f4d623f1ea2346c43ef27c0dd0f9a948c8eb007355c9cb625967b17cc9e1',
        'to_sha256': 'd6806ce3ff8f40c90eec7342c4ea2693a87c39a387a660dc1633364edd5c1f10',
        'activities': ['diag.final_test'],
        'reason': ('Library integration v1 adds the predictor.capture and '
                   'diagnostics.population activities and a final-test branch taken only when '
                   'a capture is current; final-test diagnostic dispatch and values are '
                   'unchanged.'),
        'evidence': ['framework/tests/study/test_wp_b4_diagnostics.py',
                     'framework/tests/study/libraries/test_capture_final.py'],
    },
    # Library integration v1, review E1 (integrator decision 2026-10-24): the activities whose
    # code path is unchanged when no predictor capture is used, attested only after their
    # results were compared between the engine of 506180a and that of 621d607.
    {
        'module': 'mlkit.study.activities',
        'from_sha256': '3065f4d623f1ea2346c43ef27c0dd0f9a948c8eb007355c9cb625967b17cc9e1',
        'to_sha256': 'd6806ce3ff8f40c90eec7342c4ea2693a87c39a387a660dc1633364edd5c1f10',
        'activities': ['split', 'eda.target_rate', 'eda.special_values', 'eda.rate_by',
                       'eda.target_summary', 'eda.mean_by', 'eda.distribution', 'eda.quality',
                       'eda.single_feature_signal', 'eda.correlation', 'fit.baseline',
                       'fit.logistic', 'fit.linear', 'fit.variant', 'policy.evaluation',
                       'policy.inspect', 'evaluate.regression', 'diag.binary',
                       'diag.regression', 'final_test.evaluation'],
        'reason': ('Library integration v1 only adds the predictor.capture and '
                   'diagnostics.population constants, option checks and dispatch, and a '
                   'final-test plan branch and load taken only when a predictor.capture result '
                   'is current; a study made before it has none, so every one of these '
                   'activities plans and computes exactly as before.'),
        'evidence': ['framework/tests/study/test_code_compat_library_v1.py',
                     'framework/tests/study/code_compat_evidence.py',
                     'docs/handoff/LIBRARIES-V1.md#source-compatibility-of-existing-studies: '
                     'the same 95 commands on four temporary studies (synthetic binary '
                     'holdout, synthetic binary 5-fold, the committed regression use case '
                     'with the default holdout, '
                     'synthetic regression 5-fold, each to an opened final test with '
                     'diag.final_test) with the 506180a and 621d607 engines: 73 results with '
                     'byte-identical blobs and params; 53 with byte-identical values, the 20 '
                     'others (policy, evaluation and diagnostics) differ only by the ids of '
                     'their upstream results, and all 42 leaf results recomputed at 621d607 '
                     'inside the 506180a studies (upstream ids kept) are byte-identical.'],
    },
    {
        'module': 'mlkit.study.fit',
        'from_sha256': '28c00840fe9f9a5c17d0e9a0d483cd7dbdc9ed2cc4d715a8f65073399d989161',
        'to_sha256': 'd39f3f5bfbc0927c79af7371b8358b9b4d72892b869c2ed726498a798a744579',
        'activities': ['fit.baseline', 'fit.logistic', 'fit.linear', 'fit.variant',
                       'eda.single_feature_signal', 'diag.binary', 'diag.regression',
                       'final_test.evaluation'],
        'reason': ('Library integration v1 only adds the optional predictor argument of '
                   'final_evaluation (None unless a predictor.capture result is current) and '
                   'the values it adds in that case; the fits and, without a capture, the '
                   'final evaluation are unchanged.'),
        'evidence': ['framework/tests/study/test_code_compat_library_v1.py',
                     'framework/tests/study/code_compat_evidence.py',
                     'docs/handoff/LIBRARIES-V1.md#source-compatibility-of-existing-studies: '
                     'the same comparison as the mlkit.study.activities edge of the same '
                     'commits.'],
    },
    # Review 2026-10-24 round 2 (delayed labels): activities.py leaves the development rows
    # of ``partition.training_exclusions`` out of every activity but the structural
    # inspections. With no exclusion (every study of these engines but a review-v1 study whose
    # outcome clock leaves rows out) nothing it plans or computes changes; a study with
    # exclusions is not current anyway (``partition.ignores_exclusions``). Attested only after
    # the byte comparison of both engines matched. Not attested: predictor.capture (its
    # predictor and computation ids hash the code fingerprint) and diagnostics.population
    # (its Evidently statistics and snapshot are not reproducible bit for bit).
    {
        'module': 'mlkit.study.activities',
        'from_sha256': 'd6806ce3ff8f40c90eec7342c4ea2693a87c39a387a660dc1633364edd5c1f10',
        'to_sha256': 'b7c994d2e88edba8156c47756c0c43a496f0e04d4f7005bc1d9014ab639a48c1',
        'activities': ['split', 'eda.target_rate', 'eda.special_values', 'eda.rate_by',
                       'eda.target_summary', 'eda.mean_by', 'eda.distribution', 'eda.quality',
                       'eda.single_feature_signal', 'eda.correlation', 'fit.baseline',
                       'fit.logistic', 'fit.linear', 'fit.variant', 'policy.evaluation',
                       'policy.inspect', 'evaluate.regression', 'diag.binary',
                       'diag.regression', 'final_test.evaluation', 'diag.final_test'],
        'reason': ('The delayed-label fix adds the training-exclusion identity key, row filter '
                   'and refusal, each taken only when partition.training_exclusions names at '
                   'least one row; a study without such rows plans and computes exactly as '
                   'with the 818995c engine.'),
        'evidence': ['framework/tests/study/test_review_round2_training_exclusions.py',
                     'framework/tests/study/code_compat_evidence.py',
                     'docs/handoff/LIBRARIES-V1.md#delayed-labels-review-round-2: the same '
                     'commands on six temporary studies (the four of E1 plus a review-v1 '
                     'independent and a review-v1 future study without exclusions) with the '
                     '818995c engine and the current one; every result byte-identical or '
                     'identical up to upstream ids, every leaf recomputed in the 818995c '
                     'studies byte-identical, every promoted result current.'],
    },
    {
        'module': 'mlkit.study.activities',
        'from_sha256': 'b04e5fad6c3ae1e9d563d086a879422cce372e79593bec2b31eaebb098d3f30e',
        'to_sha256': 'b7c994d2e88edba8156c47756c0c43a496f0e04d4f7005bc1d9014ab639a48c1',
        'activities': ['diag.final_test'],
        'reason': ('The reviewed pre-WP-J edge (to the 818995c bytes) carried to the current '
                   'bytes: the delayed-label fix changes nothing diag.final_test plans or '
                   'computes in a study without training exclusions.'),
        'evidence': ['framework/tests/study/test_v03_wp_j_engine.py',
                     'framework/tests/study/test_reliability_j4_j7.py',
                     'framework/tests/study/test_review_round2_training_exclusions.py',
                     'docs/handoff/LIBRARIES-V1.md#delayed-labels-review-round-2: '
                     'diag.final_test byte-identical between the 818995c and current '
                     'engines.'],
    },
    {
        'module': 'mlkit.study.activities',
        'from_sha256': '3065f4d623f1ea2346c43ef27c0dd0f9a948c8eb007355c9cb625967b17cc9e1',
        'to_sha256': 'b7c994d2e88edba8156c47756c0c43a496f0e04d4f7005bc1d9014ab639a48c1',
        'activities': ['split', 'eda.target_rate', 'eda.special_values', 'eda.rate_by',
                       'eda.target_summary', 'eda.mean_by', 'eda.distribution', 'eda.quality',
                       'eda.single_feature_signal', 'eda.correlation', 'fit.baseline',
                       'fit.logistic', 'fit.linear', 'fit.variant', 'policy.evaluation',
                       'policy.inspect', 'evaluate.regression', 'diag.binary',
                       'diag.regression', 'final_test.evaluation', 'diag.final_test'],
        'reason': ('The library-v1 change (see the 506180a edges above) and the delayed-label '
                   'fix, whose code paths are taken only when a predictor.capture result is '
                   'current or partition.training_exclusions names at least one row; a study '
                   'of the 506180a engine without such rows plans and computes exactly as '
                   'before.'),
        'evidence': ['framework/tests/study/test_review_round2_training_exclusions.py',
                     'framework/tests/study/test_code_compat_library_v1.py',
                     'framework/tests/study/code_compat_evidence.py',
                     'docs/handoff/LIBRARIES-V1.md#delayed-labels-review-round-2: the same '
                     'comparison with the 506180a engine (the same six studies).'],
    },
    {
        'module': 'mlkit.study.diagnostics',
        'from_sha256': '3d3244edc2b3bc7a7b5cb6e5519e18751ed2ad8eb7d3066ef5585242ac52059d',
        'to_sha256': 'bed0d20d0a451d1548b5ccad359482d12247f387e338ed175ad9cee06d61abf9',
        'activities': ['diag.final_test'],
        'reason': ('The coefficient-interval change applies only to development diagnostics; '
                   'final-test diagnostics have no coefficients.'),
        'evidence': ['framework/tests/study/test_v03_wp_j_engine.py',
                     'framework/tests/study/test_reliability_j4_j7.py'],
    },
)


def problems(records: Iterable[Mapping] = ATTESTATIONS) -> list[dict]:
    """Return structural/integrity problems in an attestation collection."""
    out = []
    seen = set()
    for index, item in enumerate(records):
        keys = tuple(item) if isinstance(item, Mapping) else ()
        if set(keys) != set(ATTESTATION_KEYS):
            out.append({'index': index, 'reason': 'keys',
                        'keys': sorted(str(key) for key in keys)})
            continue
        if not isinstance(item['module'], str) or not item['module']:
            out.append({'index': index, 'reason': 'module'})
        for key in ('from_sha256', 'to_sha256'):
            if not isinstance(item[key], str) or not _SHA256.fullmatch(item[key]):
                out.append({'index': index, 'reason': key})
        if item['from_sha256'] == item['to_sha256']:
            out.append({'index': index, 'reason': 'equal_digests'})
        if not isinstance(item['activities'], (list, tuple)) or not item['activities'] \
                or any(not isinstance(a, str) or not a for a in item['activities']):
            out.append({'index': index, 'reason': 'activities'})
        if not isinstance(item['reason'], str) or not item['reason'].strip():
            out.append({'index': index, 'reason': 'reason'})
        if not isinstance(item['evidence'], (list, tuple)) or not item['evidence'] \
                or any(not isinstance(e, str) or not e for e in item['evidence']):
            out.append({'index': index, 'reason': 'evidence'})
        if isinstance(item['module'], str) and isinstance(item['from_sha256'], str) \
                and isinstance(item['to_sha256'], str) \
                and isinstance(item['activities'], (list, tuple)) \
                and all(isinstance(activity, str) for activity in item['activities']):
            identity = (item['module'], item['from_sha256'], item['to_sha256'],
                        tuple(item['activities']))
            if identity in seen:
                out.append({'index': index, 'reason': 'duplicate'})
            seen.add(identity)
    return out


def integrity(records: Iterable[Mapping] = ATTESTATIONS) -> bool:
    """Whether every declaration is complete and unambiguous."""
    return not problems(records)


def equivalent(module: str, from_sha256: str | None, to_sha256: str | None = None,
               activity: str | None = None, records: Iterable[Mapping] = ATTESTATIONS) -> bool:
    """Whether one exact directed attestation covers this module and activity.

    Missing destination/activity values never broaden a declaration. Equal digests need no
    attestation and therefore return ``False``.
    """
    if from_sha256 is None or to_sha256 is None or activity is None \
            or from_sha256 == to_sha256:
        return False
    for item in records:
        if problems((item,)):
            continue
        if item['module'] == module and item['from_sha256'] == from_sha256 \
                and item['to_sha256'] == to_sha256 and activity in item['activities']:
            return True
    return False


# Transitional read-only index for integrations which display known source digests. Currency
# never consults this map; only the exact predicate above has authority.
EQUIVALENT = {item['module']: {item['from_sha256']: item['reason']} for item in ATTESTATIONS}
