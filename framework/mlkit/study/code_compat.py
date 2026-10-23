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
        'to_sha256': '4179e60b93eeb60d976a473c239a911bcc2d0398d3a53922519a026a9e48f9a3',
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
        'to_sha256': '4179e60b93eeb60d976a473c239a911bcc2d0398d3a53922519a026a9e48f9a3',
        'activities': ['diag.final_test'],
        'reason': ('Library integration v1 adds the predictor.capture and '
                   'diagnostics.population activities and a final-test branch taken only when '
                   'a capture is current; final-test diagnostic dispatch and values are '
                   'unchanged.'),
        'evidence': ['framework/tests/study/test_wp_b4_diagnostics.py',
                     'framework/tests/study/libraries/test_capture_final.py'],
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
