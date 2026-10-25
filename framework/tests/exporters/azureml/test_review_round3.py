"""Regressions of the round-3 review of the Azure ML export (B3-1 to B3-6), on temporary
studies only (synthetic material, or temporary synthetic studies taken through the engine's
commands). The reviewer's probes are ported here.

* B3-1: the exported development plan names exactly the rows the engine's final refit and
  capture train on (every development row less the delayed-label rows) for every split
  kind: a forward-chaining split (whose ``folds`` blob names its validation rows only) keeps
  its warm-up rows, with and without delayed labels; a holdout, a k-fold and an explicit
  (review-v1) k-fold plan too. The plan's development digest is checked against the
  capture's ``training_scope.membership_sha256`` (``contract_invalid`` otherwise), the
  rebuilt candidate trains on as many rows as the capture, and a rebuild outside the
  evaluated model's tolerance never reports ``passed``.
* B3-2: a non-finite feature value of ``predict --input`` is a ``contract_invalid`` refusal
  (exit code 2) with an issue in the shape of the runtime's input check.
* B3-3: an auxiliary column whose pandas type the contract cannot declare (``uint64``, an
  ``object`` of booleans) is declared ``string``, listed under
  ``hypotrail.auxiliary_as_text``, and materialised as its text.
* B3-4: every text written into the Hydra configuration reads back exactly through the
  project's OmegaConf/YAML load (a property test over hostile texts, and exports validated
  by Hydra).
* B3-5: the delayed-label rows left out are counted and explained (term first, then the
  study's example) in the snapshot limitations, its evaluation plan, the development plan,
  the README and the data contract's exclusions.
* B3-6: the profile's validation patterns refuse a value followed by a newline.
"""
from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest
import yaml

import azureml_study as fx
from export_env import needs_hydra, needs_mlflow, project_env
from mlkit.exporters.azureml import export_azureml, projection, render
from mlkit.exporters.azureml.errors import ExportError

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'study'))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'study' / 'libraries'))

MOD = 'src.pipeline.utils.project'
WORDS = 'Yes, I choose that model because its error is smaller'


def _run(root: Path, *args):
    return subprocess.run([sys.executable, '-m', MOD, *map(str, args)], cwd=root,
                          capture_output=True, text=True, env=project_env(), check=False,
                          timeout=900)


