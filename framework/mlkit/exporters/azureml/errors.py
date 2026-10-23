"""Refusals of ``hypotrail export azureml`` (contract v1 §8, export spec §05).

An :class:`ExportError` is a :class:`mlkit.study.errors.StudyError`, so the CLI answers it
in the ``hypotrail.error/1`` format with exit code 2 and nothing written. Its ``details``
always carry ``path`` (the field or file concerned, or null) and ``remediation`` (what to
do), the two fields contract v1 §8 adds to ``code`` and ``message``; other details are
bounded and never hold a secret.

Codes, and how they map onto the existing CLI codes (no existing code is reused with a
new meaning):

* existing codes kept: ``stale_revision`` (another revision than ``--expected-revision``),
  ``export_target_exists`` (contract ``destination_not_empty``: ``details.contract_code``
  names it), ``read_only``, ``invalid_arguments``;
* contract v1 §8: ``contract_invalid``, ``schema_version_unsupported``,
  ``capability_not_supported`` (the export spec's ``unsupported_export_capability``),
  ``optional_dependency_missing``, ``model_not_captured``, ``artifact_integrity_failed``,
  ``environment_unqualified``, ``scientific_config_changed``, ``template_layout_mismatch``;
* export spec §05: ``template_unsupported``, ``data_identity_mismatch``.
"""
from __future__ import annotations

from mlkit.study.errors import StudyError

CODES = ('stale_revision', 'export_target_exists', 'read_only', 'invalid_arguments',
         'contract_invalid', 'schema_version_unsupported', 'capability_not_supported',
         'optional_dependency_missing', 'model_not_captured', 'artifact_integrity_failed',
         'environment_unqualified', 'scientific_config_changed', 'template_layout_mismatch',
         'template_unsupported', 'data_identity_mismatch')
# Contract v1 §8 names whose CLI code is an older one.
CONTRACT_ALIASES = {'destination_not_empty': 'export_target_exists'}
MAX_DETAIL_ITEMS = 20


class ExportError(StudyError):
    """A refusal of the export, with nothing written."""

    def __init__(self, code: str, message: str, *, path: str | None = None,
                 remediation: str | None = None, details: dict | None = None):
        contract_code = None
        if code in CONTRACT_ALIASES:
            contract_code, code = code, CONTRACT_ALIASES[code]
        if code not in CODES:
            raise ValueError(f'unknown export error code {code!r}')
        bounded = {k: (v[:MAX_DETAIL_ITEMS] if isinstance(v, list) else v)
                   for k, v in (details or {}).items()}
        bounded = {'path': path, 'remediation': remediation, **bounded}
        if contract_code:
            bounded['contract_code'] = contract_code
        super().__init__(code, message, details=bounded)
        self.path, self.remediation = path, remediation


def from_packaging(error) -> ExportError:
    """An :class:`ExportError` of a packager refusal (same code and fields)."""
    return ExportError(error.code, error.message, path=error.path,
                       remediation=error.remediation, details=error.details)
