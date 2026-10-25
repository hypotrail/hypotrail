"""Regressions of the round-4 review of the Azure ML export (R4-B1 to R4-B3), on synthetic
material and temporary folders only. The reviewer's probes are ported here.

* R4-B1: every value the generator writes into a YAML file of the project (the Azure YAML
  included, not only ``src/conf``) is a quoted scalar that reads back as the exact profile
  or case value: ``2026``, ``True``, ``null``, ``1.10``, ``1e9``, ``yes`` and ``007`` stay
  texts, and ``~`` or an empty name is refused by the profile with ``contract_invalid``
  (never a ``template_layout_mismatch``). A YAML template takes no raw ``@@text:`` marker.
* R4-B2: the example-code check reads the template's own files before rendering; a case id,
  title or name with "reviews" or "companies" exports, a template that holds example code
  is refused.
* R4-B3: ``run-local`` passes its run paths as quoted Hydra values, so a folder named with
  ``(``, ``)``, ``,``, ``=``, quotes, ``$``, ``${``, brackets, spaces or non-ASCII letters
  runs; a failed step's refusal (code, path, remediation) is relayed in the JSON document.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

import azureml_study as fx
from export_env import needs_hydra, needs_mlflow, project_env
from mlkit.exporters.azureml import azure_yaml, layout, render
from mlkit.exporters.azureml.errors import ExportError

MOD = 'src.pipeline.utils.project'
IMAGE = 'mcr.microsoft.com/azureml/openmpi4.1.0-ubuntu22.04:20250601.v1'
# Texts a YAML 1.1 or OmegaConf resolver re-types when they are written unquoted.
HOSTILE_NAMES = ['2026', 'True', 'null', '1.10', '1e9', 'yes', '007']
# Not a name of an Azure resource: the profile refuses them.
REFUSED_NAMES = ['~', '']
# Profile fields whose pattern accepts a '.', and those whose pattern does not.
DOTTED_FIELDS = ('data_asset.name', 'data_asset.version', 'environment.name',
                 'environment.version')
PLAIN_FIELDS = ('experiment_name', 'compute', 'devops.service_connection')


def _run(root: Path, *args):
    return subprocess.run([sys.executable, '-m', MOD, *map(str, args)], cwd=root,
                          capture_output=True, text=True, env=project_env(), check=False,
                          timeout=900)


def _python(root: Path, code: str):
    return subprocess.run([sys.executable, '-c', code], cwd=root, capture_output=True,
                          text=True, env=project_env(), check=False, timeout=300)


def _set(document: dict, dotted: str, value) -> None:
    *parents, leaf = dotted.split('.')
    node = document
    for part in parents:
        node = node.setdefault(part, {})
    node[leaf] = value


def _profile_changes(value: str) -> dict:
    """Every profile field that may hold ``value`` set to it (the other fields as usual)."""
    document = {'data_asset': {'name': 'synthetic-cars-development', 'version': '1'},
                'environment': {'name': 'hypotrail-py313', 'version': '1', 'base_image': IMAGE}}
    fields = DOTTED_FIELDS + (PLAIN_FIELDS if '.' not in value else ())
    for dotted in fields:
        _set(document, dotted, value)
    return document


def _yaml_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob('*') if p.is_file() and p.suffix in ('.yml', '.yaml'))


# --- R4-B1: every YAML value is a quoted scalar that reads back exactly -------------------

def test_no_yaml_template_uses_a_raw_text_marker():
    """The audit of R4-B1: no ``@@text:`` substitution is left in a YAML file of the
    template (Azure YAML, CI, conda environment, Hydra configuration)."""
    template = layout.load('team-azureml-v1')
    yaml_entries = [e for e in template.files if e['kind'] == 'rendered'
                    and e['path'].endswith(('.yml', '.yaml'))]
    assert {e['path'] for e in yaml_entries} >= {
        'aml/pipelines/training/pipeline-job.yml', 'aml/pipelines/training/data.yml',
        'aml/pipelines/training/aml-environment.yml', 'aml/pipelines/training/pipeline.yml',
        'aml/components/training.yml', '.ci/deploy-pipeline.yml', 'environment.yml'}
    for entry in yaml_entries:
        text = template.read(entry['source']).decode('utf-8')
        assert '@@text:' not in text, entry['path']
        assert render.MARKER.search(text) or entry['path'].startswith('src/conf'), entry['path']


def test_a_raw_text_marker_in_a_yaml_file_is_refused():
    with pytest.raises(ExportError) as error:
        render.substitute('name: @@text:name@@\n', {'name': '2026'}, 'aml/x.yml')
    assert error.value.code == 'template_layout_mismatch'
    assert render.substitute('name: @@yaml:name@@\n', {'name': '2026'},
                             'aml/x.yml') == 'name: "2026"\n'
    # Outside YAML (Markdown, TOML, a Dockerfile) a raw text stays possible.
    assert render.substitute('# @@text:name@@\n', {'name': '2026'}, 'README.md') == '# 2026\n'


@needs_mlflow
@pytest.mark.parametrize('value', HOSTILE_NAMES)
def test_every_profile_name_reads_back_exactly_from_every_yaml_file(export, value):
    """The reviewer's probe P3: ``experiment_name``, ``data_asset.name`` and
    ``environment.name`` (and the versions, compute and service connection) were written
    raw, so ``2026`` read back as an integer and an environment named ``null`` failed the
    export with ``template_layout_mismatch``."""
    payload, code, out = export(profile_changes=_profile_changes(value), name='e')
    assert code == 0, payload
    expected = {dotted: value for dotted in DOTTED_FIELDS}
    if '.' not in value:
        expected.update({dotted: value for dotted in PLAIN_FIELDS})
    loaded = {}
    for path in _yaml_files(out):
        rel = path.relative_to(out).as_posix()
        text = path.read_text(encoding='utf-8')
        loaded[rel] = yaml.safe_load(text)
        if rel.startswith('src/conf/') and '${' not in text:
            # OmegaConf (the project's reader) gives the same values as PyYAML.
            assert render.load_config(path.read_bytes()) == loaded[rel], rel
    job = loaded['aml/pipelines/training/pipeline-job.yml']
    data = loaded['aml/pipelines/training/data.yml']
    environment = loaded['aml/pipelines/training/aml-environment.yml']
    assert data['name'] == expected['data_asset.name']
    assert data['version'] == expected['data_asset.version']
    assert environment['name'] == expected['environment.name']
    assert environment['version'] == expected['environment.version']
    assert job['inputs']['hypotrail_data_path']['path'] == f'azureml:{value}:{value}'
    for step in ('data_preparation', 'data_splitting', 'training', 'evaluation'):
        component = loaded[f'aml/components/{step}.yml']
        assert component['environment'] == f'azureml:{value}:{value}', step
        assert isinstance(component['name'], str) and isinstance(component['display_name'], str)
    if '.' not in value:
        assert job['experiment_name'] == value
        assert job['compute'] == f'azureml:{value}'
        steps = loaded['.ci/deploy-pipeline.yml']['steps']
        assert [s['inputs']['azureSubscription'] for s in steps] == [value] * len(steps)
    target = loaded['src/conf/azure/target.yaml']
    for dotted, wanted in expected.items():
        node = target
        for part in dotted.split('.'):
            node = node[part]
        assert node == wanted, dotted
    assert job['tags']['hypotrail_study'] == 'study-synthetic-cars'
    assert loaded['environment.yml']['name'] == 'hypotrail_synthetic_cars_v1'
    assert loaded['environment.yml']['dependencies'][0] == 'python=3.13'
    assert azure_yaml.check(out)[0] == []


@pytest.mark.parametrize('value', REFUSED_NAMES)
@pytest.mark.parametrize('dotted', DOTTED_FIELDS + PLAIN_FIELDS)
def test_a_name_that_is_no_azure_name_is_refused_by_the_profile(export, tmp_path, dotted,
                                                                  value):
    """``~`` and an empty text are not names: the profile refuses them on their own field
    (``contract_invalid``), nothing is written."""
    changes = _profile_changes('ok-1')
    _set(changes, dotted, value)
    root, _, rest = dotted.partition('.')
    with pytest.raises(ExportError) as error:
        export(profile_changes={root: changes[root]} if rest else {root: value},
               name=f'refused-{dotted}')
    assert error.value.code == 'contract_invalid'
    assert error.value.path == dotted
    assert not (tmp_path / f'refused-{dotted}').exists()


@needs_mlflow
@pytest.mark.parametrize('value', HOSTILE_NAMES + REFUSED_NAMES[:1])
def test_every_study_id_and_case_id_reads_back_exactly(export, value):
    """The study id and the case id the snapshot carries reach the job tags, the Hydra
    configuration and the component names; each reads back as the case's text."""
    payload, code, out = export(source_changes={'study_id': value,
                                                'case': {'id': value, 'title': value}},
                                name='e')
    assert code == 0, payload
    job = yaml.safe_load((out / 'aml/pipelines/training/pipeline-job.yml').read_text())
    assert job['tags']['hypotrail_study'] == value
    replay = out / 'src/conf/hypotrail/replay.yaml'
    assert yaml.safe_load(replay.read_text())['study_id'] == value
    assert render.load_config(replay.read_bytes())['study_id'] == value
    project = job['tags']['project']
    assert isinstance(project, str) and project.startswith('hypotrail_')
    assert job['experiment_name'] == project
    for step in ('data_preparation', 'data_splitting', 'training', 'evaluation'):
        component = yaml.safe_load((out / f'aml/components/{step}.yml').read_text())
        assert component['name'].startswith(project + '_'), step
    assert azure_yaml.check(out)[0] == []