def _json_of(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def _export(flow, out: Path, expect=0):
    return flow.call('export', 'azureml', '--out', out, '--expected-revision', flow.rev(),
                     '--profile', fx.profile(out.parent), '--study', flow.study,
                     expect=expect)


def _key_order(key: str):
    digits = key[1:] if key[:1].isalpha() else key
    return (0, int(digits), key) if digits.isdigit() else (1, 0, key)


def _canonical_sha(value) -> str:
    from mlkit.exporters.azureml import canonical
    return canonical.canonical_sha256(value)


# --- B3-0 workaround (not part of the export) ---------------------------------------------

@pytest.fixture(scope='module')
def engine_regression_cv():
    """Until the engine fix of B3-0 lands; remove then. ``fit.compute_explicit_cv`` calls
    ``.loc`` on the ndarray ``fit._target`` returns for a regression under review-v1; within
    that function only, ``_target`` returns a float Series indexed like the frame (the
    reviewer's ``delayed_kit.patch_engine_regression_cv``). The patch is undone after the
    module."""
    from mlkit.study import fit
    original_cv, original_target = fit.compute_explicit_cv, fit._target

    def series_target(case, frame, partition):
        return pd.Series(original_target(case, frame, partition), index=frame.index)

    def cv(*args, **kwargs):
        fit._target = series_target
        try:
            return original_cv(*args, **kwargs)
        finally:
            fit._target = original_target

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(fit, 'compute_explicit_cv', cv)
        yield


# --- real studies --------------------------------------------------------------------------

def _review_study(base: Path, *, future: bool, outcome_delay: int = 5, n_rows: int = 300):
    """A review-v1 regression study (the reviewer's ``delayed_kit.drive``): a forward-chaining
    split when ``future`` (planted prediction and outcome clocks, the outcome known
    ``outcome_delay`` ticks later), an explicit k-fold plan otherwise; captured, sealed."""
    import flowkit as fk
    from flowkit import Flow
    from mlkit.study import governance, state as st
    module = fk._module
    original = module.make_case
    module.make_case = lambda out_dir, n_rows=300, **kw: original(out_dir, task='regression',
                                                                    n_rows=n_rows)
    try:
        paths = module.make_review_case(base / 'case', future=future,
                                        outcome_delay=outcome_delay, n_rows=n_rows)
    finally:
        module.make_case = original
    flow = Flow(base / 'study', paths['case'].parent, prefix='r3')
    flow.call('init', '--case', paths['case'], '--study', flow.study,
              '--reliability-profile', 'review-v1', '--lang', 'en')
    flow.decide('prediction_time', 'Predict using information available at the planted '
                                   'decision time')
    flow.decide('feature_availability', fk.availability(flow.case_dir))
    flow.decide('split', st.b1_default_value(flow.state(), 'split'))
    flow.decide('success_criterion', {
        'metric': 'mae_reduction', 'min_share': 0.1, 'decision_rule': 'point_estimate',
        'selection': {'metric': 'mae', 'rule': None, 'scope': 'evaluation_window',
                      'batch_column': None, 'aggregation': 'row_weighted'}})
    flow.decide('preprocessing', dict(governance.DEFAULT_PREPROCESSING))
    flow.run('split')
    flow.run('fit.baseline')
    flow.run('fit.linear')
    flow.run('diag.regression')
    flow.decide('model_variant', {'variants': [{
        'kind': 'regularisation', 'strength': 'strong',
        'question': 'Does a stronger penalty generalise better?', 'origin': 'planned',
        'diagnostic_result_id': None}]})
    flow.run('fit.variant')
    flow.run('evaluate.regression')
    flow.decide('model_choice', 'fit.linear', words=WORDS)
    flow.run('predictor.capture', '--profile', 'workshop')
    return flow, paths


def _plain_study(base: Path, split: dict):
    """A synthetic regression study (default profile) with the given split, captured."""
    import flowkit as fk
    from flowkit import Flow
    paths = fk.make_case(base / 'case', task='regression', n_rows=300)
    flow = Flow(base / 'study', paths['case'].parent, prefix='p3')
    flow.init()
    flow.decide('prediction_time', 'when the record is created, before the outcome')
    flow.decide('feature_availability', fk.availability(flow.case_dir))
    flow.decide('split', split)
    flow.model_decisions()
    flow.run('split')
    flow.run('fit.baseline')
    flow.run('fit.linear')
    flow.variant()
    flow.run('evaluate.regression')
    flow.decide('model_choice', 'fit.linear', words=WORDS)
    flow.run('predictor.capture', '--profile', 'workshop')
    return flow, paths


def _eligible(flow) -> tuple[list[str], set[str]]:
    """The engine's training rows of the final refit (development rows less delayed-label
    rows), and the delayed-label rows."""
    import flowkit as fk
    from mlkit.study import partition, read, store as sto
    state = read.open(flow.study).state
    held = partition.excluded_keys(sto.StudyStore(flow.study).read_blob,
                                   partition.training_exclusions(state))
    development = fk.partition_keys(flow.study, 'development')
    return [k for k in development if k not in held], held


def _capture_values(flow) -> dict:
    from mlkit.study import read, registry, store as sto
    state = read.open(flow.study).state
    entry = registry.get(sto.StudyStore(flow.study), state['current']['predictor.capture'])
    return entry['output']['values']


def _capture_scope(flow) -> dict:
    return _capture_values(flow)['training_scope']


def _assert_plan_is_training_rows(flow, out: Path) -> dict:
    from mlkit.exporters.azureml.snapshot import membership_digests
    eligible, held = _eligible(flow)
    plan = _json_of(out / 'data/hypotrail/contracts/development-plan.json')
    keys = [k for p in plan['partitions'] for k in p['row_keys']]
    assert len(keys) == len(set(keys))
    assert set(keys) == set(eligible)
    assert not set(keys) & held
    assert plan['n_development_rows'] == len(eligible)
    assert plan['development_keys_sha256'] == _canonical_sha(sorted(eligible, key=_key_order))
    assert _capture_scope(flow)['membership_sha256'] in membership_digests(eligible)
    return plan


def _rebuild(out: Path, data: Path, run_dir: Path) -> dict:
    result = _run(out, 'materialize', '--source', data)
    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-2000:]
    result = _run(out, 'run-local', '--mode', 'rebuild_final_candidate', '--run-dir', run_dir)
    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-3000:]
    return {'run': _json_of(run_dir / '04_model/hypotrail-run.json'),
            'report': _json_of(run_dir / '05_reports/technical-report.json')}


