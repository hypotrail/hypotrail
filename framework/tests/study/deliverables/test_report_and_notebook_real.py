"""The v0.2a report and notebook on real studies (WP-A6): Bank Marketing and Auto MPG.

* The generated notebook's recomputation cells (``mlkit.study.code_cells``) run headless
  and their ``assert``\\ s pass: split counts, target rate or summary, one rate or mean by
  group, the candidate model's validation metric with the confirmed preprocessing, and the
  policy at the adopted rule (binary) or the baseline's error (regression). A changed
  registered figure makes them fail.
* They read development rows only (never a final-test row), and running the notebook
  writes nothing under ``.hypotrail``.
* Only the recomputation cells import pandas, numpy, or scikit-learn, and fit; the engine
  view cells and the notebook's read side import neither and never fit.
* The workbench (template version 2) loads the training rows in a starter cell.
* The HTML report opens with the verdict card, has the data section and 3 to 5 charts
  whose numbers are all cited, shows no raw result id in its prose, keeps the annex
  collapsed, and ``check`` is clean on both studies.

Studies live in ``tmp_path``; the committed cases are only read.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

import pytest

from mlkit.study import cmd_check, code_cells, manifest as mf, read, render_notebook as rn

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import flowkit as fk  # noqa: E402

AUTO = fk.REPO / 'use-cases' / 'auto-mpg'
WRITER_MODULES = {'store', 'lock', 'registry', 'exposure', 'dependencies', 'commands', 'cli',
                  'migrate', 'preconditions', 'cmd_render', 'cmd_run', 'render_notebook',
                  'manifest'}
FIT_CALLS = {'fit', 'fit_transform', 'partial_fit', 'fit_predict'}
RECOMPUTE_IMPORT_ROOTS = {'numpy', 'pandas', 'sklearn'}


def _bank(study: Path) -> Path:
    f = fk.Flow(study, fk.BANK, prefix='a6b')
    f.init()
    f.pauses()
    f.run('split')
    for a in ('eda.target_rate', 'eda.special_values', 'eda.quality'):
        f.run(a)
    f.run('eda.rate_by', '--column', 'poutcome')
    f.run('eda.single_feature_signal')
    f.run('fit.baseline')
    f.run('fit.logistic')
    f.variant()           # WP-B1: the variant the policy compares
    f.run('policy.evaluate', '--rule', 'capacity:100')
    f.decide('policy', 'capacity:100', 'Yes, call the top 100 because the desk has 100 slots')
    f.decide('conclusion', {'verdict': 'adopt_policy',
                            'text': 'The ranking beats the baseline on validation rows chosen '
                                    'to compare them; a pilot should confirm it.'},
             'I conclude as stated because the interval excludes zero')
    return study


def _auto(study: Path) -> Path:
    f = fk.Flow(study, AUTO, prefix='a6a')
    f.init()
    f.pauses(split=False, acceleration='uncertain_excluded')
    f.decide('split', {'method': 'ordinal_cutoff', 'column': 'model_year', 'cutoff': 79})
    f.run('split')
    f.model_decisions()
    for a in ('eda.target_summary', 'eda.special_values'):
        f.run(a)
    f.run('eda.mean_by', '--column', 'model_year')
    f.run('eda.distribution', '--column', 'weight')
    f.run('eda.single_feature_signal')
    f.run('fit.baseline')
    f.run('fit.linear')
    f.variant()           # WP-B1: the variant the model choice compares
    f.run('evaluate.regression')
    f.decide('model_choice', 'fit.linear', 'Yes, adopt the linear model because it errs less')
    return study


@pytest.fixture(scope='module')
def studies(tmp_path_factory) -> dict[str, Path]:
    root = tmp_path_factory.mktemp('wp_a6')
    return {'bank': _bank(root / 'bank'), 'auto': _auto(root / 'auto')}


def _run_app(path: Path, cwd: Path) -> dict:
    """Run a notebook's ``app.run()`` in a subprocess; return the named figures."""
    script = (
        'import importlib.util, json, sys\n'
        f'spec = importlib.util.spec_from_file_location("nb", {str(path)!r})\n'
        'nb = importlib.util.module_from_spec(spec); spec.loader.exec_module(nb)\n'
        'outputs, defs = nb.app.run()\n'
        'keep = {}\n'
        'for k in ("validation_auc", "validation_mae", "found", "precision", "baseline_mae"):\n'
        '    if k in defs: keep[k] = float(defs[k])\n'
        'if "development" in defs:\n'
        '    keep["development_keys"] = sorted(defs["development"].index)\n'
        'if "train_rows" in defs: keep["train_rows"] = len(defs["train_rows"])\n'
        'print(json.dumps(keep))\n')
    env = fk.env()
    proc = subprocess.run([sys.executable, '-c', script], cwd=cwd, env=env, capture_output=True,
                          text=True, timeout=300, stdin=subprocess.DEVNULL)
    return {'code': proc.returncode, 'stderr': proc.stderr,
            'out': json.loads(proc.stdout.strip().splitlines()[-1]) if proc.returncode == 0
            else None}


