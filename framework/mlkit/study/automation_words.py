"""What the automatic mode says while it runs and when it stops (owner session 2026-10-27,
remarks R23 and R24 of the fourth session of 2026-10-26).

R23: ``automation run --progress`` named only the step and a state ("Mode automatique · 3 ·
la disponibilité des variables · proposée", then "… · enregistrée comme automatique"). It now
tells the junior, in the study language and in plain words, what is going on
(:class:`Narrator`, stderr only):

* a short header: the mode, the case, what the run does and where it stops;
* one line per decision, once it is recorded: its value in words and why (the engine's own
  ``recommended.why``, or the fixed rule the mode applies), never raw JSON or an id;
* after each computation, its key result with the registered numbers it rests on (the split's
  folds and rows, the quality check's findings, each model's out-of-fold error, the
  comparison's advice, the diagnostics' flags), formatted as the study language writes them
  (:func:`mlkit.study.cite.format_value`);
* a closing summary: the decisions to review, the model the mode chose and its figure, what
  the junior does next.

:func:`text_summary` is the readable summary ``automation run --format text`` prints on
stdout (and, since R23, ``automation run`` without ``--format``/``--json`` when stdout is a
terminal); the JSON document stays the contract (CLI-CONTRACT §1, §5.5).

R24: :func:`review_restatement` is the quoted block of a review pause (the recorded value in
words), used by :func:`mlkit.study.guidance.pause`.

Nothing here writes to the study or computes a figure: every number is read from a current
result of the view. Nothing here is fingerprinted.
"""
from __future__ import annotations

from typing import Any, Mapping, TextIO

from . import audience, cite
from . import state as st

EN, FR = audience.EN, audience.FR


def _t(lang: str, en: str, fr: str) -> str:
    return fr if lang == FR else en


def _lang(view: Mapping) -> str:
    return FR if (view or {}).get('language') == FR else EN


def _cap(text: str) -> str:
    return text[:1].upper() + text[1:] if text else text


def _low(text: str) -> str:
    """The first letter lowered, unless the word is an acronym ("EBM", "AUC")."""
    if len(text) > 1 and text[:2].isalpha() and text[:2].isupper():
        return text
    return text[:1].lower() + text[1:] if text else text


def _colon(lang: str) -> str:
    return ' : ' if lang == FR else ': '


def _num(value: Any, lang: str, kind: str = 'f2') -> str:
    return cite.format_value(value, kind, lang)


def _int(value: Any, lang: str) -> str:
    return cite.format_value(value, 'int', lang)


def _is_number(value: Any) -> bool:
    return cite.is_number(value)


def _rows(n: Any, lang: str) -> str:
    """``318 lignes``, ``0 ligne``, ``1 row``: a count of rows with its noun."""
    one = n in (0, 1) if lang == FR else n == 1
    return f'{_int(n, lang)} ' + (_t(lang, 'row', 'ligne') if one else _t(lang, 'rows', 'lignes'))


def model_name(view: Mapping, slot: str | None) -> str:
    """A model slot in the junior's words, a variant with what it changes ("la deuxième
    variante · une Explainable Boosting Machine (EBM)"), as the choice options name it."""
    lang = _lang(view)
    try:
        from . import junior
        return _low(junior._model_label(str(slot), view, lang)).replace(' · ', ', ')
    except Exception:                        # noqa: BLE001 - the plain words then
        return audience.model_words(slot, lang)


def _end(text: str) -> str:
    text = text.rstrip()
    return text if text.endswith(('.', '!', '?', '»')) else text + '.'


# --- values in words ------------------------------------------------------------------------

AVAILABILITY_REASONS = {
    'not_available': ('known only after the prediction moment',
                      'connue seulement après le moment de la prédiction'),
    'uncertain_excluded': ('its timing is uncertain', 'moment incertain'),
}
KEPT_STATUSES = ('available_at_prediction', 'uncertain_included')


def _availability_words(value: Mapping, lang: str) -> str:
    kept = sorted(str(c) for c, s in value.items() if s in KEPT_STATUSES)
    excluded = sorted((str(c), s) for c, s in value.items() if s not in KEPT_STATUSES)
    parts = []
    if kept:
        parts.append(_t(lang, f'keep {audience.join(kept, lang)}',
                        f'garder {audience.join(kept, lang)}'))
    if excluded:
        named = [f'{c} ({AVAILABILITY_REASONS.get(s, (s, s))[lang == FR]})' for c, s in excluded]
        parts.append(_t(lang, f'exclude {audience.join(named, lang)}',
                        f'exclure {audience.join(named, lang)}'))
    return (' ; ' if lang == FR else '; ').join(parts) or _t(lang, 'no column', 'aucune colonne')


def value_words(view: Mapping, decision: str | None, value: Any) -> str:
    """A decision value as the junior reads it, in the study language: the report's words
    (:func:`mlkit.study.render_html.value_words`), the feature availability as the columns it
    keeps and excludes, the conclusion as its verdict and text. Never raw JSON for a decision
    the engine knows."""
    lang = _lang(view)
    if value is None:
        return _t(lang, 'no value', 'aucune valeur')
    if decision == 'feature_availability' and isinstance(value, Mapping):
        return _availability_words(value, lang)
    if decision == 'conclusion' and isinstance(value, Mapping):
        words = audience.verdict_words(value.get('verdict'), lang)
        text = value.get('text')
        return f'{words}{_colon(lang)}{text}' if text else words
    if decision == 'policy':
        return audience.policy_words(value, lang)
    if isinstance(value, str) and decision not in ('model_choice',):
        return value
    from . import render_html, texts
    with texts.study_context(view), texts.report_language_context(lang):
        text = _low(render_html.value_words(str(decision), value, view.get('task')))
    if decision == 'preprocessing':
        # The line names the decision already ("La préparation des variables : …").
        for prefix in ('preparation: ', 'préparation : '):
            if text.startswith(prefix):
                text = text[len(prefix):]
    if decision == 'model_choice' and isinstance(value, str):
        return model_name(view, value)
    return text


