"""v0.3 WP-H, fixes found by the agent acceptance runs (docs/acceptance/runs/, v0.3).

* the variant comparison an evaluation stores (``model_selection``, ADR 0007) is citable
  with its metric's words: an agent relaying "-0.009 of AUC per fold" (smoke run S14 on
  Hotel, French) was refused because the AUC word bound the number to ``roc_auc`` paths,
  which the selection's paths do not contain (the metric is a field).
"""
from __future__ import annotations

from mlkit.study import numtrace

RID = 'f6' * 32


def _view():
    selection = {
        'available': True, 'metric': 'roc_auc', 'direction': 'higher', 'folds': 5,
        'configurations': [
            {'slot': 'fit.logistic', 'kind': 'candidate', 'mean': 0.7848410697618815,
             'se': 0.010433388542810207, 'difference': None},
            {'slot': 'fit.variant', 'kind': 'tuned', 'mean': 0.7758519093223641,
             'se': 0.013804277102977614,
             'difference': {'against': 'fit.logistic', 'mean': -0.008989160439517275,
                            'se': 0.005080845700912673, 'low': -0.014070006140429948,
                            'high': -0.0039083147386046015}}]}
    return {'results': {'policy.evaluation': {
                'result_id': RID, 'n_rows': 32049, 'current': True, 'integrity': 'ok',
                'activity': 'policy.evaluation', 'params': {},
                'values': {'rules': {}, 'model_selection': selection}}},
            'decisions': {}, 'open_proposals': [], 'settings': {}, 'dataset': {},
            'facts': {'by_status': {}}, 'plan': [], 'final_test': {}}


def _check(text):
    findings, traced = numtrace.trace_text(numtrace.Pool(_view()), text, 'text')
    return [f['details']['number'] for f in findings if f['code'] in numtrace.NUMBER_CODES], \
        traced


def test_the_variant_comparison_is_citable_with_its_metric_word():
    # The smoke run's sentence (S14 Hotel fr), verbatim.
    refused, traced = _check("Le modèle ajusté fait un peu moins bien que le modèle logistique "
                             "de départ : -0,009 d'AUC en moyenne par pli, de -0,014 à -0,004.")
    assert refused == []
    assert [t['path'] for t in traced] == [
        'model_selection.configurations.1.difference.mean',
        'model_selection.configurations.1.difference.low',
        'model_selection.configurations.1.difference.high']
    refused, _ = _check('The candidate has a mean AUC of 0.785 over the folds.')
    assert refused == []


def test_a_wrong_selection_figure_or_another_metric_is_still_refused():
    assert _check("-0,011 d'AUC en moyenne par pli.")[0] == ['-0,011']
    # The selection is an AUC comparison: a precision word does not reach it.
    assert _check('The variant loses -0.009 of precision per fold.')[0] == ['-0.009']
