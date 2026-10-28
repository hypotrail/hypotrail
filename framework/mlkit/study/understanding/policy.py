"""The understanding policy ``hypotrail.understanding-policy/1`` (SPEC §05, §06).

A policy is a closed JSON document. Every field that can change a verdict enters
``policy_digest`` (canonical JSON v1 of the whole document); there is no global numeric
threshold. Validation refuses, never repairs:

* ``minimum_assurance: external_verified`` is ``unsupported_assurance`` (no tested external
  attestation adapter exists); it is never lowered to ``human_declared``;
* ``evidence_retention: {"purge_after_days": N}`` is ``unsupported_capability`` (v1 keeps
  evidence durably and has no purge);
* a milestone other than ``handoff`` is ``policy_invalid`` (``handoff`` is the only
  protected action the engine has; no deployment check is invented);
* an unknown key, a missing key or an inconsistent set is ``policy_invalid``.

A study without policy is ``off``. ``coaching`` gives the same tools without blocking;
``required`` blocks the named milestones only. The policy is a cooperative local control:
whoever can change the repository or the state can bypass it.
"""
from __future__ import annotations

import re
from typing import Any, Mapping

from . import DIMENSIONS, canonical, refuse

SCHEMA = 'hypotrail.understanding-policy/1'
MODES = ('off', 'coaching', 'required')
MILESTONES = ('handoff',)
ASSURANCES = ('human_declared', 'external_verified')
SUPPORTED_ASSURANCE = 'human_declared'
ASSISTANCE = ('unaided_required', 'aided_allowed')
EVIDENCE_REQUIREMENTS = ('payloads_available', 'recorded_decisions')
CONTEXT_REQUIREMENTS = ('complete', 'public_only')
KEYS = ('schema', 'policy_id', 'version', 'mode', 'milestones', 'required_dimensions',
        'responsibility_profiles', 'critical_dimensions', 'peer_required_dimensions',
        'minimum_assurance', 'assistance_rule', 'expiration_rule', 'evidence_retention',
        'evidence_requirement', 'context_requirement', 'export_policy', 'exemptions_policy',
        'team_coverage', 'role_policy')
ASSISTANCE_KEYS = ('critical', 'other')
EXPORT_KEYS = ('include_excerpts', 'include_contacts', 'external_sources')
EXEMPTION_KEYS = ('waivers_allowed',)
TEAM_KEYS = ('minimum_people',)
ROLE_KEYS = ('arbiters',)
SLUG = re.compile(r'[a-z][a-z0-9_-]{0,63}')
DATE = re.compile(r'\d{4}-\d{2}-\d{2}')
MAX_PROFILES = 16

OFF = {'mode': 'off'}


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _invalid(message: str, **details):
    return refuse('policy_invalid', message, 'Correct the policy file and apply it again with '
                  '`hypotrail understanding policy set`.', **details)


def _keys(doc: Any, keys: tuple, path: str) -> None:
    if not isinstance(doc, Mapping):
        raise _invalid(f'{path or "policy"} must be an object.', field=path)
    missing = [k for k in keys if k not in doc]
    extra = sorted(k for k in doc if k not in keys)
    if missing or extra:
        raise _invalid(f'{path or "policy"} has missing or unknown keys.', field=path,
                       missing=missing, unknown=extra)


def _dims(value, field: str, allowed=DIMENSIONS) -> list:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value) \
            or any(v not in allowed for v in value) \
            or len(set(value)) != len(value):
        raise _invalid(f'{field} must be a list of distinct dimension ids among '
                       f'{", ".join(allowed)}.', field=field)
    return value


def _bool(value, field: str) -> None:
    if not isinstance(value, bool):
        raise _invalid(f'{field} must be true or false.', field=field)


def validate(doc: Any) -> dict:
    """Return the policy when it is valid; refuse otherwise (see the module docstring)."""
    try:
        return _validate(doc)
    except (TypeError, KeyError, AttributeError) as exc:
        raise _invalid(f'A field has the wrong shape ({exc.__class__.__name__}).') from None


