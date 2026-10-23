"""AZ-STRUCT-01/02, AC20: the versioned template and the structure of an export."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from mlkit.exporters.azureml import layout
from mlkit.exporters.azureml.errors import ExportError

ROOT = Path(__file__).resolve().parents[4]
SPECS = ROOT / 'docs' / 'specs' / 'azureml-export'


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_shared_contracts_are_the_received_ones():
    """The copies in docs/specs/azureml-export match their recorded SHA-256 (the pack's)."""
    for line in (SPECS / 'SHA256SUMS').read_text().splitlines():
        digest, _, name = line.partition('  ')
        assert _sha(SPECS / name) == digest, name
    template = layout.load('team-azureml-v1')
    assert _sha(template.root / 'layout.json') == _sha(SPECS / 'TEMPLATE-LAYOUT-v1.json') \
        == layout.LAYOUT_SHA256
    assert _sha(template.root / 'transport.json') == _sha(SPECS / 'TEMPLATE-TRANSPORT.json')


def test_preserved_files_are_byte_identical_to_the_team_template():
    template = layout.load('team-azureml-v1')
    kept = {f['path']: f['sha256'] for f in template.transport['unchanged_files']}
    preserved = [e for e in template.files if e['kind'] == 'preserved']
    assert preserved
    for entry in preserved:
        assert hashlib.sha256(template.read(entry['source'])).hexdigest() == \
            kept['ml_project_template/' + entry['path']]


def test_every_original_path_is_kept_except_the_business_data():
    template = layout.load('team-azureml-v1')
    paths = {e['path'] for e in template.files}
    removed = set(template.layout['removed_business_data'])
    assert set(template.layout['required_preserved_paths']) <= paths
    assert not removed & paths
    assert set(template.layout['original_files']) - removed <= paths


def test_no_stored_file_acts_on_this_repository():
    """Stored dotfiles are named dot-..., so no stored .gitignore applies to the repo."""
    template = layout.load('team-azureml-v1')
    for path in template.root.rglob('*'):
        assert not path.name.startswith('.'), path


@pytest.mark.parametrize(('path', 'problem'), [
    ('azure/target.yaml', 'forbidden root'), ('deployment/x.json', 'forbidden root'),
    ('model/a.pkl', 'forbidden root'), ('scripts/project.py', 'forbidden root'),
    ('data/01_raw/shuttles.xlsx', 'business example data'),
    ('src/extra.py', 'outside the allowlist'), ('.DS_Store', 'metadata'),
    ('.git/config', 'metadata'), ('src/__MACOSX/x', 'metadata')])
def test_layout_problems_are_detected(path, problem):
    template = layout.load('team-azureml-v1')
    problems = layout.check_paths(template.layout, [path], require_preserved=False)
    assert any(problem in p for p in problems), problems


def test_unknown_template_is_refused():
    with pytest.raises(ExportError) as error:
        layout.load('team-azureml-v2')
    assert error.value.code == 'template_unsupported'


def test_a_damaged_preserved_file_is_refused(tmp_path, monkeypatch):
    import shutil
    template = layout.load('team-azureml-v1')
    copy = tmp_path / 'team-azureml-v1'
    shutil.copytree(template.root, copy)
    entry = next(e for e in template.files if e['kind'] == 'preserved')
    (copy / entry['source']).write_bytes(b'changed\n')
    monkeypatch.setattr(layout, 'TEMPLATES', tmp_path)
    with pytest.raises(ExportError) as error:
        layout.load('team-azureml-v1')
    assert error.value.code == 'template_layout_mismatch'


def test_an_export_conforms_to_the_layout(export):
    payload, code, out = export()
    assert code == 0 and payload['ok']
    template = layout.load('team-azureml-v1')
    assert layout.check_tree(out, template) == []
    for directory in template.layout['preserved_directory_skeleton']:
        assert (out / directory).is_dir()
    assert not (out / 'data' / '01_raw').exists() or not any((out / 'data' / '01_raw').iterdir())
    kinds = {f['kind'] for f in payload['files']}
    assert {'preserved', 'adapted', 'rendered', 'added', 'shared', 'generated'} <= kinds


def test_cli_aliases_and_makefile_are_inert(export):
    _, _, out = export()
    aliases = (out / 'cli-aliases.sh').read_text()
    makefile = (out / 'Makefile').read_text()
    for word in ('bashrc', 'zshrc', 'sed -i', 'rm ', 'conda env remove', 'source .env', 'alias cd'):
        assert word not in aliases
    assert '>> $$rcfile' not in makefile and 'sed -i' not in makefile
    tasks = json.loads((out / '.vscode' / 'tasks.json').read_text())
    commands = ' '.join(str(t.get('command')) + ' '.join(t.get('args', [])) for t in tasks['tasks'])
    assert 'git clean -fXd' not in commands and 'amlignore' not in commands
    assert {t['label'] for t in tasks['tasks']} >= {'run_data_prep_locally', 'run_training_locally',
                                                   'run_all_steps_locally', 'quality', 'tests'}


def test_random_forest_profile_is_kept_inactive(export):
    _, _, out = export()
    text = (out / 'src/conf/components/training/random_forest.yaml').read_text()
    assert 'status: inactive_not_evaluated' in text and 'NOT evaluated' in text