def _hashes(study: Path) -> dict:
    root = study / '.hypotrail'
    return {str(p.relative_to(study)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob('*')) if p.is_file() and p.name != 'writer.lock'}


# --- notebook ------------------------------------------------------------------------------

@pytest.mark.parametrize('name', ['bank', 'auto'])
def test_recomputation_cells_run_headless_and_match_the_registry(studies, name):
    study = studies[name]
    source = (study / rn.GENERATED).read_text(encoding='utf-8')
    expected = {'bank': ['recompute_split', 'recompute_target', 'recompute_by_group',
                         'recompute_model', 'recompute_policy'],
                'auto': ['recompute_split', 'recompute_target', 'recompute_by_group',
                         'recompute_model', 'recompute_comparison']}[name]
    assert re.findall(r'^def (recompute_\w+)\(', source, re.M) == ['recompute_imports'] + expected
    assert source.startswith('# Regenerated by Hypotrail at revision ')
    assert 'copy any cell to your workbench to experiment' in source.splitlines()[0]
    before = _hashes(study)
    run = _run_app(study / rn.GENERATED, study.parent)
    assert run['code'] == 0, run['stderr']
    out = run['out']
    s = read.open(study)
    if name == 'bank':
        logistic = s.current('fit.logistic')['output']['values']
        assert out['validation_auc'] == pytest.approx(logistic['validation']['roc_auc'],
                                                      abs=code_cells.FIT_TOLERANCE)
        at_rule = s.current('policy.evaluation')['output']['values']['rules']['capacity:100']
        assert out['found'] == at_rule['models']['fit.logistic']['true_positives']
    else:
        evaluation = s.current('evaluate.regression')['output']['values']
        assert out['baseline_mae'] == pytest.approx(evaluation['models']['fit.baseline']['mae'])
    # development rows only: every one, and never a final-test row
    final = set(fk.partition_keys(study, 'final_test'))
    assert final and not final & set(out['development_keys'])
    assert set(out['development_keys']) == set(fk.partition_keys(study, 'development'))
    assert _hashes(study) == before                     # the notebook wrote nothing


def test_a_changed_registered_figure_fails_the_recomputation(studies, tmp_path):
    study = fk.clone(studies['bank'], tmp_path / 'bank')
    path = study / rn.GENERATED
    source = path.read_text(encoding='utf-8')
    edited = source.replace('assert found == at_rule["true_positives"]',
                            'assert found == at_rule["true_positives"] + 1')
    assert edited != source
    path.write_text(edited, encoding='utf-8')
    run = _run_app(path, study.parent)
    assert run['code'] != 0 and 'AssertionError' in run['stderr']


def _cells(source: str) -> dict[str, ast.FunctionDef]:
    tree = ast.parse(source)
    return {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}


def _imports(node) -> set[str]:
    out = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Import):
            out |= {a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            out |= {f'{n.module}.{a.name}' for a in n.names}
    return out


def _fit_calls(node) -> list[str]:
    return [n.func.attr for n in ast.walk(node) if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute) and n.func.attr in FIT_CALLS]