# --- R4-B2: the example-code check reads the template, not the study's values ------------

@needs_mlflow
@pytest.mark.parametrize('case', [{'id': 'listing-reviews', 'title': 'Listing reviews'},
                                  {'id': 'loans', 'title': 'Loans of small companies'},
                                  {'id': 'space-shuttle-o-rings', 'title': 'Space shuttle'}])
def test_a_case_named_with_example_words_exports(export, case):
    """The reviewer's probe P5: a case id or title with "reviews", "companies" or "space
    shuttle" was refused with ``template_layout_mismatch``."""
    payload, code, out = export(source_changes={'case': case}, name='e')
    assert code == 0, payload
    readme = (out / 'README.md').read_text(encoding='utf-8')
    assert case['title'] in readme
    job = yaml.safe_load((out / 'aml/pipelines/training/pipeline-job.yml').read_text())
    assert job['tags']['project'] == 'hypotrail_' + case['id'].replace('-', '_')
    assert layout.check_tree(out, layout.load('team-azureml-v1')) == []


def test_a_template_that_holds_example_code_is_refused(tmp_path):
    """The guarantee is kept: example code in the template's own files is found before any
    rendering, and the template is refused at load."""
    source = layout.TEMPLATES / 'team-azureml-v1'
    root = tmp_path / 'team-azureml-v1'
    shutil.copytree(source, root, ignore=shutil.ignore_patterns('__pycache__'))
    template = layout.Template('team-azureml-v1', root)
    assert template.example_code() == []
    entry = next(e for e in template.files if e['kind'] == 'rendered'
                 and e['path'] == 'aml/components/training.yml')
    stored = root / entry['source']
    stored.write_text(stored.read_text() + '# predict the spaceshuttle of the companies\n')
    template = layout.Template('team-azureml-v1', root)
    assert template.example_code() == ['example business code left: aml/components/training.yml']
    with pytest.raises(ExportError) as error:
        template.verify()
    assert error.value.code == 'template_layout_mismatch'
    assert error.value.details['problems'] == template.example_code()


