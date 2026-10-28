"""Owner session 2026-10-26, lot L8 (R6, D7): the junior groups rare categories per column.

``rare_category_min_rows`` is one integer for every categorical feature (as before) or a
mapping ``{column: min_rows}``, like ``missing`` (CLI-CONTRACT §11.3). The decision accepts the
mapping and refuses a key that is not a categorical feature; every text that says the
preparation says it per column (``view``, the report in English and French, the training-mode
concept map, the partial refusal of a reply); the generated notebook recomputes the grouping
column by column and checks it against the engine's inputs. The fit, the recipe (operation
version 2) and the runtime are in ``libraries/test_rare_per_column_runtime.py``.
"""
from __future__ import annotations

import pytest

from mlkit.study import (case as c, cli, cmd_check, concepts, confirm as cf, governance, read,
                         render_html, render_notebook as rn, texts, view as view_mod)

from flowkit import Flow
from test_review_round3_engine import _run_notebook

PER_COLUMN = {'last_lapse_reason': 50, 'last_reminder_weekday': 70}
VALUE = {**governance.DEFAULT_PREPROCESSING, 'rare_category_min_rows': PER_COLUMN}


@pytest.mark.parametrize('rare', [0, 30, {}, {'last_lapse_reason': 50},
                                  {'home_branch': 0, 'last_reminder_weekday': 70}])
def test_an_integer_or_a_mapping_of_categorical_features_is_accepted(synthetic_case_dir, rare):
    case = c.load_case(synthetic_case_dir)
    governance.check_preprocessing({**governance.DEFAULT_PREPROCESSING,
                                    'rare_category_min_rows': rare}, case)


@pytest.mark.parametrize('rare, detail', [
    ({'membership_days': 30}, 'not_categorical'),     # a numeric feature
    ({'outcome': 30}, 'not_categorical'),             # the target
    ({'no_such_column': 30}, 'not_categorical'),
    ({'last_lapse_reason': -1}, 'invalid'),
    ({'last_lapse_reason': True}, 'invalid'),
    ({'last_lapse_reason': 2.5}, 'invalid'),
    (-1, None), (True, None), ('30', None), ([30], None),
])
def test_a_value_that_does_not_fit_the_case_is_refused(synthetic_case_dir, rare, detail):
    case = c.load_case(synthetic_case_dir)
    with pytest.raises(governance.ValueProblem) as e:
        governance.check_preprocessing({**governance.DEFAULT_PREPROCESSING,
                                        'rare_category_min_rows': rare}, case)
    assert e.value.details['field'] == 'rare_category_min_rows'
    if detail is not None:
        assert e.value.details[detail]
        assert 'last_lapse_reason' in e.value.details['categorical_features']
        assert 'membership_days' not in e.value.details['categorical_features']


def test_the_helpers_read_both_forms():
    assert governance.rare_min_rows({'rare_category_min_rows': 30}, 'x') == 30
    assert governance.rare_min_rows(VALUE, 'last_lapse_reason') == 50
    assert governance.rare_min_rows(VALUE, 'home_branch') == 0
    assert governance.rare_grouping(VALUE) and governance.rare_grouping({
        'rare_category_min_rows': 1})
    for value in (0, {}, {'home_branch': 0}):
        assert not governance.rare_grouping({'rare_category_min_rows': value})


def test_every_text_says_the_grouping_per_column():
    assert view_mod.preprocessing_words(VALUE) == (
        'categories of last_lapse_reason with fewer than 50 training rows grouped; categories '
        'of last_reminder_weekday with fewer than 70 training rows grouped')
    assert view_mod.preprocessing_words({**VALUE, 'rare_category_min_rows': 30}) == \
        'categories with fewer than 30 training rows grouped'
    assert render_html.value_words('preprocessing', VALUE, 'binary') == (
        'Preparation: categories of last_lapse_reason with fewer than 50 training rows '
        'grouped; categories of last_reminder_weekday with fewer than 70 training rows grouped')
    with texts.report_language_context('fr'):
        assert render_html.value_words('preprocessing', VALUE, 'binary') == (
            "Préparation : les catégories de last_lapse_reason de moins de 50 lignes "
            "d'entraînement regroupées ; les catégories de last_reminder_weekday de moins de "
            "70 lignes d'entraînement regroupées")
    # The integer keeps its words in both languages.
    assert render_html.value_words('preprocessing', {**VALUE, 'rare_category_min_rows': 30},
                                   'binary') == ('Preparation: categories with fewer than 30 '
                                                 'training rows grouped')
    # A mapping that groups nothing is the default preparation.
    assert render_html.value_words('preprocessing', {**VALUE, 'rare_category_min_rows': {
        'home_branch': 0}}, 'binary').startswith('Default preparation')


