"""The success criterion as a metric and a minimum (v0.3, WP-C; remarks R18 and R19).

``governance`` (whose source is part of every fit's code fingerprint, so editing it would
make the results of existing studies stale) keeps the v0.2 rules: a binary criterion
``{"metric": "precision_gain", "min_points": p}``, a regression one ``{"metric":
"mae_reduction", "min_share": f}``. This module widens them without touching the fits:

* :data:`METRICS_BY_TASK`: a binary criterion may also name ``recall_gain``, the recall of
  the chosen model minus the baseline's at the adopted rule, in points. With a fixed number
  of rows acted on (a capacity or a share), precision = TP / k and recall = TP / P both move
  with the true positives only, so the two metrics (and the lift) rank configurations
  identically; with a threshold they differ, and the junior chooses;
* :func:`check` validates a value (``governance.ValueProblem``);
* :func:`assess` is ``governance.assess`` with the metric the value names: for
  ``recall_gain`` the gain, its paired interval and the status are read from the recall
  deltas the policy evaluation (and the final-test evaluation) already store;
* :func:`options` is the ``next_action.criterion_options`` payload: the metric options in
  words, the default by action type, the reference value (the base rate of the development
  rows, read from the split result: the stratification already read it) and an illustrative
  translation of candidate minimums per 1,000 actions on the development rows.

AUC and average precision (AP) judge the ranking over every cut-off: they are diagnostics,
never a business criterion. An expected value needs a cost and a value per action; no case
declares them, so it is listed as not available. Every value recorded before v0.3 names a
metric of :data:`METRICS_BY_TASK` and stays valid as it is.

Pure: no file, no pandas, numpy, or scikit-learn.
"""
from __future__ import annotations

import copy
from typing import Any, Callable, Mapping

from . import governance

BINARY, REGRESSION = 'binary', 'regression'
EN, FR = 'en', 'fr'
# R46 (owner batch of 2026-10-28): a regression criterion names its metric too, MAE (the
# default) or RMSE; ``rmse_reduction`` reads the RMSE the evaluations already store (their
# ``models.<slot>.rmse`` and paired ``deltas.<slot>.rmse``), so no fit changes.
METRICS_BY_TASK = {BINARY: ('precision_gain', 'recall_gain'),
                   REGRESSION: ('mae_reduction', 'rmse_reduction')}
DEFAULT_METRIC = dict(governance.CRITERION_METRICS)
# The policy evaluation's metric each binary criterion metric reads.
DELTA_METRIC = {'precision_gain': 'precision', 'recall_gain': 'recall'}
# The error each regression criterion metric reads (the evaluations' keys).
ERROR_METRIC = {'mae_reduction': 'mae', 'rmse_reduction': 'rmse'}
# Lot 2026-10-28 (EN-9): the criterion metric of a confirmed error measure.
REDUCTION_OF_ERROR = {v: k for k, v in ERROR_METRIC.items()}
# R67 (owner validation of 2026-10-28): the optional business bar of a regression criterion,
# an absolute error in the unit of the target on the criterion's measure.
BUSINESS_KEY = 'business_max_error'
# Candidate minimums shown as options (the junior may give any other).
CANDIDATE_POINTS = (2, 5, 10)
CANDIDATE_SHARES = (0.05, 0.1, 0.2)
SCALE = 1000
OPTIONS_KEYS = ('task', 'action', 'default_metric', 'metrics', 'not_criteria', 'equivalence',
                'reference', 'candidates', 'scale', 'illustrative', 'text')
METRIC_KEYS = ('metric', 'value_key', 'unit', 'default', 'term', 'explanation')


def _t(lang: str, en: str, fr: str) -> str:
    return fr if lang == FR else en


def _num(x: float, lang: str, digits: int = 1) -> str:
    text = f'{x:.{digits}f}'
    return text.replace('.', ',') if lang == FR else text


def _int(n: int, lang: str) -> str:
    text = f'{n:,}'
    return text.replace(',', ' ') if lang == FR else text


# --- validation and assessment -------------------------------------------------------------