def review_restatement(view: Mapping, decision: str | None, value: Any) -> str:
    """R24: the quoted block of a review pause: the decision and the value the automatic mode
    recorded, in words, in the present tense; the closed question follows it."""
    lang = _lang(view)
    words = value_words(view, decision, value)
    what = _cap(audience.decision_words(decision, lang))
    return _t(lang, f'{what}: {words} (value recorded by the automatic mode, not yet in your '
                    'words).',
              f'{what} : {words} (valeur enregistrée par le mode automatique, pas encore avec '
              'vos mots).')


# --- why a value ----------------------------------------------------------------------------

def _texts(item: Mapping | None, lang: str) -> str | None:
    if not isinstance(item, Mapping):
        return None
    texts = item.get('texts')
    if isinstance(texts, Mapping) and texts.get(lang):
        return texts[lang]
    return item.get('text') if lang == EN else None


def why(view: Mapping, state: Mapping, action: Mapping, value: Any) -> str:
    """Why the automatic mode records ``value``: the engine's ``recommended.why`` when it
    recommended it, else the fixed rule it applied (``automation.RULES``), in words."""
    lang = _lang(view)
    decision = action.get('decision')
    recommended = action.get('recommended')
    if decision == 'final_test':
        # The engine's why speaks of "the configuration you chose": here the mode chose it.
        return _t(lang, 'The configuration the automatic mode chose above; the demonstration '
                        'opens the final test once to measure it.',
                  'La configuration que le mode automatique a choisie plus haut ; la '
                  'démonstration ouvre le test final une fois pour la mesurer.')
    if isinstance(recommended, Mapping) and recommended.get('why') \
            and recommended.get('value') == value:
        return recommended['why']
    if action.get('default_value') == value and isinstance(recommended, Mapping) \
            and recommended.get('why'):
        return recommended['why']
    if decision == 'model_choice':
        selection = view.get('model_selection') or {}
        one_se = selection.get('one_se') if isinstance(selection.get('one_se'), Mapping) else {}
        if one_se.get('pick') == value and _texts(one_se, lang):
            return _texts(one_se, lang)
        if selection.get('best') == value:
            return _t(lang, 'It has the smallest out-of-fold error on the declared metric.',
                      "C'est la configuration à la plus petite erreur hors pli sur la mesure "
                      'déclarée.')
        return _t(lang, 'The model selection gave no pick: the mode keeps the candidate model.',
                  "La sélection n'a rien retenu : le mode garde le modèle candidat.")
    if decision == 'policy':
        from . import junior
        try:
            return junior.POLICY_WHY[junior._policy_source(value, view, state)][lang == FR]
        except (KeyError, TypeError):
            pass
    if decision == 'conclusion':
        status = (view.get('criterion') or {}).get('judged_status')
        return _t(lang, f'The success criterion, judged on the final test, is: '
                        f'{CRITERION_STATUS[status][0] if status in CRITERION_STATUS else status}.',
                  'Le critère de succès, jugé sur le test final, est : '
                  f'{CRITERION_STATUS[status][1] if status in CRITERION_STATUS else status}.')
    return _t(lang, "The engine's default for this decision.",
              'La valeur par défaut du moteur pour cette décision.')


CRITERION_STATUS = {'met': ('met', 'atteint'), 'not_met': ('not met', 'non atteint'),
                    'uncertain': ('uncertain', 'incertain'),
                    'not_assessed': ('not assessed', 'non évalué')}


# --- the key result of a computation ---------------------------------------------------------

def _values(view: Mapping, slot: str) -> Mapping | None:
    result = (view.get('results') or {}).get(slot)
    if not isinstance(result, Mapping) or not result.get('current', True):
        return None
    values = result.get('values')
    return values if isinstance(values, Mapping) else None


def _out_of_fold(values: Mapping, lang: str) -> str:
    if values.get('evaluation') == 'out_of_fold' or (
            (values.get('predictions') or {}).get('evaluation') == 'out_of_fold'):
        return _t(lang, 'out of fold', 'hors pli')
    return _t(lang, 'on the validation rows', 'sur les lignes de validation')


def model_figure(view: Mapping, slot: str) -> tuple[str, str] | None:
    """``(metric words, figure)`` of model ``slot`` on the development rows: the out-of-fold
    mean absolute error (regression) or AUC (binary), from the comparison when it holds the
    model, else from the fit; None when no current result holds it."""
    lang = _lang(view)
    regression = view.get('task') == st.REGRESSION
    comparison = _values(view, 'evaluate.regression') if regression else None
    fit = _values(view, slot)
    unit = ''
    if regression:
        metric = (comparison or {}).get('models', {}).get(slot, {}).get('mae') \
            if comparison else None
        source = comparison if metric is not None else fit
        if metric is None and fit:
            metric = (fit.get('validation') or {}).get('mae')
        if not _is_number(metric):
            return None
        unit = f' {source.get("unit")}' if source and source.get('unit') else ''
        words = _t(lang, f'mean absolute error {_out_of_fold(fit or source, lang)}',
                   f'erreur absolue moyenne {_out_of_fold(fit or source, lang)}')
        return words, f'{_num(metric, lang)}{unit}'
    if not fit:
        return None
    metric = (fit.get('validation') or {}).get('roc_auc')
    if not _is_number(metric):
        return None
    return f'AUC {_out_of_fold(fit, lang)}', _num(metric, lang, 'f3')