@pytest.fixture(scope='module')
def delayed(tmp_path_factory, engine_regression_cv):
    """Forward chaining with five delayed-label rows (the reviewer's 195 vs 235 case)."""
    base = tmp_path_factory.mktemp('r3-delayed')
    flow, paths = _review_study(base, future=True, outcome_delay=5)
    out = base / 'export'
    payload = _export(flow, out)
    assert payload['artifact_status'] == 'packaged', payload
    return {'base': base, 'flow': flow, 'paths': paths, 'out': out, 'payload': payload}


@pytest.fixture(scope='module')
def undelayed(tmp_path_factory, engine_regression_cv):
    """Forward chaining without delayed labels (the reviewer's 200 vs 240 case)."""
    base = tmp_path_factory.mktemp('r3-undelayed')
    flow, paths = _review_study(base, future=True, outcome_delay=0)
    out = base / 'export'
    payload = _export(flow, out)
    assert payload['artifact_status'] == 'packaged', payload
    return {'base': base, 'flow': flow, 'paths': paths, 'out': out, 'payload': payload}


# --- B3-1: the exported plan is the final refit's rows --------------------------------------

@needs_mlflow
@needs_hydra
@pytest.mark.parametrize('case', ['delayed', 'undelayed'])
def test_a_forward_chaining_plan_keeps_its_warm_up_rows(request, case):
    """The forward-chaining split writes a ``folds`` blob of its validation rows only: the
    plan still names the warm-up rows, so the rebuilt candidate trains on as many rows as
    the capture (235 with five delayed-label rows, 240 without), within the evaluated
    model's tolerance."""
    material = request.getfixturevalue(case)
    flow, out = material['flow'], material['out']
    plan = _assert_plan_is_training_rows(flow, out)
    roles = {p['id']: p['role'] for p in plan['partitions']}
    assert roles.get('warmup') == 'train'
    assert sum(1 for r in roles.values() if r.startswith('fold_')) >= 2
    eligible, held = _eligible(flow)
    assert len(held) == (5 if case == 'delayed' else 0)
    checks = {c['id']: c['status'] for c in material['payload']['checks']}
    assert checks['plan_rows_are_training_rows'] == 'passed'
    rebuilt = _rebuild(out, material['paths']['data'], material['base'] / 'run')
    assert rebuilt['run']['n_training_rows'] == len(eligible) == _capture_values(flow)['n_train']
    report = rebuilt['report']
    assert report['status'] == 'passed'
    assert report['deviation_from_evaluated_model']['within_evaluated_tolerance'] is True
    statuses = {c['id']: c['status'] for c in report['checks']}
    assert statuses['candidate_within_evaluated_tolerance'] == 'passed'


@needs_mlflow
def test_an_explicit_k_fold_plan_names_every_training_row(tmp_path, engine_regression_cv):
    """A review-v1 k-fold (explicit evaluation plan, no unscored rows)."""
    flow, _ = _review_study(tmp_path, future=False)
    out = tmp_path / 'export'
    payload = _export(flow, out)
    assert payload['artifact_status'] == 'packaged'
    plan = _assert_plan_is_training_rows(flow, out)
    assert all(p['role'].startswith('fold_') for p in plan['partitions'])


@needs_mlflow
@pytest.mark.parametrize('split', [
    {'method': 'random', 'validation_fraction': 0.3, 'seed': 7},
    {'method': 'kfold_quantile', 'folds': 5, 'seed': 7}], ids=['holdout', 'kfold'])
def test_a_holdout_or_k_fold_plan_names_every_training_row(tmp_path, split):
    flow, _ = _plain_study(tmp_path, split)
    out = tmp_path / 'export'
    payload = _export(flow, out)
    assert payload['artifact_status'] == 'packaged'
    _assert_plan_is_training_rows(flow, out)
    checks = {c['id']: c['status'] for c in payload['checks']}
    assert checks['plan_rows_are_training_rows'] == 'passed'