def check(value: Any, task: str) -> None:
    """Refuse a criterion value that does not fit the task (``governance.ValueProblem``).
    R67: a regression value may add ``business_max_error``, a positive number (the business
    bar, in the unit of the target); the rest is checked as before."""
    if task == REGRESSION and isinstance(value, Mapping) and BUSINESS_KEY in value:
        bar = value[BUSINESS_KEY]
        if isinstance(bar, bool) or not isinstance(bar, (int, float)) or not bar > 0:
            raise governance.ValueProblem(f'{BUSINESS_KEY} is a positive error in the unit of '
                                          'the target.', field=BUSINESS_KEY)
        value = {k: v for k, v in value.items() if k != BUSINESS_KEY}
    if task == BINARY and isinstance(value, Mapping) and value.get('metric') == 'recall_gain':
        governance.check_criterion(dict(value, metric='precision_gain'), task)
        return
    if task == REGRESSION and isinstance(value, Mapping) \
            and value.get('metric') == 'rmse_reduction':
        if 'selection' in value or 'decision_rule' in value:
            # A review-v1 criterion selects on the row-weighted MAE only (``objective``).
            raise governance.ValueProblem(
                'rmse_reduction is not available with a review-v1 criterion: its selection '
                'is the row-weighted MAE.', metrics=['mae_reduction'])
        governance.check_criterion(dict(value, metric='mae_reduction'), task)
        return
    try:
        governance.check_criterion(value, task)
    except governance.ValueProblem as exc:
        if task == BINARY:
            raise governance.ValueProblem(
                'success_criterion is {"metric": "precision_gain" | "recall_gain", '
                '"min_points": p}: the minimum gain of that metric over the baseline at the '
                'adopted rule, in percentage points.', **dict(exc.details,
                                                             metrics=list(METRICS_BY_TASK[task])))
        raise governance.ValueProblem(exc.message, **dict(exc.details,
                                                          metrics=list(METRICS_BY_TASK[task])))


def assess(view: Mapping, canonical: Callable[[str], str] = lambda r: r) -> dict | None:
    """``governance.assess`` with the metric the confirmed value names. For ``recall_gain``
    the development gain is the recall delta of the same rule and model, and the final-test
    criterion is read from the recall delta of the final evaluation."""
    out = _assess(view, canonical)
    if out is not None:
        business = business_level(out, view)
        if business is not None:
            out['business'] = business
    return out


def business_level(out: Mapping, view: Mapping) -> dict | None:
    """R67 (owner validation of 2026-10-28): the second level of a regression criterion that
    names a business bar (``business_max_error``), fixed before any model with the minimum
    gain: the chosen model's error on the criterion's measure against that absolute bar, on
    the development evidence (``evaluate.regression``) and on the opened final test
    (``final_test.evaluation``), each read from registered values. None for a criterion
    without a bar (one level, as before)."""
    value = out.get('value')
    if not isinstance(value, Mapping) or not isinstance(value.get(BUSINESS_KEY), (int, float)):
        return None
    bar = float(value[BUSINESS_KEY])
    error = ERROR_METRIC.get(value.get('metric'), 'mae')
    results = view.get('results') or {}

    def level(slot: str, model) -> dict | None:
        item = results.get(slot)
        if not governance._citable(item) or not model:
            return None
        mine = ((item['values'].get('models') or {}).get(model) or {}).get(error)
        if not isinstance(mine, (int, float)):
            return None
        return {'model': model, 'value': mine, 'met': mine <= bar + 1e-12,
                'result_id': item['result_id'], 'path': f'models.[{model}].{error}'}

    development = level('evaluate.regression', out.get('model'))
    final_item = results.get('final_test.evaluation')
    final_model = ((final_item or {}).get('values') or {}).get('model') \
        if isinstance(final_item, Mapping) else None
    final = level('final_test.evaluation', final_model)
    judged = final if final is not None else development
    return {'max_error': bar, 'measure': error, 'development': development,
            'final_test': final,
            'judged_on': 'final_test' if final is not None else 'development',
            'met': judged['met'] if judged is not None else None}