@pytest.mark.parametrize('name', ['bank', 'auto'])
def test_only_recomputation_cells_import_sklearn_and_fit(studies, name):
    """ADR 0001 as amended by WP-A6: the engine view cells and the setup import only the
    read API; only ``recompute_*`` cells import pandas, numpy, or scikit-learn, and the only
    fit is ``model.fit`` on the training rows of the model cell. No cell imports a writer."""
    source = (studies[name] / rn.GENERATED).read_text(encoding='utf-8')
    cells = _cells(source)
    fits = []
    for cell, node in cells.items():
        imports = _imports(node)
        assert not {i for i in imports if set(i.split('.')) & WRITER_MODULES}, cell
        if cell.startswith('recompute_'):
            assert {i.split('.')[0] for i in imports} <= RECOMPUTE_IMPORT_ROOTS, cell
            fits += [(cell, f) for f in _fit_calls(node)]
        else:
            assert not imports, cell
            assert not _fit_calls(node), cell
    assert fits == [('recompute_model', 'fit')]
    assert 'model.fit(X_train, y_train)' in ast.unparse(cells['recompute_model'])
    setup = source.split('@app.cell', 1)[0]
    assert set(_imports(ast.parse(setup))) == {'os', 'pathlib.Path', 'marimo',
                                               'mlkit.study.notebook_view'}


def test_check_still_rejects_a_number_in_a_markdown_cell(studies, tmp_path):
    study = fk.clone(studies['auto'], tmp_path / 'auto')
    path = study / rn.GENERATED
    source = path.read_text(encoding='utf-8')
    edited = source.replace('**Question.**', '**Question.** About 42 rows.', 1)
    path.write_text(edited, encoding='utf-8')
    findings = cmd_check.run_check(study)['findings']
    assert any(f['code'] == 'number_outside_result' and f['details'].get('number') == '42'
               for f in findings), findings


def test_new_workbench_loads_the_training_rows(studies):
    study = studies['bank']
    source = (study / rn.WORKBENCH).read_text(encoding='utf-8')
    assert 'template_version = 2' in source and 'nv.training_frame(study)' in source
    assert 'study_generated' not in source
    run = _run_app(study / rn.WORKBENCH, study.parent)
    assert run['code'] == 0, run['stderr']
    train = read.open(study).current('split')['output']['values']['partitions']['train']
    assert run['out']['train_rows'] == train['n_rows']


# --- report --------------------------------------------------------------------------------

class _Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.order, self.prose, self.svg_numbers = [], [], [], []
        self.figures = 0
        self.annex_open = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag not in ('br', 'meta', 'circle', 'rect', 'line'):
            self.stack.append((tag, a))
        if tag == 'section' and a.get('id'):
            self.order.append(a['id'])
        if tag == 'figure':
            self.figures += 1
        if tag == 'details' and a.get('id') == 'annex':
            self.annex_open = 'open' in a

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        tags = [t for t, _ in self.stack]
        if any(t in ('script', 'style', 'title') for t in tags):
            return
        if 'svg' in tags:
            self.svg_numbers.append((data, [a for _, a in self.stack]))
        if not any('details' == t for t in tags):
            self.prose.append(data)


@pytest.mark.parametrize('name', ['bank', 'auto'])
def test_report_layout_and_traceability(studies, name):
    study = studies[name]
    page = (study / mf.ARTIFACTS['report']).read_text(encoding='utf-8')
    p = _Page()
    p.feed(page)
    assert p.order[:4] == ['verdict', 'objective', 'data', 'charts']
    assert 3 <= p.figures <= 5
    assert p.annex_open is False
    # every number drawn in a chart is a cited label or an axis tick
    for text, ancestors in p.svg_numbers:
        if re.search(r'\d', text):
            cited = any('data-result-id' in a for a in ancestors)
            literal = {a.get('data-literal') for a in ancestors}
            assert cited or literal & {'axis', 'category', 'decision_value'}, (text, ancestors)
    # no raw result id (64 hex, or its 12-character prefix) in the prose outside the annex
    prose = ' '.join(p.prose)
    assert not re.search(r'\b[0-9a-f]{12,64}\b', prose)
    assert 'Channel chat' not in prose
    # the five development rows, never a final-test row
    rows = re.search(r'<table class="rows">.*?</table>', page, re.S).group(0)
    assert rows.count('<tr>') == 1 + 5
    # the verdict card and the data section
    verdict = re.search(r'<section class="card verdict" id="verdict">.*?</section>', page,
                        re.S).group(0)
    assert 'data-result-id' in verdict and 'Met' in verdict
    assert 'stay sealed' in page and 'data-feature-basis' in page
    report = cmd_check.run_check(study)
    assert report['clean'], report['findings']


