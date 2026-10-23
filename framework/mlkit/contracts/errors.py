"""Contract v1 errors as engine refusals (CONTRAT-COMMUN-v1 §8).

The engine keeps its frozen error codes and exit codes (``docs/specs/CLI-CONTRACT.md`` §2,
§7). A :class:`~hypotrail_runtime.errors.ContractError` reaching the CLI becomes the engine
code below; its stable v1 code is kept in ``details.contract_code`` with ``path`` and
``remediation``, so no v1 code collides with an engine code and no information is lost.
"""
from __future__ import annotations

from hypotrail_runtime.errors import CODES, ContractError

ENGINE_CODES = {
    'contract_invalid': 'invalid_value',
    'schema_version_unsupported': 'unsupported_capability',
    'stale_revision': 'stale_revision',
    'partition_not_authorized': 'precondition_missing',
    'calibration_not_eligible': 'precondition_missing',
    'capability_not_supported': 'unsupported_capability',
    'optional_dependency_missing': 'unsupported_capability',
    'backend_failed': 'internal_error',
    'model_not_captured': 'precondition_missing',
    'artifact_integrity_failed': 'integrity_error',
    'environment_unqualified': 'unsupported_capability',
    'scientific_config_changed': 'invalid_value',
    'template_layout_mismatch': 'invalid_value',
    'destination_not_empty': 'export_target_exists',
}
assert set(ENGINE_CODES) == set(CODES)


def to_study_error(exc: ContractError):
    from mlkit.study.errors import StudyError
    details = {'contract_code': exc.code, 'path': exc.path, 'remediation': exc.remediation,
               **exc.details}
    if exc.issues:
        details['issues'] = exc.issues
    return StudyError(ENGINE_CODES[exc.code], exc.message, details=details)