def _assess(view: Mapping, canonical: Callable[[str], str]) -> dict | None:
    out = governance.assess(view, canonical)
    if out is None:
        return None
    value = out.get('value')
    metric = value.get('metric') if isinstance(value, Mapping) else None
    if metric == 'rmse_reduction':
        return _assess_rmse(out, view, canonical)
    if metric not in DELTA_METRIC or metric == 'precision_gain':
        return _review_assessment(out, results=view.get('results') or {})
    out['metric'] = metric
    results = view.get('results') or {}
    out.update(gain=None, low=None, high=None, interval_includes_zero=None,
               status='not_assessed')
    item = results.get('policy.evaluation')
    if governance._citable(item) and out.get('rule'):
        rules = item['values'].get('rules') or {}
        raw = next((r for r in rules if canonical(r) == out['rule']), None)
        delta = (((rules.get(raw) or {}).get('deltas') or {}).get(out.get('model')) or {}) \
            .get(DELTA_METRIC[metric]) if raw is not None else None
        if isinstance(delta, Mapping) and isinstance(delta.get('point'), (int, float)):
            out.update(gain=100 * delta['point'],
                       low=100 * delta['low'] if delta.get('low') is not None else None,
                       high=100 * delta['high'] if delta.get('high') is not None else None)
    else:
        out.update(result_id=None)
    if out['gain'] is not None:
        out['status'], out['interval_includes_zero'] = _status(out['gain'], out['low'],
                                                               out['high'], out['minimum'])
    final = _final(results, metric)
    out['final_test'] = final if isinstance(value, Mapping) else None
    judged_on, judged = 'development', out['status']
    if final and final.get('status') and governance._same_configuration(results, out,
                                                                        canonical):
        judged_on, judged = 'final_test', final['status']
    out['judged_on'], out['judged_status'] = judged_on, judged
    out['contradicts_verdict'] = out.get('verdict') in governance.ADOPT_VERDICTS \
        and judged in ('not_met', 'uncertain')
    return _review_assessment(out, results=results)


def error_gain(values: Mapping, model: str | None, error: str = 'mae'
               ) -> tuple[float, float | None, float | None] | None:
    """``(gain, low, high)``: the share of the baseline's ``error`` (``mae`` or ``rmse``)
    that ``model`` removes, with its paired interval, from an evaluation's stored
    ``models.fit.baseline.<error>`` and ``deltas.<model>.<error>``; None when absent."""
    base = ((values.get('models') or {}).get('fit.baseline') or {}).get(error)
    delta = ((values.get('deltas') or {}).get(model) or {}).get(error) if model else None
    if not isinstance(base, (int, float)) or base <= 0 or not isinstance(delta, Mapping) \
            or not isinstance(delta.get('point'), (int, float)):
        return None
    low = -delta['high'] / base if isinstance(delta.get('high'), (int, float)) else None
    high = -delta['low'] / base if isinstance(delta.get('low'), (int, float)) else None
    return -delta['point'] / base, low, high


def _assess_rmse(out: dict, view: Mapping, canonical: Callable[[str], str]) -> dict:
    """R46: a regression criterion on the RMSE, judged as the MAE one is (development
    evidence, then the opened final test), from the RMSE the evaluations store."""
    results = view.get('results') or {}
    value = out['value']
    out.update(metric='rmse_reduction', gain=None, low=None, high=None,
               interval_includes_zero=None, status='not_assessed', result_id=None)
    item = results.get('evaluate.regression')
    model = out.get('model') or governance._regression_model(view.get('decisions') or {},
                                                             view.get('open_proposals') or [])
    found = error_gain(item['values'], model, 'rmse') if governance._citable(item) else None
    if found is not None:
        out.update(result_id=item['result_id'], model=model, minimum=value['min_share'])
        out['gain'], out['low'], out['high'] = found
        out['status'], out['interval_includes_zero'] = _status(out['gain'], out['low'],
                                                               out['high'], out['minimum'])
    final = None
    item = results.get('final_test.evaluation')
    if governance._citable(item):
        vals = item['values']
        found = error_gain(vals, vals.get('model'), 'rmse')
        if found is not None:
            status, includes = _status(*found, value['min_share'])
            final = {k: None for k in governance.FINAL_CRITERION_KEYS}
            final.update(status=status, gain=found[0], low=found[1], high=found[2],
                         minimum=value['min_share'], unit='share',
                         interval_includes_zero=includes, result_id=item['result_id'])
    out['final_test'] = final
    judged_on, judged = 'development', out['status']
    if final and governance._same_configuration(results, out, canonical):
        judged_on, judged = 'final_test', final['status']
    out['judged_on'], out['judged_status'] = judged_on, judged
    out['contradicts_verdict'] = out.get('verdict') in governance.ADOPT_VERDICTS \
        and judged in ('not_met', 'uncertain')
    return out


def confirmed_metric(state: Mapping) -> str | None:
    """The metric of the study's success criterion when it is held (confirmed or awaiting
    reconfirmation), else None."""
    decision = (state.get('decisions') or {}).get('success_criterion') or {}
    value = decision.get('value')
    if decision.get('status') in ('confirmed', 'reconfirm_required') \
            and isinstance(value, Mapping):
        return value.get('metric')
    return None