FOLD_WORDS = {'kfold_stratified': ('stratified on the outcome', 'stratifiés sur le résultat'),
              'kfold_quantile': ('stratified on target quantiles',
                                 'stratifiés sur les quantiles de la cible'),
              'temporal_folds': ('in time order', "dans l'ordre du temps")}


def _split_result(values: Mapping, view: Mapping, lang: str) -> str | None:
    folds = values.get('folds')
    fold_rows = [f.get('n_rows') for f in values.get('fold_rows') or [] if _is_number(
        f.get('n_rows'))]
    final = view.get('final_test') or {}
    sealed = (_t(lang, f'; the final test stays sealed ({_int(final["rows"], lang)} rows)',
                 f' ; le test final reste scellé ({_int(final["rows"], lang)} lignes)')
              if final.get('status') == 'sealed' and _is_number(final.get('rows')) else '')
    if isinstance(folds, int) and fold_rows:
        kind = FOLD_WORDS.get(values.get('method'), ('', ''))[lang == FR]
        low, high = min(fold_rows), max(fold_rows)
        each = (_int(low, lang) if low == high else
                _t(lang, f'{_int(low, lang)} to {_int(high, lang)}',
                   f'de {_int(low, lang)} à {_int(high, lang)}'))
        total = values.get('n_rows')
        return _t(lang, f'{_int(folds, lang)} folds{f" {kind}" if kind else ""}, {each} rows '
                        f'each, on {_int(total, lang)} development rows{sealed}.',
                  f'{_int(folds, lang)} plis{f" {kind}" if kind else ""}, {each} lignes '
                  f'chacun, sur {_rows(total, lang)} de développement{sealed}.')
    parts = values.get('partitions') or {}
    train = (parts.get('train') or {}).get('n_rows')
    valid = (parts.get('validation') or {}).get('n_rows')
    if _is_number(train) and _is_number(valid):
        return _t(lang, f'{_int(train, lang)} training rows and {_int(valid, lang)} validation '
                        f'rows{sealed}.',
                  f"{_int(train, lang)} lignes d'entraînement et {_int(valid, lang)} lignes de "
                  f'validation{sealed}.')
    return None


def _quality_result(values: Mapping, lang: str) -> str | None:
    n = values.get('n_rows')
    if not _is_number(n):
        return None
    missing_cols = [m['column'] for m in values.get('missing') or []
                    if _is_number(m.get('n_missing')) and m['n_missing'] > 0]
    with_missing = values.get('n_rows_with_missing')
    parts = []
    if missing_cols and _is_number(with_missing):
        parts.append(_t(lang, f'{_int(with_missing, lang)} of {_rows(n, lang)} with a missing '
                              f'value ({audience.join(missing_cols, lang)})',
                        f'{_int(with_missing, lang)} sur {_rows(n, lang)} avec une valeur '
                        f'manquante ({audience.join(missing_cols, lang)})'))
    else:
        parts.append(_t(lang, f'no missing value in {_rows(n, lang)}',
                        f'aucune valeur manquante sur {_rows(n, lang)}'))
    dup = (values.get('duplicates') or {}).get('n_rows')
    if _is_number(dup):
        parts.append(_t(lang, f'{_rows(dup, lang)} repeated', f'{_rows(dup, lang)} en double'))
    rare = [(c['column'], len(c.get('rare') or [])) for c in values.get('cardinality') or []
            if c.get('rare')]
    if rare:
        named = audience.join([f'{c} ({_int(k, lang)})' for c, k in rare], lang)
        parts.append(_t(lang, f'rare categories in {named}', f'catégories rares dans {named}'))
    else:
        parts.append(_t(lang, 'no rare category', 'aucune catégorie rare'))
    declared = [r for r in values.get('ranges') or [] if r.get('declared')]
    if declared:
        outside = sum((r.get('n_below') or 0) + (r.get('n_above') or 0) for r in declared)
        parts.append(_t(lang, f'{_int(outside, lang)} values outside the declared ranges',
                        f'{_int(outside, lang)} valeurs hors des plages déclarées'))
    else:
        parts.append(_t(lang, 'no range declared by the case, so no check of extreme values',
                        'aucune plage déclarée par le cas, donc pas de contrôle des valeurs '
                        'extrêmes'))
    return (' ; ' if lang == FR else '; ').join(parts) + _t(
        lang, ' (the target is not read).', " (la cible n'est pas lue).")


def _target_result(values: Mapping, lang: str) -> str | None:
    if _is_number(values.get('mean')):
        unit = f' {values["unit"]}' if values.get('unit') else ''
        target = values.get('target') or _t(lang, 'the target', 'la cible')
        return _t(lang, f'mean {target} {_num(values["mean"], lang)}{unit}, median '
                        f'{_num(values.get("median"), lang)}, from {_num(values.get("min"), lang)} '
                        f'to {_num(values.get("max"), lang)}, on {_rows(values.get("n"), lang)}.',
                  f'{target} moyen {_num(values["mean"], lang)}{unit}, médiane '
                  f'{_num(values.get("median"), lang)}, de {_num(values.get("min"), lang)} à '
                  f'{_num(values.get("max"), lang)}, sur {_rows(values.get("n"), lang)}.')
    rate = values.get('rate')
    if _is_number(rate):
        return _t(lang, f'positive outcome rate {cite.format_value(rate, "fraction", lang)} on '
                        f'{_int(values.get("n_rows"), lang)} rows.',
                  f'taux de résultat positif {cite.format_value(rate, "fraction", lang)} sur '
                  f'{_int(values.get("n_rows"), lang)} lignes.')
    return None


