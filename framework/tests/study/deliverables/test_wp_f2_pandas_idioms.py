"""WP-F2 (R29): the generated notebook's exploration in pandas idioms, under cross-validation.

On synthetic cases (binary and regression) split into folds, the notebook loads the
development rows once, explores them with the pandas a junior types, and the model cell
exposes ``fold_table``, a per-fold DataFrame asserted against ``cross_validation.per_fold``.
The notebook runs headless (``app.run()`` in a subprocess). Studies live in ``tmp_path``.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from mlkit.study import case as c, code_cells, read, render_notebook as rn

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import flowkit as fk  # noqa: E402


def _cv_study(root: Path, task: str) -> Path:
    case_dir = fk.make_case(root / 'case', task=task, n_rows=600)['case'].parent
    f = fk.Flow(root / 'study', case_dir, prefix='f2')
    f.init()
    f.pauses(split=False)
    f.decide('split', {'method': 'kfold_quantile' if task == 'regression' else 'kfold_stratified',
                       'folds': 5, 'seed': 7})
    f.model_decisions()
    f.run('split')
    case = c.load_case(case_dir, verify_data=False)
    features = [v for v in case.document['variables'] if v['role'] == 'feature']
    for activity in ('eda.target_summary' if task == 'regression' else 'eda.target_rate',
                     'eda.special_values', 'eda.quality', 'eda.correlation'):
        f.run(activity)
    for v in features:
        f.run('eda.distribution', '--column', v['name'])
    f.run('fit.baseline')
    f.run('fit.linear' if task == 'regression' else 'fit.logistic')
    f.call('render', '--study', f.study)
    return f.study


@pytest.fixture(scope='module', params=['binary', 'regression'])
def cv_study(request, tmp_path_factory):
    return request.param, _cv_study(tmp_path_factory.mktemp(f'f2_{request.param}'), request.param)


def test_a_cross_validated_notebook_shows_a_per_fold_dataframe(cv_study):
    task, study = cv_study
    source = (study / rn.GENERATED).read_text(encoding='utf-8')
    assert 'fold_table = pd.DataFrame(fold_rows).set_index("fold")' in source
    assert 'for _item in candidate["cross_validation"]["per_fold"]:' in source
    for idiom in ('development.head()', 'structure.info()', 'structure.describe()',
                  'structure.isna().sum()', 'value_counts(normalize=True', '.plot.hist('):
        assert idiom in source, idiom
    script = (
        'import importlib.util, json\n'
        f'spec = importlib.util.spec_from_file_location("nb", {str(study / rn.GENERATED)!r})\n'
        'nb = importlib.util.module_from_spec(spec); spec.loader.exec_module(nb)\n'
        'outputs, defs = nb.app.run()\n'
        'table = defs["fold_table"]\n'
        'print(json.dumps({"index": [int(i) for i in table.index],\n'
        '                  "rows": [int(r) for r in table["rows"]],\n'
        '                  "columns": list(table.columns)}))\n')
    proc = subprocess.run([sys.executable, '-c', script], cwd=study.parent,
                          env=fk.env(HYPOTRAIL_NOTEBOOK_RECOMPUTE='1'),
                          capture_output=True, text=True, timeout=300, stdin=subprocess.DEVNULL)
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout.strip().splitlines()[-1])
    slot = 'fit.linear' if task == 'regression' else 'fit.logistic'
    per_fold = read.open(study).current(slot)['output']['values']['cross_validation']['per_fold']
    assert out['index'] == [f['fold'] for f in per_fold]
    assert out['rows'] == [f['n_rows'] for f in per_fold]
    assert out['columns'] == ['rows', 'mae' if task == 'regression' else 'auc']


def test_a_changed_per_fold_figure_fails_the_notebook(cv_study, tmp_path):
    _, base = cv_study
    study = fk.clone(base, tmp_path / 'study')
    path = study / rn.GENERATED
    source = path.read_text(encoding='utf-8')
    before = 'assert fold_table.loc[_item["fold"], "rows"] == _item["n_rows"]'
    assert source.count(before) == 1
    path.write_text(source.replace(before, before + ' + 1'), encoding='utf-8')
    proc = subprocess.run([sys.executable, str(path)], cwd=study.parent,
                          env=fk.env(HYPOTRAIL_NOTEBOOK_RECOMPUTE='1'),
                          capture_output=True, text=True, timeout=300, stdin=subprocess.DEVNULL)
    assert proc.returncode != 0 and 'AssertionError' in proc.stderr


# --- the study language ----------------------------------------------------------------------

def test_a_french_study_reads_its_notebook_narrative_in_french(tmp_path):
    """WP-F2 on WP-C: step titles, questions and term names in the study language; the code,
    its asserts, and the texts without a French source are unchanged; ``check`` stays clean."""
    from mlkit.study import junior, state as st, texts
    case_dir = fk.make_case(tmp_path / 'case', task='binary', n_rows=600)['case'].parent
    f = fk.Flow(tmp_path / 'study', case_dir, prefix='fr')
    f.call('init', '--case', case_dir, '--study', f.study, '--lang', 'fr')
    f.pauses()
    f.run('split')
    for activity in ('eda.target_rate', 'eda.special_values', 'eda.quality'):
        f.run(activity)
    f.call('render', '--study', f.study)
    source = (f.study / rn.GENERATED).read_text(encoding='utf-8')
    canonical = {step['id']: step['title'] for step in st.steps('binary')}
    for step in f.view()['plan']:
        localized = junior.step_text(canonical[step['id']], 'fr')
        assert localized in source, step['id']
        assert step['title'] == localized != canonical[step['id']], step['id']
    term = texts.glossary('development_rows')['term_fr']
    assert f'**{term[:1].upper() + term[1:]}.**' in source
    assert rn.RECOMPUTE_NOTE_FR in source and rn.RECOMPUTE_NOTE not in source
    assert 'structure.isna().sum()' in source
    assert f.call('check', '--study', f.study)['findings'] == []
    proc = subprocess.run([sys.executable, str(f.study / rn.GENERATED)], cwd=tmp_path,
                          env=fk.env(), capture_output=True, text=True, timeout=300,
                          stdin=subprocess.DEVNULL)
    assert proc.returncode == 0, proc.stderr


# --- generation helpers ----------------------------------------------------------------------

def test_cell_variable_names_are_unique_identifiers():
    taken: set[str] = set()
    names = [code_cells._ident(col, 'values', taken)
             for col in ('Bounce Rates', 'bounce-rates', '2nd', 'class', 'class')]
    assert names == ['bounce_rates_values', 'bounce_rates_values_2', 'column_2nd_values',
                     'class_values', 'class_values_2']
    assert all(n.isidentifier() for n in names)


@pytest.mark.parametrize('value, expected', [
    (-1, 'train["pdays"] == -1'),
    ('unknown', 'train["pdays"] == "unknown"'),
    ('?', 'train["pdays"].isna()'),          # a value the case reads as missing
])
def test_a_special_value_mask_reads_as_the_engine_matches(value, expected):
    assert code_cells._special_mask('train', 'pdays', value, ('?',)) == expected