def selection(results: Mapping, state: Mapping, task: str) -> dict:
    """``model_selection`` (``trials.selection``) on the error the confirmed criterion names
    (R46): the stored one-standard-error selection of the evaluation for the MAE (unchanged),
    or the same selection recomputed on the per-fold RMSE of the fits for ``rmse_reduction``,
    through ``trials.select``'s declared-objective path (the fits store both errors per
    fold)."""
    from . import trials as tr
    if task != REGRESSION or confirmed_metric(state) != 'rmse_reduction':
        return tr.selection(results, state, task)
    variants = tr.variants_of(tr.confirmed_value(state))
    fits, objectives = {}, {}
    for slot in ['fit.linear'] + list(tr.VARIANT_SLOTS[:len(variants)]):
        item = results.get(slot) or {}
        if not (item.get('current') and isinstance(item.get('values'), Mapping)):
            continue
        fits[slot] = item['values']
        folds = ((item['values'].get('cross_validation') or {}).get('per_fold')) or []
        per = [f.get('rmse') for f in folds]
        if per and all(isinstance(v, (int, float)) for v in per):
            objectives[slot] = {'metric': 'rmse', 'direction': 'minimize',
                                'per_window': [{'rmse': float(v)} for v in per],
                                'point': sum(per) / len(per)}
    if not objectives:
        return tr.selection(results, state, task)
    return tr.select(fits, variants, task, tr.budget(state), state.get('language', 'en'),
                     objectives=objectives)


def _review_assessment(out: dict, *, results: Mapping) -> dict:
    """Attach J3's centralized truth-table fields to a new-profile criterion."""
    value = out.get('value')
    if not isinstance(value, Mapping) or 'decision_rule' not in value:
        return out
    from . import objective
    judged = out.get('final_test') if out.get('judged_on') == 'final_test' else out
    result_slot = ('final_test.evaluation' if out.get('judged_on') == 'final_test'
                   else 'policy.evaluation')
    item = results.get(result_slot) or {}
    uncertainty = ((item.get('values') or {}).get('uncertainty') or {})
    qualified = bool(uncertainty.get('eligible'))
    assessment = objective.assess(judged.get('gain'), judged.get('minimum'),
                                  decision_rule=value['decision_rule'],
                                  low=judged.get('low'), high=judged.get('high'),
                                  interval_qualified=qualified,
                                  uncertainty_status=('available' if qualified else
                                                      'unavailable'))
    out.update(assessment)
    out['status'] = assessment['decision_status']
    out['judged_status'] = assessment['decision_status']
    return out


def _status(gain, low, high, minimum) -> tuple[str, bool | None]:
    """As ``fit.criterion_status`` (kept apart: this module stays free of numpy)."""
    if gain is None or minimum is None:
        return 'not_assessed', None
    includes = low is not None and high is not None and low <= 0 <= high
    if gain < minimum - 1e-12:
        return 'not_met', includes
    return ('uncertain' if includes else 'met'), includes


def _final(results: Mapping, metric: str) -> dict | None:
    item = results.get('final_test.evaluation')
    if not governance._citable(item):
        return None
    values = item['values']
    crit = values.get('criterion') if isinstance(values.get('criterion'), Mapping) else {}
    delta = ((values.get('deltas') or {}).get(values.get('model')) or {}).get(
        DELTA_METRIC[metric])
    if not isinstance(delta, Mapping) or not isinstance(delta.get('point'), (int, float)):
        return None
    gain = 100 * delta['point']
    low = 100 * delta['low'] if delta.get('low') is not None else None
    high = 100 * delta['high'] if delta.get('high') is not None else None
    status, includes = _status(gain, low, high, crit.get('minimum'))
    return {'status': status, 'gain': gain, 'low': low, 'high': high,
            'minimum': crit.get('minimum'), 'unit': 'percentage points',
            'interval_includes_zero': includes, 'result_id': item['result_id']}


# --- words ---------------------------------------------------------------------------------

