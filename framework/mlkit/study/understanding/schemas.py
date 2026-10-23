"""JSON Schemas of the exported review and of the policy (draft 2020-12), generated from the
closed field lists of :mod:`.export` and :mod:`.policy`.

``python -m mlkit.study.understanding.schemas`` rewrites ``schemas/*.schema.json``;
``--check`` fails when a committed schema differs. The schemas let external tools validate
an artefact; the engine and the verifier do not depend on a validation library and apply
:func:`mlkit.study.understanding.export.validate_review`, which also checks the rules a
schema cannot express (digests, rendering, approvals).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from . import DIMENSIONS, export as ex, policy as pol, snapshot as snap

DIR = Path(__file__).resolve().parent / 'schemas'
HEX64 = {'type': 'string', 'pattern': '^[0-9a-f]{64}$'}
ALIAS = {'type': 'string', 'pattern': '^[a-z][a-z0-9_-]{1,31}$'}


def _closed(props: dict, required=None) -> dict:
    return {'type': 'object', 'additionalProperties': False, 'properties': props,
            'required': list(required if required is not None else props)}


def _nullable(schema: dict) -> dict:
    return {'anyOf': [schema, {'type': 'null'}]}


def review_schema() -> dict:
    entry = _closed({'logical_key': {'type': 'string'}, 'path': _nullable({'type': 'string'}),
                     'role': {'enum': list(snap.ROLES)}, 'sha256': HEX64,
                     'ref': {'const': 'public_ref'}})
    scope = _closed({'schema': {'const': snap.PUBLIC_SCHEMA}, 'entries': {
        'type': 'array', 'items': entry}, 'omitted_private': {'type': 'array', 'items': _closed({
            'opaque_private_ref': {'type': 'string', 'pattern': '^opq-[0-9a-f]{24}$'},
            'role': {'enum': list(snap.ROLES)}})},
        'unreadable_sources': {'type': 'array', 'items': {'type': 'string'}}})
    dimension = _closed({
        'id': {'enum': list(DIMENSIONS)}, 'title': {'type': 'string'},
        'required': {'type': 'boolean'}, 'critical': {'type': 'boolean'},
        'status': {'enum': list(ex.STATUSES)}, 'freshness_at_export': {'enum': list(ex.FRESHNESS)},
        'criteria': {'type': 'array', 'items': _closed({
            'criterion_id': {'type': 'string'},
            'result': {'enum': ['met', 'not_met', 'not_applicable', 'uncertain']}})},
        'task_refs': {'type': 'array', 'items': {'type': 'string'}},
        'attempt_refs': {'type': 'array', 'items': {'type': 'string'}},
        'assistance_summary': {'enum': list(ex.ASSISTANCE)},
        'reviewer_alias': _nullable(ALIAS), 'human_review_ref': _nullable({'type': 'string'}),
        'rationale': _nullable({'type': 'string'}),
        'safe_evidence_refs': {'type': 'array', 'items': {'type': 'string'}},
        'dependency_keys': {'type': 'array', 'items': {'type': 'string'}},
        'evidence_availability': {'enum': list(ex.AVAILABILITY)},
        'next_step': {'type': 'string'}})
    dimension['if'] = {'properties': {'status': {'const': 'demonstrated'}}}
    dimension['then'] = {'properties': {'human_review_ref': {'type': 'string'}}}
    open_obj = {'type': 'object'}
    props = {
        'review_id': {'type': 'string', 'pattern': '^rv-[0-9a-f]{20}$'},
        'created_at': {'type': 'string'}, 'renderer_version': {'const': ex.RENDERER_VERSION},
        'privacy_review': _closed({'status': {'enum': ['pending', 'approved']},
                                   'required_contributors': {'type': 'array', 'items': ALIAS},
                                   'approvals': {'type': 'array', 'items': _closed({
                                       'approver_alias': ALIAS, 'approved_at': {'type': 'string'},
                                       'content_digest': HEX64})}}),
        'schema': {'const': ex.SCHEMA}, 'study_public_id': {'type': 'string'},
        'session_ref': {'type': 'string'}, 'public_source_scope': scope,
        'policy': {'$ref': 'understanding-policy-1.schema.json'}, 'policy_digest': HEX64,
        'tasks': {'type': 'array', 'items': open_obj},
        'rubrics': {'type': 'array', 'items': open_obj},
        'source_manifest': {'type': 'array', 'items': entry}, 'source_scope_digest': HEX64,
        'handover_content': _nullable(open_obj), 'handover_digest': _nullable(HEX64),
        'coverage_selection': _nullable(open_obj),
        'dimensions': {'type': 'array', 'items': dimension},
        'peer_coverage': {'type': 'array', 'items': open_obj},
        'decisions_summary': {'type': 'array', 'items': open_obj},
        'reservation_resolutions': {'type': 'array', 'items': open_obj},
        'known_gaps': {'type': 'array', 'items': _closed({'kind': {'type': 'string'},
                                                          'ref': {'type': 'string'}})},
        'limitations': {'type': 'array', 'items': {'type': 'string'}},
        'safe_evidence': {'type': 'array', 'items': {'type': 'string'}},
        'assurance': {'const': pol.SUPPORTED_ASSURANCE},
        'provenance': _closed({k: ({'type': 'integer'} if k.endswith('version')
                                   else _nullable({'type': 'string'}))
                               for k in ex.PROVENANCE_FIELDS})}
    out = _closed({k: props[k] for k in ex.REVIEW_FIELDS})
    out.update({'$schema': 'https://json-schema.org/draft/2020-12/schema',
                '$id': 'understanding-review-1.schema.json',
                'title': ex.SCHEMA,
                'description': 'An exported understanding and handover review. Numbers are '
                               'canonical JSON v1 (no raw float). A schema check is not an '
                               'integrity check: digests, rendering and approvals are '
                               'verified by `hypotrail understanding verify-export`.'})
    return out


def policy_schema() -> dict:
    dims = {'type': 'array', 'items': {'enum': list(DIMENSIONS)}, 'uniqueItems': True}
    props = {
        'schema': {'const': pol.SCHEMA}, 'policy_id': {'type': 'string',
                                                       'pattern': '^[a-z][a-z0-9_-]{0,63}$'},
        'version': {'type': 'integer', 'minimum': 1}, 'mode': {'enum': list(pol.MODES)},
        'milestones': {'type': 'array', 'items': {'enum': list(pol.MILESTONES)},
                       'uniqueItems': True},
        'required_dimensions': dims,
        'responsibility_profiles': {'type': 'object', 'additionalProperties': dims},
        'critical_dimensions': dims, 'peer_required_dimensions': dims,
        'minimum_assurance': {'const': pol.SUPPORTED_ASSURANCE},
        'assistance_rule': _closed({k: {'enum': list(pol.ASSISTANCE)}
                                    for k in pol.ASSISTANCE_KEYS}),
        'expiration_rule': {'oneOf': [
            _closed({'kind': {'const': 'none'}}),
            _closed({'kind': {'const': 'until'}, 'date': {'type': 'string', 'pattern':
                                                         r'^\d{4}-\d{2}-\d{2}$'}})]},
        'evidence_retention': {'const': 'durable'},
        'evidence_requirement': {'enum': list(pol.EVIDENCE_REQUIREMENTS)},
        'context_requirement': {'enum': list(pol.CONTEXT_REQUIREMENTS)},
        'export_policy': _closed({'include_excerpts': {'type': 'boolean'},
                                  'include_contacts': {'type': 'boolean'},
                                  'external_sources': {'enum': ['allowed', 'forbidden']}}),
        'exemptions_policy': _closed({'waivers_allowed': {'type': 'boolean'}}),
        'team_coverage': _closed({'minimum_people': {'type': 'integer', 'minimum': 2,
                                                     'maximum': 10}}),
        'role_policy': _closed({'arbiters': {'anyOf': [{'const': 'any_declared'}, {
            'type': 'array', 'items': {'type': 'string'}, 'minItems': 1}]}})}
    out = _closed({k: props[k] for k in pol.KEYS})
    out.update({'$schema': 'https://json-schema.org/draft/2020-12/schema',
                '$id': 'understanding-policy-1.schema.json', 'title': pol.SCHEMA,
                'description': 'external_verified and purge_after_days are refused by the '
                               'engine in version 1 (not implemented), never lowered.'})
    return out


def render() -> dict:
    return {'understanding-review-1.schema.json': review_schema(),
            'understanding-policy-1.schema.json': policy_schema()}


def _text(doc) -> str:
    return json.dumps(doc, indent=2, ensure_ascii=False, sort_keys=False) + '\n'


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    stale = []
    for name, doc in render().items():
        path = DIR / name
        if '--check' in argv:
            if not path.is_file() or path.read_text(encoding='utf-8') != _text(doc):
                stale.append(name)
        else:
            DIR.mkdir(exist_ok=True)
            path.write_text(_text(doc), encoding='utf-8')
    if stale:
        print('stale schemas: ' + ', '.join(stale))
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
