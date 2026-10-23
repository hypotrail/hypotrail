"""Stable error codes of the shared contract v1 (CONTRAT-COMMUN-v1 §8).

Every refusal carries ``code`` (stable, never translated), ``path`` (where in the document
or the call), ``message`` (explanatory, localisable) and ``remediation`` (the useful next
action), plus bounded ``details`` without secrets. A raw traceback is never the only
message.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

CODES = (
    'contract_invalid', 'schema_version_unsupported', 'stale_revision',
    'partition_not_authorized', 'calibration_not_eligible', 'capability_not_supported',
    'optional_dependency_missing', 'backend_failed', 'model_not_captured',
    'artifact_integrity_failed', 'environment_unqualified', 'scientific_config_changed',
    'template_layout_mismatch', 'destination_not_empty',
)
# A shown list never grows without bound (details are bounded).
MAX_ISSUES = 20
MAX_DETAIL_TEXT = 400


def _bounded(value: Any, depth: int = 0) -> Any:
    if depth > 4:
        return '…'
    if isinstance(value, str):
        return value if len(value) <= MAX_DETAIL_TEXT else value[:MAX_DETAIL_TEXT] + '…'
    if isinstance(value, Mapping):
        return {str(k): _bounded(v, depth + 1) for k, v in list(value.items())[:MAX_ISSUES]}
    if isinstance(value, (list, tuple)):
        return [_bounded(v, depth + 1) for v in list(value)[:MAX_ISSUES]]
    if isinstance(value, float) and value != value:
        return None
    return value


class ContractError(Exception):
    """A refusal of the v1 contract. ``issues`` lists every problem found (bounded)."""

    def __init__(self, code: str, message: str, *, path: str = '', remediation: str = '',
                 details: Mapping | None = None, issues: Iterable[Mapping] = ()):
        if code not in CODES:
            raise ValueError(f'unknown contract error code {code!r}')
        super().__init__(message)
        self.code = code
        self.path = path
        self.message = message
        self.remediation = remediation
        self.details = _bounded(dict(details or {}))
        self.issues = [_bounded(dict(i)) for i in list(issues)[:MAX_ISSUES]]

    def to_dict(self) -> dict:
        out = {'code': self.code, 'path': self.path, 'message': self.message,
               'remediation': self.remediation, 'details': self.details}
        if self.issues:
            out['issues'] = self.issues
        return out

    def __str__(self) -> str:      # pragma: no cover - display only
        return f'{self.code} at {self.path or "<document>"}: {self.message}'


def from_pydantic(exc, *, schema: str) -> ContractError:
    """Map a ``pydantic.ValidationError`` to one ``contract_invalid`` with readable issues
    (no Pydantic object leaves this function)."""
    issues = []
    for err in exc.errors(include_url=False, include_input=False):
        path = '/'.join(str(p) for p in err.get('loc', ()))
        issues.append({'code': 'contract_invalid', 'path': path, 'type': err.get('type'),
                       'message': err.get('msg')})
    first = issues[0] if issues else {'path': '', 'message': 'invalid document'}
    return ContractError(
        'contract_invalid',
        f'The document does not satisfy {schema}: {first["message"]} at '
        f'{first["path"] or "<root>"}' + (f' (and {len(issues) - 1} more)' if len(issues) > 1
                                          else ''),
        path=first['path'],
        remediation='Correct the listed fields; types are strict (a string "3" or a boolean '
                    'is not an integer, NaN and infinity are refused, unknown fields are '
                    'refused outside "extensions").',
        details={'schema': schema, 'n_issues': len(issues)}, issues=issues)