def value_words(value: Any, lang: str = EN, cv: bool = False,
                judged_on: str | None = None) -> str | None:
    """A criterion value in words, naming its metric (a value recorded before v0.3 reads
    the same way: its metric is named). ``judged_on`` ``final_test`` (R48): the error is
    the one on the final test, never "the validation error"."""
    if not isinstance(value, Mapping):
        return None
    metric = value.get('metric')
    if metric in DELTA_METRIC and isinstance(value.get('min_points'), (int, float)):
        name = {'precision_gain': _t(lang, 'precision', 'précision'),
                'recall_gain': _t(lang, 'recall', 'rappel')}[metric]
        points = _num(float(value['min_points']), lang, 1).rstrip('0').rstrip('.,')
        return _t(lang, f'{name} gain over the baseline of at least {points} points',
                  f'gain de {name} sur le modèle de référence d\'au moins {points} points')
    if metric == 'mae_reduction' and isinstance(value.get('min_share'), (int, float)) \
            and judged_on != 'final_test':
        pct = round(100 * value['min_share'])
        error = (_t(lang, 'out-of-fold error', 'erreur hors pli') if cv
                 else _t(lang, 'validation error', 'erreur de validation'))
        # CLI-CONTRACT §17.6 (R48): the reference of a regression is "reference (predict the mean)".
        return _t(lang, f'{error} at least {pct}% below the reference (predict the mean)',
                  f'{error} au moins {pct} % sous celle de la référence (prédire la moyenne)')
    if metric in ERROR_METRIC and isinstance(value.get('min_share'), (int, float)):
        # R46, R48: the RMSE criterion, and either criterion judged on the final test; the
        # reference is named "reference (predict the mean)".
        pct = round(100 * value['min_share'])
        name = 'MAE' if metric == 'mae_reduction' else 'RMSE'
        if judged_on == 'final_test':
            error = _t(lang, f'error ({name}) on the final test',
                       f'erreur ({name}) sur le test final')
        else:
            error = (_t(lang, f'out-of-fold error ({name})', f'erreur hors pli ({name})') if cv
                     else _t(lang, f'validation error ({name})', f'erreur de validation ({name})'))
        words = _t(lang, f'{error} at least {pct}% below the reference (predict the mean)',
                   f'{error} au moins {pct} % sous celle de la référence (prédire la moyenne)')
        bar = value.get(BUSINESS_KEY)
        if isinstance(bar, (int, float)) and not isinstance(bar, bool):
            # R67: the business bar, the second level.
            from .cite import format_value
            words += _t(lang, f', and at most {format_value(bar, "f1", "en")} (business bar)',
                        f', et au plus {format_value(bar, "f1", "fr")} (barre métier)')
        return words
    return None


# --- the options of the criterion question (R18, R19) -------------------------------------

def action_of(view: Mapping) -> str:
    """The action type the criterion is fixed for: ``share`` (the case's scenario share),
    ``capacity``, ``threshold`` (from the adopted or proposed policy), or ``not_decided``."""
    decisions = view.get('decisions') or {}
    candidates = [(decisions.get('policy') or {}).get('value')]
    candidates += [p.get('value') for p in view.get('open_proposals') or []
                   if p.get('decision_id') == 'policy']
    for c in candidates:
        if isinstance(c, str):
            kind = c.split('@')[0].partition(':')[0]
            if kind in ('share', 'capacity', 'threshold'):
                return kind
    share = ((view.get('scenario_defaults') or {}).get('capacity_share') or {})
    if isinstance(share, Mapping) and share.get('value') is not None:
        return 'share'
    return 'not_decided'


def _scenario_share(view: Mapping) -> float | None:
    share = ((view.get('scenario_defaults') or {}).get('capacity_share') or {})
    value = share.get('value') if isinstance(share, Mapping) else None
    return float(value) if isinstance(value, (int, float)) else None


def _reference(view: Mapping, lang: str, cv: bool) -> dict | None:
    """The base rate of the development rows (cross-validation) or of the training rows,
    from the current split result (its stratification read the target)."""
    item = (view.get('results') or {}).get('split')
    if not governance._citable(item):
        return None
    part = ((item['values'].get('partitions') or {}).get('train') or {})
    rate, n = part.get('rate'), part.get('n_rows')
    if not isinstance(rate, (int, float)) or not isinstance(n, int):
        return None
    pct = _num(100 * rate, lang)
    rows = (_t(lang, 'development rows', "lignes de l'échantillon de développement") if cv
            else _t(lang, 'training rows', "lignes du jeu d'entraînement"))
    return {'what': 'base_rate', 'value': rate, 'percent': round(100 * rate, 1), 'n_rows': n,
            'rows': 'development' if cv else 'training', 'result_id': item['result_id'],
            'text': _t(lang, f'Without a model, {pct}% of the {_int(n, lang)} {rows} are '
                             f'positive: acting on rows at random finds positives at that rate.',
                       f'Sans modèle, {pct} % des {_int(n, lang)} {rows} sont positives : '
                       f'agir sur des lignes au hasard trouve des positifs à ce taux.')}