def _special_result(values: Mapping, lang: str) -> str | None:
    items = [s for s in values.get('special_values') or [] if _is_number(s.get('n_rows'))]
    if not items:
        return _t(lang, 'no special value found.', 'aucune valeur spéciale trouvée.')
    named = audience.join([_t(lang, f'{s["column"]} = "{s["value"]}" on {_rows(s["n_rows"], lang)}',
                              f'{s["column"]} = « {s["value"]} » sur {_rows(s["n_rows"], lang)}')
                           for s in items], lang)
    return _t(lang, f'{named}.', f'{named}.')


def _fit_result(view: Mapping, slot: str, lang: str) -> str | None:
    figure = model_figure(view, slot)
    if figure is None:
        return None
    words, number = figure
    text = f'{words} {number}'
    if slot != 'fit.baseline':
        reference = 'fit.baseline' if view.get('task') == st.REGRESSION else None
        if slot.startswith('fit.variant'):
            reference = 'fit.linear' if view.get('task') == st.REGRESSION else 'fit.logistic'
        other = model_figure(view, reference) if reference else None
        if other:
            text += _t(lang, f' (against {other[1]} for {model_name(view, reference)})',
                       f' (contre {other[1]} pour {model_name(view, reference)})')
    return _end(text)


def _comparison_result(view: Mapping, values: Mapping, lang: str) -> str | None:
    models = values.get('models') or {}
    unit = f' {values["unit"]}' if values.get('unit') else ''
    listed = [_t(lang, f'{_num(m["mae"], lang)}{unit} for {model_name(view, slot)}',
                 f'{_num(m["mae"], lang)}{unit} pour {model_name(view, slot)}')
              for slot, m in models.items() if _is_number((m or {}).get('mae'))]
    if not listed:
        return None
    text = _t(lang, f'mean absolute error out of fold: {"; ".join(listed)}.',
              f'erreur absolue moyenne hors pli : {" ; ".join(listed)}.')
    selection = view.get('model_selection') or {}
    advice = _texts(selection.get('advice'), lang)
    if advice:
        text += _t(lang, f' Advice: {advice}', f' Conseil : {advice}')
    one_se = selection.get('one_se') if isinstance(selection.get('one_se'), Mapping) else {}
    if one_se.get('pick'):
        best = one_se.get('best')
        text += _t(lang, f' The one-standard-error rule keeps '
                         f'{audience.model_words(one_se["pick"], lang)}'
                         + (f'; the best on average is {audience.model_words(best, lang)}.'
                            if best and best != one_se['pick'] else '.'),
                   f" La règle d'une erreur type retient "
                   f'{audience.model_words(one_se["pick"], lang)}'
                   + (f' ; la meilleure en moyenne est {audience.model_words(best, lang)}.'
                      if best and best != one_se['pick'] else '.'))
    return text


FLAG_WORDS = {'nonlinearity': ('a shape the linear model does not follow',
                               'une forme que le modèle linéaire ne suit pas'),
              'interaction': ('a slope that differs across groups',
                              'une pente qui change selon les groupes'),
              'calibration_slope': ('predictions too spread or too narrow',
                                    'des prédictions trop ou pas assez étalées')}


def _pct(value: Any, lang: str) -> str:
    return cite.format_value(value, 'fraction', lang)


def _distribution_result(values: Mapping, lang: str) -> str | None:
    column = values.get('column')
    numeric = values.get('numeric') if isinstance(values.get('numeric'), Mapping) else None
    special = sum(s.get('n_rows') or 0 for s in values.get('special_values') or [])
    if numeric and _is_number(numeric.get('median')):
        text = _t(lang, f'{column}: median {_num(numeric["median"], lang)}, from '
                        f'{_num(numeric.get("min"), lang)} to {_num(numeric.get("max"), lang)}, '
                        f'on {_rows(numeric.get("n"), lang)}',
                  f'{column} : médiane {_num(numeric["median"], lang)}, de '
                  f'{_num(numeric.get("min"), lang)} à {_num(numeric.get("max"), lang)}, sur '
                  f'{_rows(numeric.get("n"), lang)}')
        if special:
            text += _t(lang, f' (and {_rows(special, lang)} with a special value)',
                       f' (et {_rows(special, lang)} avec une valeur spéciale)')
        return text + '.'
    if _is_number(values.get('n_groups')):
        return _t(lang, f'{column}: {_int(values["n_groups"], lang)} groups on '
                        f'{_rows(values.get("n_rows"), lang)}.',
                  f'{column} : {_int(values["n_groups"], lang)} groupes sur '
                  f'{_rows(values.get("n_rows"), lang)}.')
    return None


