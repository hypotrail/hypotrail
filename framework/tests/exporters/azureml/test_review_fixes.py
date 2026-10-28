"""Regressions of the review of 24 October 2026 (``docs/acceptance/REVIEW-2026-10-24.md``),
on the synthetic study material: B-M1 (a superseded selection is never exported as the
selected model), B-M2 and B-M5 (``materialize`` reads records exactly as the engine does),
B-M4 (the exported commands always answer one JSON document), E2 (a reader refusal is an
export refusal), and the export minor items.

The study-level shapes (a real capture, a real final test) are in
``test_review_fixes_real.py``.
"""
from __future__ import annotations

import copy
import importlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

import azureml_study as fx
from export_env import needs_hydra, needs_mlflow, project_env
from mlkit.exporters.azureml import export_azureml
from mlkit.exporters.azureml.errors import ExportError

MOD = 'src.pipeline.utils.project'


def _doc(material, *, bundle=True):
    return fx.export_source(material['folder'],
                            bundle_dir=material['bundle'] if bundle else None,
                            contract=material['contract'], source=material['source'])


def _refused(run, code, **kwargs) -> ExportError:
    with pytest.raises(ExportError) as error:
        run(**kwargs)
    assert error.value.code == code, error.value.to_dict()
    assert {'path', 'remediation'} <= set(error.value.details)
    return error.value


# --- B-M1: the exported model is the confirmed selection --------------------------------

def test_a_selection_from_another_confirmation_is_refused(export, material, tmp_path):
    """The recipe names model_choice confirmed at revision 6; the decision in force is the
    one confirmed at revision 9 (another value). Nothing is exported as the selection."""
    doc = _doc(material)
    doc['decisions'][0].update({'value': 'fit.variant', 'revision': 9})
    error = _refused(export, 'contract_invalid', reader=fx.reader_of(doc))
    assert error.details['reason'] == 'selection_not_current_decision'
    assert error.details['selection_revision'] == 6 and error.details['decision_revision'] == 9
    assert not (tmp_path / 'export').exists()


def test_a_superseded_capture_before_the_opening_is_refused_with_a_reachable_remedy(
        export, material, tmp_path):
    doc = _doc(material)
    doc['predictor']['status'] = 'stale'
    doc['final_test'] = {'status': 'sealed', 'n_rows': fx.N_FINAL, 'final_result_id': None}
    error = _refused(export, 'model_not_captured', reader=fx.reader_of(doc))
    assert error.details['reason'] == 'capture_not_current_selection'
    assert 'predictor.capture' in error.details['remediation']
    assert not (tmp_path / 'export').exists()


def test_a_stale_capture_after_the_opening_is_exported_recipe_only(export, material):
    """B-M3 on the synthetic material: the capture can no longer be redone, so the recipe of
    the current selection is exported, without the model and without its evidence."""
    doc = _doc(material)
    doc['predictor'].update(status='stale', evidence_status='stale')
    doc['final_test'] = {'status': 'opened', 'n_rows': fx.N_FINAL, 'final_result_id': 'r-f'}
    payload, code, out = export(reader=fx.reader_of(doc), name='recipe-only')
    assert code == 0 and payload['artifact_status'] == 'missing'
    assert 'artifact_missing' in payload['warnings']
    assert not (out / 'data/hypotrail/models/evaluated').exists()
    ready = json.loads((out / 'data/hypotrail/contracts/readiness.json').read_text())
    assert ready['evidence_status'] == 'missing'


def test_the_evidence_status_follows_the_study_not_the_editable_binding(export, material):
    """The bundle's binding says evaluated; the study says the evidence is stale."""
    doc = _doc(material)
    doc['predictor']['evidence_status'] = 'stale'
    payload, _, out = export(reader=fx.reader_of(doc), name='ev')
    ready = json.loads((out / 'data/hypotrail/contracts/readiness.json').read_text())
    assert ready['evidence_status'] == 'stale'
    assert 'evidence_binding_disagrees_with_study' in payload['warnings']
    snapshot = json.loads((out / 'data/hypotrail/contracts/deployment-snapshot.json')
                          .read_text())
    assert snapshot['predictor']['evidence_status'] == 'stale'