def test_check_accepts_an_axis_tick_only_inside_an_svg(studies, tmp_path):
    study = fk.clone(studies['bank'], tmp_path / 'bank')
    page_path = study / mf.ARTIFACTS['report']
    page = page_path.read_text(encoding='utf-8')
    assert cmd_check.run_check(study)['clean']
    page_path.write_text(page.replace('<main>', '<main><p><span data-literal="axis">77</span>'
                                                '</p>', 1), encoding='utf-8')
    findings = cmd_check.run_check(study)['findings']
    assert any(f['code'] == 'number_outside_result' and '77' in f['message'] for f in findings)


def test_check_verifies_chart_labels_and_points(studies, tmp_path):
    study = fk.clone(studies['bank'], tmp_path / 'bank')
    page_path = study / mf.ARTIFACTS['report']
    page = page_path.read_text(encoding='utf-8')
    label = re.search(r'(<text [^>]*data-result-id="[0-9a-f]{64}"[^>]*>(?:[^<]*)<tspan>)'
                      r'([\d,.]+)(</tspan>)', page)
    points = re.search(r'(<data [^>]*data-scale="100"[^>]*>)([\d.]+)(</data>)', page)
    assert label and points
    edited = page.replace(label.group(0), label.group(1) + '999' + label.group(3), 1)
    edited = edited.replace(points.group(0), points.group(1) + '0.3' + points.group(3), 1)
    page_path.write_text(edited, encoding='utf-8')
    mismatches = [f for f in cmd_check.run_check(study)['findings']
                  if f['code'] == 'value_mismatch']
    shown = {f['details']['shown'] for f in mismatches}
    assert '999' in ''.join(shown) and '0.3' in shown, mismatches


# --- WP-B1: a cross-validated study, its variant, and its opened final test ---------------

def _cv(study: Path, case_dir: Path, task: str) -> Path:
    import json
    f = fk.Flow(study, case_dir, prefix='b1')
    f.init()
    f.pauses(split=False)
    f.decide('split', f.view()['next_action']['default_value'])
    f.model_decisions()
    f.run('split')
    for a in (('eda.target_summary', 'eda.special_values') if task == 'regression'
              else ('eda.target_rate', 'eda.special_values')):
        f.run(a)
    f.run('fit.baseline')
    f.run('fit.linear' if task == 'regression' else 'fit.logistic')
    f.variant()
    if task == 'regression':
        f.run('evaluate.regression')
        f.decide('model_choice', 'fit.linear', 'Yes, adopt the linear model because it errs less')
    else:
        f.run('policy.evaluate', '--rule', 'capacity:100')
        f.decide('policy', 'capacity:100', 'Yes, call the top 100 because the desk has 100 slots')
    # v0.3 (WP-F1, R28): the plan runs the diagnostics before the opening is drafted.
    f.run('diag.regression' if task == 'regression' else 'diag.binary')
    value = f.view()['next_action']['default_value']
    p = f.call('decide', 'propose', 'final_test', '--value-json', json.dumps(value),
               '--restatement', 'You open the sealed final test once for the chosen configuration.',
               '--rationale', 'The choice is fixed.', '--request-id', f.rid(),
               '--expected-revision', f.rev(), '--study', f.study)
    f.call('decide', 'confirm', p['result']['proposal_id'], '--user-words',
           'Yes, I open it now because the choice is fixed', '--request-id', f.rid(),
           '--expected-revision', f.rev(), '--study', f.study)
    return study


@pytest.fixture(scope='module')
def cv_studies(tmp_path_factory) -> dict[str, Path]:
    root = tmp_path_factory.mktemp('wp_b1')
    return {'bank': _cv(root / 'bank', fk.BANK, 'binary'),
            'auto': _cv(root / 'auto', AUTO, 'regression')}


