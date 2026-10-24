"""Regressions of the round-2 review of the Azure ML export (N1 to N7 and A1-R2b), on
temporary studies only (synthetic material, or temporary Auto MPG and synthetic studies
taken through the engine's commands).

* N1: re-confirming the same model choice after the final test opened (a hold, then the
  same value confirmed again, or the same value proposed and confirmed again) keeps the
  evaluated export: the capture is the confirmed selection when its configuration equals
  the confirmed one and the engine reports it current. Another configuration confirmed
  after the capture is still refused.
* N5: while the choice awaits re-confirmation, the refusal says that confirming the choice
  again in the chat makes the export possible, and no limitation claims that an earlier
  predictor was evaluated.
* A1-R2b: a self-consistent bundle put at the recorded bundle path is refused
  (``artifact_integrity_failed``), never exported under the study's evidence.
* N4: the capture's computation context names the study by the export's path-independent
  ``study_id``.
* N2, N3: the exported project reads the values the engine trained on (the engine's
  ``pandas.read_csv`` call), compared value by value with the engine's own frame; numbers
  are what pandas reads; the exported predict of the evaluated model equals the engine
  model's prediction on a row with an empty category.
* N6: a malformed ``hypotrail.parity_frame/1`` input of ``predict`` is a refusal.
* N7: a dataset token ``???`` in the recipe's preprocessing is carried to the exported
  configuration exactly, without refusal.
"""
from __future__ import annotations

import hashlib
import importlib
import io
import json
import re
import shutil
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

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'study'))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'study' / 'libraries'))

MOD = 'src.pipeline.utils.project'
WORDS = 'Yes, I choose that model because its error is smaller'
VARIANT_WORDS = 'Yes, I choose the variant because it is more stable'
OPEN = 'Yes, I open the final test now, because the model and the rule are fixed'


# --- helpers of the real studies -------------------------------------------------------

def _open_final(flow):
    from mlkit.study import state as st
    value = st.b1_default_value(flow.state(), 'final_test')
    proposal = flow.call('decide', 'propose', 'final_test', '--value-json', json.dumps(value),
                         '--restatement', 'You open the sealed final test once.',
                         '--rationale', 'The model is chosen.', '--request-id', flow.rid(),
                         '--expected-revision', flow.rev(), '--study', flow.study)
    flow.call('decide', 'confirm', proposal['result']['proposal_id'], '--user-words', OPEN,
              '--request-id', flow.rid(), '--expected-revision', flow.rev(),
              '--study', flow.study)


def _regression(base: Path, *, opened: bool, case_dir=None):
    import libkit
    flow = libkit.study_at_fits(base, case_dir=case_dir or libkit.AUTO)
    flow.run('fit.baseline')
    flow.run('fit.linear')
    flow.variant()
    flow.run('evaluate.regression')
    flow.decide('model_choice', 'fit.linear', words=WORDS)
    flow.run('predictor.capture', '--profile', 'workshop')
    if opened:
        _open_final(flow)
    return flow


def _copy(flow0, target: Path, prefix: str):
    from flowkit import Flow
    shutil.copytree(flow0.study, target)
    return Flow(target, flow0.case_dir, prefix=prefix)


def _export(flow, out: Path, expect=0):
    return flow.call('export', 'azureml', '--out', out, '--expected-revision', flow.rev(),
                     '--profile', fx.profile(out.parent), '--study', flow.study,
                     expect=expect)


def _propose_confirm(flow, decision: str, value, words: str):
    p = flow.call('decide', 'propose', decision, '--value-json', json.dumps(value),
                  '--restatement', f'You decide the {decision} as stated.',
                  '--rationale', 'It fits.', '--request-id', flow.rid(),
                  '--expected-revision', flow.rev(), '--study', flow.study)
    flow.call('decide', 'confirm', p['result']['proposal_id'], '--user-words', words,
              '--request-id', flow.rid(), '--expected-revision', flow.rev(),
              '--study', flow.study)


def _readiness(out: Path) -> dict:
    return json.loads((out / 'data/hypotrail/contracts/readiness.json').read_text())


@pytest.fixture(scope='module')
def sealed(tmp_path_factory):
    return _regression(tmp_path_factory.mktemp('sealed'), opened=False)


@pytest.fixture(scope='module')
def opened(tmp_path_factory):
    return _regression(tmp_path_factory.mktemp('opened'), opened=True)


# --- N1: the same choice confirmed again keeps the evaluated export ---------------------