def test_a_study_evaluated_bundle_without_binding_is_unassessed(export, material):
    doc = fx.export_source(material['folder'], bundle_dir=material['native_bundle'],
                           contract=material['contract'], source=material['source'])
    _, _, out = export(reader=fx.reader_of(doc), name='nb')
    ready = json.loads((out / 'data/hypotrail/contracts/readiness.json').read_text())
    assert ready['evidence_status'] == 'unassessed'


# --- E2: a refusal of the reader is an export refusal -----------------------------------

def test_a_stale_revision_from_the_reader_keeps_the_contract_fields(export, tmp_path):
    error = _refused(export, 'stale_revision', expected_revision=fx.REVISION - 1)
    assert error.details['contract_code'] == 'stale_revision'
    assert error.details['path'] == 'expected_revision'
    assert error.details['remediation']
    assert not (tmp_path / 'export').exists()


def test_any_runtime_contract_error_of_the_reader_is_a_refusal(export):
    from hypotrail_runtime.errors import ContractError

    def reader(path, revision):
        raise ContractError('artifact_integrity_failed', 'The bundle does not verify.',
                            path='payload/model.pkl', remediation='Capture again.')
    error = _refused(export, 'artifact_integrity_failed', reader=reader)
    assert error.details['contract_code'] == 'artifact_integrity_failed'
    assert error.details['path'] == 'payload/model.pkl'

    def other(path, revision):
        raise ContractError('backend_failed', 'A backend failed.', path='x')
    error = _refused(export, 'contract_invalid', reader=other)
    assert error.details['contract_code'] == 'backend_failed'


# --- minor: a study without recipe, profile, permissions, '???' ------------------------

@pytest.mark.parametrize(('predictor', 'final', 'expected'), [
    ({'status': 'not_applicable'}, {'status': 'absent'}, 'created before the final test'),
    ({'status': 'not_captured'}, {'status': 'opened'}, 'final test is opened'),
    ({'status': 'not_captured'}, {'status': 'sealed'}, 'Confirm the model choice'),
    ({'status': 'not_captured'}, {'status': 'absent'}, 'no final test'),
])
def test_a_source_without_recipe_names_a_reachable_remediation(export, material, predictor,
                                                                final, expected):
    doc = _doc(material, bundle=False)
    doc['scientific_contracts'] = {'source': 'none'}
    doc['predictor'] = {**predictor, 'evidence_status': 'unassessed'}
    doc['final_test'] = final
    doc['limitations'] = ['No configuration is chosen: no recipe can be described.']
    error = _refused(export, 'capability_not_supported', reader=fx.reader_of(doc))
    assert 'Update the engine' not in error.details['remediation']
    assert expected in error.details['remediation']
    assert error.details['limitations'] == doc['limitations']


def test_a_profile_that_is_not_utf8_is_a_refusal(tmp_path):
    from mlkit.exporters.azureml import profile as pf
    path = tmp_path / 'atelier.yaml'
    path.write_bytes('schema_version: hypotrail.azure_target/1\nresource_group: r\xe9seau\n'
                     .encode('latin-1'))
    with pytest.raises(ExportError) as error:
        pf.load(path)
    assert error.value.code == 'contract_invalid' and error.value.details['path'] == 'profile'


def test_a_profile_that_is_not_utf8_through_the_cli_exits_2(tmp_path):
    from mlkit.study import cli
    path = tmp_path / 'atelier.yaml'
    path.write_bytes(b'schema_version: hypotrail.azure_target/1\nworkspace: \xe9\n')
    outcome = cli.run(['export', 'azureml', '--study', str(tmp_path / 'study'),
                       '--expected-revision', '1', '--profile', str(path), '--plan'])
    assert outcome.exit_code == 2, outcome.payload
    assert outcome.payload['error']['code'] == 'contract_invalid'


def test_the_exported_root_folder_follows_the_umask(export):
    previous = os.umask(0o027)
    try:
        _, _, out = export(name='perm')
    finally:
        os.umask(previous)
    assert stat.S_IMODE(out.stat().st_mode) == 0o750
    assert stat.S_IMODE(out.stat().st_mode) == stat.S_IMODE((out / 'src').stat().st_mode)