def _metric_items(task: str, action: str, lang: str) -> list[dict]:
    if task == REGRESSION:
        # R46: the metric is a decision too: MAE by default (with why), or RMSE.
        return [{'metric': 'mae_reduction', 'value_key': 'min_share', 'unit': 'share',
                 'default': True,
                 'term': _t(lang, 'Mean absolute error (MAE)', 'erreur absolue moyenne (MAE)'),
                 'explanation': _t(
                     lang, 'The average size of an error, in the unit of the target: every '
                           'error weighs the same. The criterion is the share of the '
                           'reference\'s (predict the mean) MAE the model must remove. '
                           'Proposed by default: it reads directly in the unit of the target, '
                           'and a few large errors do not dominate it.',
                     'La taille moyenne d\'une erreur, dans l\'unité de la cible : chaque '
                     'erreur pèse autant. Le critère est la part de la MAE de la référence '
                     '(prédire la moyenne) que le modèle doit retirer. Proposée par défaut : '
                     'elle se lit directement dans l\'unité de la cible, et quelques grosses '
                     'erreurs ne la dominent pas.')},
                {'metric': 'rmse_reduction', 'value_key': 'min_share', 'unit': 'share',
                 'default': False,
                 'term': _t(lang, 'Root mean squared error (RMSE)',
                            'racine de l\'erreur quadratique moyenne (RMSE)'),
                 'explanation': _t(
                     lang, 'Also in the unit of the target, but each error is squared before '
                           'the average, so large errors weigh more. Choose it if one big miss '
                           'is much worse than several small ones.',
                     'Aussi dans l\'unité de la cible, mais chaque erreur est mise au carré '
                     'avant la moyenne : les grosses erreurs pèsent davantage. Choisissez-la '
                     'si une grosse erreur est bien pire que plusieurs petites.')}]
    threshold = action == 'threshold'
    return [
        {'metric': 'precision_gain', 'value_key': 'min_points', 'unit': 'percentage points',
         'default': True,
         'term': _t(lang, 'Precision', 'précision'),
         'explanation': _t(
             lang, 'Among the rows acted on, the share that turn out positive: it counts the '
                   'actions that were not wasted. The gain is read in points over the baseline, '
                   'whose precision is the base rate.',
             'Parmi les lignes sur lesquelles on agit, la part qui se révèle positive : elle '
             'compte les actions qui ne sont pas perdues. Le gain se lit en points au-dessus du '
             'modèle de référence, dont la précision est le taux de base.')},
        {'metric': 'recall_gain', 'value_key': 'min_points', 'unit': 'percentage points',
         'default': False,
         'term': _t(lang, 'Recall', 'rappel'),
         'explanation': _t(
             lang, 'Among all positive rows, the share the rule reaches: it counts the positives '
                   'not missed. ' + ('With a threshold it differs from precision: choose the one '
                                     'that matters more for the action.' if threshold else
                                     'At a fixed number of actions it ranks configurations as '
                                     'precision does.'),
             'Parmi toutes les lignes positives, la part que la règle atteint : il compte les '
             'positifs qu\'on ne manque pas. ' + (
                 'Avec un seuil, il diffère de la précision : choisissez celui qui compte le '
                 'plus pour l\'action.' if threshold else
                 'À nombre d\'actions fixé, il classe les configurations comme la précision.'))},
    ]


def _not_criteria(lang: str, task: str) -> list[dict]:
    out = [{'metric': 'expected_value', 'available': False,
            'why': _t(lang, 'An expected value needs a cost and a value per action; this case '
                            'declares none.',
                      'Une valeur attendue demande un coût et une valeur par action ; ce cas '
                      'n\'en déclare aucun.')}]
    if task == BINARY:
        out += [{'metric': 'auc', 'available': False,
                 'why': _t(lang, 'AUC judges the ranking over every cut-off, not the result of '
                                 'the rule you adopt: a ranking diagnostic, not a business '
                                 'criterion.',
                           "L'AUC juge le classement sur tous les seuils, pas le résultat de la "
                           'règle adoptée : un diagnostic du classement, pas un critère '
                           'métier.')},
                {'metric': 'average_precision', 'available': False,
                 'why': _t(lang, 'Average precision (AP) also judges the whole ranking: a '
                                 'diagnostic, not a business criterion.',
                           "L'average precision (AP, somme pondérée des précisions selon les "
                           'hausses de rappel) juge aussi tout le classement : un diagnostic, '
                           'pas une aire trapézoïdale arbitraire ni un critère métier.')}]
    return out