@needs_mlflow
def test_the_same_choice_confirmed_again_after_the_opening_keeps_the_export(opened, tmp_path):
    from mlkit.contracts.export_source import read_export_source
    flow = _copy(opened, tmp_path / 'study', 'n1a')
    before = flow.state()['decisions']['model_choice']['revision']
    _propose_confirm(flow, 'model_choice', 'fit.linear', WORDS)
    assert flow.state()['decisions']['model_choice']['revision'] > before
    source = read_export_source(flow.study, flow.rev())
    assert source.predictor.status == 'captured'
    assert source.predictor.evidence_status == 'evaluated'
    assert source.scientific_contracts['source'] == 'captured_bundle'
    assert source.scientific_contracts['selection']['capture'] == 'selected'
    assert not any('earlier predictor' in x for x in source.limitations)
    payload = _export(flow, tmp_path / 'out')
    assert payload['artifact_status'] == 'packaged'
    assert _readiness(tmp_path / 'out')['evidence_status'] == 'evaluated'


@needs_mlflow
def test_a_hold_then_the_same_choice_again_keeps_the_export(opened, tmp_path):
    """N1 and N5: a hold on the confirmed model choice after the opening, then the same
    choice confirmed again in the chat."""
    from mlkit.contracts.export_source import read_export_source
    flow = _copy(opened, tmp_path / 'study', 'n1b')
    note = flow.call('decide', 'note', '--about', 'model_choice', '--text',
                     'Wait, I want to check the model choice with my manager first',
                     '--request-id', flow.rid(), '--expected-revision', flow.rev(),
                     '--study', flow.study)
    assert note['ok']
    assert flow.state()['decisions']['model_choice']['status'] == 'reconfirm_required'
    resolved = flow.call('decide', 'note', '--resolve', note['result']['note_id'], '--text',
                         'My manager agrees with the model choice, the linear model',
                         '--request-id', flow.rid(), '--expected-revision', flow.rev(),
                         '--study', flow.study)
    assert resolved['ok']
    assert flow.state()['decisions']['model_choice']['status'] == 'reconfirm_required'
    source = read_export_source(flow.study, flow.rev())
    assert source.predictor.status == 'stale'
    assert source.scientific_contracts['selection']['capture'] == 'awaiting_reconfirmation'
    assert not any('earlier predictor' in x for x in source.limitations)
    assert not any('did not score a captured predictor' in x for x in source.limitations)
    assert any('Re-confirming the same choice in the chat makes the export possible again' in x
               for x in source.limitations)
    refused = _export(flow, tmp_path / 'held', expect=2)['error']
    assert refused['code'] == 'contract_invalid'
    assert refused['details']['reason'] == 'selection_awaits_reconfirmation'
    assert 'Confirm the same model choice again in the chat' in refused['details']['remediation']
    assert 'makes the export possible again' in refused['details']['remediation']
    assert not (tmp_path / 'held').exists()
    _propose_confirm(flow, 'model_choice', 'fit.linear', WORDS)
    source = read_export_source(flow.study, flow.rev())
    assert (source.predictor.status, source.predictor.evidence_status) == ('captured',
                                                                            'evaluated')
    payload = _export(flow, tmp_path / 'out')
    assert payload['artifact_status'] == 'packaged'
    assert _readiness(tmp_path / 'out')['evidence_status'] == 'evaluated'


@needs_mlflow
def test_another_model_then_back_before_the_opening_keeps_the_capture(sealed, tmp_path):
    """The reviewer's probe S1 asserted ``stale`` here (the round-1 rule: value **and**
    revision). Under the round-2 rule (the engine's own: same configuration and a current
    capture, which is what the final-test opening requires) the capture of ``fit.linear``
    is the confirmed selection again once ``fit.linear`` is confirmed again, so the
    expectation changed: it is exported, still unassessed (the final test is sealed)."""
    from mlkit.contracts.export_source import read_export_source
    flow = _copy(sealed, tmp_path / 'study', 'n1c')
    flow.decide('model_choice', 'fit.variant', words=VARIANT_WORDS)
    middle = read_export_source(flow.study, flow.rev())
    assert middle.predictor.status == 'stale'
    assert middle.scientific_contracts['selection']['capture'] == 'superseded'
    flow.decide('model_choice', 'fit.linear', words=WORDS)
    source = read_export_source(flow.study, flow.rev())
    assert source.predictor.status == 'captured'
    assert source.predictor.evidence_status == 'unassessed'
    payload = _export(flow, tmp_path / 'out')
    assert payload['artifact_status'] == 'packaged'


@needs_mlflow
def test_another_configuration_confirmed_after_the_opening_is_never_the_capture(opened,
                                                                                tmp_path):
    from mlkit.contracts.export_source import read_export_source
    flow = _copy(opened, tmp_path / 'study', 'n1d')
    _propose_confirm(flow, 'model_choice', 'fit.variant', VARIANT_WORDS)
    source = read_export_source(flow.study, flow.rev())
    assert source.predictor.status == 'stale'
    assert source.predictor.evidence_status != 'evaluated'
    assert source.scientific_contracts['selection']['capture'] == 'superseded'
    assert source.scientific_contracts.get('source') != 'captured_bundle'
    assert any('earlier predictor' in x for x in source.limitations)


