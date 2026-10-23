"""The exported project, moved away from the study and run as an engineer would (AC22,
A06, A10, A11, A14, AC17, AC18, AC23).

Every command runs in a subprocess from the moved folder, with no path to the study or
to this repository: only the runtime (workstream A's, installed) is available, as the
wheel would be. These tests are local; none contacts Azure.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from export_env import needs_hydra, needs_mlflow, project_env
from mlkit.exporters.azureml import azure_yaml

pytestmark = [needs_mlflow, needs_hydra]


def _run(root: Path, *args, check=True):
    result = subprocess.run([sys.executable, *args], cwd=root, capture_output=True, text=True,
                            env=project_env(), check=False, timeout=600)
    if check:
        assert result.returncode == 0, (result.stdout[-3000:], result.stderr[-3000:])
    return result


def _json(result) -> dict:
    return json.loads(result.stdout[result.stdout.index('{'):])


@pytest.fixture(scope='module')
def project(tmp_path_factory, material):
    """One export, moved to another folder, with its development rows materialised."""
    import azureml_study as fx

    from mlkit.exporters.azureml import export_azureml
    folder = tmp_path_factory.mktemp('project')
    doc = fx.export_source(material['folder'], bundle_dir=material['bundle'],
                           contract=material['contract'], source=material['source'])
    _, code = export_azureml(folder / 'study', expected_revision=fx.REVISION,
                             out=folder / 'export', profile_path=fx.profile(folder),
                             reader=fx.reader_of(doc))
    assert code == 0
    moved = folder / 'moved' / 'auto-mpg-azureml'
    moved.parent.mkdir()
    shutil.move(str(folder / 'export'), moved)
    source = folder / 'original.data'
    shutil.copyfile(material['source'], source)
    _run(moved, '-m', 'src.pipeline.utils.project', 'materialize', '--source', str(source))
    return {'root': moved, 'source': source, 'folder': folder}


def test_validate_passes_offline_on_the_moved_folder(project):
    report = _json(_run(project['root'], '-m', 'src.pipeline.utils.project', 'validate',
                        '--offline'))
    statuses = {c['id']: c['status'] for c in report['checks']}
    assert report['status'] == 'passed' and report['network_used'] is False
    assert statuses == {'data_checksums': 'passed', 'code_contract_copies': 'passed',
                        'hydra_config_frozen': 'passed', 'azure_yaml_graph': 'passed',
                        'configuration_markers': 'passed', 'code_upload_content': 'passed',
                        'no_credentials': 'passed', 'evaluated_model_parity': 'passed',
                        'evaluated_model_mlflow_package': 'passed', 'development_rows': 'passed'}


def test_predict_with_the_evaluated_model_needs_no_target(project, tmp_path):
    rows = tmp_path / 'rows.csv'
    rows.write_text('weight,cylinders,displacement,horsepower,origin\n'
                    '2500,4,120.5,,2\n3500,8,300,150,1\n')
    out = tmp_path / 'predictions.json'
    _run(project['root'], '-m', 'src.pipeline.utils.project', 'predict', '--input', str(rows),
         '--output', str(out))
    document = json.loads(out.read_text())
    assert document['columns'] == ['prediction'] and len(document['rows']) == 2
    assert document['output_contract']['unit'] == 'mpg'
    assert document['role'] == 'final_development_refit'


def test_project_tests_pass(project):
    result = _run(project['root'], '-m', 'pytest', '-q', '-p', 'no:cacheprovider')
    assert ' passed' in result.stdout and 'failed' not in result.stdout


def test_run_local_builds_a_new_candidate_without_the_verdict(project):
    root = project['root']
    run = _json(_run(root, '-m', 'src.pipeline.utils.project', 'run-local', '--mode',
                     'rebuild_final_candidate', '--run-dir', str(project['folder'] / 'run1')))
    assert run['ok'] and run['role'] == 'rebuilt_candidate'
    assert run['scientific_verdict'] == 'not_inherited'
    report = json.loads((project['folder'] / 'run1/05_reports/technical-report.json').read_text())
    assert report['generalisation_metrics'] is None
    assert report['candidate_predictor_id'] != report['evaluated_predictor_id']
    assert {c['id']: c['status'] for c in report['checks']}['mlflow_package_parity'] == 'passed'
    partitions = json.loads((project['folder'] / 'run1/03_partitions/partitions.json').read_text())
    assert partitions['new_split_drawn'] is False
    assert sum(p['n_rows'] for p in partitions['partitions']) == 48
    frozen = json.loads((project['folder'] / 'run1/04_model/hypotrail-run-config.json').read_text())
    assert frozen['schema_version'] == 'hypotrail.frozen_run_config/1'
    again = _run(root, '-m', 'src.pipeline.utils.project', 'run-local', '--mode',
                 'rebuild_final_candidate', '--run-dir', str(project['folder'] / 'run1'),
                 check=False)
    assert again.returncode == 2 and 'destination_not_empty' in again.stdout


def test_a_scientific_override_of_a_step_is_refused(project, tmp_path):
    result = _run(project['root'], '-m', 'src.pipeline.training.main',
                  'components.training.model.type=ridge',
                  f'models.path={tmp_path / "m"}', f'hydra.run.dir={tmp_path / "h"}', check=False)
    assert result.returncode == 2
    assert 'scientific_config_changed' in result.stdout + result.stderr
    assert not (tmp_path / 'm').exists()


def test_development_evaluation_mode_is_refused(project, tmp_path):
    result = _run(project['root'], '-m', 'src.pipeline.utils.project', 'run-local', '--mode',
                  'development_evaluation', '--run-dir', str(tmp_path / 'r'), check=False)
    assert result.returncode == 2 and 'capability_not_supported' in result.stdout


def test_another_source_file_is_refused(project, tmp_path):
    changed = tmp_path / 'changed.data'
    lines = project['source'].read_text().splitlines()
    changed.write_text('\n'.join(reversed(lines)) + '\n')
    result = _run(project['root'], '-m', 'src.pipeline.utils.project', 'materialize', '--source',
                  str(changed), check=False)
    assert result.returncode == 2 and 'data_identity_mismatch' in result.stdout


def test_azure_commands_are_printed_not_run(project):
    preflight = _json(_run(project['root'], '-m', 'src.pipeline.utils.project', 'preflight'))
    submit = _json(_run(project['root'], '-m', 'src.pipeline.utils.project', 'submit'))
    assert preflight['executed'] is False and submit['executed'] is False
    assert {c['scope'] for c in preflight['commands']} == {'network_read'}
    assert {c['scope'] for c in submit['commands']} == {'azure_write'}
    assert not (project['root'] / 'outputs' / 'submission.json').exists()


def test_a_changed_contract_fails_validation(project, tmp_path):
    copy = tmp_path / 'copy'
    shutil.copytree(project['root'], copy)
    recipe = copy / 'data/hypotrail/contracts/model-recipe.json'
    changed = recipe.read_text().replace('"family": "linear"', '"family": "ridge"')
    assert changed != recipe.read_text()
    recipe.write_text(changed)
    report = _json(_run(copy, '-m', 'src.pipeline.utils.project', 'validate', check=False))
    assert {c['id']: c['status'] for c in report['checks']}['data_checksums'] == 'failed'


def test_the_azure_graph_check_finds_a_broken_binding(project, tmp_path):
    copy = tmp_path / 'copy'
    shutil.copytree(project['root'], copy)
    pipeline = copy / azure_yaml.PIPELINE
    pipeline.write_text(pipeline.read_text().replace(
        'parent.jobs.split_job.outputs.partitions_path',
        'parent.jobs.split_job.outputs.train_data_path'))
    problems, _ = azure_yaml.check(copy)
    assert any('has no output train_data_path' in p for p in problems)


def test_secrets_and_data_are_not_uploaded(project, tmp_path):
    from mlkit.exporters.azureml import transfer
    copy = tmp_path / 'copy'
    shutil.copytree(project['root'], copy)
    (copy / '.env').write_text('SUBSCRIPTION=x\n')
    (copy / 'src' / 'conf' / 'local.key').write_text('x')
    uploaded = transfer.transferable(copy)
    assert '.env' not in uploaded and 'src/conf/local.key' not in uploaded
    assert not [p for p in uploaded if p.startswith(('data/', 'outputs/', 'notebooks/'))]


def test_the_project_passes_the_team_lint(project):
    """The exported project passes its own quality CI (`ruff check src`, the team's rules
    and ruff version), so an engineer starts from a green lint."""
    ruff = shutil.which('ruff', path=str(Path(sys.executable).parent))
    if ruff is None:
        pytest.skip('ruff is not installed (azureml group)')
    version = subprocess.run([ruff, '--version'], capture_output=True, text=True, check=True)
    assert version.stdout.split()[1] == '0.4.5'
    result = subprocess.run([ruff, 'check', 'src', '--no-cache'], cwd=project['root'],
                            capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout[-3000:]
