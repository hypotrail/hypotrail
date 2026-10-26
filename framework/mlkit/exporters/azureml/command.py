"""``hypotrail export azureml``: a study as a project in the team's Azure ML template.

    hypotrail export azureml --study DIR --expected-revision REV
        [--template team-azureml-v1] [--profile FILE] [--require-configured]
        (--out DIR | --plan) [--json]

The export reads one consistent revision through chantier A's ``read_export_source``; it
never fits, never evaluates, never reads the final test, never contacts Azure, and never
changes the study (no state, event, exposure or channel record). ``--plan`` lists the files,
statuses and missing fields without writing. Without a complete profile the project is a
``draft``; ``--require-configured`` then refuses, writing nothing. The payload is
``hypotrail.azureml_export/1``; a refusal is ``hypotrail.error/1`` with exit code 2.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

from mlkit.study import guard

from . import artifact, layout, profile as pf, render, snapshot as sn, writer
from .errors import ExportError

SCHEMA = 'hypotrail.azureml_export/1'
PAYLOAD_KEYS = ('schema', 'ok', 'plan', 'study_revision', 'snapshot_id', 'export_id', 'out',
                'template', 'files', 'configuration_status', 'artifact_status', 'checks',
                'missing_fields', 'warnings', 'next_commands')
DEFAULT_TEMPLATE = 'team-azureml-v1'


def _next_commands(configured: bool, artifact_status: str) -> list[dict]:
    module = 'python -m src.pipeline.utils.project'
    out = [{'command': f'{module} validate --offline', 'scope': 'local',
            'purpose': 'check the folder: checksums, Hydra freeze, Azure YAML graph, upload, '
                       'model parity'}]
    if artifact_status != 'missing':
        out.append({'command': f'{module} predict --parity --output outputs/predictions.json',
                    'scope': 'local', 'purpose': 'predict with the evaluated model; no fit'})
    out += [{'command': f'{module} materialize --source <original dataset file>',
             'scope': 'local', 'purpose': 'extract the development rows (no final-test row)'},
            {'command': f'{module} run-local --mode rebuild_final_candidate', 'scope': 'local',
             'purpose': 'fit a new candidate; it does not inherit the verdict'}]
    if configured:
        out += [{'command': f'{module} preflight --execute', 'scope': 'network_read',
                 'purpose': 'read the Azure resources named by the profile'},
                {'command': f'{module} submit --execute --wait', 'scope': 'azure_write',
                 'purpose': 'create the assets and submit one pipeline job'}]
    return out


def current_revision(study) -> int | None:
    """The revision of the study at ``study``, read-only (no lock, nothing written), or None
    when the folder holds no readable study."""
    from mlkit.study import read
    from mlkit.study.errors import StudyError
    try:
        revision = read.load_state(study).get('revision')
    except (StudyError, OSError, ValueError):
        return None
    return revision if type(revision) is int else None


def _revision_refusal(study, value) -> ExportError:
    """R18 (L7, D16): ``--expected-revision`` missing or malformed. The flag is required
    (the export reads exactly one revision); the refusal names the study and its current
    revision, so the user can pass it without another command."""
    study = os.path.abspath(study)
    current = current_revision(study)
    if value is None:
        if current is None:
            message = (f'--expected-revision is required, and {study} holds no readable study: '
                       'check the --study folder.')
        else:
            message = (f'--expected-revision is required: the study at {study} is at revision '
                       f'{current}; add --expected-revision {current}.')
        reason = 'missing'
    else:
        message = '--expected-revision must be a revision number.'
        reason = 'malformed'
    remediation = (f'Add --expected-revision {current} (the revision read now; a later change '
                   'is refused as stale_revision).' if current is not None else
                   'Check the --study folder, then read its revision with hypotrail status.')
    return ExportError('invalid_arguments', message, path='expected_revision',
                       remediation=remediation,
                       details={'reason': reason, 'current_revision': current,
                                'study': study})


# R18 (L7): the refusals that a wrong --study folder produces name the folder and revision.
NAMED_STUDY_CODES = ('model_not_captured', 'capability_not_supported')


def _naming_the_study(error: ExportError, study, revision: int) -> ExportError:
    """``error`` with the study path and revision in its message and details when it is a
    refusal of :data:`NAMED_STUDY_CODES`; unchanged otherwise (code, path and remediation
    are kept)."""
    if error.code not in NAMED_STUDY_CODES:
        return error
    details = {k: v for k, v in error.details.items() if k not in ('path', 'remediation')}
    study = os.path.abspath(study)
    details.update(study=study, study_revision=revision)
    return ExportError(error.code, f'{error.message} (Study: {study}, revision {revision}.)',
                       path=error.details.get('path'),
                       remediation=error.details.get('remediation'), details=details)


def export_azureml(study, *, expected_revision, out=None, profile_path=None,
                   template_id: str = DEFAULT_TEMPLATE, plan: bool = False,
                   require_configured: bool = False,
                   reader: Callable | None = None) -> tuple[dict, int]:
    """``(payload, exit code)`` of one export or plan; refusals raise :class:`ExportError`."""
    if not plan and guard.read_only():
        raise ExportError('read_only', f'{guard.ENV}=1: a read-only process writes no file.',
                          path='out', remediation='Use --plan, or unset the variable.')
    if type(expected_revision) is not int or expected_revision < 0:
        raise _revision_refusal(study, expected_revision)
    template = layout.load(template_id)
    normal, missing = pf.validate(pf.load(profile_path) if profile_path else None)
    if require_configured and missing:
        raise ExportError('contract_invalid', 'The profile misses required destination fields; '
                          'nothing was written.', path='profile',
                          remediation='Complete the profile, or export a draft without '
                                      '--require-configured.',
                          details={'reason': 'profile_incomplete', 'missing_fields': missing})
    study_dir = Path(study)
    destination = None if plan else writer.target(out, study_dir)
    source = sn.read_source(study_dir, expected_revision, reader)
    try:
        snap = sn.build(source, template_capabilities=template.document['capabilities'],
                        verify_predictor=artifact.verify_predictor)
    except ExportError as error:
        raise _naming_the_study(error, study_dir, expected_revision) from None
    files, summary = render.render(snap, normal, missing, template)
    if not plan:
        writer.publish(files, template.document['directories'], destination, template)
    ready = summary['readiness']
    configured = ready['configuration'] == 'configured'
    warnings = list(snap.warnings)
    if not configured:
        warnings.append('draft_not_ready_to_submit')
    if summary['lock_status'] != 'pinned':
        warnings.append('model_environment_missing')
    payload = {
        'schema': SCHEMA, 'ok': True, 'plan': plan,
        'study_revision': snap.document['study_revision'],
        'snapshot_id': summary['identities']['snapshot_id'],
        'export_id': summary['identities']['export_id'],
        'out': None if destination is None else str(destination),
        'template': {'id': template.id, 'version': template.version, 'sha256': template.sha256},
        'files': [{'path': f.path, 'kind': f.kind, 'sha256': f.sha256, 'bytes': len(f.data)}
                  for f in files],
        'configuration_status': ready['configuration'],
        'artifact_status': ready['artifact'],
        'checks': snap.checks + [{'id': 'layout_conforms', 'status': 'passed' if not plan
                                  else 'not_run'},
                                 {'id': 'azure_qualification', 'status': 'not_run',
                                  'detail': 'Generated files are not an Azure run.'}],
        'missing_fields': missing,
        'warnings': warnings,
        'next_commands': _next_commands(configured, ready['artifact']),
    }
    return {k: payload[k] for k in PAYLOAD_KEYS}, 0