def _policy_result(view: Mapping, values: Mapping, lang: str) -> str | None:
    model = (values.get('gain_points') or {}).get('model') or 'fit.logistic'
    rules = values.get('rules') or {}
    found = [(rule, (((item or {}).get('models') or {}).get(model) or {}).get('precision'))
             for rule, item in rules.items()]
    found = [(rule, p) for rule, p in found if _is_number(p)]
    if not found:
        return None
    name = model_name(view, model)
    shares = [str(rule).partition(':') for rule, _ in found]
    if all(kind == 'share' and k for kind, _, k in shares):
        # One list of figures, then one list of shares: the engine's check reads each
        # figure against the evaluation (a share named next to a figure would bind it).
        figures = audience.join([_pct(p, lang) for _, p in found], lang)
        parts = audience.join([audience.share_percent(k, lang) for _, _, k in shares], lang)
        text = _t(lang, f'out-of-fold precision for {name}: {figures} for the top {parts} by '
                        'score',
                  f'précision hors pli pour {name} : {figures} pour les {parts} meilleurs '
                  'scores')
    else:
        listed = [_t(lang, f'{_pct(p, lang)} to {audience.rule_words(rule, lang)}',
                     f'{_pct(p, lang)} pour {audience.rule_words(rule, lang)}')
                  for rule, p in found]
        text = _t(lang, f'out-of-fold precision for {name}: {"; ".join(listed)}',
                  f'précision hors pli pour {name} : {" ; ".join(listed)}')
    base = (values.get('gain_points') or {}).get('base_rate')
    if _is_number(base):
        text += _t(lang, f' (base rate {_pct(base, lang)})', f' (taux de base {_pct(base, lang)})')
    return text + '.'


def _diagnostics_result(values: Mapping, lang: str) -> str | None:
    checks = values.get('linear_checks')
    if not isinstance(checks, Mapping):
        return None
    flags = checks.get('flags') or []
    if not flags:
        return _t(lang, 'no flag: the checks of the linear model raise nothing.',
                  'aucun signal : les contrôles du modèle linéaire ne relèvent rien.')
    by_check: dict[str, list[str]] = {}
    for flag in flags:
        by_check.setdefault(flag.get('check'), []).append(flag.get('feature') or '')
    parts = []
    for check, features in by_check.items():
        words = FLAG_WORDS.get(check, (str(check), str(check)))[lang == FR]
        named = [f for f in features if f]
        parts.append(f'{words} ({audience.join(named, lang)})' if named else words)
    one = len(flags) == 1
    count = _int(len(flags), lang) + ' ' + (_t(lang, 'flag', 'signal') if one
                                            else _t(lang, 'flags', 'signaux'))
    return _t(lang, f'{count}: {"; ".join(parts)}. A flag is a hint that another model '
                    'family may follow the data more closely, not a proof.',
              f'{count} : {" ; ".join(parts)}. Un signal suggère qu\'une autre famille '
              'de modèles pourrait mieux suivre les données ; ce n\'est pas une preuve.')


def _final_result(view: Mapping, lang: str) -> str | None:
    values = _values(view, 'final_test.evaluation')
    if not values:
        return None
    criterion = view.get('criterion') or {}
    status = criterion.get('judged_status')
    words = CRITERION_STATUS.get(status, (status, status))[lang == FR] if status else None
    n = values.get('n')
    text = _t(lang, 'the final test is open, once', 'le test final est ouvert, une fois')
    if _is_number(n):
        text += _t(lang, f', on {_rows(n, lang)}', f', sur {_rows(n, lang)}')
    models = values.get('models') or {}
    chosen = models.get(values.get('model')) or {}
    unit = f' {values["unit"]}' if values.get('unit') else ''
    if _is_number(chosen.get('mae')):
        text += _t(lang, f': mean absolute error {_num(chosen["mae"], lang)}{unit} for '
                         f'{model_name(view, values.get("model"))}',
                   f' : erreur absolue moyenne {_num(chosen["mae"], lang)}{unit} pour '
                   f'{model_name(view, values.get("model"))}')
        base = models.get('fit.baseline') or {}
        if _is_number(base.get('mae')) and values.get('model') != 'fit.baseline':
            text += _t(lang, f', against {_num(base["mae"], lang)}{unit} for the mean baseline',
                       f', contre {_num(base["mae"], lang)}{unit} pour la moyenne de référence')
    elif _is_number(chosen.get('precision')):
        text += _t(lang, f': precision of {model_name(view, values.get("model"))} '
                         f'{_pct(chosen["precision"], lang)}',
                   f' : précision du {model_name(view, values.get("model"))[3:]} '
                   f'{_pct(chosen["precision"], lang)}'
                   if model_name(view, values.get('model')).startswith('le ') else
                   f' : précision pour {model_name(view, values.get("model"))} '
                   f'{_pct(chosen["precision"], lang)}')
        base = models.get('fit.baseline') or {}
        if _is_number(base.get('precision')):
            text += _t(lang, f', against {_pct(base["precision"], lang)} for the baseline',
                       f', contre {_pct(base["precision"], lang)} pour le modèle de référence')
    if words:
        text += _t(lang, f'; success criterion: {words}', f' ; critère de succès : {words}')
    return text + '.'


def result_words(view: Mapping, activity: str) -> str | None:
    """The key result of the computation ``activity`` in the study language, or None when
    there is nothing to cite (no current result)."""
    lang = _lang(view)
    slot = str(activity)
    base = slot.partition(':')[0]
    if base == 'final_test.evaluation':
        return _final_result(view, lang)
    values = _values(view, slot)
    if values is None:
        return None
    if base == 'split':
        return _split_result(values, view, lang)
    if base == 'eda.quality':
        return _quality_result(values, lang)
    if base in ('eda.target_summary', 'eda.target_rate'):
        return _target_result(values, lang)
    if base == 'eda.special_values':
        return _special_result(values, lang)
    if base.startswith('fit.'):
        return _fit_result(view, slot, lang)
    if base == 'evaluate.regression':
        return _comparison_result(view, values, lang)
    if base.startswith('diag.'):
        return _diagnostics_result(values, lang)
    if base == 'eda.distribution':
        return _distribution_result(values, lang)
    if base in ('policy.evaluation', 'policy.evaluate'):
        return _policy_result(view, values, lang)
    if base == 'predictor.capture':
        return _t(lang, 'the chosen model is captured, so the export carries it.',
                  "le modèle choisi est capturé : l'export le portera.")
    return None