def test_the_concepts_and_the_partial_refusal_read_the_mapping():
    state = {'task': 'binary'}
    prop = {'decision_id': 'preprocessing', 'value': VALUE,
            'restatement': 'You group the rare categories of last_lapse_reason and '
                           'last_reminder_weekday.'}
    names = [i['concept'] for i in concepts.concept_map(state, prop)]
    assert names == ['rare_categories']
    none = {**prop, 'value': {**VALUE, 'rare_category_min_rows': {'home_branch': 0}}}
    assert [i['concept'] for i in concepts.concept_map(state, none)] == ['no_preprocessing']
    # "Not for last_reminder_weekday" refuses a column the value groups; "no grouping" refuses
    # the step; a value that groups nothing agrees with "no grouping".
    assert cf.partial_refusal('yes, except last_reminder_weekday', prop) == {
        'negator': 'except', 'part': 'last_reminder_weekday'}
    assert cf.partial_refusal('oui, sans regroupement', prop) is not None
    assert cf.partial_refusal('oui, sans regroupement', none) is None


@pytest.fixture(scope='module')
def grouped(tmp_path_factory, synthetic_case_dir):
    """A holdout binary study whose preparation groups two columns, each with its own
    minimum, fitted and rendered."""
    flow = Flow(tmp_path_factory.mktemp('rare') / 'study', synthetic_case_dir, prefix='r')
    flow.init()
    flow.pauses(model_decisions=False)
    flow.model_decisions(preprocessing=VALUE)
    flow.run('split')
    flow.run('fit.baseline')
    flow.run('fit.logistic')
    assert cli.run(['render', '--study', str(flow.study)]).exit_code == 0
    return flow


def test_the_decision_records_the_mapping_and_the_fit_applies_it(grouped):
    s = read.open(grouped.study)
    decision = s.state['decisions']['preprocessing']
    assert decision['status'] == 'confirmed'
    assert decision['value']['rare_category_min_rows'] == PER_COLUMN
    values = s.current('fit.logistic')['output']['values']['preprocessing']
    assert values['value']['rare_category_min_rows'] == PER_COLUMN
    assert set(values['fitted']['rare_categories']) == set(PER_COLUMN)
    assert values['fitted']['ignored'] == []


def test_the_notebook_recomputes_the_grouping_column_by_column(grouped):
    source = (grouped.study / rn.GENERATED).read_text(encoding='utf-8')
    assert ('# Categories of last_lapse_reason with fewer than 50 training rows are grouped'
            in source)
    assert ('# Categories of last_reminder_weekday with fewer than 70 training rows are '
            'grouped' in source)
    assert '_kept = set(_counts[_counts >= 50].index)' in source
    assert '_kept = set(_counts[_counts >= 70].index)' in source
    assert 'Categories of home_branch' not in source
    # Headless run: the readable steps equal the engine's inputs (assert_frame_equal in the
    # cell) and the recomputed AUC is the registry's.
    out = _run_notebook(grouped.study / rn.GENERATED, grouped.study.parent)
    auc = read.open(grouped.study).current('fit.logistic')['output']['values'][
        'validation']['roc_auc']
    assert abs(out['validation_auc'] - auc) < 1e-6


def test_the_report_says_the_grouping_per_column_and_passes_check(grouped):
    reports = [p for p in grouped.study.rglob('*.html') if '.hypotrail' not in p.parts]
    assert reports
    text = '\n'.join(p.read_text(encoding='utf-8') for p in reports)
    assert 'categories of last_lapse_reason with fewer than 50 training rows grouped' in text
    result = cmd_check.run_check(grouped.study)
    assert not [f for f in result['findings'] if f['severity'] == 'error'], result['findings']
