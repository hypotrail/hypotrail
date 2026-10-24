"""Deterministic rendering of the team-azureml-v1 project (export spec §09, §16 I-05).

The generator is declarative: ``templates/team-azureml-v1/template.json`` lists every file
of the project with its kind, and this module computes each file's bytes from the snapshot,
the profile and the template store. No language model writes any file; no clock, absolute
path, user name or random value enters a rendered byte. Identical inputs give identical
bytes (the copied model files are byte copies of the captured bundle).

File kinds:

* ``preserved``: byte-identical to the team template (checked against the transport
  inventory's SHA-256 before use);
* ``adapted``: same path as in the team template, fixed new content (for example an inert
  ``cli-aliases.sh`` or steps that call the runtime);
* ``rendered``: a template file whose ``@@filter:name@@`` markers are replaced from the
  snapshot (``text``: raw, ``yaml``: a JSON scalar or flow value, valid YAML, ``py``: a
  Python literal, ``json``); an unknown marker refuses the export;
* ``added``: a new path from the layout allowlist, fixed content;
* ``shared``: a byte copy of a standalone generator module, so the project computes what
  the generator computed (``canonical``, ``projection``, ``transfer``, ``azure_yaml``,
  ``mlflow_packaging``);
* ``generated``: a JSON or text document built here (contracts, notebook, lock, manifest);
* ``copied``: the captured model's files and its runtime wheel.
"""
from __future__ import annotations

import importlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from . import azure_yaml, canonical as cj, layout, profile as pf, projection
from .errors import ExportError
from .snapshot import Snapshot

GENERATOR_VERSION = '1.0.0'
EXPORT_SCHEMA = 'hypotrail.export_manifest/1'
READINESS_SCHEMA = 'hypotrail.export_readiness/1'
MARKER = re.compile(r'@@([a-z]+):([a-z0-9_]+)@@')
MISSING = 'MISSING-'
OMEGACONF_MISSING = '???'
KINDS = ('preserved', 'adapted', 'rendered', 'added', 'shared', 'generated', 'copied')
MANIFEST_PATH = 'data/hypotrail/contracts/export-manifest.json'
SUMS_PATH = 'data/hypotrail/SHA256SUMS'
EVALUATED = 'data/hypotrail/models/evaluated/'
RUNTIME_DIR = 'aml/pipelines/training/runtime/'
LOCK_REQUIREMENT = re.compile(r'^([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s;#]+)\s*$')


@dataclass(frozen=True)
class File:
    path: str
    kind: str
    data: bytes

    @property
    def sha256(self) -> str:
        return cj.sha256_hex(self.data)


def _slug(text: str, sep: str = '_') -> str:
    out = re.sub(r'[^a-z0-9]+', sep, text.lower()).strip(sep)
    return out or 'study'


def _value(profile_value, field: str):
    return profile_value if profile_value is not None else f'{MISSING}{field.replace(".", "-")}'


def _yaml(value) -> str:
    return json.dumps(cj.normalise(value), ensure_ascii=False, sort_keys=True)


def _py(value, indent: int = 0) -> str:
    """A Python literal in the style of the team's ruff rules: double quotes, one item
    per line with a trailing comma."""
    value = cj.normalise(value) if indent == 0 else value
    pad, inner = '    ' * indent, '    ' * (indent + 1)
    if isinstance(value, dict):
        if not value:
            return '{}'
        items = ''.join(f'{inner}{json.dumps(k, ensure_ascii=False)}: {_py(v, indent + 1)},\n'
                        for k, v in value.items())
        return '{\n' + items + pad + '}'
    if isinstance(value, list):
        if not value:
            return '[]'
        return '[\n' + ''.join(f'{inner}{_py(v, indent + 1)},\n' for v in value) + pad + ']'
    if isinstance(value, bool) or value is None:
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    return repr(value)


FILTERS = {'text': lambda v: str(v), 'yaml': _yaml, 'json': _yaml, 'py': _py}


def _yaml_block(value, indent: int) -> str:
    """A non-empty mapping or list as block YAML under its key, indented by ``indent``."""
    import yaml
    dumped = yaml.safe_dump(cj.normalise(value), sort_keys=True, default_flow_style=False,
                            allow_unicode=True, width=1000)
    pad = ' ' * (indent + 2)
    return '\n' + '\n'.join(pad + line for line in dumped.rstrip('\n').split('\n'))