# --- header and closing summary --------------------------------------------------------------

def case_title(state: Mapping) -> str | None:
    try:
        from . import case as case_mod
        return case_mod.case_of(state).document.get('title')
    except Exception:                        # noqa: BLE001 - a title is never required
        return None


def _mode_words(mode: str | None, lang: str) -> str:
    return {st.UNTIL_FINAL_TEST: _t(lang, 'up to the final test', "jusqu'au test final"),
            st.FULL_DEMO: _t(lang, 'full demonstration', 'démonstration complète')}.get(
        mode, str(mode))


def header_lines(view: Mapping, state: Mapping) -> list[str]:
    lang = _lang(view)
    record = st.automation_of(state) or {}
    mode = record.get('mode')
    title = case_title(state)
    head = _t(lang, 'Automatic mode', 'Mode automatique')
    first = ' · '.join(x for x in (head, _mode_words(mode, lang), title) if x)
    remaining = [s for s in view.get('plan') or [] if s.get('status') != 'done'
                 and (mode == st.FULL_DEMO or s.get('id') not in st.DEMO_ONLY_DECISIONS)]
    titles = [_low(s.get('title') or audience.decision_words(s.get('id'), lang))
              for s in remaining]
    lines = [first,
             _t(lang, 'What I do: I take each decision with the value the engine drafts or '
                      'recommends, and I run each computation, in the order of the plan.',
                'Ce que je fais : je prends chaque décision avec la valeur que le moteur rédige '
                'ou recommande, et je lance chaque calcul, dans l\'ordre du plan.')]
    if titles:
        lines.append(_t(lang, f'On the programme: {"; ".join(titles)}.',
                        f'Au programme : {" ; ".join(titles)}.'))
    if mode == st.FULL_DEMO:
        lines.append(_t(lang, 'Where I stop: at the end. This demonstration also opens the final '
                              'test, once, and concludes; the study then waits for your review.',
                        "Où je m'arrête : à la fin. Cette démonstration ouvre aussi le test "
                        'final, une fois, et conclut ; l\'étude attend ensuite votre relecture.'))
    else:
        lines.append(_t(lang, 'Where I stop: before the final test, which stays sealed. You then '
                              'review each decision: you adopt it in your own words or change it.',
                        "Où je m'arrête : avant le test final, qui reste scellé. Ensuite, vous "
                        "relisez chaque décision : vous l'adoptez avec vos mots ou vous la "
                        'changez.'))
    return lines


STOP_WORDS = {
    'reached_end': ('I stopped where the automatic mode ends, as planned.',
                    "Je me suis arrêté là où le mode automatique s'arrête, comme prévu."),
    'needs_junior': ('I stopped: what comes next needs your answer.',
                     'Je me suis arrêté : la suite demande votre réponse.'),
    'no_automatic_value': ('I stopped: the engine has no value to record here; your answer is '
                           'needed.',
                           "Je me suis arrêté : le moteur n'a pas de valeur à enregistrer ici ; "
                           'votre réponse est nécessaire.'),
    'refused': ('I stopped: the engine refused a step, and nothing was bypassed.',
                "Je me suis arrêté : le moteur a refusé une étape, et rien n'a été contourné."),
    'not_promoted': ('I stopped: a computation did not complete.',
                     "Je me suis arrêté : un calcul n'a pas abouti."),
    'automation_not_set': ('Nothing was done: this study has no automatic mode in force.',
                           "Rien n'a été fait : cette étude n'a pas de mode automatique en "
                           'cours.'),
    'limit': ('I stopped after the maximum number of steps.',
              "Je me suis arrêté après le nombre maximal d'étapes."),
}


def _chosen_model(view: Mapping) -> str | None:
    decisions = view.get('decisions') or {}
    choice = decisions.get('model_choice') or {}
    value = choice.get('value')
    if isinstance(value, str) and choice.get('status') in ('confirmed', 'reconfirm_required'):
        return value
    policy = decisions.get('policy') or {}
    rule, sep, model = str(policy.get('value') or '').partition('@')
    if policy.get('status') in ('confirmed', 'reconfirm_required') and policy.get('value'):
        return model if sep and model else 'fit.logistic'
    return None


def _model_line(view: Mapping, lang: str) -> str | None:
    slot = _chosen_model(view)
    if slot is None:
        return None
    figure = model_figure(view, slot)
    name = model_name(view, slot)
    selection = view.get('model_selection') or {}
    one_se = selection.get('one_se') if isinstance(selection.get('one_se'), Mapping) else {}
    rule = (_t(lang, ' (one-standard-error rule)', " (règle d'une erreur type)")
            if one_se.get('pick') == slot else '')
    text = _t(lang, f'Model kept: {name}{rule}', f'Modèle retenu : {name}{rule}')
    if figure:
        text += f', {figure[0]} {figure[1]}'
    reference = 'fit.baseline' if view.get('task') == st.REGRESSION else None
    base = model_figure(view, reference) if reference and reference != slot else None
    if base:
        text += _t(lang, f', against {base[1]} for the mean baseline',
                   f', contre {base[1]} pour la moyenne de référence')
    best = selection.get('best')
    if best and best != slot:
        other = model_figure(view, best)
        if other:
            text += _t(lang, f'; the best on average is {model_name(view, best)}, with '
                             f'{other[1]}',
                       f' ; la meilleure en moyenne est {model_name(view, best)}, avec '
                       f'{other[1]}')
    return text + '.'