def test_a_plan_that_is_not_the_capture_s_rows_is_refused(export, tmp_path):
    """A plan without one fold names fewer rows than the capture trained on."""
    plan = fx.plan()
    plan['partitions'] = [p for p in plan['partitions'] if p['id'] != 'fold_5']
    kept = sum(len(p['row_keys']) for p in plan['partitions'] if p['role'] != 'final_test')
    with pytest.raises(ExportError) as error:
        export(source_changes={'development_plan': plan}, name='short')
    assert error.value.code == 'contract_invalid'
    assert error.value.details['reason'] == 'plan_rows_not_training_rows'
    assert error.value.details['n_development_rows'] == kept < fx.N_ROWS - fx.N_FINAL
    assert not (tmp_path / 'short').exists()


def test_the_capture_digest_names_the_set_of_training_rows():
    from mlkit.exporters.azureml.snapshot import membership_digests
    from mlkit.study import records as rec
    keys = ['L10', 'L2', 'L3']
    digests = membership_digests(keys)
    assert hashlib.sha256(rec.row_keys_bytes(keys)).hexdigest() in digests
    assert hashlib.sha256('\n'.join(sorted(keys)).encode()).hexdigest() in digests
    assert not digests & membership_digests(keys[:2])


@pytest.fixture(scope='module')
def drifted(tmp_path_factory, runtime):
    """An exported project whose evaluated bundle was fitted on fewer rows than its plan (its
    recorded training scope says otherwise): a rebuild cannot reproduce it."""
    folder = tmp_path_factory.mktemp('r3-drift')
    source = fx.write_source(folder)
    contract = fx.data_contract(source)
    recipe = fx.recipe()
    frame = fx.typed_development(source, contract)
    scope = {'role': 'final_development_refit', 'dataset_id': contract['dataset_id'],
             'membership_sha256': fx.training_membership(list(frame.index)),
             'protocol_id': 'cv5-synthetic'}
    fitted = runtime.fit_predictor(recipe, contract, frame.iloc[12:], scope)
    bundle = folder / 'artifacts' / 'bundle'
    runtime.capture_predictor(fitted, None, frame[fx.FEATURES].head(8), bundle, packager=None,
                              parity_origin='authorized_development',
                              code_fingerprint=hashlib.sha256(b'test-code').hexdigest())
    doc = fx.export_source(folder, bundle_dir=bundle, contract=contract, source=source)
    doc['predictor']['evidence_status'] = 'unassessed'
    out = folder / 'export'
    _, code = export_azureml(folder / 'study', expected_revision=fx.REVISION, out=out,
                             profile_path=fx.profile(folder), reader=fx.reader_of(doc))
    assert code == 0
    assert _run(out, 'materialize', '--source', source).returncode == 0
    return folder, out


@needs_mlflow
@needs_hydra
def test_a_rebuild_outside_the_evaluated_tolerance_never_passes(drifted):
    """The reviewer's report said ``status: passed`` with ``within_evaluated_tolerance:
    false``: a check of that deviation now fails the technical report (and the run)."""
    folder, out = drifted
    result = _run(out, 'run-local', '--mode', 'rebuild_final_candidate', '--run-dir',
                  folder / 'run')
    assert result.returncode == 2
    assert json.loads(result.stdout)['failed_step'] == 'evaluation'
    report = _json_of(folder / 'run/05_reports/technical-report.json')
    assert report['deviation_from_evaluated_model']['within_evaluated_tolerance'] is False
    assert report['status'] == 'failed'
    statuses = {c['id']: c['status'] for c in report['checks']}
    assert statuses['candidate_within_evaluated_tolerance'] == 'failed'


# --- B3-5: delayed-label rows are counted and explained ------------------------------------