# --- N1 on the synthetic material: the exporter applies the same rule --------------------

def _doc(material, *, bundle=True):
    return fx.export_source(material['folder'],
                            bundle_dir=material['bundle'] if bundle else None,
                            contract=material['contract'], source=material['source'])


def _reconfirmed(material, **changes) -> dict:
    """The recipe was selected at revision 6; the same choice was confirmed again at 9."""
    doc = _doc(material)
    doc['decisions'][0]['revision'] = 9
    doc['scientific_contracts']['source'] = 'captured_bundle'
    config = {'model': 'linear', 'rule': None}
    doc['development_plan']['configuration'] = config
    doc['results'].append({'result_id': 'r-capture-1', 'activity': 'predictor.capture',
                           'current': True})
    doc['scientific_contracts']['selection'] = {
        'decision_id': 'model_choice', 'decision_status': 'confirmed', 'decision_revision': 9,
        'confirmed_configuration': config, 'capture_result_id': 'r-capture-1',
        'capture_configuration': dict(config), 'capture': 'selected', 'rule': 'r'}
    for key, value in changes.items():
        if key == 'capture_current':
            doc['results'][-1]['current'] = value
        else:
            doc['scientific_contracts']['selection'][key] = value
    return doc


def test_the_same_configuration_confirmed_again_is_exported(export, material):
    payload, code, out = export(reader=fx.reader_of(_reconfirmed(material)), name='same')
    assert code == 0 and payload['artifact_status'] in ('captured', 'packaged')
    snapshot = json.loads((out / 'data/hypotrail/contracts/deployment-snapshot.json')
                          .read_text())
    assert snapshot['selected']['revision'] == 6


@pytest.mark.parametrize('changes', [
    {'capture_configuration': {'model': 'variant_1', 'rule': None}},
    {'capture': 'superseded'},
    {'capture_current': False},
    {'decision_revision': 7},
    {'capture_result_id': 'r-capture-0'},
])
def test_a_reconfirmation_that_is_not_the_capture_is_refused(export, material, changes):
    with pytest.raises(ExportError) as error:
        export(reader=fx.reader_of(_reconfirmed(material, **changes)))
    assert error.value.code == 'contract_invalid'
    assert error.value.details['reason'] == 'selection_not_current_decision'


def test_a_choice_awaiting_reconfirmation_is_refused_with_its_remedy(export, material):
    doc = _doc(material)
    doc['predictor']['status'] = 'stale'
    doc['scientific_contracts']['selection'] = {'capture': 'awaiting_reconfirmation',
                                                'decision_id': 'model_choice'}
    with pytest.raises(ExportError) as error:
        export(reader=fx.reader_of(doc))
    assert error.value.details['reason'] == 'selection_awaits_reconfirmation'
    assert 'makes the export possible again' in error.value.details['remediation']


# --- A1-R2b: the bundle at the recorded path is the recorded predictor -------------------

def test_a_source_naming_another_predictor_id_is_refused(export, material):
    doc = _doc(material)
    doc['predictor']['predictor_id'] = 'f' * 64
    with pytest.raises(ExportError) as error:
        export(reader=fx.reader_of(doc))
    assert error.value.code == 'artifact_integrity_failed'
    assert error.value.details['reason'] == 'bundle_not_recorded_predictor'
    assert 'predictor_id' in error.value.details['mismatched']


def test_a_binding_of_another_final_result_is_refused(export, material):
    doc = _doc(material)
    doc['predictor']['final_result_id'] = 'r-final-other'
    with pytest.raises(ExportError) as error:
        export(reader=fx.reader_of(doc))
    assert error.value.code == 'artifact_integrity_failed'
    assert 'evidence_binding' in error.value.details['mismatched']


def _other_model(bundle: Path):
    """Another self-consistent predictor of the same recipe and data contract: the fitted
    pipeline of ``bundle`` with other cap bounds (its parity rows unchanged)."""
    import pickle

    from hypotrail_runtime import inference, verify_bundle
    from hypotrail_runtime.predictor import FittedPredictor, frame_from_document
    desc = verify_bundle(bundle)
    pipe = pickle.loads((bundle / desc.manifest.payload_files[0].relative_path).read_bytes())
    parity = frame_from_document(json.loads((bundle / desc.bundle.parity.features_path)
                                            .read_bytes()))
    view, _ = inference.check_frame(desc.data_contract, parity,
                                    features=list(desc.recipe.features))
    prep = pipe.named_steps['prepare']
    column = next(c for c in desc.recipe.features
                  if desc.data_contract.column(c).physical_type == 'float64'
                  and view[c].notna().sum() > 1)
    prep.cap_bounds_ = {**prep.cap_bounds_,
                        column: [float(view[column].min()), float(view[column].max())]}
    fitted = FittedPredictor(recipe=desc.recipe, data_contract=desc.data_contract,
                             pipeline=pipe, training_scope=desc.manifest.training_scope,
                             n_train=int(desc.manifest.extensions['hypotrail.n_train']))
    return fitted, view