def _final_line(view: Mapping, lang: str) -> str:
    final = view.get('final_test') or {}
    if final.get('status') == 'opened':
        if any(x.get('id') == 'final_test_opened_automatically'
               for x in view.get('not_yet_defensible') or []):
            return _t(lang, 'The final test was opened automatically (a demonstration), once.',
                      'Le test final a été ouvert automatiquement (une démonstration), une fois.')
        return _t(lang, 'The final test is open.', 'Le test final est ouvert.')
    return _t(lang, 'The final test stays sealed: no final-test row was read.',
              "Le test final reste scellé : aucune ligne du test final n'a été lue.")


def _next_line(view: Mapping, payload: Mapping, lang: str) -> str:
    reason = payload.get('reason')
    nxt = payload.get('next_action') or view.get('next_action') or {}
    queue = payload.get('review_queue') or []
    if reason in ('reached_end', 'automation_not_set') and queue:
        first = audience.decision_words(queue[0].get('decision_id'), lang)
        text = _t(lang, f'Next: review each decision in the chat, starting with {first}; adopt it '
                        'in your own words or say what you change.',
                  f'Et maintenant : relisez chaque décision dans le chat, en commençant par '
                  f'{first} ; adoptez-la avec vos mots ou dites ce que vous changez.')
        if (view.get('final_test') or {}).get('status') == 'sealed':
            text += _t(lang, ' Only then do you open the final test yourself.',
                       ' Ensuite seulement, vous ouvrirez vous-même le test final.')
        return text
    message = nxt.get('junior_message') or nxt.get('junior_digest')
    if message:
        return _t(lang, f'Next: {message}', f'Et maintenant : {message}')
    return _t(lang, 'Next: continue in the chat.', 'Et maintenant : continuez dans le chat.')


def closing_lines(view: Mapping, payload: Mapping) -> list[str]:
    """The closing summary of a run: why it stopped, the decisions to review, the model the
    mode kept and its figure, the final test, what the junior does next."""
    lang = _lang(view)
    reason = payload.get('reason')
    stop = STOP_WORDS.get(reason, (str(reason), str(reason)))[lang == FR]
    if reason == 'reached_end':
        mode = (payload.get('automation') or {}).get('mode')
        stop = (_t(lang, 'The demonstration went to the end, as planned.',
                   'La démonstration est allée jusqu\'au bout, comme prévu.')
                if mode == st.FULL_DEMO else
                _t(lang, 'I stopped before the final test, as planned.',
                   "Je me suis arrêté avant le test final, comme prévu."))
    lines = [_t(lang, 'Summary · ', 'Bilan · ') + stop]
    refusal = payload.get('refusal') or {}
    if reason == 'refused':
        message = (refusal.get('details') or {}).get('junior_message')
        stopped = (payload.get('stopped_at') or {}).get('decision')
        if stopped:
            lines.append(_t(lang, f'Refused at: {audience.decision_words(stopped, lang)}.',
                            f'Refusé à : {audience.decision_words(stopped, lang)}.'))
        if message:
            lines.append(message)
    queue = payload.get('review_queue') or []
    if queue:
        names = audience.join([audience.decision_words(q.get('decision_id'), lang)
                               for q in queue], lang)
        lines.append(_t(lang, f'Decisions to review ({_int(len(queue), lang)}): {names}.',
                        f'Décisions à relire ({_int(len(queue), lang)}) : {names}.'))
    model = _model_line(view, lang)
    if model:
        lines.append(model)
    policy = (view.get('decisions') or {}).get('policy') or {}
    if policy.get('value') and policy.get('status') in ('confirmed', 'reconfirm_required'):
        rule = str(policy['value']).partition('@')[0]
        lines.append(_t(lang, f'Decision rule: {audience.rule_words(rule, lang)}.',
                        f'Règle de décision : {audience.rule_words(rule, lang)}.'))
    if payload.get('steps') or queue:
        lines.append(_final_line(view, lang))
    lines.append(_next_line(view, payload, lang))
    return lines


def text_summary(payload: Mapping) -> str:
    """The readable summary of a ``hypotrail.automation/1`` payload (``--format text``): the
    study and its revision, why the run stopped, each automatic decision with its value in
    words, the model kept, the final test, what comes next. Read only."""
    view: Mapping = {}
    try:
        from . import lock, read, view as view_mod
        view = view_mod.build(read.open(payload['study']),
                              leases=lock.probe_leases(payload['study']))
    except Exception:                        # noqa: BLE001 - the summary still reads
        view = {'language': ((payload.get('next_action') or {}).get('language'))}
    lang = _lang(view)
    state = {}
    try:
        from . import read
        state = read.open(payload['study']).state
    except Exception:                        # noqa: BLE001
        pass
    title = case_title(state) if state else None
    head = _t(lang, 'Automatic mode', 'Mode automatique')
    mode = (payload.get('automation') or {}).get('mode')
    lines = [' · '.join(x for x in (head, _mode_words(mode, lang) if mode else None, title) if x)
             + _t(lang, f' · revision {payload.get("revision")}',
                  f' · révision {payload.get("revision")}'),
             _t(lang, f'Study: {payload.get("study")}', f'Étude : {payload.get("study")}')]
    steps = payload.get('steps') or []
    if steps:
        decisions = sum(s.get('kind') == 'await_user_words' for s in steps)
        runs = sum(s.get('kind') == 'run' for s in steps)
        lines.append(_t(lang, f'This run: {_int(decisions, lang)} decisions recorded, '
                              f'{_int(runs, lang)} computations.',
                        f'Cette exécution : {_int(decisions, lang)} décisions enregistrées, '
                        f'{_int(runs, lang)} calculs.'))
    queue = payload.get('review_queue') or []
    if queue:
        lines.append(_t(lang, 'Recorded by the automatic mode, to review:',
                        'Enregistré par le mode automatique, à relire :'))
        for q in queue:
            what = _cap(audience.decision_words(q.get('decision_id'), lang))
            lines.append(f'  - {what}{_colon(lang)}{value_words(view, q.get("decision_id"), q.get("value"))}')
    closing = closing_lines(view, payload)
    lines.append(closing[0].split(' · ', 1)[-1])
    lines += [x for x in closing[1:] if not x.startswith(
        (_t(lang, 'Decisions to review', 'Décisions à relire')))]
    report = ((payload.get('artifacts') or {}).get('report') or {})
    if report.get('path'):
        lines.append(_t(lang, f'Report: {report["path"]} ({report.get("status")})',
                        f'Rapport : {report["path"]} ({report.get("status")})'))
    lines.append(_t(lang, 'The full JSON document: add --json.',
                    'Le document JSON complet : ajoutez --json.'))
    return '\n'.join(lines)