@needs_mlflow
def test_the_delayed_label_rows_are_counted_and_explained(delayed):
    flow, out = delayed['flow'], delayed['out']
    from mlkit.study import state as st
    limit = st.delayed_labels_limit(flow.state())
    assert limit is not None and limit['n_rows'] == 5
    text = limit['text']
    assert text.startswith('A delayed label is') and '5 development rows' in text
    assert 'For example' in text
    snapshot = _json_of(out / 'data/hypotrail/contracts/deployment-snapshot.json')
    assert text in snapshot['limitations']
    excluded = snapshot['evaluation_plan']['excluded_rows']
    assert excluded == [{'reason': 'outcome_not_available_before_final', 'n_rows': 5,
                         'text': text}]
    plan = _json_of(out / 'data/hypotrail/contracts/development-plan.json')
    assert plan['excluded_rows'] == excluded
    readme = (out / 'README.md').read_text(encoding='utf-8')
    assert f'- {text}' in readme
    contract = _json_of(out / 'data/hypotrail/contracts/data-contract.json')
    [exclusion] = contract['exclusions']
    assert exclusion['rule'] == 'outcome_not_available_before_final'
    assert exclusion['justification'].startswith('A delayed label is')
    assert '5 development rows' in exclusion['justification']
    assert f"{limit['clock']} {st._clock_value(limit['final_start'])}" in \
        exclusion['justification']


@needs_mlflow
def test_a_study_without_delayed_labels_states_no_exclusion(undelayed):
    out = undelayed['out']
    snapshot = _json_of(out / 'data/hypotrail/contracts/deployment-snapshot.json')
    assert 'excluded_rows' not in snapshot['evaluation_plan']
    assert not any('delayed label' in x for x in snapshot['limitations'])
    assert _json_of(out / 'data/hypotrail/contracts/data-contract.json')['exclusions'] == []


# --- B3-2: a non-finite feature value is a refusal -------------------------------------------

@needs_mlflow
@needs_hydra
@pytest.mark.parametrize('token', ['inf', '-Infinity', 'INF'])
def test_predict_refuses_a_non_finite_feature_value(export, tmp_path, token):
    """Round 2 (N3) reads ``inf`` as pandas does; such a value reached scikit-learn and gave
    ``internal_error``. It is now refused before any prediction."""
    _, code, out = export(name=f'inf-{token}')
    assert code == 0
    rows = tmp_path / 'rows.csv'
    rows.write_text('weight,cylinders,displacement,horsepower,origin\n'
                    f'2500,4,120.5,{token},2\n3500,8,300,150,1\n')
    result = _run(out, 'predict', '--input', rows, '--output', tmp_path / 'p.json')
    assert result.returncode == 2, result.stdout + result.stderr
    error = json.loads(result.stdout)['error']
    assert error['code'] == 'contract_invalid'
    assert error['path'] == 'input/horsepower'
    [issue] = error['details']['issues']
    assert issue == {'code': 'contract_invalid', 'path': 'input/horsepower',
                     'kind': 'non_finite_values', 'n_rows': 1, 'rows': [0]}
    assert not (tmp_path / 'p.json').exists()


@needs_mlflow
@needs_hydra
def test_predict_still_reads_finite_numbers_and_missing_cells(export, tmp_path):
    _, code, out = export(name='finite')
    assert code == 0
    rows = tmp_path / 'rows.csv'
    rows.write_text('weight,cylinders,displacement,horsepower,origin\n2500,4,120.5,,2\n')
    result = _run(out, 'predict', '--input', rows, '--output', tmp_path / 'p.json')
    assert result.returncode == 0, result.stdout + result.stderr


# --- B3-3: auxiliary columns the contract cannot type are text ------------------------------

def _auxiliary_case(base: Path) -> tuple[Path, Path]:
    """A synthetic regression case with two auxiliary columns pandas reads with a type the
    contract v1 cannot declare: an identifier above the int64 range (``uint64``) and a
    boolean column with a missing token (an ``object`` of booleans)."""
    import flowkit as fk
    paths = fk.make_case(base / 'case', task='regression', n_rows=300)
    sep = fk._module.SEP
    rows = list(csv.reader(io.StringIO(paths['data'].read_text()), delimiter=sep))
    rows[0] += ['txn_id', 'audited']
    for i, row in enumerate(rows[1:]):
        row += [str(18000000000000000000 + i), ['True', 'False', 'NA'][i % 3]]
    buf = io.StringIO(newline='')
    csv.writer(buf, delimiter=sep, lineterminator='\n').writerows(rows)
    paths['data'].write_text(buf.getvalue())
    doc = yaml.safe_load(paths['case'].read_text())
    doc['dataset']['sha256'] = hashlib.sha256(paths['data'].read_bytes()).hexdigest()
    doc['dataset']['columns'] += 2
    for name, kind in (('txn_id', 'integer'), ('audited', 'category')):
        doc['variables'].append({
            'name': name, 'type': kind, 'role': 'identifier', 'description': f'Synthetic {name}',
            'status': 'documented_fact', 'source': 'Synthetic',
            'availability': {'value': 'not_available', 'status': 'documented_fact',
                             'source': 'Synthetic'},
            'special_values': []})
    paths['case'].write_text(yaml.safe_dump(doc, sort_keys=False))
    return paths['case'].parent, paths['data']