def substitute(text: str, context: Mapping, where: str) -> str:
    def one(match: re.Match) -> str:
        kind, name = match.groups()
        if kind not in FILTERS or name not in context:
            raise ExportError('template_layout_mismatch', f'Unknown template marker {match.group(0)}.',
                              path=where, remediation='The template and the generator disagree.')
        value = context[name]
        if kind == 'yaml' and isinstance(value, (dict, list)) and value:
            line = text[text.rfind('\n', 0, match.start()) + 1:match.start()]
            return _yaml_block(value, len(line) - len(line.lstrip(' ')))
        return FILTERS[kind](value)
    # A block value follows "key: ", whose space would be trailing whitespace.
    out = re.sub(r'[ \t]+\n', '\n', MARKER.sub(one, text))
    if '@@' in out:
        raise ExportError('template_layout_mismatch', 'A template marker was not replaced.',
                          path=where, remediation='The template and the generator disagree.')
    return out


# --- environment lock ------------------------------------------------------------------

def lock_bytes(template: layout.Template, snapshot: Snapshot) -> tuple[bytes, str]:
    """``(requirements.lock, status)``: the captured model's lock (chantier A) plus the
    template's qualified addendum (Hydra, OmegaConf, MLflow). A distribution pinned to two
    versions refuses the export (``environment_unqualified``)."""
    addendum = template.read(template.document['addendum_lock']).decode('utf-8')
    pins: dict[str, tuple[str, str]] = {}

    def take(text: str, origin: str) -> None:
        for number, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if not stripped or stripped.startswith('#'):
                continue
            match = LOCK_REQUIREMENT.match(stripped)
            if not match:
                raise ExportError('environment_unqualified',
                                  f'The {origin} lock has a line this template cannot pin.',
                                  path=f'{origin}:{number}',
                                  remediation='The lock must list name==version lines.')
            name = match.group(1).lower().replace('_', '-')
            if name in pins and pins[name][0] != match.group(2):
                raise ExportError('environment_unqualified',
                                  f'{name} is pinned to {pins[name][0]} ({pins[name][1]}) and '
                                  f'{match.group(2)} ({origin}).', path='requirements.lock',
                                  remediation='Qualify one environment for the model and the '
                                              'template before exporting.')
            pins[name] = (match.group(2), origin)

    status = 'model_environment_missing'
    if snapshot.predictor and snapshot.predictor.get('lock') is not None:
        take(snapshot.predictor['lock'].decode('utf-8'), 'model')
        status = 'pinned'
    take(addendum, 'template')
    header = ['# Generated by Hypotrail (team-azureml-v1): Python 3.13.',
              '# The model environment captured by the study, then the template addendum.']
    if status != 'pinned':
        header.append('# No captured model: the runtime dependencies of a model are not '
                      'pinned here.')
    lines = header + [f'{name}=={pins[name][0]}' for name in sorted(pins)]
    return ('\n'.join(lines) + '\n').encode('utf-8'), status


# --- the context of the markers --------------------------------------------------------

def _verdict(snapshot: Snapshot) -> str:
    conclusion = snapshot.document.get('conclusion')
    if isinstance(conclusion, Mapping) and conclusion.get('verdict'):
        text = f'`{conclusion["verdict"]}`'
        if conclusion.get('text'):
            text += f' ("{conclusion["text"]}")'
        return text + '. It applies to the evaluated model only.'
    return 'no conclusion is recorded; nothing here establishes a result.'