def test_an_omegaconf_missing_marker_is_refused_at_export(export, material, tmp_path):
    doc = _doc(material, bundle=False)
    recipe = doc['scientific_contracts']['model_recipe']
    recipe['target']['unit'] = '???'
    recipe['output_contract']['unit'] = '???'
    error = _refused(export, 'contract_invalid', reader=fx.reader_of(doc), bundle=None)
    assert 'unit' in error.details['path']
    assert not (tmp_path / 'export').exists()


def test_parity_compare_refuses_swapped_infinities():
    from mlkit.integrations.mlflow_packaging import compare
    inf = float('inf')
    swapped = compare(pd.DataFrame({'p': [inf, 1.0]}), pd.DataFrame({'p': [1.0, inf]}),
                      1e-10, 1e-12)
    assert swapped['equal'] is False and swapped['reason'] == 'infinities_differ'
    signs = compare(pd.DataFrame({'p': [inf]}), pd.DataFrame({'p': [-inf]}), 1e-10, 1e-12)
    assert signs['equal'] is False
    same = compare(pd.DataFrame({'p': [inf, 1.0, -inf]}),
                   pd.DataFrame({'p': [inf, 1.0, -inf]}), 1e-10, 1e-12)
    assert same['equal'] is True


def test_the_development_plan_records_the_source_record_count(export):
    _, _, out = export(name='count')
    plan = json.loads((out / 'data/hypotrail/contracts/development-plan.json').read_text())
    assert plan['n_source_records'] == fx.N_ROWS


def test_a_record_count_below_the_development_rows_is_refused(export, material):
    doc = _doc(material)
    doc['development_plan']['n_source_records'] = 3
    _refused(export, 'contract_invalid', reader=fx.reader_of(doc))


# --- B-M2, B-M5: the exported record reader is the engine's -----------------------------

@pytest.fixture(scope='module')
def project_module(tmp_path_factory, material):
    """The exported ``project`` module, imported from a recipe-only export."""
    folder = tmp_path_factory.mktemp('reader')
    doc = fx.export_source(material['folder'], bundle_dir=None,
                           contract=material['contract'], source=material['source'])
    export_azureml(folder / 'study', expected_revision=fx.REVISION, out=folder / 'export',
                   profile_path=fx.profile(folder), reader=fx.reader_of(doc))
    sys.path.insert(0, str(folder / 'export'))
    try:
        yield importlib.import_module(MOD)
    finally:
        sys.path.remove(str(folder / 'export'))
        for name in [m for m in sys.modules if m == 'src' or m.startswith('src.')]:
            del sys.modules[name]


def _engine_records(path: Path, *, sep, header, columns, encoding='utf-8') -> dict:
    """``{row key: fields}`` as the engine reads the file (``mlkit.study.data``)."""
    from mlkit.study import data as dt
    case = SimpleNamespace(dataset={'sep': sep, 'quotechar': '"', 'header': header,
                                    'encoding': encoding, 'sha256': 'x'},
                           dataset_path=path, column_names=columns,
                           duplicates_policy=dt.DUPLICATES_GROUP)
    keys = dt.row_index(case, verify=False).keys
    split = dt._field_splitter(case)
    lines = path.read_bytes().decode(encoding).split('\n')
    first = 2 if header else 1
    body = lines[1:] if header else lines
    out = {f'L{first + i}': split(raw.rstrip('\r')) for i, raw in enumerate(body)}
    return {k: out[k] for k in keys}


def _contract(*, sep, header, columns, encoding='utf-8'):
    return {'parser': {'encoding': encoding, 'delimiter': sep, 'header': header,
                       'quotechar': '"', 'na_values': []},
            'row_identity': {'kind': 'source_position'},
            'columns': [{'name': c} for c in columns]}


