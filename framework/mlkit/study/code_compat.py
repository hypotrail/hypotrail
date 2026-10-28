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
# The evidence of the L8 edges (owner session 2026-10-26), shared by each of them.
_L8_EVIDENCE = ('docs/handoff/LIBRARIES-V1.md#owner-session-2026-10-26-l8: the same commands on '
                'the seven temporary studies of L8 (the six of round 2 and a binary holdout '
                'study with a non-default integer preparation and a tuned variant) with the '
                '10c1e70, 818995c and 506180a engines and the L8 one; every result '
                'byte-identical, identical up to upstream ids, or (eda.quality only) identical '
                'but for the additive quantiles and skewness; every leaf recomputed inside the '
                'old studies identical the same way; every promoted result current.')
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
    # Review 2026-10-25 round 3: fit.py reads the regression target by row key in the
    # explicit (review-v1) cross-validation, which raised AttributeError on every regression
    # fit of a review-v1 explicit plan (B3-0), and families.py imports numpy where the
    # explicit inner plan of a tuned or family variant used it, which raised NameError. Both
    # paths crashed with every earlier engine, so no earlier result was computed on them;
    # every other path is unchanged. Attested from the ce82ca9 digests (fit.py unchanged since
    # 621d607, families.py since 506180a) and from the 506180a fit.py digest, only after the
    # byte comparison of each engine matched. Not attested: predictor.capture (its predictor
    # and computation ids hash the code fingerprint).
    {
        'module': 'mlkit.study.fit',
        'from_sha256': 'd39f3f5bfbc0927c79af7371b8358b9b4d72892b869c2ed726498a798a744579',
        'to_sha256': '9ca62f79a0cb335374beb1c8047cd34047bd4456a192f300282e269f1979c8f7',
        'activities': ['fit.baseline', 'fit.logistic', 'fit.linear', 'fit.variant',
                       'eda.single_feature_signal', 'diag.binary', 'diag.regression',
                       'final_test.evaluation'],
        'reason': ('Review round 3 (B3-0) indexes the regression target of the explicit '
                   'review-v1 cross-validation by row key; that path raised AttributeError '
                   'before, and every other path (binary, legacy folds, holdout, final '
                   'evaluation) is unchanged.'),
        'evidence': ['framework/tests/study/test_review_round3_engine.py',
                     'framework/tests/study/code_compat_evidence.py',
                     'docs/handoff/LIBRARIES-V1.md#review-round-3: the same commands on the six '
                     'temporary studies of round 2 with the ce82ca9 engine and the current '
                     'one; every result byte-identical or identical up to upstream ids, every '
                     'leaf recomputed in the ce82ca9 studies byte-identical, every promoted '
                     'result current.'],
    },
    {
        'module': 'mlkit.study.fit',
        'from_sha256': '28c00840fe9f9a5c17d0e9a0d483cd7dbdc9ed2cc4d715a8f65073399d989161',
        'to_sha256': '9ca62f79a0cb335374beb1c8047cd34047bd4456a192f300282e269f1979c8f7',
        'activities': ['fit.baseline', 'fit.logistic', 'fit.linear', 'fit.variant',
                       'eda.single_feature_signal', 'diag.binary', 'diag.regression',
                       'final_test.evaluation'],
        'reason': ('The library-v1 change (see the 506180a fit edge above) and the review '
                   'round 3 fix (B3-0), whose code paths are taken only when a '
                   'predictor.capture result is current or a regression study fits a '
                   'review-v1 explicit plan (which raised AttributeError before); a study of '
                   'the 506180a engine fits and evaluates exactly as before.'),
        'evidence': ['framework/tests/study/test_review_round3_engine.py',
                     'framework/tests/study/test_code_compat_library_v1.py',
                     'framework/tests/study/code_compat_evidence.py',
                     'docs/handoff/LIBRARIES-V1.md#review-round-3: the same comparison with '
                     'the 506180a engine.'],
    },
    {
        'module': 'mlkit.study.families',
        'from_sha256': '2d8748798498388525c94ef85f8d73779b2a0c5d3145270e32d67cbbfc860e85',
        'to_sha256': '4e207920618b1a59da54d1a66066a22c771a276795012931a4aa74f9a78a3f00',
        'activities': ['fit.variant', 'final_test.evaluation'],
        'reason': ('Review round 3 imports numpy in families.choose, which the explicit inner '
                   'plan of a tuned or family variant under a review-v1 plan used without it '
                   '(NameError before); the legacy inner folds and the fits are unchanged.'),
        'evidence': ['framework/tests/study/test_review_round3_engine.py',
                     'framework/tests/study/code_compat_evidence.py',
                     'docs/handoff/LIBRARIES-V1.md#review-round-3: tuned and family variants '
                     'byte-identical between the ce82ca9 (and 506180a) engines and the current '
                     'one.'],
    },
    # Review 2026-10-25 round 5 (area E, R5E-2): activities.py adds the runtime files the
    # wheel holds (errors, packaging, wheel, the schemas) to the predictor.capture fingerprint
    # only; nothing any other activity plans or computes changes. Attested from the b5f6dba
    # bytes (unchanged since ce82ca9), the 818995c bytes (unchanged since 621d607) and the
    # 506180a bytes, each only after the byte comparison of that engine matched. Not attested:
    # predictor.capture (its fingerprint now holds more modules: a new capture) and
    # diagnostics.population (not reproducible bit for bit).
    {
        'module': 'mlkit.study.activities',
        'from_sha256': 'b7c994d2e88edba8156c47756c0c43a496f0e04d4f7005bc1d9014ab639a48c1',
        'to_sha256': '9f5e8c3fa79d7ebbfdb146bc2c556733998377fc023d4309e99964feac48175b',
        'activities': ['split', 'eda.target_rate', 'eda.special_values', 'eda.rate_by',
                       'eda.target_summary', 'eda.mean_by', 'eda.distribution', 'eda.quality',
                       'eda.single_feature_signal', 'eda.correlation', 'fit.baseline',
                       'fit.logistic', 'fit.linear', 'fit.variant', 'policy.evaluation',
                       'policy.inspect', 'evaluate.regression', 'diag.binary',
                       'diag.regression', 'final_test.evaluation', 'diag.final_test'],
        'reason': ('Round 5 (R5E-2) changes only the module list of predictor.capture; every '
                   'other activity plans and computes exactly as with the b5f6dba engine.'),
        'evidence': ['framework/tests/study/test_review_round5_engine.py',
                     'framework/tests/study/code_compat_evidence.py',
                     'docs/handoff/LIBRARIES-V1.md#review-round-5-area-e: the same commands on '
                     'the six temporary studies of round 2 with the b5f6dba engine and the '
                     'current one; every result byte-identical or identical up to upstream '
                     'ids, every leaf recomputed in the b5f6dba studies byte-identical, every '
                     'promoted result current.'],
    },
    {
        'module': 'mlkit.study.activities',
        'from_sha256': 'd6806ce3ff8f40c90eec7342c4ea2693a87c39a387a660dc1633364edd5c1f10',
        'to_sha256': '9f5e8c3fa79d7ebbfdb146bc2c556733998377fc023d4309e99964feac48175b',
        'activities': ['split', 'eda.target_rate', 'eda.special_values', 'eda.rate_by',
                       'eda.target_summary', 'eda.mean_by', 'eda.distribution', 'eda.quality',
                       'eda.single_feature_signal', 'eda.correlation', 'fit.baseline',
                       'fit.logistic', 'fit.linear', 'fit.variant', 'policy.evaluation',
                       'policy.inspect', 'evaluate.regression', 'diag.binary',
                       'diag.regression', 'final_test.evaluation', 'diag.final_test'],
        'reason': ('The delayed-label fix (see the 818995c edge above) and the round-5 change '
                   'of the predictor.capture module list; a study of the 818995c engine without '
                   'training exclusions plans and computes exactly as before.'),
        'evidence': ['framework/tests/study/test_review_round5_engine.py',
                     'framework/tests/study/code_compat_evidence.py',
                     'docs/handoff/LIBRARIES-V1.md#review-round-5-area-e: the same comparison '
                     'with the 818995c engine.'],
    },
    {
        'module': 'mlkit.study.activities',
        'from_sha256': '3065f4d623f1ea2346c43ef27c0dd0f9a948c8eb007355c9cb625967b17cc9e1',
        'to_sha256': '9f5e8c3fa79d7ebbfdb146bc2c556733998377fc023d4309e99964feac48175b',
        'activities': ['split', 'eda.target_rate', 'eda.special_values', 'eda.rate_by',
                       'eda.target_summary', 'eda.mean_by', 'eda.distribution', 'eda.quality',
                       'eda.single_feature_signal', 'eda.correlation', 'fit.baseline',
                       'fit.logistic', 'fit.linear', 'fit.variant', 'policy.evaluation',
                       'policy.inspect', 'evaluate.regression', 'diag.binary',
                       'diag.regression', 'final_test.evaluation', 'diag.final_test'],
        'reason': ('The library-v1 change, the delayed-label fix (see the 506180a edges above) '
                   'and the round-5 change of the predictor.capture module list; a study of the '
                   '506180a engine without training exclusions plans and computes exactly as '
                   'before.'),
        'evidence': ['framework/tests/study/test_review_round5_engine.py',
                     'framework/tests/study/code_compat_evidence.py',
                     'docs/handoff/LIBRARIES-V1.md#review-round-5-area-e: the same comparison '
                     'with the 506180a engine.'],
    },
    {
        'module': 'mlkit.study.activities',
        'from_sha256': 'b04e5fad6c3ae1e9d563d086a879422cce372e79593bec2b31eaebb098d3f30e',
        'to_sha256': '9f5e8c3fa79d7ebbfdb146bc2c556733998377fc023d4309e99964feac48175b',
        'activities': ['diag.final_test'],
        'reason': ('The reviewed pre-WP-J edge (to the b5f6dba bytes) carried to the current '
                   'bytes: round 5 changes only the predictor.capture module list, nothing '
                   'diag.final_test plans or computes.'),
        'evidence': ['framework/tests/study/test_v03_wp_j_engine.py',
                     'framework/tests/study/test_reliability_j4_j7.py',
                     'framework/tests/study/test_review_round5_engine.py',
                     'docs/handoff/LIBRARIES-V1.md#review-round-5-area-e: diag.final_test '
                     'byte-identical between the b5f6dba and current engines.'],
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
    # Owner session 2026-10-26, lot L8 (R6, R5, R10 level 2): per-column rare grouping
    # (governance, fit), the quantiles and skewness of the quality check (eda) and the progress
    # steps of a long run (fit, families, policy, regression, objective; progress.step does
    # nothing unless ``run --progress`` listens). Every value an existing study can hold (an
    # integer rare_category_min_rows) plans and computes as before; an eda.quality result of
    # an earlier engine only lacks the two additive keys (the WP-F1 precedent of ADR 0007).
    # Attested from the digests of the attested engines: those of 10c1e70 (= ba4819c) for
    # every module, and the earlier fit and families digests of 818995c and 506180a, each
    # only after the byte comparison of that engine matched (governance, eda, policy,
    # regression and objective have the same bytes at all three). Not attested:
    # predictor.capture (its ids hash the code fingerprint, and the recipe and the runtime
    # changed: an existing capture is no longer current, risk K3 accepted by the owner, D19).
    {
        'module': 'mlkit.study.governance',
        'from_sha256': '09af3783c18fd7947b6f979a24a5266cca85ca576e69c8ee6a233e6e2e6fa413',
        'to_sha256': '9c86f512c9a3beafe0d37f477a71e669555eb639c4e97b78155223b833ed4c77',
        'activities': ['fit.logistic', 'fit.linear', 'fit.variant', 'final_test.evaluation',
                       'diag.binary', 'diag.regression'],
        'reason': ('L8 (R6) accepts a mapping {column: min_rows} as rare_category_min_rows and '
                   'adds its readers; an integer, the only form an existing study holds, is '
                   'checked and read as before.'),
        'evidence': ['framework/tests/study/test_code_compat_l8.py',
                     'framework/tests/study/code_compat_evidence.py',
                     'framework/tests/study/test_rare_per_column.py',
                     _L8_EVIDENCE],
    },
    {
        'module': 'mlkit.study.eda',
        'from_sha256': '45d9aea4b6cb8e83f27025665734a93e0cecf30a37e8903c3ea4b711ce85157e',
        'to_sha256': '9d419bd785382586e5edd3f8cefbae3edbd6fd5506629a5173816aa884e2539b',
        'activities': ['eda.target_rate', 'eda.special_values', 'eda.rate_by',
                       'eda.target_summary', 'eda.mean_by', 'eda.distribution', 'eda.quality',
                       'eda.single_feature_signal'],
        'reason': ('L8 (R5) adds the keys quantiles and skewness to each numeric range of '
                   'eda.quality; every other value of every EDA activity is unchanged, and an '
                   'earlier quality result only lacks the two additive keys.'),
        'evidence': ['framework/tests/study/test_code_compat_l8.py',
                     'framework/tests/study/code_compat_evidence.py',
                     'framework/tests/study/test_quality_quantiles.py',
                     _L8_EVIDENCE],
    },
    {
        'module': 'mlkit.study.fit',
        'from_sha256': '9ca62f79a0cb335374beb1c8047cd34047bd4456a192f300282e269f1979c8f7',
        'to_sha256': '49981afe99bb73270f2fd71cb2948b9d44eb22136e9b44b3120358a9656bec98',
        'activities': ['fit.baseline', 'fit.logistic', 'fit.linear', 'eda.single_feature_signal',
                       'fit.variant', 'final_test.evaluation', 'diag.binary', 'diag.regression'],
        'reason': ('L8 applies rare_category_min_rows per column (an integer still to every '
                   'categorical column) and reports each outer fold to progress.step, a no-op '
                   'without run --progress; a study of the 10c1e70 engine (fit.py unchanged since '
                   'ce82ca9) fits and evaluates as before.'),
        'evidence': ['framework/tests/study/test_code_compat_l8.py',
                     'framework/tests/study/code_compat_evidence.py',
                     'framework/tests/study/libraries/test_rare_per_column_runtime.py',
                     _L8_EVIDENCE],
    },
    {
        'module': 'mlkit.study.fit',
        'from_sha256': 'd39f3f5bfbc0927c79af7371b8358b9b4d72892b869c2ed726498a798a744579',
        'to_sha256': '49981afe99bb73270f2fd71cb2948b9d44eb22136e9b44b3120358a9656bec98',
        'activities': ['fit.baseline', 'fit.logistic', 'fit.linear', 'eda.single_feature_signal',
                       'fit.variant', 'final_test.evaluation', 'diag.binary', 'diag.regression'],
        'reason': ('L8 applies rare_category_min_rows per column (an integer still to every '
                   'categorical column) and reports each outer fold to progress.step, a no-op '
                   'without run --progress; a study of the 818995c engine (fit.py of 621d607 to '
                   '818995c) fits and evaluates as before.'),
        'evidence': ['framework/tests/study/test_code_compat_l8.py',
                     'framework/tests/study/code_compat_evidence.py',
                     'framework/tests/study/libraries/test_rare_per_column_runtime.py',
                     _L8_EVIDENCE],
    },
    {
        'module': 'mlkit.study.fit',
        'from_sha256': '28c00840fe9f9a5c17d0e9a0d483cd7dbdc9ed2cc4d715a8f65073399d989161',
        'to_sha256': '49981afe99bb73270f2fd71cb2948b9d44eb22136e9b44b3120358a9656bec98',
        'activities': ['fit.baseline', 'fit.logistic', 'fit.linear', 'eda.single_feature_signal',
                       'fit.variant', 'final_test.evaluation', 'diag.binary', 'diag.regression'],
        'reason': ('L8 applies rare_category_min_rows per column (an integer still to every '
                   'categorical column) and reports each outer fold to progress.step, a no-op '
                   'without run --progress; a study of the 506180a engine fits and evaluates as '
                   'before.'),
        'evidence': ['framework/tests/study/test_code_compat_l8.py',
                     'framework/tests/study/code_compat_evidence.py',
                     'framework/tests/study/libraries/test_rare_per_column_runtime.py',
                     _L8_EVIDENCE],
    },
    {
        'module': 'mlkit.study.families',
        'from_sha256': '4e207920618b1a59da54d1a66066a22c771a276795012931a4aa74f9a78a3f00',
        'to_sha256': 'cc9f13d151e5fe985707a968254bacfa46ba3e538ff7a82ff0d5dfe266833eda',
        'activities': ['fit.variant', 'final_test.evaluation'],
        'reason': ('L8 reports each value of an inner tuning grid to progress.step, a no-op '
                   'without run --progress; in a study of the 10c1e70 engine (families.py '
                   'unchanged since ce82ca9) the inner cross-validation chooses and fits as '
                   'before.'),
        'evidence': ['framework/tests/study/test_code_compat_l8.py',
                     'framework/tests/study/code_compat_evidence.py',
                     _L8_EVIDENCE],
    },
    {
        'module': 'mlkit.study.families',
        'from_sha256': '2d8748798498388525c94ef85f8d73779b2a0c5d3145270e32d67cbbfc860e85',
        'to_sha256': 'cc9f13d151e5fe985707a968254bacfa46ba3e538ff7a82ff0d5dfe266833eda',
        'activities': ['fit.variant', 'final_test.evaluation'],
        'reason': ('L8 reports each value of an inner tuning grid to progress.step, a no-op '
                   'without run --progress; in a study of the 818995c and 506180a engines the '
                   'inner cross-validation chooses and fits as before.'),
        'evidence': ['framework/tests/study/test_code_compat_l8.py',
                     'framework/tests/study/code_compat_evidence.py',
                     _L8_EVIDENCE],
    },
    {
        'module': 'mlkit.study.policy',
        'from_sha256': '5bd077037ff250399e8058780419caaa3f1488a3cd8025b5d8b3d948ab109ed1',
        'to_sha256': '6b1d050040a77235b8ce47886c863a0efd02400da7a887662d8bf87c66233c8a',
        'activities': ['policy.evaluation', 'policy.inspect', 'final_test.evaluation',
                       'diag.binary', 'diag.final_test'],
        'reason': ('L8 reports each bootstrap replicate to progress.step, a no-op without run '
                   '--progress; the resamples and the intervals are unchanged.'),
        'evidence': ['framework/tests/study/test_code_compat_l8.py',
                     'framework/tests/study/code_compat_evidence.py',
                     _L8_EVIDENCE],
    },
    {
        'module': 'mlkit.study.regression',
        'from_sha256': '3d48d0912580fcd8cb0837da51c3bef5dbdc0092267bc9fa6f955e969915db21',
        'to_sha256': 'c7e0677a68608ad21cb28764cae5dfafc396c5f3c07f6f3f2ff6420e105dfd07',
        'activities': ['fit.baseline', 'fit.linear', 'evaluate.regression', 'fit.variant',
                       'final_test.evaluation', 'diag.regression', 'diag.final_test'],
        'reason': ('L8 reports each bootstrap replicate to progress.step, a no-op without run '
                   '--progress; the resamples and the intervals are unchanged.'),
        'evidence': ['framework/tests/study/test_code_compat_l8.py',
                     'framework/tests/study/code_compat_evidence.py',
                     _L8_EVIDENCE],
    },
    {
        'module': 'mlkit.study.objective',
        'from_sha256': '130a6184006f915880dfb1451437b5ebe5bf5cc0847105a02befa0f603794318',
        'to_sha256': '917cd720307df2e0b61c1e5476ce91ff24df95995887bf123606921c0cc47a71',
        'activities': ['fit.baseline', 'fit.logistic', 'policy.evaluation', 'policy.inspect',
                       'fit.linear', 'evaluate.regression', 'fit.variant', 'final_test.evaluation'],
        'reason': ('L8 reports each replicate of the paired row bootstrap to progress.step, a '
                   'no-op without run --progress; the resamples and the intervals are unchanged.'),
        'evidence': ['framework/tests/study/test_code_compat_l8.py',
                     'framework/tests/study/code_compat_evidence.py',
                     _L8_EVIDENCE],
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