@needs_mlflow
def test_an_auxiliary_column_the_contract_cannot_type_is_read_as_text(tmp_path):
    """The reviewer's probe 7: the export said packaged, then materialize refused with an
    unactionable message (``physical_type`` string expected, None found)."""
    import flowkit as fk
    import test_review_round2 as r2
    from mlkit.study import case as c, data as dt
    case_dir, data = _auxiliary_case(tmp_path)
    flow = r2._regression(tmp_path, opened=False, case_dir=case_dir)
    engine = dt.load_development(c.load_case(case_dir),
                                 fk.partition_keys(flow.study, 'development')).frame
    assert str(engine['txn_id'].dtype) == 'uint64'
    assert str(engine['audited'].dtype) == 'object'
    out = tmp_path / 'export'
    assert _export(flow, out)['artifact_status'] == 'packaged'
    contract = _json_of(out / 'data/hypotrail/contracts/data-contract.json')
    columns = {col['name']: col for col in contract['columns']}
    for name in ('txn_id', 'audited'):
        assert (columns[name]['physical_type'], columns[name]['role']) == ('string',
                                                                           'auxiliary')
    assert contract['extensions']['hypotrail.auxiliary_as_text'] == [
        {'column': 'txn_id', 'engine_dtype': 'uint64'},
        {'column': 'audited', 'engine_dtype': 'object'}]
    result = _run(out, 'materialize', '--source', data)
    assert result.returncode == 0, result.stdout[-2000:]
    sys.path.insert(0, str(out))
    try:
        from src.pipeline.utils.hypotrail import contracts
        typed = contracts.read_rows(out / 'data/hypotrail/development/development.csv',
                                    contract)
    finally:
        sys.path.remove(str(out))
        for name in [m for m in sys.modules if m == 'src' or m.startswith('src.')]:
            del sys.modules[name]
    typed = typed.set_index(contracts.KEY_COLUMN).loc[list(engine.index)]
    assert typed['txn_id'].tolist() == [str(v) for v in engine['txn_id']]
    assert [None if pd.isna(v) else v for v in typed['audited']] == \
        [None if pd.isna(v) else str(v) for v in engine['audited']]
    report = json.loads(_run(out, 'validate', '--offline').stdout)
    statuses = {check['id']: check['status'] for check in report['checks']}
    assert statuses['development_rows'] == 'passed'


# --- B3-4: every text of the configuration reads back exactly ------------------------------

HOSTILE_TEXTS = [
    '1e9', '1E-3', '+1e5', '-1e5', '1e+9', '1.5e3', '1_000', '0x1F', '0o17', '0b11', '.5',
    '1.', '+.5', 'inf', '.inf', '-.Inf', 'nan', '.NaN', '\x85', 'a\x85b', ' ',
    'a b', ' lead', 'trail ', ' both ', ' ', '', '~', 'null', 'Null', 'NULL', 'yes', 'no',
    'Yes', 'ON', 'on', 'off', 'y', 'n', 'true', 'False', '2026-10-25', '2026-10-25 12:00:00',
    '2026-10-25T12:00:00Z', '12:30', '1:20:30', '0755', '007', '1,000', '"', "'", '\\',
    '\\n', 'a\tb', '\t', '#x', 'a #b', ': x', 'a: b', '- x', '[a]', '{a: 1}', '&a', '*a',
    '!tag', '%x', '@x', '`x', '|', '>', '?', '? x', '﻿x', '\x00', '\x07', '\x7f', '\x9f',
    '', '\U0001f600', 'a\nb', '\r', 'a\r\nb', '=', '<<', '---', '...', 'éà', '\xa0',
    '$x', '\\$', 'x$', '}', '{', '$', '$\\{x}']