SOURCES = {
    'csv_quoted_delimiter': (b'a;b;c\n1;"x;y";3\n4;"p";6\n', ';', True, 'utf-8'),
    'csv_crlf': (b'a;b;c\r\n1;x;3\r\n4;p;6\r\n', ';', True, 'utf-8'),
    'csv_line_separator': ('a;b;c\n1;"north\u2028east";3\n4;p;6\n'.encode(), ';', True,
                           'utf-8'),
    'csv_paragraph_separator': ('a;b;c\n1;"x\u2029y";3\n4;p;6\n'.encode(), ';', True,
                                'utf-8'),
    'csv_form_feed': (b'a;b;c\n1;"x\x0cy";3\n4;p;6\n', ';', True, 'utf-8'),
    'csv_vertical_tab_and_lone_cr': (b'a;b;c\n1;"x\x0by\rz";3\n4;p;6\n', ';', True, 'utf-8'),
    'csv_doubled_quotes': (b'a;b;c\n1;"say ""hi""";3\n4;p;6\n', ';', True, 'utf-8'),
    'latin1_nel_byte': (b'a;b;c\n1;"caf\x85";3\n4;p;6\n', ';', True, 'latin-1'),
    'ws_doubled_quote': (b'1 "say ""hi""" 3\n4 p 6\n', 'whitespace', False, 'utf-8'),
    'ws_backslash': (b'1 C:\\temp 3\n4 "a\\"b" 6\n', 'whitespace', False, 'utf-8'),
    'ws_lone_apostrophe': (b"1 o'neil 3\n4 p 6\n", 'whitespace', False, 'utf-8'),
    'ws_hash': (b'1 #5 3\n4 p 6\n', 'whitespace', False, 'utf-8'),
    'ws_crlf_and_tabs': (b'1\tx\t3\r\n4  p   6\r\n', 'whitespace', False, 'utf-8'),
    'ws_unicode_space': ('1 a\u2028b 3\n4 p 6\n'.encode(), 'whitespace', False, 'utf-8'),
}


@pytest.mark.parametrize('name', sorted(SOURCES))
def test_materialize_reads_records_as_the_engine_does(project_module, tmp_path, name):
    data, sep, header, encoding = SOURCES[name]
    path = tmp_path / 'source.data'
    path.write_bytes(data)
    columns = ['a', 'b', 'c']
    try:
        engine = _engine_records(path, sep=sep, header=header, columns=columns,
                                 encoding=encoding)
    except Exception:                       # noqa: BLE001 - the engine refuses this file
        with pytest.raises(project_module.ProjectError) as error:
            project_module._records(path, _contract(sep=sep, header=header, columns=columns,
                                                    encoding=encoding))
        assert error.value.code == 'data_identity_mismatch'
        return
    contract = _contract(sep=sep, header=header, columns=columns, encoding=encoding)
    keys, rows = project_module._source_lines(path, contract, set(engine))
    assert dict(zip(keys, rows)) == engine
    assert dict(project_module._records(path, contract)) == engine


def test_a_final_test_record_never_enters_the_development_rows(project_module, tmp_path):
    """Engine keys: L2 dev, L3 final (its text holds U+2028), L4 final, L5 and L6 dev. A
    reader splitting on U+2028 would read the engine's L4 under the key L5."""
    path = tmp_path / 'source.data'
    path.write_bytes('a;b;c\n1;dev-a;2\n3;"final\u2028secret";4\n5;FINAL-ROW;6\n'
                     '7;dev-b;8\n9;dev-c;10\n'.encode())
    contract = _contract(sep=';', header=True, columns=['a', 'b', 'c'])
    engine = _engine_records(path, sep=';', header=True, columns=['a', 'b', 'c'])
    development = {'L2', 'L5', 'L6'}
    keys, rows = project_module._source_lines(path, contract, development)
    got = dict(zip(keys, rows))
    assert got == {k: engine[k] for k in development}
    assert not any('FINAL-ROW' in v for row in rows for v in row)


def test_a_line_that_is_not_one_record_is_refused(project_module, tmp_path):
    path = tmp_path / 'source.data'
    path.write_bytes(b'1 2 3\n4 5\n6 7 8\n')
    with pytest.raises(project_module.ProjectError) as error:
        project_module._records(path, _contract(sep='whitespace', header=False,
                                                columns=['a', 'b', 'c']))
    assert error.value.code == 'data_identity_mismatch'
    assert error.value.details['problems'][0]['row_key'] == 'L2'


def test_a_source_that_is_not_in_the_contract_encoding_is_refused(project_module, tmp_path):
    path = tmp_path / 'source.data'
    path.write_bytes(b'1 caf\xe9 3\n')
    with pytest.raises(project_module.ProjectError) as error:
        project_module._records(path, _contract(sep='whitespace', header=False,
                                                columns=['a', 'b', 'c']))
    assert error.value.code == 'data_identity_mismatch'


