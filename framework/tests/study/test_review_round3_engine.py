"""Review round 3 of the study engine (2026-10-25): E3-1..E3-4, B3-0 and four known bugs.

Every study is a temporary synthetic one (the reviewer's scripts, ported).

* E3-1: with delayed-label rows (review-v1, ``partition.training_exclusions``) the generated
  and editable notebooks show and use exactly the engine's rows: ``development_frame`` marks
  the rows left out ``delayed_label``, the split cell's ``train`` holds none of them, every
  assert holds, and the notebook says why (the term first, then this study's example).
* E3-2: the engine's own ``delayed_labels_excluded`` text is traceable (its partition values
  are traced in the context the limit writes them, nowhere else), so ``export handoff`` and
  ``check --text`` accept it in English and French.
* E3-3: the final test opens only when every result its confirmation rests on (split, fits,
  variants, evaluation, review-v1 diagnostics, capture) is current by the rule ``status``
  uses (code changed under the attestations, delayed labels, upstream), on the decision and
  the run paths; otherwise ``precondition_missing`` names the slots, with a junior message,
  and no final-test row is read; ``next_action`` then recommends running them, not opening.
* E3-4: after the opening, ``diag.final_test`` on a final evaluation that is not current says
  it cannot be recomputed (with a junior message), never "run it again".
* B3-0: regression under review-v1 explicit plans fits, cross-validates, captures and opens
  its final test; (a) a tuned variant under an explicit plan fits; (b), (c) the notebook of a
  review-v1 explicit-plan study runs; (d) is the panel's (``limits-severity.test.js``).
* The round-3 attestation edges of ``fit.py`` and ``families.py`` are exact, directed and
  scoped; the byte comparison itself is the opt-in test at the end.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from mlkit.study import (activities as act, cli, code_cells, code_compat, commands as cmd,
                         junior, notebook_view as nv, numtrace, partition, read,
                         records as rec, registry, render_notebook as rn, state as st,
                         store as sto)

import flowkit as fk
from flowkit import Flow
from test_review_round2_training_exclusions import CRITERION, OPEN, VARIANT, ReviewFlow

REPO = Path(__file__).resolve().parents[3]
FAKE = '0' * 64
CHOOSE = 'Yes, I choose that model because it ranks the rows best for us'
ADOPT = 'Yes, I adopt that rule because the desk can act on that share'
REG_WORDS = 'Yes, I choose that model because its error is smaller'
REG_CRITERION = {'metric': 'mae_reduction', 'min_share': 0.1, 'decision_rule': 'point_estimate',
                 'selection': {'metric': 'mae', 'rule': None, 'scope': 'evaluation_window',
                               'batch_column': None, 'aggregation': 'row_weighted'}}
TUNED = {'kind': 'tuned', 'question': 'Does a tuned penalty do better than the default one?',
         'origin': 'planned', 'diagnostic_result_id': None}


# --- driving the studies ----------------------------------------------------------------------

def _to_choice(f: ReviewFlow, *, eda: bool = True) -> None:
    """A review-v1 binary study up to an adopted rule, its diagnostics current (no capture,
    final test sealed)."""
    f.init()
    f.pauses()
    f.run('split')
    if eda:
        for activity in ('eda.target_rate', 'eda.special_values', 'eda.quality',
                         'eda.correlation'):
            f.run(activity)
    f.models()
    f.decide('model_choice', 'fit.logistic', words=CHOOSE)
    f.call('run', 'policy.evaluate', '--rule', 'share:0.2', '--request-id', f.rid(),
           '--expected-revision', f.rev(), '--study', f.study)
    f.run('diag.binary')
    f.decide('policy', 'share:0.2', words=ADOPT)
    f.run('diag.binary')


def _propose_final(f: Flow) -> dict:
    value = st.b1_default_value(f.state(), 'final_test')
    return f.call('decide', 'propose', 'final_test', '--value-json', json.dumps(value),
                  '--restatement', 'You open the final test.', '--rationale', 'Fixed.',
                  '--request-id', f.rid(), '--expected-revision', f.rev(), '--study', f.study)


def _confirm_final(f: Flow, expect=0) -> dict:
    p = _propose_final(f)
    return f.call('decide', 'confirm', p['result']['proposal_id'], '--user-words', OPEN,
                  '--request-id', f.rid(), '--expected-revision', f.rev(), '--study', f.study,
                  expect=expect)


def _regression_flow(base: Path, monkeypatch, *, delay: int, name: str = 'reg') -> Flow:
    """A review-v1 regression study on a future case (``delay`` ticks of outcome delay)."""
    mod = fk._module
    original = mod.make_case
    with monkeypatch.context() as m:
        m.setattr(mod, 'make_case', lambda out_dir, n_rows=300, **kw:
                  original(out_dir, task='regression', n_rows=n_rows))
        paths = mod.make_review_case(base / f'case-{name}', future=True, outcome_delay=delay,
                                     n_rows=300)
    f = Flow(base / name, paths['case'].parent, prefix=name[:3])
    f.call('init', '--case', paths['case'], '--study', f.study, '--reliability-profile',
           'review-v1', '--lang', 'en')
    f.decide('prediction_time', 'Predict using information available at the planted decision '
                                'time')
    f.decide('feature_availability', fk.availability(f.case_dir))
    f.decide('split', st.b1_default_value(f.state(), 'split'))
    f.decide('success_criterion', REG_CRITERION)
    from mlkit.study import governance
    f.decide('preprocessing', dict(governance.DEFAULT_PREPROCESSING))
    return f


def _sealed(f: Flow) -> None:
    state = f.state()
    assert not st.final_test_opened(state)
    assert (state.get('partition') or {}).get('opening') is None
    assert act.FINAL not in state['current']
    assert [e for e in fk.exposure_records(f.study)
            if e['partition'] == partition.FINAL_TEST and e['activity'] == act.FINAL] == []


def _changed(monkeypatch, module: str) -> None:
    """The engine now reads another digest for ``module`` (an engine upgrade no attestation
    covers), for currency and for new plans."""
    original = read.Study._module_sha
    monkeypatch.setattr(read.Study, '_module_sha',
                        lambda self, name: FAKE if name == module else original(self, name))
    fingerprint = registry.code_fingerprint

    def fp(modules):
        out = fingerprint(modules)
        if module in out['modules']:
            shas = {**out['modules'], module: FAKE}
            out = {'fingerprint': rec.code_digest(shas), 'modules': shas}
        return out
    monkeypatch.setattr(registry, 'code_fingerprint', fp)


def _excluded(study: Path) -> set[str]:
    s = read.open(study)
    return set(rec.parse_row_keys(s.blob(s.state['partition']['training_exclusions']
                                         ['row_keys'])))


def _run_notebook(path: Path, cwd: Path) -> dict:
    """Run a notebook's guarded recomputations headless (Marimo's app run), returning a few
    of the names its cells define."""
    script = (
        'import importlib.util, json\n'
        f'spec = importlib.util.spec_from_file_location("nb", {str(path)!r})\n'
        'nb = importlib.util.module_from_spec(spec); spec.loader.exec_module(nb)\n'
        'outputs, defs = nb.app.run()\n'
        'keep = {}\n'
        'for k in ("validation_auc", "validation_mae", "found", "precision", "baseline_mae"):\n'
        '    if k in defs: keep[k] = float(defs[k])\n'
        'for k in ("development", "train", "validation", "delayed_label_rows"):\n'
        '    if k in defs: keep[k] = sorted(defs[k].index)\n'
        'if "development" in defs:\n'
        '    keep["partitions"] = {str(k): int(v) for k, v in\n'
        '        defs["development"]["partition"].value_counts(dropna=False).items()}\n'
        'print(json.dumps(keep))\n')
    proc = subprocess.run([sys.executable, '-c', script], cwd=cwd,
                          env=fk.env(HYPOTRAIL_NOTEBOOK_RECOMPUTE='1'), capture_output=True,
                          text=True, timeout=600, stdin=subprocess.DEVNULL)
    assert proc.returncode == 0, proc.stderr[-6000:]
    assert 'Traceback' not in proc.stderr, proc.stderr[-6000:]
    return json.loads(proc.stdout.strip().splitlines()[-1])


def _cells(source: str) -> list[str]:
    return re.findall(r'^def ((?:recompute|explore)_\w+)\(', source, re.M)


@pytest.fixture(scope='module')
def delayed(tmp_path_factory):
    """A review-v1 binary study whose two last development rows have a delayed label, taken
    to an opened final test (with a capture), then rendered."""
    f = ReviewFlow(tmp_path_factory.mktemp('round3'))
    _to_choice(f)
    f.run('predictor.capture')
    f.decide('final_test', st.b1_default_value(f.state(), 'final_test'), words=OPEN)
    f.run('diag.final_test')
    assert cli.run(['render', '--study', str(f.study)]).exit_code == 0
    return f


@pytest.fixture(scope='module')
def old_study(tmp_path_factory):
    """A review-v1 binary study whose results were computed before the delayed-label fix
    (simulated: the engine ignores the exclusions while they are computed), its rule
    adopted, final test sealed, no capture."""
    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setattr(partition, 'training_exclusions', lambda state: None)
        f = ReviewFlow(tmp_path_factory.mktemp('round3-old'), name='old')
        _to_choice(f)
    finally:
        monkeypatch.undo()
    return f


def _copy(f: Flow, base: Path, name: str) -> Flow:
    target = base / name
    shutil.copytree(f.study, target)
    out = Flow(target, f.case_dir, prefix=name[:3])
    out.n = 1000
    return out


# --- E3-1: the notebooks use exactly the engine's rows ----------------------------------------

def test_development_frame_marks_the_delayed_label_rows(delayed):
    study = nv.open_study(delayed.study)
    excluded = _excluded(delayed.study)
    frame = nv.development_frame(study, study.state['current']['split'])
    assert set(frame.index[frame['partition'] == nv.DELAYED_LABEL]) == excluded == \
        {'L240', 'L241'}
    split = study.result(study.state['current']['split'])
    train = frame[frame['partition'] == 'train']
    assert len(train) == split['output']['values']['n_rows'] == len(frame) - 2
    assert not set(train.index) & excluded
    assert nv.delayed_label_keys(study) == ['L240', 'L241']
    # The training rows of the workbench are the split's too.
    assert not set(nv.training_frame(study).index) & excluded
    # The explicit plan, read as the engine reads it.
    plan = nv.evaluation_plan(study)
    assert plan == act.evaluation_membership(sto.StudyStore(delayed.study), split['result_id'])
    scored = {k for fold in plan['folds'] for k in fold['validation_keys']}
    assert scored == set(nv.folds(study).index) and not scored & excluded


def test_the_reviewers_split_cell_holds(delayed):
    """The reviewer's ``nb_split_cell.py``: the explore and split cells' code, run on the
    study, keep their asserts, and ``train`` holds no delayed-label row."""
    source = (delayed.study / rn.GENERATED).read_text(encoding='utf-8')
    ids = json.loads(re.search(r'RESULT_IDS = (\{.*?\})\n', source, re.S).group(1))

    def body(name):
        text = source.split(f'def {name}(')[1].split('\n    return')[0]
        return '\n'.join(line[4:] for line in text.splitlines()[1:] if 'mo.stop' not in line)
    g = {'nv': nv, 'study': nv.open_study(delayed.study), 'RESULT_IDS': ids}
    exec(body('explore_rows'), g)
    exec(body('recompute_split'), g)
    assert len(g['train']) == 238 and set(g['delayed_label_rows'].index) == {'L240', 'L241'}
    assert not set(g['train'].index) & _excluded(delayed.study)


def test_the_notebooks_run_headless_on_the_engines_rows(delayed):
    source = (delayed.study / rn.GENERATED).read_text(encoding='utf-8')
    assert _cells(source)[:6] == ['recompute_imports', 'explore_rows', 'explore_info',
                                  'explore_missing', 'explore_describe', 'recompute_split']
    for name in ('recompute_target', 'explore_special_values', 'explore_correlation',
                 'recompute_model', 'recompute_policy', 'recompute_dev_diagnostics',
                 'recompute_final_diagnostics'):
        assert name in _cells(source), name
    # The explanation: the term first, then this study's example (the engine's limit).
    rows = source.split('def explore_rows(')[1].split('\n    return')[0]
    assert rows.index('A delayed label is an outcome that becomes known only some time after '
                      'the prediction') < rows.index('print(nv.delayed_labels_text(study))')
    assert 'rows you may explore and fit on' not in rows
    assert 'mo.Html(nv.delayed_labels_html(study))' in source
    excluded = _excluded(delayed.study)
    for name in (rn.GENERATED, rn.EDITABLE):
        out = _run_notebook(delayed.study / name, delayed.study.parent)
        assert set(out['delayed_label_rows']) == excluded
        assert out['partitions'] == {'train': 238, nv.DELAYED_LABEL: 2}
        assert not set(out['train']) & excluded and len(out['train']) == 238
        values = read.open(delayed.study).current('fit.logistic')['output']['values']
        assert abs(out['validation_auc'] - values['validation']['roc_auc']) < 1e-6


def test_the_split_step_explains_the_delayed_labels(delayed, tmp_path):
    study = nv.open_study(delayed.study)
    html = nv.delayed_labels_html(study)
    assert html.startswith('<p data-limit="delayed_labels_excluded">A delayed label is an '
                           'outcome')
    assert 'Here 2 development rows' in html and 'For example' in html
    # In a French study, the engine's French text (the term first).
    f = ReviewFlow(tmp_path, language='fr')
    f.init()
    f.pauses()
    f.run('split')
    text = nv.delayed_labels_text(nv.open_study(f.study))
    assert text.startswith('Une étiquette tardive est un résultat connu seulement')
    assert text == junior.limit_fr(st.delayed_labels_limit(f.state()))
    # Without exclusions, nothing.
    g = ReviewFlow(tmp_path, name='nodelay', outcome_delay=0)
    g.init()
    g.pauses()
    g.run('split')
    assert nv.delayed_labels_html(nv.open_study(g.study)) == ''
    assert set(nv.development_frame(nv.open_study(g.study))['partition']) == {'train'}


class _Values:
    """A stand-in for ``nv`` in the generated code: the registry values of one split."""

    def __init__(self, split):
        self.split = split

    def values(self, study, rid):
        return self.split


def test_the_holdout_split_cell_counts_the_delayed_label_rows_apart():
    """The single-validation branch (not reachable with exclusions today: review-v1 studies
    cross-validate) keeps its asserts with delayed-label rows."""
    import pandas as pd
    split = {'n_rows': 6, 'partitions': {'train': {'n_rows': 4}, 'validation': {'n_rows': 2}},
             'training_exclusions': {'n_rows': 2, 'reasons': [], 'note': ''}}
    view = {'results': {'split': {'current': True, 'integrity': 'ok', 'values': split,
                                  'blobs': {'train': 'a', 'validation': 'b'}}}}
    name, code = code_cells.split_cell(view, 'binary')
    development = pd.DataFrame({'partition': ['train'] * 4 + ['validation'] * 2
                                + [nv.DELAYED_LABEL] * 2}, index=[f'L{i}' for i in range(8)])
    g = {'nv': _Values(split), 'study': None, 'RESULT_IDS': {'split': 'x'},
         'development': development,
         'delayed_label_rows': development[development['partition'] == nv.DELAYED_LABEL]}
    exec(code, g)
    assert len(g['train']) == 4 and len(g['validation']) == 2
    # Without exclusions the cell is the one it was.
    del split['training_exclusions']
    assert 'assert len(development) == split["n_rows"]' in code_cells.split_cell(view,
                                                                                 'binary')[1]


# --- E3-2: the engine's own limit text is traceable -------------------------------------------

def _check(study: Path, text: str, tmp_path: Path) -> dict:
    path = tmp_path / 'draft.txt'
    path.write_text(text, encoding='utf-8')
    return cli.run(['check', '--study', str(study), '--text', str(path)]).payload


def test_the_limit_text_passes_check_in_english_and_french(delayed, tmp_path):
    item = st.delayed_labels_limit(delayed.state())
    for text in (item['text'], junior.limit_fr(item)):
        out = _check(delayed.study, text, tmp_path)
        assert out['counts'] == {'error': 0, 'warning': 0}, out['findings']
        assert [t for t in out['traced'] if t.get('source') == 'partition'] == [
            {'text': '241', 'source': 'partition', 'id': 'partition.order.final_start',
             'value': 241.0}] * 2


def test_the_partition_values_are_traced_only_where_the_limit_writes_them(delayed, tmp_path):
    # Elsewhere the final boundary stays untraceable, as any other number.
    for text in ('The model reached 241 clients.', 'The final test starts at 241.',
                 'prediction_tick 9241 was the last tick.'):
        out = _check(delayed.study, text, tmp_path)
        assert [f['details']['number'] for f in out['findings']
                if f['code'] == 'untraceable_number'] in (['241'], ['9241']), (text, out)
    # The unit test of the matcher on a view that holds only the limit.
    view = {'results': {}, 'decisions': {}, 'open_proposals': [], 'settings': {},
            'dataset': {}, 'facts': {'by_status': {}}, 'plan': [],
            'not_yet_defensible': [{'id': 'delayed_labels_excluded', 'n_rows': 3,
                                    'clock': 'prediction_tick', 'final_start': 241}]}
    pool = numtrace.Pool(view)

    def traced(text):
        findings, found = numtrace.trace_text(pool, text, 'draft')
        return ([t['id'] for t in found], [f['details']['number'] for f in findings])
    assert traced('Here 3 development rows were left out (prediction_tick 241).') == (
        ['partition.training_exclusions.n_rows', 'partition.order.final_start'], [])
    assert traced('Ici, 3 lignes de développement ont été écartées.') == (
        ['partition.training_exclusions.n_rows'], [])
    assert traced('Here 3 clients and 241 calls.') == ([], ['3', '241'])
    assert traced('prediction_tick 242 and 4 development rows.') == ([], ['242', '4'])
    assert traced('other_prediction_tick 241') == ([], ['241'])


def test_export_handoff_accepts_a_study_with_exclusions(delayed, tmp_path):
    out = cli.run(['export', 'handoff', '--study', str(delayed.study), '--out',
                   str(tmp_path / 'handoff')])
    assert out.exit_code == 0, out.payload
    text = (tmp_path / 'handoff' / 'handoff.md').read_text(encoding='utf-8')
    assert 'prediction_tick 241' in text and 'A delayed label is an outcome' in text


# --- E3-3: the final test opens only on fully current selection evidence ----------------------

def test_an_unattested_code_change_refuses_the_opening(tmp_path, monkeypatch):
    """The reviewer's ``codechange_open.py``: no capture, the code of the variant and of the
    policy evaluation changed (no attestation covers it)."""
    f = ReviewFlow(tmp_path, outcome_delay=0)
    _to_choice(f)
    with monkeypatch.context() as m:
        _changed(m, 'mlkit.study.trials')
        s = read.open(f.study)
        assert st.is_current(s.state, 'fit.variant')               # the stale map says so
        assert s.currency(s.state['current']['fit.variant'])['reason']['code_changed'] \
            == ['mlkit.study.trials']
        nxt = f.view()['next_action']
        assert nxt['kind'] == 'run' and nxt.get('decision') is None
        assert nxt['activity'] == 'fit.variant'
        # The diagnostics compare the variant: computed from a result that is not current.
        assert nxt['not_current'] == ['fit.variant', 'policy.evaluation', 'diag.binary']
        assert 'No final-test row was read' in nxt['junior_message']
        out = _confirm_final(f, expect=2)
        error = out['error']
        assert error['code'] == 'precondition_missing'
        named = {x['slot']: x for x in error['details']['missing']
                 if x.get('requirement') == 'result_current' and 'reason' in x}
        assert set(named) == {'fit.variant', 'policy.evaluation', 'diag.binary'}
        assert named['fit.variant']['code_changed'] == ['mlkit.study.trials']
        assert named['policy.evaluation']['code_changed'] == ['mlkit.study.trials']
        assert named['diag.binary']['code_changed'] == []
        assert named['diag.binary']['upstream_not_current']
        junior_message = error['details']['junior_message']
        assert ('the variant model, the policy evaluation and the development diagnostics'
                in junior_message)
        assert "the engine's code that computed them changed since" in junior_message
        assert 'No final-test row was read' in junior_message
        _sealed(f)
        assert f.state()['decisions']['final_test']['status'] != 'confirmed'
        # The proposal stays open, but the next action is still to run the results again.
        nxt = f.view()['next_action']
        assert (nxt['kind'], nxt['activity']) == ('run', 'fit.variant')
    # The code is back: the final test opens (it was never consumed).
    assert f.view()['next_action']['kind'] == 'await_user_words'
    assert _confirm_final(f)['result']['opening']['status'] == 'promoted'


def test_the_run_path_refuses_before_the_opening(tmp_path, monkeypatch):
    f = ReviewFlow(tmp_path, outcome_delay=0)
    _to_choice(f)
    with monkeypatch.context() as m:
        m.setattr(cmd, '_opening', lambda store, payload, request_id: None)
        _confirm_final(f)
    assert not st.final_test_opened(f.state())
    nxt = f.view()['next_action']
    assert (nxt['kind'], nxt['activity']) == ('run', act.FINAL)
    with monkeypatch.context() as m:
        _changed(m, 'mlkit.study.policy')
        nxt = f.view()['next_action']
        assert nxt['kind'] == 'run' and nxt['activity'] == 'policy.evaluation'
        out = f.run(act.FINAL, expect=2)
        assert out['error']['code'] == 'precondition_missing'
        assert {x['slot'] for x in out['error']['details']['missing']} == {
            'policy.evaluation', 'diag.binary'}
        assert 'No final-test row was read' in out['error']['details']['junior_message']
        _sealed(f)
    assert f.run(act.FINAL)['status'] == 'promoted'


def test_an_old_study_with_exclusions_never_opens_on_its_old_evidence(old_study, tmp_path):
    """The reviewer's ``open_direct.py`` and ``recover.py``: every result of the study was
    computed with the delayed-label rows; none is current, though the stale map says they
    are; the opening is refused (no final-test row read) and ``next_action`` recommends
    running the split first; once everything is run again the final test opens."""
    f = _copy(old_study, tmp_path, 'old-copy')
    state = f.state()
    for slot in ('split', 'fit.baseline', 'fit.logistic', 'fit.variant', 'policy.evaluation',
                 'diag.binary'):
        assert st.is_current(state, slot), slot
    nxt = f.view()['next_action']
    assert nxt['kind'] == 'run' and nxt['activity'] == 'split'
    assert nxt['not_current'] == ['split', 'fit.baseline', 'fit.logistic', 'fit.variant',
                                  'policy.evaluation', 'diag.binary']
    assert 'delayed labels' in nxt['junior_message']
    out = _confirm_final(f, expect=2)
    missing = [x for x in out['error']['details']['missing'] if x.get('delayed_labels_included')]
    assert [x['slot'] for x in missing] == nxt['not_current']
    assert 'were computed with development rows whose label was not known yet' in \
        out['error']['details']['junior_message']
    _sealed(f)
    # Recovery: run again what the next action names, upstream first.
    for activity in ('split', 'fit.baseline', 'fit.logistic', 'fit.variant'):
        f.run(activity)
    f.call('run', 'policy.evaluate', '--rule', 'share:0.2', '--request-id', f.rid(),
           '--expected-revision', f.rev(), '--study', f.study)
    f.run('diag.binary')
    for decision in ('model_choice', 'policy'):
        if f.state()['decisions'][decision]['status'] != 'confirmed':
            f.decide(decision, 'fit.logistic' if decision == 'model_choice' else 'share:0.2',
                     words=CHOOSE if decision == 'model_choice' else ADOPT)
    f.run('diag.binary')
    assert f.view()['next_action'].get('not_current') is None
    assert _confirm_final(f)['result']['opening']['status'] == 'promoted'
    s = read.open(f.study)
    final = s.result(s.state['current'][act.FINAL])
    assert final['inputs']['training_exclusions']['n_rows'] == 2
    assert s.currency(final['result_id'])['current']


def test_the_junior_message_is_in_the_study_language():
    state = {'language': 'fr'}
    from mlkit.study import opening
    text = opening.message(state, [{'slot': 'split', 'delayed_labels_included': True,
                                    'code_changed': []}])
    assert text.startswith("Le test final s'ouvre seulement sur des résultats à jour")
    assert 'le découpage' in text and 'étiquettes tardives' in text
    assert text.endswith("Aucune ligne de l'échantillon de test final n'a été lue : il reste "
                         "scellé.")


# --- E3-4: after the opening, diag.final_test says the final test cannot be recomputed --------

def test_diag_final_test_on_an_old_opening_cannot_be_recomputed(old_study, tmp_path,
                                                                monkeypatch):
    """A study opened before the delayed-label fix (its final evaluation computed with the
    delayed-label rows): ``run diag.final_test`` is refused as not recomputable, with a junior
    message, whether or not the diagnostics were computed before."""
    for name, with_diag in (('opened-diag', True), ('opened-nodiag', False)):
        f = _copy(old_study, tmp_path, name)
        with monkeypatch.context() as m:
            m.setattr(partition, 'training_exclusions', lambda state: None)
            f.decide('final_test', st.b1_default_value(f.state(), 'final_test'), words=OPEN)
            if with_diag:
                f.run('diag.final_test')
        assert st.final_test_opened(f.state())
        out = f.run('diag.final_test', expect=2)
        error = out['error']
        assert error['code'] == 'precondition_missing', error
        assert 'cannot be recomputed' in error['message']
        assert 'run it again' not in json.dumps(error)
        assert error['details']['current'] is False
        assert error['details']['delayed_labels_included'] is True
        assert error['details']['final_result_id'] == f.state()['current'][act.FINAL]
        assert error['details']['junior_message'].startswith(
            'The final-test diagnostics cannot be computed')
        assert 'opened only once' in error['details']['junior_message']
        # The final evaluation itself is refused as already opened (E2-2).
        out = f.run(act.FINAL, expect=2)
        assert out['error']['code'] == 'final_test_already_opened'


# --- B3-0, (a): regression and tuned variants under review-v1 explicit plans ------------------

@pytest.mark.parametrize('delay', [5, 0])
def test_regression_under_an_explicit_plan_fits_captures_and_opens(tmp_path, monkeypatch,
                                                                   delay):
    """The reviewer's ``delayed_kit.drive`` without its engine patch: fits, explicit
    cross-validation, a tuned variant, the comparison, the capture, the final test."""
    f = _regression_flow(tmp_path, monkeypatch, delay=delay)
    f.run('split')
    f.run('eda.target_summary')
    for activity in ('fit.baseline', 'fit.linear', 'diag.regression'):
        f.run(activity)
    f.decide('model_variant', {'variants': [TUNED]})
    f.run('fit.variant')
    f.run('evaluate.regression')
    f.decide('model_choice', 'fit.linear', words=REG_WORDS)
    f.run('diag.regression')
    f.run('predictor.capture', '--profile', 'workshop')
    f.decide('final_test', st.b1_default_value(f.state(), 'final_test'), words=OPEN)
    f.run('diag.final_test')
    s = read.open(f.study)
    assert all(s.currency(rid)['current'] for rid in s.state['current'].values())
    excluded = (set(rec.parse_row_keys(s.blob(s.state['partition']['training_exclusions']
                                              ['row_keys']))) if delay else set())
    assert len(excluded) == delay
    n_dev = len(fk.partition_keys(f.study, 'development'))
    split = s.current('split')['output']['values']
    for slot in ('fit.baseline', 'fit.linear', 'fit.variant'):
        values = s.current(slot)['output']['values']
        cv = values['cross_validation']
        assert cv['method'] == 'forward_chaining' and cv['n_development'] == n_dev - delay
        assert cv['n_scored'] == split['n_scored'] and cv['n_warmup'] == split['n_warmup']
        keys = set(s.predictions(s.state['current'][slot])['row_key'])
        assert len(keys) == split['n_scored'] and not keys & excluded, slot
    assert s.current('fit.baseline')['output']['values']['model'] == 'train_median'
    tuning = s.current('fit.variant')['output']['values']['tuning']
    assert len(tuning['per_fold']) == split['folds'] and tuning['development'] is not None
    assert s.current('predictor.capture')['output']['values']['n_train'] == n_dev - delay
    final = s.current(act.FINAL)['output']['values']
    assert final['refit']['n_rows'] == n_dev - delay
    # The notebook recomputes the explicit plan's figures (B3-0, (b), (c)).
    assert cli.run(['render', '--study', str(f.study)]).exit_code == 0
    source = (f.study / rn.GENERATED).read_text(encoding='utf-8')
    for name in ('recompute_split', 'recompute_model', 'recompute_comparison'):
        assert name in _cells(source), name
    out = _run_notebook(f.study / rn.GENERATED, f.study.parent)
    linear = s.current('fit.linear')['output']['values']
    assert abs(out['validation_mae'] - linear['validation']['mae']) < 1e-6
    assert not set(out['train']) & excluded and len(out['train']) == n_dev - delay


@pytest.mark.parametrize('variant', [TUNED, {'kind': 'family', 'family': 'hgb',
                                              'question': 'Does boosting find more?',
                                              'origin': 'planned',
                                              'diagnostic_result_id': None}])
def test_a_tuned_or_family_variant_fits_under_an_explicit_plan(tmp_path, variant):
    """Known bug (a): families.choose used numpy without importing it on the explicit inner
    plan (NameError)."""
    f = ReviewFlow(tmp_path)
    f.init()
    f.pauses()
    f.run('split')
    from mlkit.study import governance
    f.decide('preprocessing', dict(governance.DEFAULT_PREPROCESSING))
    f.run('fit.baseline')
    f.run('fit.logistic')
    f.run('diag.binary')
    f.decide('model_variant', {'variants': [variant]})
    out = f.run('fit.variant')
    assert out['status'] == 'promoted'
    values = read.open(f.study).current('fit.variant')['output']['values']
    assert values['cross_validation']['method'] == 'forward_chaining'
    if variant['kind'] == 'tuned':
        # One choice per outer fold, each by the explicit inner plan of its training rows.
        assert len(values['tuning']['per_fold']) == len(values['cross_validation']['per_fold'])


def test_a_review_v1_explicit_plan_notebook_runs_without_exclusions(tmp_path):
    """Known bugs (b) and (c): the explicit plan's CV cell ("Item wrong length") and the
    baseline example ("no value at 'train_rate'") of a review-v1 study."""
    f = ReviewFlow(tmp_path, outcome_delay=0)
    _to_choice(f)
    f.decide('final_test', st.b1_default_value(f.state(), 'final_test'), words=OPEN)
    f.run('diag.final_test')
    assert cli.run(['render', '--study', str(f.study)]).exit_code == 0
    study = nv.open_study(f.study)
    cited = nv.citer(study, rn.result_ids(f.view()))
    assert 'train_rate' not in study.current('fit.baseline')['output']['values']
    assert nv.example_html(cited, 'baseline') == ''
    source = (f.study / rn.GENERATED).read_text(encoding='utf-8')
    for name in ('recompute_split', 'recompute_model', 'recompute_policy'):
        assert name in _cells(source), name
    assert 'delayed_label' not in source.split('def explore_rows(')[1].split('return')[0]
    out = _run_notebook(f.study / rn.GENERATED, f.study.parent)
    values = study.current('fit.logistic')['output']['values']
    assert abs(out['validation_auc'] - values['validation']['roc_auc']) < 1e-6
    policy = study.current('policy.evaluation')['output']['values']
    assert out['found'] == policy['rules']['share:0.2']['models']['fit.logistic'][
        'true_positives']
    proc = subprocess.run([sys.executable, str(f.study / rn.GENERATED)], cwd=f.study.parent,
                          env=fk.env(), capture_output=True, text=True, timeout=300,
                          stdin=subprocess.DEVNULL)
    assert proc.returncode == 0, proc.stderr[-4000:]


# --- the round-3 attestation edges are exact --------------------------------------------------

FIT, FAMILIES = 'mlkit.study.fit', 'mlkit.study.families'
FILES = {FIT: 'framework/mlkit/study/fit.py', FAMILIES: 'framework/mlkit/study/families.py'}
# At ce82ca9 (fit.py unchanged since 621d607, families.py since 506180a), at 506180a, now.
PREVIOUS = {FIT: 'd39f3f5bfbc0927c79af7371b8358b9b4d72892b869c2ed726498a798a744579',
            FAMILIES: '2d8748798498388525c94ef85f8d73779b2a0c5d3145270e32d67cbbfc860e85'}
BASE = {FIT: '28c00840fe9f9a5c17d0e9a0d483cd7dbdc9ed2cc4d715a8f65073399d989161',
        FAMILIES: '2d8748798498388525c94ef85f8d73779b2a0c5d3145270e32d67cbbfc860e85'}
CURRENT = {FIT: '9ca62f79a0cb335374beb1c8047cd34047bd4456a192f300282e269f1979c8f7',
           FAMILIES: '4e207920618b1a59da54d1a66066a22c771a276795012931a4aa74f9a78a3f00'}
# The attested activity lists, written out: every activity whose fingerprint holds the module
# but the capture (its predictor and computation ids hash the code fingerprint).
ATTESTED = {FIT: ['fit.baseline', 'fit.logistic', 'fit.linear', 'fit.variant',
                  'eda.single_feature_signal', 'diag.binary', 'diag.regression',
                  'final_test.evaluation'],
            FAMILIES: ['fit.variant', 'final_test.evaluation']}


def _edges(module: str, source: str) -> list[dict]:
    return [r for r in code_compat.ATTESTATIONS if r['module'] == module
            and r['from_sha256'] == source and r['to_sha256'] == CURRENT[module]]


def test_the_round3_edges_target_the_current_bytes():
    assert code_compat.integrity()
    for module, path in FILES.items():
        now = hashlib.sha256((REPO / path).read_bytes()).hexdigest()
        assert now == CURRENT[module], (f'{path} changed again: re-run '
                                        'code_compat_evidence.py against the new bytes and, '
                                        'only if it matches, add new edges.')
        assert read._module_path(module).read_bytes() == (REPO / path).read_bytes()
        holding = {a for a in act.ACTIVITIES if module in act.MODULES[a]
                   or module in act.REGRESSION_MODULES.get(a, ())}
        assert set(ATTESTED[module]) == holding - {act.CAPTURE}
        for source in {PREVIOUS[module], BASE[module]}:
            [record] = _edges(module, source)
            assert record['activities'] == ATTESTED[module]
            assert act.CAPTURE not in record['activities']
            assert 'framework/tests/study/test_review_round3_engine.py' in record['evidence']
            assert 'framework/tests/study/code_compat_evidence.py' in record['evidence']


def test_the_round3_edges_start_at_the_recorded_bytes():
    for commit, digests in (('ce82ca9', PREVIOUS), ('818995c', PREVIOUS), ('506180a', BASE)):
        probe = subprocess.run(['git', '-C', str(REPO), 'cat-file', '-e', f'{commit}^{{commit}}'],
                               capture_output=True)
        if probe.returncode != 0:
            pytest.skip(f'{commit} is not in this clone')
        for module, path in FILES.items():
            blob = subprocess.run(['git', '-C', str(REPO), 'show', f'{commit}:{path}'],
                                  capture_output=True, check=True).stdout
            assert hashlib.sha256(blob).hexdigest() == digests[module], (commit, module)


def _entry(activity: str, **digests) -> dict:
    modules = dict(registry.code_fingerprint(list(act.MODULES[activity]))['modules'])
    modules.update({m: d for m, d in digests.items() if m in modules})
    return {'activity': activity, 'code': {'modules': modules}}


def test_the_round3_edges_are_exact_directed_and_scoped(tmp_path):
    case_dir = fk.make_case(tmp_path / 'case', n_rows=200)['case'].parent
    Flow(tmp_path / 'study', case_dir).init()
    study = read.open(tmp_path / 'study')
    acts = 'mlkit.study.activities'
    ce82 = 'b7c994d2e88edba8156c47756c0c43a496f0e04d4f7005bc1d9014ab639a48c1'
    for activity in ATTESTED[FIT]:
        # A result of the ce82ca9 engine, and one of the 506180a engine.
        assert study.code_changed(_entry(activity, **PREVIOUS)) == [], activity
        assert study.code_changed(_entry(activity, **BASE, **{
            acts: '3065f4d623f1ea2346c43ef27c0dd0f9a948c8eb007355c9cb625967b17cc9e1'})) == []
    assert study.code_changed(_entry(act.CAPTURE, **PREVIOUS)) == [FAMILIES, FIT]
    assert study.code_changed(_entry(act.CAPTURE, **{acts: ce82, **PREVIOUS})) == [FAMILIES,
                                                                                     FIT]
    for module in (FIT, FAMILIES):
        assert not code_compat.equivalent(module, CURRENT[module], PREVIOUS[module],
                                          'fit.variant')
        assert not code_compat.equivalent(module, PREVIOUS[module], CURRENT[module], None)
        assert not code_compat.equivalent(module, PREVIOUS[module], CURRENT[module],
                                          act.CAPTURE)
        assert not code_compat.equivalent(module, PREVIOUS[module], CURRENT[module],
                                          'policy.evaluation')
    assert study.code_changed(_entry('fit.logistic', **{FIT: 'e' * 64})) == [FIT]


@pytest.mark.skipif(not (os.environ.get('HYPOTRAIL_COMPAT_OLD_PYTHON')
                         and os.environ.get('HYPOTRAIL_COMPAT_OLD_ROOT')),
                    reason='needs a ce82ca9 (or 506180a) engine and a Python with its '
                           'dependencies (HYPOTRAIL_COMPAT_OLD_PYTHON, HYPOTRAIL_COMPAT_OLD_ROOT)')
def test_byte_comparison_with_the_previous_engine(tmp_path):
    """The evidence itself: the same flows on both engines, then leaf recomputation."""
    script = Path(__file__).with_name('code_compat_evidence.py')
    proc = subprocess.run([sys.executable, str(script), 'evidence',
                           os.environ['HYPOTRAIL_COMPAT_OLD_PYTHON'],
                           os.environ['HYPOTRAIL_COMPAT_OLD_ROOT'], str(tmp_path / 'work')],
                          capture_output=True, text=True, timeout=3600)
    assert proc.returncode == 0, proc.stdout[-4000:] + proc.stderr[-4000:]
    assert 'DIFFERENT' not in proc.stdout and proc.stdout.rstrip().endswith('MATCH')


def test_check_text_given_a_long_message_instead_of_a_path_is_a_refusal(tmp_path):
    """`check --text` with a long literal string (not a path) answers invalid_arguments, not
    internal_error (an OSError, file name too long)."""
    from mlkit.study import cmd_check
    from mlkit.study.errors import StudyError
    with pytest.raises(StudyError) as caught:
        cmd_check._read_text('The rate is 37 % on 319 rows. ' * 40)
    assert caught.value.code == 'invalid_arguments'