def _candidates(task: str, reference: dict | None, share: float | None, lang: str,
                unit: str | None) -> list[dict]:
    out = []
    if task == REGRESSION:
        for f in CANDIDATE_SHARES:
            pct = round(100 * f)
            u = f' {unit}' if unit else ''
            out.append({'value': {'metric': 'mae_reduction', 'min_share': f},
                        'per_1000': None,
                        'text': _t(lang, f'{pct}% less error: if the mean baseline errs by E{u} '
                                         f'on average, the model must err by at most '
                                         f'{_num(1 - f, lang, 2)} E{u}.',
                                   f'{pct} % d\'erreur en moins : si la référence (prédire la moyenne) se '
                                   f'trompe de E{u} en moyenne, le modèle doit se tromper d\'au '
                                   f'plus {_num(1 - f, lang, 2)} E{u}.')})
        return out
    rate = reference['value'] if reference else None
    for p in CANDIDATE_POINTS:
        item = {'value': {'metric': 'precision_gain', 'min_points': p}, 'per_1000': None,
                'text': None}
        if rate is not None and rate + p / 100 <= 1:
            base = round(SCALE * rate)
            with_min = round(SCALE * (rate + p / 100))
            item['per_1000'] = {'reference': base, 'with_minimum': with_min,
                                'extra': with_min - base}
            item['text'] = _t(
                lang, f'+{p} points: acting on {_int(SCALE, lang)} rows, the baseline finds '
                      f'about {_int(base, lang)} positives, a model at the minimum about '
                      f'{_int(with_min, lang)}, so about {_int(with_min - base, lang)} more.',
                f'+{p} points : en agissant sur {_int(SCALE, lang)} lignes, le modèle de '
                f'référence trouve environ {_int(base, lang)} positifs, un modèle au minimum '
                f'environ {_int(with_min, lang)}, soit environ {_int(with_min - base, lang)} de '
                f'plus.')
        else:
            item['text'] = _t(lang, f'+{p} points of precision over the baseline.',
                              f'+{p} points de précision au-dessus du modèle de référence.')
        out.append(item)
    return out


# Round 5 (review E, R5E-6): the parts a review-v1 criterion adds to a legacy one
# (``mlkit.study.objective.validate_criterion``). The decision rule compares the point
# estimate with the minimum; the binary selection acts on the scenario's share of the scored
# rows, or on the engine's default share (the share the development diagnostics use) when the
# case assumes none, within each evaluation window, by pooled counts.
REVIEW_DECISION_RULE = 'point_estimate'
REVIEW_DEFAULT_RULE = 'share:0.1'
SELECTION_METRIC = {'precision_gain': 'precision', 'recall_gain': 'recall'}


def review_value(value: Mapping, task: str, share: float | None = None) -> dict:
    """``value`` (a legacy criterion: metric and minimum) completed into a valid review-v1
    criterion: ``decision_rule`` and ``selection``. A value that already has them is
    returned unchanged (a copy)."""
    from . import records as rec
    out = copy.deepcopy(dict(value))
    out.setdefault('decision_rule', REVIEW_DECISION_RULE)
    if 'selection' in out:
        return out
    if task == REGRESSION:
        out['selection'] = {'metric': 'mae', 'rule': None, 'scope': 'evaluation_window',
                            'batch_column': None, 'aggregation': 'row_weighted'}
        return out
    rule = (rec.canonical_rule(f'share:{share}') if share is not None else None) \
        or REVIEW_DEFAULT_RULE
    out['selection'] = {'metric': SELECTION_METRIC.get(out.get('metric'), 'precision'),
                        'rule': rule, 'scope': 'evaluation_window', 'batch_column': None,
                        'aggregation': 'pooled_counts'}
    return out


