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


def export_azureml(study, *, expected_revision, out=None, profile_path=None,
                   template_id: str = DEFAULT_TEMPLATE, plan: bool = False,
                   require_configured: bool = False,
                   reader: Callable | None = None) -> tuple[dict, int]:
    """``(payload, exit code)`` of one export or plan; refusals raise :class:`ExportError`."""
    if not plan and guard.read_only():
        raise ExportError('read_only', f'{guard.ENV}=1: a read-only process writes no file.',
                          path='out', remediation='Use --plan, or unset the variable.')
    if type(expected_revision) is not int or expected_revision < 0:
        raise ExportError('invalid_arguments', '--expected-revision must be a revision number.',
                          path='expected_revision',
                          remediation='Read the revision with hypotrail status first.')
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
    snap = sn.build(source, template_capabilities=template.document['capabilities'],
                    verify_predictor=artifact.verify_predictor)
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