# Texts OmegaConf interprets even when quoted: carried as encoded literals in the
# preprocessing, refused elsewhere (round 2, N7).
INTERPRETED_TEXTS = ['???', '${x}', '\\${x}', 'a${b}c', 'x${', '${', '@@a', '@@']


def _omegaconf(text: str):
    from omegaconf import OmegaConf
    return OmegaConf.to_container(OmegaConf.create(text), resolve=True, throw_on_missing=True)


def _documents(value) -> list[str]:
    """``value`` under a key as the generator renders it: as a block (a mapping or list
    marker in the template) and as a flow value (a scalar or an empty container)."""
    return ['key: ' + render._yaml_block(value, 0).lstrip(' ') + '\n'
            if isinstance(value, (dict, list)) and value else None,
            'key: ' + render._yaml(value) + '\n']


def _round_trip(value) -> None:
    for document in filter(None, _documents(value)):
        assert yaml.safe_load(document) == {'key': value}, document
        assert _omegaconf(document) == {'key': value}, document


@needs_hydra
@pytest.mark.parametrize('text', HOSTILE_TEXTS)
def test_every_text_of_the_configuration_reads_back_exactly(text):
    _round_trip(text)
    _round_trip([text, {'name': text}])
    _round_trip({text: text, 'list': [text]})
    _round_trip({'feature_types': {text: {'semantic': 'numeric', 'physical': 'float64'}}})


@needs_hydra
@pytest.mark.parametrize('text', HOSTILE_TEXTS + INTERPRETED_TEXTS)
def test_every_preprocessing_literal_reads_back_exactly(text):
    steps = [{'operation': 'special_value_indicator', 'version': 1, 'parameters': {
        'values': [{'column': 'horsepower', 'value': text, 'name': f'horsepower={text}',
                    'reads_missing': True}]}}]
    carried = render._config_preprocessing(steps)
    for document in filter(None, _documents(carried)):
        assert projection.decode_literals(_omegaconf(document)['key']) == steps, document


@needs_hydra
def test_texts_read_back_exactly_property():
    """A property over generated texts (any Unicode text but surrogates)."""
    from hypothesis import given, settings, strategies as st

    @settings(max_examples=300, deadline=None, derandomize=True)
    @given(st.text(max_size=12))
    def check(text):
        if projection.interpreted(text):
            return
        _round_trip(text)
        _round_trip({text: [text]})

    check()


def _hostile_doc(material) -> dict:
    """A recipe-only export whose names, unit and dataset tokens have the shapes YAML or
    OmegaConf re-type or fold (exponent forms without a dot, NEL, U+2028, surrounding
    spaces, YAML 1.1 words, a date)."""
    doc = fx.export_source(material['folder'], bundle_dir=None, contract=material['contract'],
                           source=material['source'])
    recipe = doc['scientific_contracts']['model_recipe']
    contract = doc['scientific_contracts']['data_contract']
    renames = {'weight': '1E-3', 'displacement': ' disp lacement ', 'mpg': '1e9'}
    text = json.dumps(doc, ensure_ascii=False)
    for old, new in renames.items():
        text = text.replace(json.dumps(old), json.dumps(new, ensure_ascii=False))
    doc = json.loads(text)
    recipe = doc['scientific_contracts']['model_recipe']
    contract = doc['scientific_contracts']['data_contract']
    recipe['target']['unit'] = '+1e5'
    recipe['output_contract']['unit'] = '+1e5'
    tokens = ['1e9', '\x85', '1E-3', '+1e5', ' ', ' x ', 'null', 'yes', '~', '2026-10-25']
    contract['parser']['na_values'] = tokens
    for step in recipe['preprocessing']:
        if step['operation'] == 'special_value_indicator':
            step['parameters']['values'] = [
                {'column': 'horsepower', 'value': t, 'name': f'horsepower={t}',
                 'reads_missing': True} for t in tokens]
    assert 'weight' not in recipe['features'] and '1E-3' in recipe['features']
    return doc