def context(snapshot: Snapshot, normal: Mapping, missing: list, template: layout.Template,
            identities: Mapping) -> dict:
    recipe, contract, plan = snapshot.recipe, snapshot.data_contract, snapshot.plan
    doc = snapshot.document
    case_id = (doc.get('case') or {}).get('id') or doc['study_id']
    project = f'hypotrail_{_slug(case_id)}'
    target = recipe['target']
    unit = target.get('unit')
    predictor = snapshot.predictor
    configured = not missing
    wheel = predictor['wheel'][0] if predictor and predictor.get('wheel') else None
    parity_rel = None
    if predictor:
        parity_rel = (predictor['bundle'].get('parity') or {}).get('features_path')
    columns = [c for c in contract['columns'] if isinstance(c, Mapping)]
    limitations = list(doc.get('limitations') or [])
    if not configured:
        limitations.append('Draft: the destination profile misses ' + ', '.join(missing) + '.')
    if not predictor:
        limitations.append('No captured model: the evaluated model is not in this export; '
                           'the recipe is, and run-local builds a new candidate from it.')
    limitations.append('Azure ML execution is not qualified by this export: it needs an '
                       'authorised recipe run in a workspace.')
    final = plan['final_test']
    return {
        'project_title': f'{doc.get("case", {}).get("title") or case_id} (Hypotrail export)',
        'project_name': project,
        'project_version': '0.1.0',
        'project_description': f'Azure ML project of Hypotrail study {doc["study_id"]}',
        'component_prefix': project,
        'display_suffix': ''.join(p.capitalize() for p in _slug(case_id).split('_')),
        'component_version': identities['export_id'][:16],
        'template_id': template.id, 'template_version': template.version,
        'template_source_sha256': template.layout['source_sha256'],
        'generator_version': GENERATOR_VERSION,
        'study_id': doc['study_id'], 'study_revision': doc['study_revision'],
        'study_revision_text': str(doc['study_revision']),
        'snapshot_id': identities['snapshot_id'], 'export_id': identities['export_id'],
        'configuration_status': 'configured' if configured else 'draft',
        'artifact_status': predictor['artifact_status'] if predictor else 'missing',
        'evidence_status': predictor['evidence_status'] if predictor else 'missing',
        'readiness_sentence': (
            'This folder is prepared for Azure ML; nothing was submitted, provisioned or '
            'deployed.' if configured else
            'This folder is a **draft**: the destination profile is incomplete, so the Azure '
            'commands refuse to run until it is exported again with a complete profile.'),
        'missing_fields_sentence': ('Missing profile fields: ' + ', '.join(f'`{m}`' for m in missing)
                                    + '.') if missing else 'Every profile field is resolved.',
        'verdict_sentence': _verdict(snapshot),
        'predict_sentence': ('Its outputs must match the captured parity outputs within the '
                             'declared tolerance.' if predictor else
                             'This export has no captured model, so predict refuses.'),
        'task': recipe['task'], 'family': recipe['family'], 'parameters': recipe['parameters'],
        'parameters_inline': json.dumps(recipe['parameters'], sort_keys=True),
        'features': recipe['features'], 'features_inline': ', '.join(f'`{f}`' for f in
                                                                   recipe['features']),
        'feature_types': recipe['feature_types'], 'preprocessing': recipe['preprocessing'],
        'seeds': recipe['seeds'], 'output_contract': recipe['output_contract'],
        'target': target, 'target_name': target['name'],
        'target_unit_suffix': f' (in {unit})' if unit else '',
        'metrics': snapshot.metrics,
        'selection_decision': recipe['selection_reference'].get('decision_id'),
        'selection_reference': recipe['selection_reference'],
        'method_contract_version': recipe['method_contract_version'],
        'runtime_api_version': recipe['runtime_api_version'],
        'protocol_id': plan['protocol_id'], 'keys_sha256': plan['keys_sha256'],
        'roles': [p['role'] for p in plan['partitions']],
        'roles_inline': ', '.join(f'`{p["id"]}`' for p in plan['partitions']),
        'n_development_rows': plan['n_development_rows'],
        'final_test_sentence': (f'{final.get("status")}, '
                                f'{final.get("n_rows") if final.get("n_rows") is not None else "an unknown number of"} '
                                'rows kept by the study; neither their keys nor their labels '
                                'are in this folder.'),
        'recipe_sha256': snapshot.recipe_sha256,
        'data_contract_sha256': snapshot.data_contract_sha256,
        'expected_scientific_sha256': identities['scientific_sha256'],
        'dataset_id': contract['dataset_id'], 'source_sha256': contract['source_sha256'],
        'row_identity_kind': (contract.get('row_identity') or {}).get('kind'),
        'materialization_sha256': ((snapshot.development_data or {}).get('materialization_sha256')
                                   or 'computed by project.py materialize'),
        'schema_columns': {c['name']: [c.get('role'), c.get('physical_type'),
                                       c.get('semantic_type'), bool(c.get('nullable'))]
                           for c in columns},
        'columns_table': '\n'.join(
            ['| Column | Role | Physical type | Semantic type | Nullable |', '|---|---|---|---|---|']
            + [f'| `{c["name"]}` | {c.get("role")} | {c.get("physical_type")} | '
               f'{c.get("semantic_type")} | {"yes" if c.get("nullable") else "no"} |'
               for c in columns]),
        'limitations_list': '\n'.join(f'- {x}' for x in limitations),
        'python_version': template.document['python'],
        'subscription_id': _value(normal['subscription_id'], 'subscription_id'),
        'compute': _value(normal['compute'], 'compute'),
        'experiment_name': normal['experiment_name'] or project,
        'data_asset_name': _value(normal['data_asset']['name'], 'data_asset.name'),
        'data_asset_version': _value(normal['data_asset']['version'], 'data_asset.version'),
        'data_asset_description': f'Development rows, contracts and evaluated model of study '
                                  f'{doc["study_id"]} (no final test).',
        'environment_name': _value(normal['environment']['name'], 'environment.name'),
        'environment_version': _value(normal['environment']['version'], 'environment.version'),
        'environment_description': 'Python 3.13 environment of the Hypotrail export.',
        'base_image': _value(normal['environment']['base_image'], 'environment.base_image'),
        # Optional: without a name, the team template's pipeline variable is kept.
        'service_connection': normal['devops']['service_connection'] or '$(azure.rm)',
        'cloud_ci_enabled': 'true' if normal['ci']['cloud_enabled'] else 'false (manual only)',
        'job_description': f'Rebuild a candidate of study {doc["study_id"]} with its selected '
                           'recipe; technical checks only.',
        'pipeline_description': 'Prepare, split by the recorded plan, fit a rebuilt candidate, '
                                'check it.',
        'mlflow_tracking_cloud': 'false',
        'packaging_format': 'mlflow_pyfunc',
        'packaging_required': True,
        'parity_features_relpath': parity_rel or '<parity features file>',
        'wheel_install': (f'RUN python -m pip install --no-cache-dir --no-deps /tmp/hypotrail/{wheel}'
                          if wheel else '# No runtime wheel in this export (no captured model): '
                                        'the training step refuses until one is installed.'),
    }


