"""v0.3 WP-H3: engine fixes from the third agent acceptance round.

* ``check`` reads a French thousands group written with a space ("37 062 lignes") as one
  number, and still refuses an unregistered one.
* The first bound of an interval range (« intervalle de 7,02 % à 7,55 % ») is a value, not
  the interval's level (a WP-J rule read it as a level and refused it).
* The regression success step no longer says "training mean" (« moyenne du jeu
  d'entraînement »): under cross-validation the mean baseline is fitted on the training
  folds.
"""
from __future__ import annotations

from mlkit.study import cite, junior, numtrace
from mlkit.study import state as st


def _item(rid, values, n_rows=37062):
    return {'result_id': rid, 'values': values, 'n_rows': n_rows, 'current': True,
            'integrity': 'ok', 'activity': None, 'params': {}}


def _view():
    return {
        'results': {
            'eda.target_rate': _item('a1' * 32, {
                'n_rows': 37062, 'n_positive': 2697, 'rate': 0.07277,
                'interval': {'low': 0.07020, 'high': 0.07548, 'level': 0.95}}),
            'eda.special_values': _item('b2' * 32, {'n_rows': 37062, 'special_values': [
                {'column': 'pdays', 'value': -1, 'n_rows': 32818, 'n_positive': 2266,
                 'rate': 0.069047, 'interval': {'low': 0.066355, 'high': 0.071841,
                                                'level': 0.95}}]}),
            'split': _item('c3' * 32, {'n_development': 37062, 'n_final_test': 8149}),
        },
        'decisions': {}, 'open_proposals': [], 'settings': {'bootstrap': {'level': 0.95}},
        'dataset': {}, 'facts': {'by_status': {}}, 'plan': [], 'final_test': {}}


def _refused(text):
    findings, _ = numtrace.trace_text(numtrace.Pool(_view()), text, 'text')
    return [f['details']['number'] for f in findings if f['code'] in numtrace.NUMBER_CODES]


def test_a_french_thousands_group_is_one_number():
    tokens = [(t.text, t.value, t.decimals) for t in cite.parse_numbers(
        "L'échantillon de développement (37 062 lignes) ; le test final, 8 149 lignes ; "
        '12 345,5 mpg.')]
    assert tokens == [('37 062', 37062.0, 0), ('8 149', 8149.0, 0),
                      ('12 345,5', 12345.5, 1)]
    # At the end of a sentence (S14 Bank full fr, round-3 re-run: « il en compte 37 062. »).
    assert [(t.text, t.value) for t in cite.parse_numbers('Il en compte 37 062. Ensuite')] == \
        [('37 062', 37062.0)]
    # Not a group: one to three digits then a space and three digits only.
    assert [t.text for t in cite.parse_numbers('en 5 plis, de 2 à 3, 1 2345')] == \
        ['5', '2', '3', '1', '2345']
    # The English forms are unchanged.
    assert [(t.text, t.value) for t in cite.parse_numbers('3,164 rows, 1,234.5 and 0,115')] == \
        [('3,164', 3164.0), ('1,234.5', 1234.5), ('0,115', 0.115)]


def test_check_traces_french_grouped_counts_and_refuses_others():
    # S14 Bank full fr round 3.
    assert _refused("L'échantillon de développement (37 062 lignes) est découpé en plis.") == []
    assert _refused("L'échantillon de développement en compte 37 062.") == []
    assert _refused('Parmi les 32 818 lignes où pdays vaut -1, 2 266 sont positives.') == []
    assert _refused("L'échantillon de développement compte 37 063 lignes.") == ['37 063']
    # Before WP-H3 the group read as two numbers, "37" and "062".
    assert '37' not in _refused("L'échantillon de développement (37 062 lignes).")


def test_the_first_bound_of_an_interval_range_is_a_value_not_a_level():
    # S14 Bank full fr round 3: the lower bounds were refused as interval levels.
    assert _refused('2697 des 37062 lignes, soit 7,3 % (intervalle de 7,02 % à 7,55 %).') == []
    assert _refused('Parmi ces lignes, le taux de positifs est de 6,9 % (intervalle de '
                    '6,64 % à 7,18 %).') == []
    assert _refused('The rate is 7.3% (interval of 7.02% to 7.55%).') == []
    # A bound that is not registered is still refused, and a level is still a level.
    assert _refused('Le taux est de 7,3 % (intervalle de 6,80 % à 7,55 %).') == ['6,80 %']
    assert _refused('Le taux est de 7,3 %, intervalle de confiance à 95 %.') == []
    assert _refused('Le taux est de 7,3 %, intervalle de confiance à 90 %.') == ['90 %']


def test_the_regression_success_step_names_the_glossary_partitions():
    """S14 Auto MPG fr (rounds 1-3): the agent paraphrased "the rows it is fitted on" as « ses
    lignes d'entraînement ». The step now names the glossary's partitions: the training
    folds under cross-validation, the training set otherwise, in English and French."""
    cv = st.REGRESSION_CV_STEP_TEXTS['success_criterion']['question']
    holdout = st.REGRESSION_SUCCESS_STEP['question']
    cv_fr, holdout_fr = junior.step_text(cv, 'fr'), junior.step_text(holdout, 'fr')
    assert cv_fr != cv and holdout_fr != holdout
    assert 'mean of the training folds' in cv and 'validation fold' in cv
    assert "la moyenne des plis d'entraînement" in cv_fr and 'pli de validation' in cv_fr
    assert 'training set' in holdout and "jeu d'entraînement" in holdout_fr
    for text in (cv, holdout):
        assert 'training mean' not in text and 'training rows' not in text
    for text in (cv_fr, holdout_fr):
        assert "lignes d'entraînement" not in text
        assert "moyenne du jeu d'entraînement" not in text


def test_status_fields_gives_the_views_model_selection_and_families(tmp_path):
    """Round 3: every full study asked ``status --summary --fields model_families,...`` and
    was refused (the two keys live in the full view only). They are now given."""
    import flowkit as fk
    from flowkit import Flow

    case_dir = fk.make_case(tmp_path / 'case', task='binary', n_rows=300)['case'].parent
    flow = Flow(tmp_path / 'study', case_dir)
    flow.call('init', '--case', case_dir, '--study', flow.study)
    out = flow.call('status', '--summary', '--fields', 'model_families,model_selection,trials',
                    '--study', flow.study)
    assert tuple(out) == ('schema', 'ok', 'study', 'revision', 'model_families',
                          'model_selection', 'trials')
    full = flow.call('status', '--study', flow.study)['view']
    assert out['model_families'] == full['model_families']
    assert out['model_selection'] == full['model_selection']
    # Not in the plain summary, and an unknown key is still refused, naming them as allowed.
    assert 'model_families' not in flow.call('status', '--summary', '--study', flow.study)
    bad = flow.call('status', '--summary', '--fields', 'model_family', '--study', flow.study,
                    expect=2)
    assert bad['error']['details']['unknown'] == ['model_family']
    assert 'model_families' in bad['error']['details']['keys']