@needs_hydra
def test_an_export_with_hostile_texts_passes_the_hydra_check(export, material):
    """The reviewer's ``test_yaml_literals`` (``1e9``, NEL, ``1E-3``), widened to names, a
    unit and more tokens: ``validate`` composes the configuration with Hydra and its
    scientific projection is the study's."""
    doc = _hostile_doc(material)
    payload, code, out = export(reader=fx.reader_of(doc), bundle=None, name='hostile')
    assert code == 0, payload
    result = _run(out, 'validate', '--offline')
    report = json.loads(result.stdout)
    check = next(c for c in report['checks'] if c['id'] == 'hydra_config_frozen')
    assert check['status'] == 'passed', check
    recipe = _json_of(out / 'data/hypotrail/contracts/model-recipe.json')
    assert recipe['features'] == doc['scientific_contracts']['model_recipe']['features']


def test_the_generator_reads_its_configuration_as_the_project_does(export, material,
                                                                     monkeypatch, tmp_path):
    """The generator's self-check reads the rendered configuration through OmegaConf: a
    rendering that OmegaConf would re-type (the round-2 plain block style, where ``1e9`` is
    unquoted) is refused at export, never written."""
    pytest.importorskip('omegaconf')
    monkeypatch.setattr(render, '_quoted_dumper', lambda: yaml.SafeDumper)
    doc = _hostile_doc(material)
    with pytest.raises(ExportError) as error:
        export(reader=fx.reader_of(doc), bundle=None, name='unquoted')
    assert error.value.code == 'scientific_config_changed'
    assert not (tmp_path / 'unquoted').exists()


# --- B3-6: validation patterns match the whole value --------------------------------------

@pytest.mark.parametrize(('dotted', 'value'), [
    ('subscription_id', '00000000-0000-4000-8000-000000000000\n'),
    ('resource_group', 'rg-atelier\n'), ('workspace', 'ws-atelier\n'),
    ('compute', 'cpu-atelier\n'), ('experiment_name', 'exp\n'),
    ('data_asset.name', 'synthetic-cars-development\n'), ('data_asset.version', '1\n'),
    ('environment.name', 'hypotrail-py313\n'), ('environment.version', '1\n'),
    ('environment.base_image', 'mcr.microsoft.com/azureml/openmpi4.1.0-ubuntu22.04:20250601.v1\n'),
    ('devops.service_connection', 'svc\n')])
def test_a_profile_value_followed_by_a_newline_is_refused(tmp_path, dotted, value):
    from mlkit.exporters.azureml import profile
    document = yaml.safe_load(fx.profile(tmp_path).read_text())
    document = copy.deepcopy(document)
    node = document
    *parents, leaf = dotted.split('.')
    for part in parents:
        node = node.setdefault(part, {})
    node[leaf] = value
    with pytest.raises(ExportError) as error:
        profile.validate(document)
    assert error.value.code == 'contract_invalid'
    assert error.value.path == dotted
    node[leaf] = value.rstrip('\n')
    profile.validate(document)


def test_the_azure_yaml_and_upload_patterns_match_the_whole_text():
    from mlkit.exporters.azureml import azure_yaml, layout, transfer
    assert azure_yaml.ASSET_REF.fullmatch('azureml:env:1')
    assert not azure_yaml.ASSET_REF.fullmatch('azureml:env:1\n')
    assert azure_yaml.FORMS['component'].fullmatch('inputs.data')
    assert not azure_yaml.FORMS['component'].fullmatch('inputs.data\n')
    assert layout.UPLOAD_ALLOWED.fullmatch('README.md')
    assert not layout.UPLOAD_ALLOWED.fullmatch('README.md\n')
    assert layout.METADATA.search('a/.DS_Store')
    assert not layout.METADATA.search('a/.DS_Store\nx')
    rules = transfer.parse('data/\n*.log\n')
    assert transfer.ignored('run.log', False, rules)
    assert not transfer.ignored('run.log\n', False, rules)


def test_render_quotes_every_text_and_escapes_line_breaks():
    for text in ('1e9', 'a\x85b', 'a b', ' x ', '﻿'):
        quoted = render.yaml_quoted(text)
        assert quoted.startswith('"') and quoted.endswith('"')
        assert not any(ch in quoted for ch in '\x85  ﻿\n\r')
        assert yaml.safe_load(quoted) == text