# --- generated documents ---------------------------------------------------------------

def _notebook(ctx: Mapping) -> bytes:
    def md(text):
        return {'cell_type': 'markdown', 'metadata': {}, 'source': text.splitlines(keepends=True)}

    def code(text):
        return {'cell_type': 'code', 'execution_count': None, 'metadata': {}, 'outputs': [],
                'source': text.splitlines(keepends=True)}
    cells = [
        md(f'# {ctx["project_title"]}\n\nWalkthrough of the model selected by study '
           f'`{ctx["study_id"]}` (revision {ctx["study_revision"]}). Run it from the project '
           'folder with the environment of `environment.yml`.'),
        md('## The selected recipe\n\nThe study decided these values; this notebook reads '
           'them, it does not choose them.'),
        code('import json\nfrom pathlib import Path\n\nroot = Path.cwd().parent if '
             'Path.cwd().name == "notebooks" else Path.cwd()\nrecipe = json.loads((root / '
             '"data/hypotrail/contracts/model-recipe.json").read_text())\n'
             'recipe["family"], recipe["parameters"], recipe["features"]'),
        md('## One prediction without the target\n\nThe evaluated model predicts its parity '
           'rows; the target column is not needed. A missing runtime is an explicit error.'),
        code('import subprocess, sys\nsubprocess.run([sys.executable, "-m", '
             '"src.pipeline.utils.project", "predict", "--parity", "--output", '
             '"outputs/predictions.json"], cwd=root, check=False)'),
        md('## The fidelity check\n\n`validate --offline` reloads the model and compares its '
           'predictions with the captured ones within the declared tolerance. A rebuilt '
           'candidate (`run-local`) is a new object: it does not inherit the verdict.'),
        code('subprocess.run([sys.executable, "-m", "src.pipeline.utils.project", "validate", '
             '"--offline"], cwd=root, check=False)'),
    ]
    doc = {'cells': cells, 'metadata': {'kernelspec': {'display_name': 'Python 3',
                                                       'language': 'python', 'name': 'python3'},
                                        'language_info': {'name': 'python'}},
           'nbformat': 4, 'nbformat_minor': 5}
    for i, cell in enumerate(cells):
        cell['id'] = f'hypotrail-{i:02d}'
    return (json.dumps(doc, indent=1, ensure_ascii=False, sort_keys=True) + '\n').encode('utf-8')