def test_another_bundle_at_the_recorded_path_is_refused(tmp_path):
    """The reviewer's attack: after a promoted final test, the folder at the registry's
    bundle path is replaced by another self-consistent bundle of the same recipe, with an
    evidence binding naming itself."""
    import test_capture_final as tcf
    from hypotrail_runtime import capture_predictor, verify_bundle, write_evidence_binding

    from mlkit.contracts.export_source import read_export_source
    from mlkit.exporters.azureml.command import export_azureml as run_export
    flow = tcf._chosen(tmp_path, 'regression')
    values = flow.run('predictor.capture')['values']
    assert tcf._open(flow)['result']['opening']['status'] == 'promoted'
    bundle = tcf._home(flow) / values['bundle']
    fitted, parity = _other_model(bundle)
    forged = tmp_path / 'forged'
    capture_predictor(fitted, None, parity, forged, None, code_fingerprint='c' * 64)
    forged_id = verify_bundle(forged).predictor_id
    assert forged_id != values['predictor_id']
    binding = json.loads((bundle / verify_bundle(bundle).bundle.evidence_binding_path)
                         .read_bytes())
    shutil.rmtree(bundle)
    shutil.copytree(forged, bundle)
    write_evidence_binding(bundle, {**binding, 'predictor_id': forged_id})
    assert read_export_source(flow.study, flow.rev()).predictor.predictor_id == \
        values['predictor_id']
    with pytest.raises(ExportError) as error:
        run_export(flow.study, expected_revision=flow.rev(), out=tmp_path / 'export')
    assert error.value.code == 'artifact_integrity_failed'
    assert error.value.details['found_predictor_id'] == forged_id
    assert error.value.details['recorded_predictor_id'] == values['predictor_id']
    assert 'never replace or edit a bundle' in error.value.details['remediation']
    assert not (tmp_path / 'export').exists()


# --- N4: the capture names the study by its path-independent identity --------------------

def test_the_capture_context_names_the_study_without_its_path(tmp_path):
    import test_capture_final as tcf

    from mlkit.contracts.export_source import read_export_source
    flow = tcf._chosen(tmp_path / 'deep' / 'folder', 'regression')
    values = flow.run('predictor.capture')['values']
    bundle = tcf._home(flow) / values['bundle']
    context = json.loads((bundle / 'computation_context.json').read_bytes())
    path_hash = hashlib.sha256(str(Path(flow.study).resolve()).encode()).hexdigest()[:16]
    assert context['study_id'] == read_export_source(flow.study, flow.rev()).study_id
    assert context['study_id'] != path_hash
    files = b''.join(p.read_bytes() for p in bundle.rglob('*') if p.is_file())
    assert path_hash.encode() not in files
    assert str(tmp_path).encode() not in files


# --- N2, N3: the exported project reads the engine's values ------------------------------

@pytest.fixture(scope='module')
def project_module(tmp_path_factory, material):
    """The exported ``project`` module, imported from a recipe-only export."""
    folder = tmp_path_factory.mktemp('round2-reader')
    export_azureml(folder / 'study', expected_revision=fx.REVISION, out=folder / 'export',
                   profile_path=fx.profile(folder), reader=fx.reader_of(_doc(material,
                                                                              bundle=False)))
    sys.path.insert(0, str(folder / 'export'))
    try:
        module = importlib.import_module(MOD)
        yield SimpleNamespace(project=module,
                              contracts=sys.modules['src.pipeline.utils.hypotrail.contracts'])
    finally:
        sys.path.remove(str(folder / 'export'))
        for name in [m for m in sys.modules if m == 'src' or m.startswith('src.')]:
            del sys.modules[name]