def _validate(doc: Any) -> dict:
    if isinstance(doc, Mapping) and doc.get('schema') not in (None, SCHEMA):
        raise _invalid(f'Unknown policy schema {doc.get("schema")!r}; this engine reads '
                       f'{SCHEMA}.', field='schema')
    _keys(doc, KEYS, '')
    if not isinstance(doc['policy_id'], str) or not SLUG.fullmatch(doc['policy_id']):
        raise _invalid('policy_id must be a short lowercase identifier.', field='policy_id')
    if not _is_int(doc['version']) or doc['version'] < 1:
        raise _invalid('version must be a positive integer.', field='version')
    if doc['mode'] not in MODES:
        raise _invalid(f'mode must be one of {", ".join(MODES)}.', field='mode')
    milestones = doc['milestones']
    if not isinstance(milestones, list) or len(set(milestones)) != len(milestones):
        raise _invalid('milestones must be a list of distinct names.', field='milestones')
    unknown = [m for m in milestones if m not in MILESTONES]
    if unknown:
        raise _invalid('Only the handoff milestone exists in this engine; other milestone '
                       'names are refused rather than checked by a control that does not '
                       'exist.', field='milestones', unsupported=unknown)
    required = _dims(doc['required_dimensions'], 'required_dimensions')
    profiles = doc['responsibility_profiles']
    if not isinstance(profiles, Mapping) or not profiles or len(profiles) > MAX_PROFILES:
        raise _invalid('responsibility_profiles must map one to sixteen profile names to '
                       'dimensions.', field='responsibility_profiles')
    for name, dims in profiles.items():
        if not SLUG.fullmatch(name):
            raise _invalid('A profile name must be a short lowercase identifier.',
                           field=f'responsibility_profiles/{name}')
        _dims(dims, f'responsibility_profiles/{name}', tuple(required))
    _dims(doc['critical_dimensions'], 'critical_dimensions', tuple(required))
    _dims(doc['peer_required_dimensions'], 'peer_required_dimensions', tuple(required))
    if doc['minimum_assurance'] not in ASSURANCES:
        raise _invalid(f'minimum_assurance must be one of {", ".join(ASSURANCES)}.',
                       field='minimum_assurance')
    if doc['minimum_assurance'] != SUPPORTED_ASSURANCE:
        raise refuse('unsupported_assurance',
                     'external_verified needs an external attestation adapter; none is '
                     'implemented and tested in this version, so the policy is refused '
                     'instead of being lowered to human_declared.',
                     'Use minimum_assurance human_declared, or enforce the milestone with a '
                     'trusted external system.', field='minimum_assurance',
                     supported=[SUPPORTED_ASSURANCE])
    _keys(doc['assistance_rule'], ASSISTANCE_KEYS, 'assistance_rule')
    for k in ASSISTANCE_KEYS:
        if doc['assistance_rule'][k] not in ASSISTANCE:
            raise _invalid(f'assistance_rule/{k} must be one of {", ".join(ASSISTANCE)}.',
                           field=f'assistance_rule/{k}')
    rule = doc['expiration_rule']
    if not isinstance(rule, Mapping) or rule.get('kind') not in ('none', 'until') or (
            rule['kind'] == 'none' and set(rule) != {'kind'}) or (
            rule['kind'] == 'until' and (set(rule) != {'kind', 'date'}
                                         or not isinstance(rule['date'], str)
                                         or not DATE.fullmatch(rule['date']))):
        raise _invalid('expiration_rule is {"kind": "none"} or {"kind": "until", "date": '
                       '"YYYY-MM-DD"}; time alone does not stale a review by default.',
                       field='expiration_rule')
    retention = doc['evidence_retention']
    if isinstance(retention, Mapping) and 'purge_after_days' in retention:
        raise refuse('unsupported_capability',
                     'purge_after_days is not implemented: version 1 keeps the evidence '
                     'durably and has no automatic purge. The request is refused, not '
                     'ignored.', 'Use evidence_retention "durable".',
                     field='evidence_retention', reason='not_implemented')
    if retention != 'durable':
        raise _invalid('evidence_retention must be "durable" in version 1.',
                       field='evidence_retention')
    if doc['evidence_requirement'] not in EVIDENCE_REQUIREMENTS:
        raise _invalid('evidence_requirement must be payloads_available or recorded_decisions.',
                       field='evidence_requirement')
    if doc['context_requirement'] not in CONTEXT_REQUIREMENTS:
        raise _invalid('context_requirement must be complete or public_only.',
                       field='context_requirement')
    _keys(doc['export_policy'], EXPORT_KEYS, 'export_policy')
    _bool(doc['export_policy']['include_excerpts'], 'export_policy/include_excerpts')
    _bool(doc['export_policy']['include_contacts'], 'export_policy/include_contacts')
    if doc['export_policy']['external_sources'] not in ('allowed', 'forbidden'):
        raise _invalid('export_policy/external_sources must be allowed or forbidden.',
                       field='export_policy/external_sources')
    _keys(doc['exemptions_policy'], EXEMPTION_KEYS, 'exemptions_policy')
    _bool(doc['exemptions_policy']['waivers_allowed'], 'exemptions_policy/waivers_allowed')
    _keys(doc['team_coverage'], TEAM_KEYS, 'team_coverage')
    n = doc['team_coverage']['minimum_people']
    if not _is_int(n) or not 2 <= n <= 10:
        raise _invalid('team_coverage/minimum_people must be an integer from 2 to 10 (two '
                       'distinct declared people, the author included, is the design '
                       'minimum).', field='team_coverage/minimum_people')
    _keys(doc['role_policy'], ROLE_KEYS, 'role_policy')
    arbiters = doc['role_policy']['arbiters']
    if arbiters != 'any_declared' and not (
            isinstance(arbiters, list) and arbiters
            and all(isinstance(a, str) and SLUG.fullmatch(a) for a in arbiters)):
        raise _invalid('role_policy/arbiters is "any_declared" or a list of declared ids.',
                       field='role_policy/arbiters')
    if doc['mode'] == 'required' and not milestones:
        raise _invalid('A required policy names at least one milestone.', field='milestones')
    if doc['mode'] == 'required' and (not required or not all(profiles.values())):
        raise _invalid('A required policy requires something: required dimensions, and at '
                       'least one dimension per responsibility profile.',
                       field='required_dimensions')
    canonical.dumps(doc)
    return dict(doc)


def digest(doc: Mapping) -> str:
    return canonical.digest(doc)


def mode(doc: Mapping | None) -> str:
    return 'off' if not doc else doc['mode']


def author_dimensions(doc: Mapping, profile: str) -> list:
    """The dimensions the author covers for ``profile``: the profile's own plus every
    critical dimension (a critical scope never disappears because no profile chose it),
    in canonical order."""
    profiles = doc['responsibility_profiles']
    if profile not in profiles:
        raise refuse('policy_invalid', f'The policy has no responsibility profile {profile!r}.',
                     'Choose one of the profiles the policy lists.', field='profile',
                     profiles=sorted(profiles))
    chosen = set(profiles[profile]) | set(doc['critical_dimensions'])
    return [d for d in DIMENSIONS if d in chosen]


def limitations(doc: Mapping) -> list[str]:
    """The relaxations a policy allows, shown in every result (SPEC §05)."""
    out = ['assurance_human_declared', 'local_policy_cooperative']
    if doc.get('evidence_requirement') == 'recorded_decisions':
        out.append('recorded_decisions_accepted')
    if doc.get('context_requirement') == 'public_only':
        out.append('public_only_context')
    return out