def _target_yaml(normal: Mapping, missing: list) -> bytes:
    import yaml
    document = {**normal, 'status': 'configured' if not missing else 'draft',
                'missing_fields': list(missing)}
    head = ('# Destination profile (hypotrail.azure_target/1), normalised by the export. It holds\n'
            '# no credential. Operational only: the scientific contracts are in data/hypotrail.\n')
    return (head + yaml.safe_dump(document, sort_keys=True, allow_unicode=True)).encode('utf-8')


def readiness(snapshot: Snapshot, missing: list, identities: Mapping) -> dict:
    predictor = snapshot.predictor
    return {
        'schema_version': READINESS_SCHEMA,
        'export_id': identities['export_id'],
        'snapshot_id': identities['snapshot_id'],
        'configuration': 'configured' if not missing else 'draft',
        'missing_fields': list(missing),
        'artifact': predictor['artifact_status'] if predictor else 'missing',
        'evidence_status': predictor['evidence_status'] if predictor else 'missing',
        'local_validation': 'not_run',
        'azure_preflight': 'not_run',
        'azure_job': 'not_submitted',
        'registered_model': 'not_registered',
        'scientific_verdict': snapshot.document.get('conclusion'),
        'production_authorisation': 'outside_scope',
        'azure_qualification': 'not_qualified',
    }


def identities(snapshot: Snapshot, normal: Mapping, template: layout.Template) -> dict:
    scientific = projection.from_recipe(
        snapshot.recipe, protocol_id=snapshot.plan['protocol_id'],
        keys_sha256=snapshot.plan['keys_sha256'], metrics=snapshot.metrics,
        recipe_sha256=snapshot.recipe_sha256, data_contract_sha256=snapshot.data_contract_sha256)
    runtime = (snapshot.predictor or {}).get('runtime') or {}
    export_basis = {'snapshot_id': snapshot.snapshot_id,
                    'template': {'id': template.id, 'version': template.version,
                                 'sha256': template.sha256},
                    'generator_version': GENERATOR_VERSION,
                    'runtime': {'distribution': runtime.get('distribution'),
                                'version': runtime.get('version')},
                    'destination': pf.operational_identity(normal)}
    return {'scientific': scientific, 'scientific_sha256': cj.canonical_sha256(scientific),
            'snapshot_id': snapshot.snapshot_id, 'export_id': cj.canonical_sha256(export_basis),
            'export_basis': export_basis}


def _shared(module: str) -> bytes:
    path = Path(importlib.import_module(module).__file__)
    return path.read_bytes()


def _no_interpolation(value, path: str) -> None:
    """A scientific value rendered into Hydra YAML may not look like an interpolation, nor
    be OmegaConf's mandatory-missing marker ``???`` (read back as a missing value)."""
    if isinstance(value, str) and ('${' in value or '@@' in value or value == OMEGACONF_MISSING):
        raise ExportError('contract_invalid', 'A recipe or plan value contains "${" or "@@", '
                          'or is "???", which the project configuration would interpret.',
                          path=path, remediation='Rename the value in the study.')
    if isinstance(value, Mapping):
        for key, item in value.items():
            _no_interpolation(key, f'{path}.{key}')
            _no_interpolation(item, f'{path}.{key}')
    elif isinstance(value, list):
        for i, item in enumerate(value):
            _no_interpolation(item, f'{path}[{i}]')