# name: (bytes, sep, header, columns, na_values, numeric columns or None, development rows)
HOSTILE = {
    'empty_category': (b'colour,score\nred,1\n,2\nblue,?\n', ',', True, ['colour', 'score'],
                       ['?'], None, None),
    'na_value_float_variant': (b'colour,score\nred,1.5\nblue,-999.0\ngreen,-999\n', ',', True,
                               ['colour', 'score'], ['-999'], None, None),
    'whitespace_nbsp_in_a_token': ('1 alpha 3.5\n2 be ta\n3 gamma 4.5\n'.encode(),
                                   'whitespace', False, ['id', 'name', 'score'], [], None,
                                   None),
    'whitespace_form_feed': (b'1 alpha 3.5\n2 beta\x0c4\n3 gamma 4.5\n', 'whitespace', False,
                             ['id', 'name', 'score'], [], None, None),
    'csv_quote_inside_field': (b'a;b;c\n1;"x"y;3\n2;p"q"r;4\n3;" s";5\n', ';', True,
                               ['a', 'b', 'c'], [], None, None),
    'bom_headerless': ('﻿red,1\nblue,2\n'.encode(), ',', False, ['colour', 'score'], [],
                       None, None),
    'quoted_empty_whitespace': (b'1 "" 3.5\n2 b 4\n', 'whitespace', False,
                                ['id', 'name', 'score'], [], None, None),
    'numbers_pandas_reads': (b'colour,ratio\nred,1.5\nblue,inf\ngreen,\x0c2.5\nwhite,-Infinity'
                             b'\n', ',', True, ['colour', 'ratio'], [], None, None),
    'number_text_only_in_excluded_rows': (b'colour,ratio\nred,1.5\nblue,n/a\ngreen,2\n', ',',
                                          True, ['colour', 'ratio'], [], ['ratio'],
                                          ['L2', 'L4']),
    'numeric_codes_as_text': (b'code,score\n01,1\n2,2\nx,3\n', ',', True, ['code', 'score'],
                              [], None, None),
    'backslash_and_marker_texts': (b'name,score\n\\N,1\n\\x,2\n,3\n', ',', True,
                                   ['name', 'score'], [], None, None),
    'booleans': (b'flag,score\nTrue,1\nfalse,2\nTRUE,3\n', ',', True, ['flag', 'score'], [],
                 None, None),
}


def _round1_sources() -> dict:
    """The round-1 record sources (``test_review_fixes.SOURCES``) that the engine reads."""
    import test_review_fixes as r1
    out = {}
    for name, (data, sep, header, encoding) in r1.SOURCES.items():
        if encoding == 'utf-8':
            out[f'round1_{name}'] = (data, sep, header, ['a', 'b', 'c'], [], None, None)
    return out


SOURCES = {**HOSTILE, **_round1_sources()}


def _engine(path: Path, sep, header, columns, na, numeric, rows):
    """The engine's own development frame (``mlkit.study.data``: row index, the pandas
    read, the restriction to the development rows and the value check), and its contract
    columns."""
    from pandas.api.types import is_numeric_dtype

    from hypotrail_runtime.inference import physical_type
    from mlkit.study import data as dt
    dataset = {'sep': sep, 'quotechar': '"', 'header': header, 'encoding': 'utf-8',
               'sha256': 'x', 'decimal': '.', 'na_values': list(na)}
    case = SimpleNamespace(dataset=dataset, dataset_path=path, column_names=columns,
                           duplicates_policy=dt.DUPLICATES_GROUP,
                           read_sep=r'\s+' if sep == 'whitespace' else sep)
    index = dt.row_index(case, verify=False)
    raw = dt.read_frame(case, index)
    if numeric is None:
        numeric = [c for c in columns if is_numeric_dtype(raw[c].dtype)]
    target = next(c for c in columns if raw[c].notna().all())
    case.document = {'variables': [{'name': c, 'type': 'numeric' if c in numeric
                                    else 'category'} for c in columns]}
    case.target_column, case.task = target, 'regression'
    keys = list(index.keys) if rows is None else rows
    frame = raw.loc[keys].copy()
    dt.check_values(case, frame)
    contract = {'parser': {'encoding': 'utf-8', 'delimiter': sep, 'header': header,
                           'quotechar': '"', 'na_values': list(na), 'decimal': '.'},
                'row_identity': {'kind': 'source_position'},
                'columns': [{'name': c, 'physical_type': physical_type(frame[c]) or 'string',
                             'semantic_type': 'numeric' if c in numeric else 'category',
                             'nullable': True, 'allowed_values': None} for c in columns]}
    return frame, contract


def _same(a, b) -> bool:
    if pd.isna(a) or pd.isna(b):
        return bool(pd.isna(a) and pd.isna(b))
    return type(a) is type(b) and a == b if isinstance(a, str) or isinstance(b, str) \
        else bool(a == b) and isinstance(a, bool) == isinstance(b, bool)


def _plain(value):
    return value.item() if hasattr(value, 'item') else value