def _typed_number(project_module, tmp_path, text: str, kind: str = 'float64',
                  decimal: str = '.'):
    """The value ``text`` of a prediction input in a ``kind`` column (round 2: number typing
    is what pandas reads, ``contracts.typed_features``; the private ``_convert`` of round 1
    was removed with the text typing it implemented)."""
    contracts = sys.modules['src.pipeline.utils.hypotrail.contracts']
    contract = {'parser': {'encoding': 'utf-8', 'delimiter': ';', 'header': True,
                           'quotechar': '"', 'na_values': [], 'decimal': decimal},
                'columns': [{'name': 'x', 'physical_type': kind, 'nullable': False,
                             'semantic_type': 'numeric', 'allowed_values': None}]}
    path = tmp_path / 'rows.csv'
    path.write_text('x\n"' + text.replace('"', '""') + '"\n', encoding='utf-8')
    return contracts.typed_features(path, contract)['x'].tolist()[0]


def test_a_decimal_comma_contract_types_its_values(project_module, tmp_path):
    """Round 2 changed one expectation: with a decimal comma, a value written with a point
    is not a number for pandas' parser but ``pandas.to_numeric`` (the engine's conversion,
    ``mlkit.study.data.check_values``) reads it, so the engine reads ``1.5`` as 1.5 and the
    export does too (round 1 refused it)."""
    assert _typed_number(project_module, tmp_path, '1,5', decimal=',') == 1.5
    assert _typed_number(project_module, tmp_path, '-2,25e1', decimal=',') == -22.5
    assert _typed_number(project_module, tmp_path, '1.5', decimal=',') == 1.5


@pytest.mark.parametrize('text', ['1_000', '0x10', '\u0663', '1e', 'nan', '1,5', '--1'])
def test_python_only_float_syntax_is_refused(project_module, tmp_path, text):
    """Round 2 changed two expectations: ``inf`` and ``Infinity`` are numbers for pandas
    (the engine's reader), so they are accepted (``test_review_round2``); the other texts
    are still refused."""
    contracts = sys.modules['src.pipeline.utils.hypotrail.contracts']
    with pytest.raises(contracts.ProjectError):
        _typed_number(project_module, tmp_path, text)


@pytest.mark.parametrize('text', ['1_000', '\u0663', '4.5', '0x4'])
def test_python_only_integer_syntax_is_refused(project_module, tmp_path, text):
    contracts = sys.modules['src.pipeline.utils.hypotrail.contracts']
    with pytest.raises(contracts.ProjectError):
        _typed_number(project_module, tmp_path, text, kind='int64')


@pytest.mark.parametrize(('text', 'value'), [(' 1e3 ', 1000.0), ('+1.5', 1.5), ('.5', 0.5),
                                             ('5.', 5.0), ('-.5e-3', -0.0005)])
def test_the_number_syntax_pandas_reads_is_accepted(project_module, tmp_path, text, value):
    assert _typed_number(project_module, tmp_path, text) == value


# --- B-M4 and the README: the exported commands, as an engineer runs them -------------

def _run(root, *args):
    return subprocess.run([sys.executable, *map(str, args)], cwd=root, capture_output=True,
                          text=True, env=project_env(), check=False, timeout=600)


def _json(proc) -> dict:
    assert '{' in proc.stdout, (proc.returncode, proc.stdout[-1500:], proc.stderr[-2500:])
    return json.loads(proc.stdout[proc.stdout.index('{'):])


@pytest.fixture(scope='module')
def exported(tmp_path_factory, material):
    folder = tmp_path_factory.mktemp('commands')
    export_azureml(folder / 'study', expected_revision=fx.REVISION, out=folder / 'export',
                   profile_path=fx.profile(folder), reader=fx.reader_of(_doc(material)))
    source = folder / 'original.data'
    shutil.copyfile(material['source'], source)
    return {'export': folder / 'export', 'source': source}


@pytest.fixture
def project(exported, tmp_path):
    root = tmp_path / 'moved' / 'p'
    shutil.copytree(exported['export'], root)
    assert _run(root, '-m', MOD, 'materialize', '--source', exported['source']).returncode == 0
    return root