# --- R4-B3: run-local paths are quoted Hydra values; a refusal is relayed -----------------

FOLDER_TEXTS = ['My Project (2)', 'Smith, Jane', 'a=b', "it's", 'say "hi"', '$HOME',
                '${oc.env:HOME}', '[draft]', 'été 漢字', 'back\\slash', 'end\\',
                "q\\'x", '\\${x}', 'a,b=c(d)[e]{f}:g']


@needs_hydra
def test_a_hydra_quoted_value_reads_back_exactly(export):
    """Hydra's own override parser, then OmegaConf's resolution, give back each folder
    text, whatever the grammar characters it holds."""
    payload, code, out = export(name='e', bundle=None)
    assert code == 0, payload
    script = (
        'import json, sys\n'
        'from hydra.core.override_parser.overrides_parser import OverridesParser\n'
        'from omegaconf import OmegaConf\n'
        'from src.pipeline.utils.project import hydra_quoted\n'
        'parser = OverridesParser.create()\n'
        'out = []\n'
        f'for text in json.loads({json.dumps(json.dumps(FOLDER_TEXTS))}):\n'
        '    value = parser.parse_override("models.path=" + hydra_quoted(text)).value()\n'
        '    cfg = OmegaConf.create({"models": {"path": "x"}})\n'
        '    cfg.models.path = value\n'
        '    out.append(OmegaConf.to_container(cfg, resolve=True)["models"]["path"])\n'
        'sys.stdout.write(json.dumps(out))\n')
    result = _python(out, script)
    assert result.returncode == 0, result.stderr[-2000:]
    assert json.loads(result.stdout) == FOLDER_TEXTS