@pytest.mark.parametrize('name', sorted(SOURCES))
def test_the_materialised_rows_hold_the_engine_values(project_module, tmp_path, name):
    """Value by value: the engine's development frame against the frame the exported project
    materialises (its pandas reading, its numeric conversion, its row files written and read
    back), never the record splitter against itself."""
    data, sep, header, columns, na, numeric, rows = SOURCES[name]
    path = tmp_path / 'source.data'
    path.write_bytes(data)
    pm, contracts = project_module.project, project_module.contracts
    from mlkit.study.case import CaseError
    try:
        engine, contract = _engine(path, sep, header, columns, na, numeric, rows)
    except CaseError:
        # The engine refuses this file (not one record per line): so does the project.
        contract = {'parser': {'encoding': 'utf-8', 'delimiter': sep, 'header': header,
                               'quotechar': '"', 'na_values': list(na), 'decimal': '.'},
                    'row_identity': {'kind': 'source_position'},
                    'columns': [{'name': c} for c in columns]}
        with pytest.raises(pm.ProjectError) as error:
            pm._records(path, contract)
        assert error.value.code == 'data_identity_mismatch'
        return
    keys = [key for key, _ in pm._records(path, contract)]
    frame = contracts.read_source(path, contract, keys)
    development = frame.loc[list(engine.index)]
    development = contracts.engine_values(development, contract, 'source')
    written = tmp_path / 'development.csv'
    contracts.write_rows(development.reset_index(), written)
    exported = contracts.read_rows(written, contract).set_index(contracts.KEY_COLUMN)
    assert list(exported.index) == list(engine.index)
    differences = {}
    for key in engine.index:
        for column in columns:
            e, x = _plain(engine.loc[key, column]), _plain(exported.loc[key, column])
            if not _same(e, x):
                differences[(key, column)] = (e, x)
    assert differences == {}, differences
    from hypotrail_runtime.inference import physical_type
    for column in columns:
        assert physical_type(exported[column]) == physical_type(engine[column]), column


def test_the_project_row_files_keep_every_text(project_module, tmp_path):
    contracts = project_module.contracts
    contract = {'columns': [{'name': 't', 'physical_type': 'string', 'nullable': True,
                             'allowed_values': None},
                            {'name': 'x', 'physical_type': 'float64', 'nullable': True,
                             'allowed_values': None}]}
    texts = ['', '\\N', '\\', '\\\\N', 'a\rb', 'x\ny', ' ', ' lead', '"q"', 'a,b',
             '﻿bom', '\x0c', None]
    numbers = [0.1, float('inf'), float('-inf'), 1e308, -0.0, 5e-324, 2.0 ** 60, None, 1.5,
               -2.25, 3.0, 7.0, None]
    frame = pd.DataFrame({contracts.KEY_COLUMN: [f'L{i}' for i in range(len(texts))],
                          't': texts, 'x': numbers})
    path = tmp_path / 'rows.csv'
    contracts.write_rows(frame, path)
    back = contracts.read_rows(path, contract)
    for i, text in enumerate(texts):
        got = back['t'][i]
        assert (pd.isna(got) if text is None else got == text), (i, text, got)
    for i, number in enumerate(numbers):
        got = back['x'][i]
        assert (pd.isna(got) if number is None else repr(float(got)) == repr(number))


@pytest.mark.parametrize(('text', 'value'), [
    ('inf', float('inf')), ('Infinity', float('inf')), ('-iNF', float('-inf')),
    ('\x0c2.5', 2.5), ('2.5\x0b', 2.5), (' 1e3 ', 1000.0), ('+1.5', 1.5), ('.5', 0.5)])
def test_prediction_numbers_are_what_pandas_reads(project_module, tmp_path, text, value):
    """N3: a number of the prediction input is what pandas reads (the engine's reader); the
    round-1 refusal of ``inf`` and ``Infinity`` is withdrawn (pandas reads them)."""
    contracts = project_module.contracts
    contract = {'parser': {'encoding': 'utf-8', 'delimiter': ',', 'header': True,
                           'quotechar': '"', 'na_values': ['?'], 'decimal': '.'},
                'columns': [{'name': 'x', 'physical_type': 'float64', 'nullable': True,
                             'semantic_type': 'numeric', 'allowed_values': None}]}
    path = tmp_path / 'rows.csv'
    path.write_bytes(b'x\n' + text.encode() + b'\n?\n')
    typed = contracts.typed_features(path, contract)
    assert typed['x'].dtype == 'float64'
    assert typed['x'][0] == value and pd.isna(typed['x'][1])
    engine = pd.to_numeric(pd.read_csv(io.StringIO('x\n' + text + '\n'), keep_default_na=False)
                           ['x'])
    assert float(engine[0]) == value


@pytest.mark.parametrize('text', ['1_000', '0x10', 'abc', '--1'])
def test_prediction_texts_pandas_does_not_read_as_numbers_are_refused(project_module, tmp_path,
                                                                     text):
    contracts = project_module.contracts
    contract = {'parser': {'encoding': 'utf-8', 'delimiter': ',', 'header': True,
                           'quotechar': '"', 'na_values': [], 'decimal': '.'},
                'columns': [{'name': 'x', 'physical_type': 'float64', 'nullable': True,
                             'semantic_type': 'numeric', 'allowed_values': None}]}
    path = tmp_path / 'rows.csv'
    path.write_text(f'x\n{text}\n')
    with pytest.raises(contracts.ProjectError) as error:
        contracts.typed_features(path, contract)
    assert error.value.code == 'contract_invalid'