def _tamper(root: Path) -> None:
    pkl = root / 'data/hypotrail/models/evaluated/payload/model.pkl'
    pkl.write_bytes(pkl.read_bytes() + b'\0')


@needs_mlflow
@needs_hydra
def test_validate_with_a_tampered_model_reports_failed_checks(project):
    _tamper(project)
    proc = _run(project, '-m', MOD, 'validate', '--offline')
    report = _json(proc)
    assert proc.returncode == 1 and report['status'] == 'failed'
    failed = {c['id']: c for c in report['checks'] if c['status'] == 'failed'}
    assert {'data_checksums', 'evaluated_model_parity'} <= set(failed)
    assert failed['evaluated_model_parity']['error']['code'] == 'artifact_integrity_failed'
    written = json.loads((project / 'outputs/validation.json').read_text())
    assert written['status'] == 'failed'
    assert 'Traceback' not in proc.stderr


@needs_mlflow
@needs_hydra
def test_predict_with_a_tampered_model_is_a_json_refusal(project, tmp_path):
    _tamper(project)
    proc = _run(project, '-m', MOD, 'predict', '--parity', '--output', tmp_path / 'p.json')
    out = _json(proc)
    assert proc.returncode == 2 and out['ok'] is False
    assert out['error']['code'] == 'artifact_integrity_failed'
    assert 'Traceback' not in proc.stderr


@needs_mlflow
@needs_hydra
@pytest.mark.parametrize('text', [
    'cylinders,displacement,horsepower,origin\n4,120.5,90,2\n',                 # missing
    'cylinders,displacement,horsepower,weight,origin,colour\n4,120.5,90,2500,2,red\n',
    'cylinders,displacement,horsepower,weight,origin\n4,1_20.5,90,2500,2\n',    # py float
    'cylinders;displacement;horsepower;weight;origin\n4;120.5;90;2500;2\n',     # other sep
    '',                                                                         # empty
    'cylinders,displacement\n"4,1\n',                                           # bad CSV
])
def test_predict_answers_a_malformed_input_with_a_json_refusal(project, tmp_path, text):
    rows = tmp_path / 'rows.csv'
    rows.write_text(text)
    proc = _run(project, '-m', MOD, 'predict', '--input', rows, '--output', tmp_path / 'o.json')
    out = _json(proc)
    assert proc.returncode == 2, (proc.returncode, out, proc.stderr[-800:])
    assert out['ok'] is False and out['error']['code']
    assert 'Traceback' not in proc.stderr


@needs_mlflow
@needs_hydra
def test_predict_of_a_missing_input_file_is_a_json_refusal(project, tmp_path):
    proc = _run(project, '-m', MOD, 'predict', '--input', tmp_path / 'absent.csv', '--output',
                tmp_path / 'o.json')
    assert proc.returncode == 2 and _json(proc)['error']['code'] == 'invalid_arguments'


@needs_mlflow
@needs_hydra
def test_validate_with_a_broken_yaml_config_reports_a_failed_check(project):
    path = project / 'src/conf/components/evaluation/default.yaml'
    path.write_text(path.read_text() + '\n  bad: [unclosed\n')
    proc = _run(project, '-m', MOD, 'validate', '--offline')
    report = _json(proc)
    assert proc.returncode == 1
    hydra = next(c for c in report['checks'] if c['id'] == 'hydra_config_frozen')
    assert hydra['status'] == 'failed' and hydra['error']['code'] == 'contract_invalid'
    assert (project / 'outputs/validation.json').is_file()