def options(view: Mapping, lang: str = EN, unit: str | None = None, *,
            measure: str | None = None, business: float | None = None) -> dict:
    """The ``criterion_options`` of ``next_action`` at the success criterion (R18, R19).

    Lot 2026-10-28: ``measure`` is the confirmed error measure of a regression study that
    decides it (EN-9): the metrics are then that measure's only, and every candidate is fixed
    on it. ``business`` (R67) is the default business bar, the current method's error from
    the use-case brief: every candidate then carries it as ``business_max_error``."""
    from . import texts
    task = view.get('task') or BINARY
    cv = texts.scheme_of(view) == texts.CROSS_VALIDATION
    action = action_of(view) if task == BINARY else 'model_choice'
    reference = _reference(view, lang, cv) if task == BINARY else None
    share = _scenario_share(view)
    metrics = _metric_items(task, action, lang)
    default = DEFAULT_METRIC[task]
    if task == BINARY and action == 'threshold':
        # A threshold leaves the number of actions free: precision stays the default, recall
        # is the alternative the junior weighs.
        default = 'precision_gain'
    equivalence = None
    if task == BINARY:
        equivalence = _t(
            lang, 'With a fixed number of rows acted on (a capacity or a share), precision is '
                  'TP/k and recall is TP/P: both move with the true positives only, so '
                  'precision, recall and lift rank configurations identically. With a '
                  'threshold the number acted on changes, and they differ.',
            'Avec un nombre fixé de lignes sur lesquelles on agit (une capacité ou une part), '
            'la précision vaut VP/k et le rappel VP/P : les deux ne bougent qu\'avec les vrais '
            'positifs, donc précision, rappel et lift classent les configurations de la même '
            'façon. Avec un seuil, le nombre d\'actions change et ils diffèrent.')
    candidates = _candidates(task, reference, share, lang, unit)
    if task == REGRESSION and measure in REDUCTION_OF_ERROR:
        default = REDUCTION_OF_ERROR[measure]
        metrics = [m for m in metrics if m['metric'] == default]
        for item in candidates:
            item['value'] = dict(item['value'], metric=default)
    if task == REGRESSION and isinstance(business, (int, float)) and business > 0:
        for item in candidates:
            item['value'] = dict(item['value'], **{BUSINESS_KEY: float(business)})
    if (view.get('assurance') or {}).get('profile') == 'review-v1':
        # Round 5 (review E, R5E-6): under review-v1 a criterion also states its decision
        # rule and the selection it is measured at, so each option is a complete value.
        for item in candidates:
            item['value'] = review_value(item['value'], task, share)
    if task == BINARY:
        illustrative = _t(lang, 'Illustrative, per 1,000 actions, from the development rows; '
                                'the real gain is measured later, out of fold, and on the '
                                'holdout (final test).',
                          'Illustratif, pour 1 000 actions, calculé sur l\'échantillon de '
                          'développement ; le vrai gain se mesure plus tard, hors pli, puis sur '
                          "l'échantillon de test final (holdout).")
        lead = {'share': _t(lang, 'Your action acts on a fixed share of the rows, so the '
                                  'default metric is the precision gain at that share.',
                            "Votre action porte sur une part fixée des lignes : le critère par "
                            'défaut est le gain de précision à cette part.'),
                'capacity': _t(lang, 'Your action acts on a fixed number of rows, so the '
                                     'default metric is the precision gain at that capacity.',
                               "Votre action porte sur un nombre fixé de lignes : le critère par "
                               'défaut est le gain de précision à cette capacité.'),
                'threshold': _t(lang, 'Your action acts on every row above a score threshold: '
                                      'choose precision (fewer wasted actions) or recall (fewer '
                                      'missed positives).',
                                "Votre action porte sur chaque ligne au-dessus d'un seuil de "
                                'score : choisissez la précision (moins d\'actions perdues) ou le '
                                'rappel (moins de positifs manqués).'),
                'not_decided': _t(lang, 'The action type is not decided yet; the default metric '
                                        'is the precision gain, which suits a capacity or a '
                                        'share.',
                                  "Le type d'action n'est pas encore décidé ; le critère par "
                                  'défaut est le gain de précision, adapté à une capacité ou '
                                  'une part.')}[action]
    else:
        illustrative = None
        lead = _t(lang, f'The criterion is a share of the mean baseline\'s mean absolute error, '
                        f'in {unit or "the unit of the target"}; the baseline\'s error is known '
                        f'once the models are fitted.',
                  f'Le critère est une part de l\'erreur absolue moyenne de la moyenne de '
                  f'référence, en {unit or "unité de la cible"} ; l\'erreur de référence est '
                  f'connue une fois les modèles ajustés.')
    out = {'task': task, 'action': action, 'default_metric': default,
           'metrics': [dict(m, default=m['metric'] == default) for m in metrics],
           'not_criteria': _not_criteria(lang, task), 'equivalence': equivalence,
           'reference': reference, 'candidates': candidates,
           'scale': SCALE if task == BINARY else None, 'illustrative': illustrative,
           'text': lead}
    return {k: copy.deepcopy(out[k]) for k in OPTIONS_KEYS}


__all__ = ['METRICS_BY_TASK', 'DEFAULT_METRIC', 'DELTA_METRIC', 'check', 'assess', 'options',
           'value_words', 'action_of']