def test_a_prediction_input_keeps_an_empty_category(project_module, tmp_path):
    contracts = project_module.contracts
    contract = {'parser': {'encoding': 'utf-8', 'delimiter': ';', 'header': True,
                           'quotechar': '"', 'na_values': ['NA'], 'decimal': '.'},
                'columns': [{'name': 'kind', 'physical_type': 'string', 'nullable': True,
                             'semantic_type': 'category', 'allowed_values': None}]}
    path = tmp_path / 'rows.csv'
    path.write_text('kind\nurban\n\nNA\n"01"\n')
    typed = contracts.typed_features(path, contract)
    values = typed['kind'].tolist()
    assert values[0] == 'urban' and values[1] == '' and pd.isna(values[2])
    assert values[3] == '01'


# --- N2 end to end: a real study with an empty category ---------------------------------

def _empty_category_case(base: Path) -> Path:
    """A synthetic regression case whose categorical feature holds empty cells ('' is a
    category for the engine: na_values is ['NA'])."""
    import flowkit as fk
    made = fk.make_case(base / 'case', task='regression', n_rows=300)
    lines = made['data'].read_text().split('\n')
    out = [lines[0]]
    for line in lines[1:]:
        if line:
            fields = line.split(';')
            fields[3] = {'1': 'urban', '2': 'rural', '3': ''}[fields[3]]
            line = ';'.join(fields)
        out.append(line)
    raw = '\n'.join(out).encode()
    made['data'].write_bytes(raw)
    text = made['case'].read_text()
    made['case'].write_text(re.sub(r'sha256: [0-9a-f]{64}',
                                   'sha256: ' + hashlib.sha256(raw).hexdigest(), text, count=1))
    return made['case'].parent


def _run(root: Path, *args):
    return subprocess.run([sys.executable, '-m', MOD, *map(str, args)], cwd=root,
                          capture_output=True, text=True, env=project_env(), check=False,
                          timeout=600)


@pytest.fixture(scope='module')
def empty_category(tmp_path_factory):
    base = tmp_path_factory.mktemp('empty-category')
    case_dir = _empty_category_case(base)
    flow = _regression(base, opened=False, case_dir=case_dir)
    out = base / 'export'
    payload = flow.call('export', 'azureml', '--out', out, '--expected-revision', flow.rev(),
                        '--profile', fx.profile(base), '--study', flow.study)
    assert payload['artifact_status'] == 'packaged', payload
    result = _run(out, 'materialize', '--source', case_dir / 'data.csv')
    assert result.returncode == 0, result.stdout + result.stderr
    return flow, case_dir, out


@needs_mlflow
@needs_hydra
def test_the_materialised_rows_of_a_real_study_are_the_engine_frame(empty_category):
    import flowkit as fk
    from mlkit.study import case as c, data as dt
    flow, case_dir, out = empty_category
    engine = dt.load_development(c.load_case(case_dir),
                                 fk.partition_keys(flow.study, 'development')).frame
    assert (engine['branch_type'] == '').any()
    sys.path.insert(0, str(out))
    try:
        from src.pipeline.utils.hypotrail import contracts
        contract = json.loads((out / 'data/hypotrail/contracts/data-contract.json').read_text())
        typed = contracts.read_rows(out / 'data/hypotrail/development/development.csv',
                                    contract)
    finally:
        sys.path.remove(str(out))
        for name in [m for m in sys.modules if m == 'src' or m.startswith('src.')]:
            del sys.modules[name]
    typed = typed.set_index(contracts.KEY_COLUMN).loc[list(engine.index)]
    differences = [(k, col) for col in engine.columns for k in engine.index
                   if not _same(_plain(engine.loc[k, col]), _plain(typed.loc[k, col]))]
    assert differences == []


@needs_mlflow
@needs_hydra
def test_the_exported_predict_equals_the_engine_model_on_an_empty_category(empty_category,
                                                                         tmp_path):
    import hypotrail_runtime as rt
    _, _, out = empty_category
    bundle = out / 'data/hypotrail/models/evaluated'
    predictor = rt.load_predictor(bundle, trusted_roots=[bundle])
    contract = json.loads((out / 'data/hypotrail/contracts/data-contract.json').read_text())
    features = [c['name'] for c in contract['columns'] if c['role'] == 'feature']
    assert 'branch_type' in features
    row = {'floor_area': 1200.0, 'staff_count': 10, 'opening_hours': 40.0, 'branch_type': '',
           'survey_score': 5.0, 'heating_cost': 1500.0, 'returns_logged': 250.0}
    row = {k: row[k] for k in features}
    native = predictor.predict(pd.DataFrame([row])).values
    rows = tmp_path / 'rows.csv'
    pd.DataFrame([row]).to_csv(rows, index=False)
    result = _run(out, 'predict', '--input', rows, '--output', tmp_path / 'p.json')
    assert result.returncode == 0, result.stdout + result.stderr
    exported = json.loads((tmp_path / 'p.json').read_text())['rows']
    assert abs(next(iter(exported[0].values())) - float(native[0])) < 1e-9


