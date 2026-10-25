"""Round-3 integration follow-ups: a bytecode cache in a bundle is named to the junior and
refused by the export's copy; the runtime's remediation reaches the export's refusal."""
from __future__ import annotations

from pathlib import Path

import pytest

from mlkit.contracts import capture
from mlkit.exporters.azureml import artifact
from mlkit.exporters.azureml.errors import ExportError


class _Refusal(Exception):
    def __init__(self, details):
        super().__init__('refused')
        self.code = 'artifact_unavailable'
        self.message = 'refused'
        self.details = details


@pytest.mark.parametrize('lang, words', [('en', 'bytecode cache'), ('fr', 'cache de bytecode')])
def test_the_junior_is_told_to_delete_the_bytecode_folder(lang, words):
    exc = _Refusal({'contract_code': 'artifact_integrity_failed',
                    'bytecode_folders': ['packages/mlflow_pyfunc/__pycache__']})
    item = capture.loading_refusal({'language': lang}, {'result_id': 'r1'}, exc)
    assert words in item['junior_message']
    assert 'packages/mlflow_pyfunc/__pycache__' in item['junior_message']


def test_the_export_copy_refuses_a_bytecode_cache(tmp_path: Path):
    (tmp_path / 'packages' / 'p' / '__pycache__').mkdir(parents=True)
    (tmp_path / 'packages' / 'p' / '__pycache__' / 'w.cpython-313.pyc').write_bytes(b'x')
    (tmp_path / 'predictor_bundle.json').write_text('{}')
    with pytest.raises(ExportError) as caught:
        artifact.read_files(tmp_path)
    assert 'artifact_integrity_failed' in (caught.value.code,
                                           caught.value.details.get('contract_code'))
    assert '__pycache__' in caught.value.remediation