# --- the narrator of a run (stderr) ----------------------------------------------------------

class _Indented:
    """A stream that indents every line written to it (the activities' own progress lines,
    under the step that runs them); a terminal's carriage return keeps the indent."""

    def __init__(self, stream: TextIO, prefix: str = '    '):
        self.stream, self.prefix, self.at_start = stream, prefix, True

    def write(self, text: str) -> int:
        out = []
        for char in text:
            if char in '\r\n':
                out.append(char)
                self.at_start = True
                continue
            if self.at_start:
                out.append(self.prefix)
                self.at_start = False
            out.append(char)
        self.stream.write(''.join(out))
        return len(text)

    def flush(self) -> None:
        self.stream.flush()

    def isatty(self) -> bool:
        try:
            return bool(self.stream.isatty())
        except (AttributeError, ValueError):
            return False


class Narrator:
    """The progress of ``automation run --progress`` on stderr (R23). Every method is a no-op
    without a stream, and a failure to say something never changes the run."""

    def __init__(self, stream: TextIO | None):
        self.stream = stream
        self.index = 0
        self.pending: dict[str, tuple[Any, str]] = {}
        self.due: str | None = None

    @property
    def activities(self) -> TextIO | None:
        return _Indented(self.stream) if self.stream is not None else None

    def _write(self, line: str) -> None:
        if self.stream is None:
            return
        try:
            self.stream.write(line + '\n')
            self.stream.flush()
        except (OSError, ValueError):     # progress never changes the run's outcome
            pass

    def _say(self, build) -> None:
        if self.stream is None:
            return
        try:
            lines = build()
        except Exception:                 # noqa: BLE001 - words never change the run
            return
        for line in ([lines] if isinstance(lines, str) else lines or []):
            self._write(line)

    def header(self, view: Mapping, state: Mapping) -> None:
        self._say(lambda: header_lines(view, state))

    def proposed(self, view: Mapping, state: Mapping, action: Mapping, value: Any) -> None:
        """Remember the value and its why; the line is written once it is recorded."""
        if self.stream is None:
            return
        try:
            self.pending[action['decision']] = (value, why(view, state, action, value))
        except Exception:                 # noqa: BLE001
            pass

    def recorded(self, view: Mapping, action: Mapping) -> None:
        def build():
            lang = _lang(view)
            decision = action.get('decision')
            value, reason = self.pending.pop(decision, (None, None))
            if value is None:
                proposal = next((p for p in view.get('open_proposals') or []
                                 if p.get('proposal_id') == action.get('proposal_id')), {})
                value = proposal.get('value')
            self.index += 1
            what = _cap(audience.decision_words(decision, lang))
            words = (audience.verdict_words(value.get('verdict'), lang)
                     if decision == 'conclusion' and isinstance(value, Mapping)
                     else value_words(view, decision, value))
            line = (f'{self.index} · ' + _t(lang, 'Decision', 'Décision') + f' · {what}'
                    + _colon(lang) + _end(words))
            if reason:
                line += _t(lang, f' Why: {_end(reason)}', f' Pourquoi : {_end(reason)}')
            return line
        self._say(build)

    def computing(self, view: Mapping, activity: str) -> None:
        def build():
            lang = _lang(view)
            self.index += 1
            self.due = activity
            words = (model_name(view, activity) if str(activity).startswith('fit.variant')
                     else audience.activity_words(activity, lang))
            return (f'{self.index} · ' + _t(lang, 'Computation', 'Calcul') + ' · ' + _cap(words))
        self._say(build)

    def opened(self) -> None:
        self.due = 'final_test.evaluation'

    def result(self, view: Mapping) -> None:
        """The key result of the computation that just ran, read from ``view``."""
        if self.due is None:
            return
        activity, self.due = self.due, None

        def build():
            words = result_words(view, activity)
            if not words:
                return None
            return '    ' + _t(_lang(view), 'Result: ', 'Résultat : ') + words
        self._say(build)

    def closing(self, view: Mapping, payload: Mapping) -> None:
        self._say(lambda: closing_lines(view, payload))


__all__ = ['Narrator', 'closing_lines', 'header_lines', 'model_figure', 'result_words',
           'review_restatement', 'text_summary', 'value_words', 'why']