# --- N6: every predict input is answered with one JSON document --------------------------

HEADER = 'floor_area,staff_count,opening_hours,branch_type,survey_score,heating_cost,' \
         'returns_logged'
INPUTS = {
    'missing_feature_column': 'floor_area,staff_count\n1,2\n',
    'extra_column': HEADER + ',zzz\n1,2,3,urban,4,5,6,7\n',
    'header_only': HEADER + '\n',
    'not_number': HEADER + '\nx,2,3,urban,4,5,6\n',
    'unknown_category': HEADER + '\n1,2,3,metro,4,5,6\n',
    'duplicate_header': HEADER.replace('staff_count', 'floor_area') + '\n1,2,3,urban,4,5,6\n',
    'empty_file': '',
    'binary': None,
    'json_not_parity': '{"schema_version": "x"}',
    'parity_frame_bad': '{"schema_version": "hypotrail.parity_frame/1", "columns": 3}',
    'parity_frame_no_rows': '{"schema_version": "hypotrail.parity_frame/1"}',
}


@needs_mlflow
@needs_hydra
@pytest.mark.parametrize('name', sorted(INPUTS))
def test_predict_answers_every_input_with_one_json_document(empty_category, tmp_path, name):
    _, _, out = empty_category
    text = INPUTS[name]
    path = tmp_path / ('in.json' if name.startswith(('json', 'parity')) else 'in.csv')
    if text is None:
        path.write_bytes(b'\xff\xfe\x00bad\x00')
    else:
        path.write_text(text)
    result = _run(out, 'predict', '--input', path, '--output', tmp_path / 'p.json')
    document = json.loads(result.stdout)
    assert 'Traceback' not in result.stderr
    assert result.returncode in (0, 2), document
    if result.returncode == 2:
        assert document['error']['code'] != 'internal_error'
    if name.startswith('parity_frame'):
        assert result.returncode == 2
        assert document['error']['code'] == 'contract_invalid'


# --- N7: a dataset token '???' in the preprocessing --------------------------------------

def _question_marks(material) -> dict:
    doc = _doc(material, bundle=False)
    recipe = doc['scientific_contracts']['model_recipe']
    contract = doc['scientific_contracts']['data_contract']
    contract['parser']['na_values'] = ['???', '${x}']
    for step in recipe['preprocessing']:
        if step['operation'] == 'special_value_indicator':
            step['parameters']['values'] = [
                {'column': 'horsepower', 'value': '???', 'name': 'horsepower=???',
                 'reads_missing': True},
                {'column': 'weight', 'value': '${x}', 'name': 'weight=${x}',
                 'reads_missing': True}]
    return doc


def _texts(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from _texts(item)
    elif isinstance(value, list):
        for item in value:
            yield from _texts(item)


def test_a_dataset_token_read_by_omegaconf_is_carried_exactly(export, material):
    from mlkit.exporters.azureml import projection
    doc = _question_marks(material)
    payload, code, out = export(reader=fx.reader_of(doc), bundle=None, name='qm')
    assert code == 0, payload
    import yaml
    training = yaml.safe_load((out / 'src/conf/components/training/default.yaml').read_text())
    text = json.dumps(training)
    assert not [t for t in _texts(training) if projection.interpreted(t)]
    assert projection.LITERAL_KEY in text
    steps = projection.decode_literals(training['preprocessing'])
    special = next(s for s in steps if s['operation'] == 'special_value_indicator')
    assert [v['value'] for v in special['parameters']['values']] == ['???', '${x}']
    recipe = json.loads((out / 'data/hypotrail/contracts/model-recipe.json').read_text())
    assert recipe['preprocessing'] == steps


@needs_hydra
def test_the_composed_configuration_reads_the_exact_token(export, material, tmp_path):
    """Hydra composes the exported configuration and its scientific projection is the
    study's (``validate``'s ``hydra_config_frozen`` check)."""
    _, code, out = export(reader=fx.reader_of(_question_marks(material)), bundle=None,
                          name='qm-hydra')
    assert code == 0
    result = _run(out, 'validate', '--offline')
    report = json.loads(result.stdout)
    check = next(c for c in report['checks'] if c['id'] == 'hydra_config_frozen')
    assert check['status'] == 'passed', check


def test_a_case_value_read_by_omegaconf_is_still_refused(export, material, tmp_path):
    """A name or unit the case states has nothing to escape: it is still refused, with a
    remediation the junior can follow."""
    doc = _doc(material, bundle=False)
    doc['scientific_contracts']['model_recipe']['target']['unit'] = '???'
    doc['scientific_contracts']['model_recipe']['output_contract']['unit'] = '???'
    with pytest.raises(ExportError) as error:
        export(reader=fx.reader_of(doc), bundle=None)
    assert error.value.code == 'contract_invalid'
    assert 'case of the study' in error.value.details['remediation']