@pytest.mark.parametrize('name', ['bank', 'auto'])
def test_cross_validated_recomputation_cells_refit_fold_by_fold(cv_studies, name):
    """WP-B1: the split cell counts the folds, the model cell refits the candidate on the
    other folds of each fold and recomputes its out-of-fold metric."""
    study = cv_studies[name]
    source = (study / rn.GENERATED).read_text(encoding='utf-8')
    assert 'nv.folds(study, RESULT_IDS["split"])' in source
    assert 'Out-of-fold' in source
    run = _run_app(study / rn.GENERATED, study.parent)
    assert run['code'] == 0, run['stderr']
    out = run['out']
    s = read.open(study)
    if name == 'bank':
        logistic = s.current('fit.logistic')['output']['values']
        assert out['validation_auc'] == pytest.approx(logistic['validation']['roc_auc'],
                                                      abs=code_cells.FIT_TOLERANCE)
        at_rule = s.current('policy.evaluation')['output']['values']['rules']['capacity:100']
        assert out['found'] == at_rule['models']['fit.logistic']['true_positives']
    else:
        evaluation = s.current('evaluate.regression')['output']['values']
        assert out['validation_mae'] == pytest.approx(evaluation['models']['fit.linear']['mae'],
                                                      abs=code_cells.FIT_TOLERANCE)
        assert out['baseline_mae'] == pytest.approx(evaluation['models']['fit.baseline']['mae'])
    assert set(out['development_keys']) == set(fk.partition_keys(study, 'development'))


@pytest.mark.parametrize('name', ['bank', 'auto'])
def test_the_verdict_card_separates_development_and_final_evidence(cv_studies, name):
    study = cv_studies[name]
    page = (study / mf.ARTIFACTS['report']).read_text(encoding='utf-8')
    verdict = re.search(r'<section class="card verdict" id="verdict">.*?</section>', page,
                        re.S).group(0)
    assert 'Development evidence' in verdict and 'out-of-fold' in verdict
    assert 'Final test' in verdict and 'Opened once, on' in verdict
    assert 'Success criterion on the final test' in verdict
    final = read.open(study).current('final_test.evaluation')['result_id']
    assert f'data-result-id="{final}"' in verdict
    assert 'Configurations compared' in verdict
    # WP-B6a: once opened, the final-test evidence comes first, the development second.
    assert verdict.index('Opened once, on') < verdict.index('Development evidence')
    assert verdict.index('Success criterion on the final test') \
        < verdict.index('Development evidence')
    assert 'id="variant-comparison"' in page
    report = cmd_check.run_check(study)
    assert report['clean'], report['findings']
    # B6c (B1): the final-test criterion is shown at its registered size, in its unit.
    crit = read.open(study).current('final_test.evaluation')['output']['values']['criterion']
    shown = _cited_text(verdict, final, 'criterion.gain')
    if name == 'bank':
        assert crit['unit'] == 'percentage points'
        assert shown == f'{crit["gain"]:.1f}'
        assert abs(float(shown)) <= 100
        row = verdict[verdict.index('Success criterion on the final test'):]
        assert f'{shown}</data> percentage points' in row
        for bound in ('low', 'high'):
            assert _cited_text(verdict, final, f'criterion.{bound}') == f'{crit[bound]:.1f}'
    else:
        assert shown == f'{100 * crit["gain"]:.1f}%'


def _cited_text(page: str, rid: str, path: str) -> str:
    m = re.search(r'<data value="[^"]*" data-result-id="' + re.escape(rid) + r'" data-path="'
                  + re.escape(path) + r'"[^>]*>([^<]*)</data>', page)
    assert m, path
    return m.group(1)


def test_check_catches_a_final_criterion_shown_100_times_too_large(cv_studies, tmp_path):
    """B6c (B1): a value already in percentage points shown with the points format (which
    multiplies by 100) matches its attribute times the scale, yet it is wrong: check says so."""
    import shutil
    study = tmp_path / 'bank'
    shutil.copytree(cv_studies['bank'], study)
    report = study / mf.ARTIFACTS['report']
    page = report.read_text(encoding='utf-8')
    final = read.open(study).current('final_test.evaluation')['result_id']
    gain = read.open(study).current('final_test.evaluation')['output']['values']['criterion'][
        'gain']
    m = re.search(r'<data value="([^"]*)" data-result-id="' + re.escape(final)
                  + r'" data-path="criterion.gain"([^>]*)>([^<]*)</data>', page)
    assert m and 'data-scale' not in m.group(2)
    bad = m.group(0).replace(' data-path="criterion.gain"',
                             ' data-path="criterion.gain" data-scale="100"').replace(
        f'>{m.group(3)}<', f'>{100 * gain:.1f}<')
    report.write_text(page.replace(m.group(0), bad, 1), encoding='utf-8')
    result = cmd_check.run_check(study)
    found = [f for f in result['findings'] if f['code'] == 'value_mismatch'
             and f['details'].get('path') == 'criterion.gain']
    assert found and found[0]['details']['reason'] == 'double_scaled'
    assert result['clean'] is False