@needs_mlflow
@needs_hydra
def test_validate_refuses_a_scientific_change_whose_identity_was_edited(project):
    """The family is changed in the Hydra config and the expected identity in replay.yaml
    with it: the data folder's checksummed projection is the authority."""
    training = project / 'src/conf/components/training/default.yaml'
    training.write_text(training.read_text().replace('type: "linear"', 'type: "ridge"'))
    code = ('import sys\nfrom hydra import compose, initialize_config_dir\n'
            'from omegaconf import OmegaConf\n'
            'from src.pipeline.utils.hypotrail import canonical, projection\n'
            'with initialize_config_dir(config_dir=sys.argv[1], version_base=None):\n'
            '    cfg = compose(config_name="config")\n'
            'c = OmegaConf.to_container(cfg, resolve=True)\n'
            'print(canonical.canonical_sha256(projection.from_config(c)))\n')
    new = _run(project, '-c', code, project / 'src/conf').stdout.strip().splitlines()[-1]
    replay = project / 'src/conf/hypotrail/replay.yaml'
    replay.write_text(re.sub(r'expected_scientific_sha256: .*',
                             f'expected_scientific_sha256: "{new}"', replay.read_text()))
    proc = _run(project, '-m', MOD, 'validate', '--offline')
    report = _json(proc)
    hydra = next(c for c in report['checks'] if c['id'] == 'hydra_config_frozen')
    assert proc.returncode == 1 and report['status'] == 'failed'
    assert hydra['error']['code'] == 'scientific_config_changed'
    assert any('model' in d for d in hydra['error']['details']['differences'])


@needs_mlflow
@needs_hydra
def test_the_readme_quickstart_predict_command_works(project):
    readme = (project / 'README.md').read_text()
    match = re.search(r'python -m src\.pipeline\.utils\.project predict --input (\S+) '
                      r'--output (\S+)', readme)
    assert match, 'no predict command in README'
    proc = _run(project, '-m', MOD, 'predict', '--input', match.group(1), '--output',
                match.group(2))
    assert proc.returncode == 0, (proc.stdout[-600:], proc.stderr[-600:])
    document = json.loads((project / match.group(2)).read_text())
    parity = _run(project, '-m', MOD, 'predict', '--parity', '--output', 'outputs/parity.json')
    assert parity.returncode == 0
    assert document['rows'] == json.loads((project / 'outputs/parity.json').read_text())['rows']


def test_materialize_checks_the_recorded_record_count(project_module, tmp_path, monkeypatch):
    """With the checksum satisfied, a file the exported reader splits into another number of
    records than the study counted is refused (the count of development-plan.json)."""
    contracts = sys.modules['src.pipeline.utils.hypotrail.contracts']
    steps = sys.modules.get('src.pipeline.utils.hypotrail.steps') or importlib.import_module(
        'src.pipeline.utils.hypotrail.steps')
    source = tmp_path / 'source.data'
    source.write_bytes(b'1 a 3\n4 b 6\n7 c 9\n')
    contract = {**_contract(sep='whitespace', header=False, columns=['a', 'b', 'c']),
                'source_sha256': contracts.sha256_file(source)}
    contract['columns'] = [{'name': c, 'physical_type': 'string'} for c in ('a', 'b', 'c')]
    # A plan bound to its projection and snapshot (review round 9, R9AB-1: materialize
    # checks them before it reads the source).
    digest = contracts.canonical.canonical_sha256
    keys = ['L1', 'L2']
    plan = {'partitions': [{'id': 'fold_1', 'role': 'fold_1', 'row_keys': keys,
                            'keys_sha256': digest(keys)}],
            'protocol_id': 'p', 'keys_sha256': digest({'fold_1': keys}),
            'development_keys_sha256': digest(keys), 'n_development_rows': 2,
            'final_test': {'status': 'sealed'}, 'n_source_records': 4}
    projection = {'plan': {'protocol_id': 'p', 'keys_sha256': plan['keys_sha256']}}
    snapshot = {'evaluation_plan': {'protocol_id': 'p', 'keys_sha256': plan['keys_sha256'],
                                    'roles': ['fold_1'], 'n_development_rows': 2,
                                    'final_test': {'status': 'sealed'}}}
    documents = {'data-contract.json': contract, 'development-plan.json': plan,
                 'scientific-projection.json': projection, 'deployment-snapshot.json': snapshot}
    monkeypatch.setattr(contracts, 'verify_data_dir', lambda _d: {})
    monkeypatch.setattr(contracts, 'load_json', lambda p: copy.deepcopy(documents[p.name]))
    monkeypatch.setattr(project_module, 'DATA_DIR', tmp_path / 'data')
    with pytest.raises(project_module.ProjectError) as error:
        project_module.materialize(SimpleNamespace(source=str(source)))
    assert error.value.code == 'data_identity_mismatch'
    assert error.value.details == {'records_found': 3, 'records_expected': 4}
    assert not (tmp_path / 'data').exists()
    assert steps.development_keys(plan) == ['L1', 'L2']