def render(snapshot: Snapshot, normal: Mapping, missing: list,
           template: layout.Template) -> tuple[list[File], dict]:
    """``(files, summary)``: every file of the project, in path order, and the identities,
    statuses and checks the command reports."""
    ids = identities(snapshot, normal, template)
    _no_interpolation(ids['scientific'], 'scientific_projection')
    ctx = context(snapshot, normal, missing, template, ids)
    lock, lock_status = lock_bytes(template, snapshot)
    ready = readiness(snapshot, missing, ids)
    recipe = cj.pretty_bytes(snapshot.recipe)
    contract = cj.pretty_bytes(snapshot.data_contract)
    generated = {
        'notebook': _notebook(ctx), 'recipe': recipe, 'data_contract': contract,
        'plan': cj.pretty_bytes(snapshot.plan), 'snapshot': cj.pretty_bytes(snapshot.document),
        'projection': cj.pretty_bytes(ids['scientific']), 'readiness': cj.pretty_bytes(ready),
        'azure_target': _target_yaml(normal, missing), 'lock': lock,
    }
    files: dict[str, File] = {}
    late = []
    for entry in template.files:
        kind, path = entry['kind'], entry['path']
        if kind in ('preserved', 'adapted', 'added'):
            data = template.read(entry['source'])
        elif kind == 'rendered':
            data = substitute(template.read(entry['source']).decode('utf-8'), ctx,
                              path).encode('utf-8')
        elif kind == 'shared':
            data = _shared(entry['module'])
        elif kind == 'generated' and entry['generator'] in generated:
            data = generated[entry['generator']]
        elif kind == 'generated':
            late.append(entry)
            continue
        else:
            raise ExportError('template_layout_mismatch', f'Unknown file kind {kind!r}.',
                              path=path, remediation='Fix the template manifest.')
        files[path] = File(path, kind, data)
    predictor = snapshot.predictor
    if predictor:
        for rel, data in predictor['files'].items():
            files[EVALUATED + rel] = File(EVALUATED + rel, 'copied', data)
        if predictor.get('wheel'):
            name, data = predictor['wheel']
            files[RUNTIME_DIR + name] = File(RUNTIME_DIR + name, 'copied', data)
    listed = [{'path': f.path, 'kind': f.kind, 'sha256': f.sha256, 'bytes': len(f.data)}
              for f in sorted(files.values(), key=lambda f: f.path)]
    manifest = {
        'schema_version': EXPORT_SCHEMA, 'export_id': ids['export_id'],
        'snapshot_id': ids['snapshot_id'], 'basis': ids['export_basis'],
        'template': {'id': template.id, 'version': template.version, 'sha256': template.sha256,
                     'source_sha256': template.layout['source_sha256'],
                     'cleaned_source_sha256': template.transport['delivered_sha256']},
        'generator_version': GENERATOR_VERSION,
        'configuration': ready['configuration'], 'artifact': ready['artifact'],
        'environment_lock': lock_status,
        'files': listed,
        'checks': snapshot.checks,
        'limitations': ctx['limitations_list'].splitlines(),
        'execution_results': 'none: results of local or Azure runs are written to outputs/, '
                             'never into this manifest',
    }
    for entry in late:
        if entry['generator'] == 'export_manifest':
            files[entry['path']] = File(entry['path'], 'generated', cj.pretty_bytes(manifest))
    sums = ''.join(f'{f.sha256}  {f.path[len("data/hypotrail/"):]}\n'
                   for f in sorted(files.values(), key=lambda f: f.path)
                   if f.path.startswith('data/hypotrail/'))
    for entry in late:
        if entry['generator'] == 'sha256sums':
            files[entry['path']] = File(entry['path'], 'generated', sums.encode('utf-8'))
    ordered = sorted(files.values(), key=lambda f: f.path)
    _self_check(ordered, ids, missing)
    summary = {'identities': ids, 'readiness': ready, 'lock_status': lock_status,
               'context': ctx}
    return ordered, summary


def _self_check(files: list[File], ids: Mapping, missing: list) -> None:
    """The rendered configuration projects to the expected identity, and a configured
    export holds no missing-value marker in an executable file."""
    import yaml
    by_path = {f.path: f for f in files}
    container = {'hypotrail': yaml.safe_load(by_path['src/conf/hypotrail/replay.yaml'].data),
                 'components': {}}
    for step in ('data_preparation', 'data_splitting', 'training', 'evaluation'):
        container['components'][step] = yaml.safe_load(
            by_path[f'src/conf/components/{step}/default.yaml'].data)
    actual = projection.from_config(container)
    if cj.canonical_sha256(actual) != ids['scientific_sha256']:
        raise ExportError('scientific_config_changed', 'The rendered configuration does not '
                          'project to the selected recipe; nothing was written.',
                          path='src/conf', remediation='Report this generator defect.',
                          details={'differences': projection.differences(ids['scientific'],
                                                                         actual)})
    if not missing:
        marked = [f.path for f in files if f.kind == 'rendered' and MISSING.encode() in f.data]
        if marked:
            raise ExportError('template_layout_mismatch', 'A configured export kept a '
                              'missing-value marker.', path=marked[0],
                              remediation='Report this generator defect.')
    for f in files:
        if f.path.startswith('aml/') and f.path.endswith('.yml'):
            text = f.data.decode('utf-8')
            if '${{' in text and not azure_yaml.expressions(text):
                raise ExportError('template_layout_mismatch', 'An Azure expression was damaged.',
                                  path=f.path, remediation='Report this generator defect.')
