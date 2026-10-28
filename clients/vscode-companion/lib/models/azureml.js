'use strict';
// AzuremlPlanModel (lot P, owner request R49, ADR 0004 decision 14): the Azure ML export plan
// (`export azureml --plan --json`, `hypotrail.azureml_export/1`, CLI-CONTRACT §15), which
// lists the files the export would write and writes nothing. The panel shows it read only
// in "And after", next to W8 (the export itself, outside the study state).
//
// Kept: the template, the files (path, kind, bytes), their count per kind, the configuration
// and artifact statuses, the checks, the fields still to configure, the warning codes. Not
// kept: `next_commands` (some of them write to Azure; the panel never shows or runs a
// command that reaches the cloud) and the ids.

const { str, strOrNull, list, obj, int, expectSchema, plain } = require('./common');

const SCHEMA = 'hypotrail.azureml_export/1';

function toAzuremlPlanModel(payload) {
  const p = expectSchema(payload, SCHEMA);
  const files = list(p.files).filter(f => f && typeof f.path === 'string')
    .map(f => ({ path: f.path, kind: str(f.kind), bytes: int(f.bytes) }));
  const kinds = {};
  for (const f of files) kinds[f.kind] = (kinds[f.kind] || 0) + 1;
  const template = obj(p.template);
  return plain({
    revision: int(p.study_revision),
    plan: p.plan === true,
    out: strOrNull(p.out),
    template: { id: str(template.id), version: str(template.version) },
    files,
    kinds,
    configurationStatus: strOrNull(p.configuration_status),
    artifactStatus: strOrNull(p.artifact_status),
    checks: list(p.checks).filter(c => c && typeof c.id === 'string').map(c => ({ id: c.id, status: str(c.status) })),
    missingFields: list(p.missing_fields).map(str).filter(Boolean),
    warnings: list(p.warnings).map(str).filter(Boolean),
  });
}

const FIXTURES = ['captured/export.azureml.plan'];

module.exports = { toAzuremlPlanModel, FIXTURES, SCHEMA };