@needs_mlflow
@needs_hydra
def test_run_local_runs_from_a_folder_named_with_hydra_grammar(export, material, tmp_path):
    """The reviewer's probe P6: a duplicated folder ("My Project (2)") or a name with a
    comma made run-local fail at the first step with only ``failed_step``."""
    payload, code, out = export(name='e')
    assert code == 0, payload
    folder = tmp_path / 'My (2), x=y \'q\' "d" $HOME $ [b] {c} été 漢字' / 'export'
    folder.parent.mkdir()
    shutil.copytree(out, folder)
    assert _run(folder, 'materialize', '--source', material['source']).returncode == 0
    result = _run(folder, 'run-local', '--mode', 'rebuild_final_candidate')
    document = json.loads(result.stdout)
    assert result.returncode == 0, (document, result.stderr[-3000:])
    assert document['ok'] is True and document['technical_status'] == 'passed'
    assert document['run_dir'] == str(folder / 'outputs/local-run')
    assert (folder / 'outputs/local-run/05_reports/technical-report.json').is_file()
    assert (folder / 'outputs/local-run/04_model/hypotrail-run.json').is_file()
    # Hydra's own run folder is inside the run folder, and no other folder was created.
    assert (folder / 'outputs/local-run/hydra/.hydra/overrides.yaml').is_file()
    assert [p.name for p in tmp_path.iterdir() if p.name.startswith('My')] == [folder.parent.name]


@needs_hydra
@pytest.mark.parametrize('where', ['run_dir', 'project'])
def test_a_run_folder_hydra_cannot_name_is_refused(export, tmp_path, where):
    """Hydra resolves the absolute path of its run folder twice, so a run folder whose path
    holds ``${`` (a --run-dir, or the project folder of the default run folder) is refused
    before any step runs (``invalid_arguments``), never left to a Hydra traceback."""
    payload, code, out = export(name='e', bundle=None)
    assert code == 0, payload
    if where == 'run_dir':
        run_dir = tmp_path / 'runs ${x}' / 'run'
        result = _run(out, 'run-local', '--mode', 'rebuild_final_candidate', '--run-dir',
                      run_dir)
    else:
        moved = tmp_path / 'copy ${x}' / 'export'
        shutil.copytree(out, moved)
        run_dir = moved / 'outputs/local-run'
        result = _run(moved, 'run-local', '--mode', 'rebuild_final_candidate')
    assert result.returncode == 2, result.stderr[-2000:]
    document = json.loads(result.stdout)
    assert document['ok'] is False
    assert document['error']['code'] == 'invalid_arguments'
    assert document['error']['path'] == str(run_dir)
    assert 'failed_step' not in document
    assert not run_dir.exists()


@needs_mlflow
@needs_hydra
def test_run_local_relays_the_refusal_of_the_failed_step(export, tmp_path):
    """Without materialised rows the preparation step refuses: run-local's document names
    the step and carries its refusal (code, path, remediation), exit code 2."""
    payload, code, out = export(name='e')
    assert code == 0, payload
    result = _run(out, 'run-local', '--mode', 'rebuild_final_candidate', '--run-dir',
                  tmp_path / 'run (1)')
    assert result.returncode == 2, result.stderr[-2000:]
    document = json.loads(result.stdout)
    assert document['ok'] is False
    assert document['failed_step'] == 'data_preparation'
    error = document['error']
    assert error['code'] == 'data_identity_mismatch'
    assert error['path'].endswith('development/development.csv')
    assert 'materialize' in error['remediation']
    assert error['message'] == 'The development rows are not materialised.'


@needs_hydra
def test_a_step_failure_without_a_refusal_is_reported_with_its_output(export):
    payload, code, out = export(name='e', bundle=None)
    assert code == 0, payload
    script = (
        'import json, sys\n'
        'from src.pipeline.utils.project import _step_refusal\n'
        'logged = "[2026-10-25 10:00:00] - [ERROR] - " + json.dumps({"error": {"code": '
        '"contract_invalid", "path": "p", "message": "m", "remediation": "r", "details": {}},'
        ' "ok": False})\n'
        'found = _step_refusal("training", 2, "info {not json}\\n" + logged + "\\n", "")\n'
        'other = _step_refusal("training", 1, "", "Traceback\\nKeyError: x\\n")\n'
        'sys.stdout.write(json.dumps([found, other]))\n')
    result = _python(out, script)
    assert result.returncode == 0, result.stderr[-2000:]
    found, other = json.loads(result.stdout)
    assert found == {'code': 'contract_invalid', 'path': 'p', 'message': 'm',
                     'remediation': 'r', 'details': {}}
    assert other['code'] == 'step_failed'
    assert other['path'] == 'src/pipeline/training/main.py'
    assert other['details']['exit_code'] == 1
    assert other['details']['output_tail'][-1] == 'KeyError: x'
