"""The trial budget, the model families, and the selection summary (v0.3, WP-F1, ADR 0007).

Pure: no file I/O, no pandas, numpy, or scikit-learn (the read side imports it).

**Variants.** The ``model_variant`` decision names up to :data:`MAX_VARIANTS` variants of the
candidate model, each declared with the question it answers::

    {"variants": [{"kind": "tuned", "question": "Does a tuned penalty rank better?"},
                  {"kind": "family", "family": "ebm", "question": "..."}]}

A value written before v0.3 is one variant without a question (``{"kind":
"regularisation", "strength": "strong"}``); it is read as a list of one (:func:`variants_of`):
the budget is then one variant used. Nothing is rewritten in the state. The kinds:

* ``regularisation`` (``strength``: ``weak`` or ``strong``), ``drop_group`` (``group``): as in
  v0.2b (ADR 0006 amendment, WP-B1);
* ``tuned``: the candidate's penalty (logistic ``C``, ridge ``alpha``) chosen by nested
  cross-validation (:data:`GRIDS`); one tuning is one trial;
* ``family``: another model family of the catalogue (:data:`CATALOGUE`), its own small grid
  tuned by nested cross-validation; one family is one trial.

Variant ``i`` (1-based) is fitted into slot :func:`variant_slot`: ``fit.variant`` for the
first (the v0.2b slot, so earlier identities are unchanged), ``fit.variant:2`` and
``fit.variant:3`` for the others. The registry entry keeps ``activity: "fit.variant"``.

**Selection** (:func:`selection`): the candidate and the declared variants compared on their
per-fold out-of-fold metric (ROC AUC for a binary target, MAE for a numeric one), with the
one-standard-error rule (Hastie, Tibshirani & Friedman 2009, *The Elements of Statistical
Learning*, 2nd ed., §7.10: the simplest model whose mean is within one standard error of the
best), the approximate optimism of picking the best (Tibshirani & Tibshirani 2009, "A bias
correction for the minimum error rate in cross-validation", *Annals of Applied Statistics*
3(2): 822-829: the mean over folds of the gap between each fold's best configuration and the
configuration chosen on the mean), and the engine's advice to stop when the paired per-fold
differences stay within their own fold noise (one standard error).

**Shortlist** (:func:`shortlist`): the catalogue filtered by the case's declared
``constraints`` and ordered by the diagnostics of the first linear fit
(``linear_checks`` of ``diag.binary`` / ``diag.regression``): a non-linear family is
proposed only with that evidence shown.

Junior texts are given in English and French (the study language picks one).
"""
from __future__ import annotations

import json
import math
from typing import Any, Mapping

VARIANT_ACTIVITY = 'fit.variant'
MAX_VARIANTS = 3
VARIANT_SLOTS = ('fit.variant', 'fit.variant:2', 'fit.variant:3')
LIST_KEY = 'variants'
QUESTION_KEY = 'question'
ORIGIN_KEY = 'origin'
DIAGNOSTIC_RESULT_KEY = 'diagnostic_result_id'
ORIGINS = ('planned', 'diagnostic_informed')
KINDS = ('regularisation', 'drop_group', 'tuned', 'family')
KIND_KEYS = {'regularisation': ('kind', 'strength'), 'drop_group': ('kind', 'group'),
             'tuned': ('kind',), 'family': ('kind', 'family')}
STRENGTHS = ('weak', 'strong')
MAX_QUESTION = 400

# --- the catalogue -----------------------------------------------------------------------

FAMILIES = ('linear', 'ebm', 'hgb')
NONLINEAR_FAMILIES = ('ebm', 'hgb')
VARIANT_FAMILIES = NONLINEAR_FAMILIES
# Nested cross-validation (WP-F1): within each outer fold, an inner cross-validation of the
# outer training rows picks the hyperparameter; the grids are ordered from the simplest model
# to the most flexible, and a tie keeps the simplest.
INNER_FOLDS = 3
INNER_SEED = 20261020
GRIDS = {
    ('linear', 'binary'): {'parameter': 'C', 'values': (0.01, 0.1, 1.0, 10.0, 100.0),
                           'meaning': 'inverse penalty strength of the logistic model'},
    ('linear', 'regression'): {'parameter': 'alpha', 'values': (100.0, 10.0, 1.0, 0.1, 0.01),
                               'meaning': 'ridge penalty strength on the standardised '
                                          'features'},
    ('ebm', 'binary'): {'parameter': 'interactions', 'values': (0, 3),
                        'meaning': 'number of pairwise interaction terms'},
    ('ebm', 'regression'): {'parameter': 'interactions', 'values': (0, 3),
                            'meaning': 'number of pairwise interaction terms'},
    ('hgb', 'binary'): {'parameter': 'max_depth', 'values': (2, 4),
                        'meaning': 'depth of each tree'},
    ('hgb', 'regression'): {'parameter': 'max_depth', 'values': (2, 4),
                            'meaning': 'depth of each tree'},
}
INNER_METRIC = {'binary': 'roc_auc', 'regression': 'mae'}
# Fixed settings that keep a fit short and reproducible (seeded).
# One outer bag, no inner bag, at most 500 boosting rounds at learning rate 0.05: about one
# second per fit on a few hundred rows, a few seconds on tens of thousands (measured on the
# development machine); the shapes are those of one boosted model, not an average of bags.
EBM_SETTINGS = {'outer_bags': 1, 'inner_bags': 0, 'max_rounds': 500, 'learning_rate': 0.05,
                'n_jobs': 1}
HGB_SETTINGS = {'max_iter': 100, 'learning_rate': 0.1, 'early_stopping': False,
                'max_categories_encoded': 250}
CATALOGUE = {
    'linear': {'family': 'linear', 'default': True, 'interpretability': 'glass_box',
               'models': {'binary': 'logistic regression', 'regression': 'linear regression'},
               'implementation': 'scikit-learn (LogisticRegression, LinearRegression, Ridge)',
               'diagnostics': 'coefficients with bootstrap intervals'},
    'ebm': {'family': 'ebm', 'default': False, 'interpretability': 'glass_box',
            'models': {'binary': 'Explainable Boosting Machine',
                       'regression': 'Explainable Boosting Machine'},
            'implementation': 'interpret-core (InterpretML, MIT licence)',
            'diagnostics': 'a shape function per feature and the pairwise interaction terms'},
    'hgb': {'family': 'hgb', 'default': False, 'interpretability': 'black_box',
            'models': {'binary': 'histogram gradient boosting',
                       'regression': 'histogram gradient boosting'},
            'implementation': 'scikit-learn (HistGradientBoostingClassifier, '
                              'HistGradientBoostingRegressor)',
            'diagnostics': 'permutation importance on the out-of-fold rows'},
}
FAMILY_WORDS = {
    'en': {'linear': 'the linear model', 'ebm': 'an Explainable Boosting Machine',
           'hgb': 'histogram gradient boosting'},
    'fr': {'linear': 'le modèle linéaire', 'ebm': 'une Explainable Boosting Machine (EBM)',
           'hgb': 'le gradient boosting par histogrammes'},
}
# The case's optional ``constraints`` (CASE-CONTRACT, v0.3): ``interpretability`` is a
# statement ``{value, status, source}`` whose value is one of these; absent means ``none``.
INTERPRETABILITY = ('required', 'preferred', 'none')
CONSTRAINT_KEYS = ('interpretability',)


# --- variants ------------------------------------------------------------------------------

def is_list_value(value: Any) -> bool:
    """Whether a ``model_variant`` value is the v0.3 list form ``{"variants": [...]}``."""
    return isinstance(value, Mapping) and set(value) == {LIST_KEY}


def variants_of(value: Any) -> list[dict]:
    """The variants a ``model_variant`` value declares, in order (a v0.2b value is one
    variant without a question). An unreadable value declares none."""
    if is_list_value(value):
        items = value[LIST_KEY]
        return [dict(v) for v in items if isinstance(v, Mapping)] \
            if isinstance(items, (list, tuple)) else []
    if isinstance(value, Mapping) and value.get('kind') in KINDS:
        return [dict(value)]
    return []


def spec_of(variant: Mapping) -> dict:
    """What makes a variant's numerical model (wording/provenance excluded)."""
    return {k: v for k, v in variant.items()
            if k not in (QUESTION_KEY, ORIGIN_KEY, DIAGNOSTIC_RESULT_KEY)}


def spec_key(variant: Mapping) -> str:
    return json.dumps(spec_of(variant), sort_keys=True, separators=(',', ':'))


def variant_slot(index: int) -> str:
    """The slot of variant ``index`` (1-based)."""
    return VARIANT_SLOTS[index - 1]


def variant_index(slot: str) -> int | None:
    """The 1-based index of a variant slot, else None."""
    return VARIANT_SLOTS.index(slot) + 1 if slot in VARIANT_SLOTS else None


def is_variant_slot(slot: Any) -> bool:
    return slot in VARIANT_SLOTS


def confirmed_value(state: Mapping) -> Any:
    """The ``model_variant`` value the study holds (confirmed, or awaiting reconfirmation),
    else None."""
    decision = (state.get('decisions') or {}).get('model_variant') or {}
    if decision.get('status') in ('confirmed', 'reconfirm_required'):
        return decision.get('value')
    return None


def declared_slots(state: Mapping) -> list[str]:
    """The variant slots of the confirmed ``model_variant`` value, in order."""
    return list(VARIANT_SLOTS[:len(variants_of(confirmed_value(state)))])


def changed_slots(old: Any, new: Any) -> list[str]:
    """The variant slots whose model changes from ``old`` to ``new``: a variant whose spec
    changed, and a variant no longer declared. A question reworded changes no model."""
    before, after = variants_of(old), variants_of(new)
    out = []
    for i, slot in enumerate(VARIANT_SLOTS):
        b = spec_key(before[i]) if i < len(before) else None
        a = spec_key(after[i]) if i < len(after) else None
        if b is not None and b != a:
            out.append(slot)
    return out


def used_specs(state: Mapping, extra: Any = None) -> list[str]:
    """The distinct variant models the study ever confirmed (each a trial of the budget):
    the variants of every confirmed ``model_variant`` proposal and of the decision's value,
    then those of ``extra`` (a value being proposed), in first-seen order. A study written
    before v0.3 with one variant has used one."""
    seen: list[str] = []
    proposals = sorted((p for p in (state.get('proposals') or {}).values()
                        if p.get('decision_id') == 'model_variant'
                        and p.get('status') == 'confirmed'),
                       key=lambda p: (p.get('revision') or 0, str(p.get('proposal_id'))))
    values = [p.get('value') for p in proposals] + [confirmed_value(state)]
    if extra is not None:
        values.append(extra)
    for value in values:
        for v in variants_of(value):
            key = spec_key(v)
            if key not in seen:
                seen.append(key)
    return seen


def budget(state: Mapping) -> dict:
    """``{max, declared, used, remaining, legacy}`` of the variant budget."""
    value = confirmed_value(state)
    used = len(used_specs(state))
    return {'max': MAX_VARIANTS, 'declared': len(variants_of(value)), 'used': used,
            'remaining': max(0, MAX_VARIANTS - used),
            'legacy': bool(value is not None and not is_list_value(value))}


def check_value(value: Any, groups: Mapping, task: str) -> str | None:
    """Why a ``model_variant`` value is not acceptable (a sentence), else None. ``groups``
    are the case's variable groups (``{group: [features]}``)."""
    items = variants_of(value)
    if is_list_value(value):
        raw = value[LIST_KEY]
        if not isinstance(raw, (list, tuple)) or not raw or len(items) != len(raw):
            return 'variants is a list of 1 to 3 variants.'
        if len(raw) > MAX_VARIANTS:
            return f'At most {MAX_VARIANTS} variants are compared (the trial budget).'
    elif not items:
        return 'model_variant names a variant: {"kind": ...} or {"variants": [...]}.'
    seen = set()
    for v in items:
        kind = v.get('kind')
        if kind not in KIND_KEYS:
            return f'kind is one of {", ".join(KINDS)}.'
        allowed = set(KIND_KEYS[kind]) | ({QUESTION_KEY, ORIGIN_KEY, DIAGNOSTIC_RESULT_KEY}
                                         if is_list_value(value) else set())
        if set(v) - allowed or not set(KIND_KEYS[kind]) <= set(v):
            return (f'A {kind} variant is {{' + ', '.join(f'"{k}"' for k in KIND_KEYS[kind])
                    + (', "question"' if is_list_value(value) else '') + '}.')
        if is_list_value(value):
            q = v.get(QUESTION_KEY)
            if not isinstance(q, str) or not q.strip() or len(q) > MAX_QUESTION:
                return ('Each variant is declared with the question it answers (a non-empty '
                        f'sentence of at most {MAX_QUESTION} characters).')
            if ORIGIN_KEY in v:
                if v.get(ORIGIN_KEY) not in ORIGINS:
                    return f'origin is one of {", ".join(ORIGINS)}.'
                diagnostic = v.get(DIAGNOSTIC_RESULT_KEY)
                if v[ORIGIN_KEY] == 'diagnostic_informed' \
                        and (not isinstance(diagnostic, str) or not diagnostic):
                    return 'A diagnostic_informed variant requires diagnostic_result_id.'
                if v[ORIGIN_KEY] == 'planned' and diagnostic is not None:
                    return 'A planned variant has diagnostic_result_id null.'
            elif DIAGNOSTIC_RESULT_KEY in v:
                return 'diagnostic_result_id requires an origin.'
        if kind == 'regularisation' and v['strength'] not in STRENGTHS:
            return 'strength is "weak" or "strong".'
        if kind == 'drop_group' and v['group'] not in groups:
            return f'{v["group"]!r} is not a group of candidate features of this case.'
        if kind == 'family' and v['family'] not in VARIANT_FAMILIES:
            return f'family is one of {", ".join(VARIANT_FAMILIES)} (the linear model is the ' \
                   f'candidate).'
        key = spec_key(v)
        if key in seen:
            return 'The same variant is declared twice.'
        seen.add(key)
    return None


def family_of(variant: Mapping | None) -> str:
    """The model family of a variant (``linear`` unless it is a ``family`` variant)."""
    if isinstance(variant, Mapping) and variant.get('kind') == 'family':
        return str(variant.get('family'))
    return 'linear'


def grid(family: str, task: str) -> dict:
    g = GRIDS[(family, task)]
    return {'parameter': g['parameter'], 'values': list(g['values']),
            'meaning': g['meaning'], 'inner_folds': INNER_FOLDS, 'seed': INNER_SEED,
            'metric': INNER_METRIC[task], 'tie': 'the simplest value of the grid (listed first)',
            'method': 'nested cross-validation: within each outer fold, an inner '
                      f'{INNER_FOLDS}-fold cross-validation of the outer training rows picks '
                      'the value; the model is refitted with it on those rows'}


# --- words (English and French) ------------------------------------------------------------

def _lang(language: str | None) -> str:
    return language if language in ('en', 'fr') else 'en'


def variant_words(variant: Mapping, language: str = 'en') -> str:
    """One variant in words, in ``language``."""
    lang = _lang(language)
    kind = variant.get('kind')
    if kind == 'regularisation':
        return {'en': {'weak': 'weaker regularisation', 'strong': 'stronger regularisation'},
                'fr': {'weak': 'régularisation plus faible',
                       'strong': 'régularisation plus forte'}}[lang].get(
            variant.get('strength'), str(variant.get('strength')))
    if kind == 'drop_group':
        return (f'without the group "{variant.get("group")}"' if lang == 'en'
                else f'sans le groupe « {variant.get("group")} »')
    if kind == 'tuned':
        return ('penalty chosen by nested cross-validation' if lang == 'en'
                else 'pénalité choisie par validation croisée imbriquée')
    if kind == 'family':
        return FAMILY_WORDS[lang].get(variant.get('family'), str(variant.get('family')))
    return str(kind)


def value_words(value: Any, language: str = 'en') -> str:
    """A ``model_variant`` value in words: its variants joined."""
    items = variants_of(value)
    if not items:
        return str(value)
    words = [variant_words(v, language) for v in items]
    sep = ' and ' if _lang(language) == 'en' else ' et '
    return words[0] if len(words) == 1 else ', '.join(words[:-1]) + sep + words[-1]


TEXTS = {
    'draft.tuned.binary': {
        'en': 'Does a penalty chosen by nested cross-validation rank the rows better than the '
              'default penalty?',
        'fr': 'Une pénalité choisie par validation croisée imbriquée classe-t-elle mieux les '
              'lignes que la pénalité par défaut ?'},
    'draft.tuned.regression': {
        'en': 'Does a ridge penalty chosen by nested cross-validation predict with a smaller '
              'error than the unpenalised linear model?',
        'fr': 'Une pénalité ridge choisie par validation croisée imbriquée prédit-elle avec une '
              'erreur plus petite que le modèle linéaire sans pénalité ?'},
    'advice.budget_exhausted': {
        'en': 'The budget of three variants is used: choose among the configurations compared; '
              'a new variant would be a fourth trial on the same rows.',
        'fr': 'Le budget de trois variantes est utilisé : choisissez parmi les configurations '
              'comparées ; une nouvelle variante serait un quatrième essai sur les mêmes '
              'lignes.'},
    'advice.fold_noise': {
        'en': 'The differences between the variants and the candidate stay within the noise '
              'between folds: another variant is unlikely to show a difference that chance '
              'would not explain. Stop here and choose.',
        'fr': 'Les écarts entre les variantes et le candidat restent dans le bruit entre les '
              'plis : une autre variante a peu de chances de montrer un écart que le hasard '
              "n'expliquerait pas. Arrêtez-vous ici et choisissez."},
    'advice.may_continue': {
        'en': 'At least one variant differs from the candidate by more than the noise between '
              'folds. Another variant is possible within the budget, each one counted.',
        'fr': 'Au moins une variante diffère du candidat de plus que le bruit entre les plis. '
              'Une autre variante reste possible dans le budget, chacune comptée.'},
    'advice.no_variant': {
        'en': 'No variant is compared yet. To be told apart from the noise between folds, a '
              'variant would need to move the mean by more than one standard error of the '
              'candidate.',
        'fr': "Aucune variante n'est encore comparée. Pour se distinguer du bruit entre les "
              "plis, une variante devrait déplacer la moyenne de plus d'une erreur type du "
              'candidat.'},
    'advice.not_available': {
        'en': 'The comparison across folds needs a cross-validation of the development rows.',
        'fr': 'La comparaison entre plis demande une validation croisée des lignes de '
              'développement.'},
    'one_se': {
        'en': 'The one-standard-error rule keeps the simplest configuration whose mean is within '
              'one standard error of the best one.',
        'fr': "La règle d'une erreur type retient la configuration la plus simple dont la "
              "moyenne est à moins d'une erreur type de la meilleure."},
    'optimism': {
        'en': 'Choosing the best of several configurations on the same folds flatters it: the '
              'optimism is the average gap, fold by fold, between that fold\'s best '
              'configuration and the one chosen.',
        'fr': 'Choisir la meilleure de plusieurs configurations sur les mêmes plis la flatte : '
              "l'optimisme est l'écart moyen, pli par pli, entre la meilleure configuration du "
              'pli et celle retenue.'},
    'shortlist.stay_linear': {
        'en': 'The diagnostics of the linear model show no sign of a non-linear shape, an '
              'interaction, or a calibration problem: stay with the linear model.',
        'fr': 'Les diagnostics du modèle linéaire ne montrent ni forme non linéaire, ni '
              'interaction, ni problème de calibration : restez sur le modèle linéaire.'},
    'shortlist.try_nonlinear': {
        'en': 'The diagnostics of the linear model show a pattern it cannot follow; a '
              'non-linear family may be compared as one variant (a trial, chosen after seeing '
              'the diagnostics).',
        'fr': 'Les diagnostics du modèle linéaire montrent une forme qu\'il ne suit pas ; une '
              'famille non linéaire peut être comparée comme une variante (un essai, choisi '
              'après avoir vu les diagnostics).'},
    'shortlist.no_diagnostics': {
        'en': 'The diagnostics of the linear model are not computed yet: the shortlist waits '
              'for them.',
        'fr': 'Les diagnostics du modèle linéaire ne sont pas encore calculés : la liste '
              'courte les attend.'},
    'shortlist.old_diagnostics': {
        'en': 'The diagnostics of the linear model were computed before the engine checked for '
              'shapes, interactions and calibration: run them again to draft the shortlist.',
        'fr': 'Les diagnostics du modèle linéaire ont été calculés avant que le moteur ne '
              'vérifie les formes, les interactions et la calibration : relancez-les pour '
              'établir la liste courte.'},
    'excluded.interpretability': {
        'en': 'excluded: the case requires an interpretable model, and gradient boosting is a '
              'black box',
        'fr': 'exclu : le cas exige un modèle interprétable, et le gradient boosting est une '
              'boîte noire'},
}


def draft(task: str, language: str = 'en') -> dict:
    """The engine's drafted ``model_variant`` value: the candidate's penalty chosen by nested
    cross-validation (one trial), declared with its question in ``language``."""
    return {LIST_KEY: [{'kind': 'tuned', QUESTION_KEY: text(f'draft.tuned.{task}', language)}]}


def text(key: str, language: str = 'en') -> str:
    return TEXTS[key][_lang(language)]


def texts(key: str) -> dict:
    return dict(TEXTS[key])


# --- selection -------------------------------------------------------------------------------

SELECTION_KEYS = ('available', 'metric', 'direction', 'folds', 'configurations', 'best',
                  'one_se', 'optimism', 'advice', 'budget', 'trials', 'note')
CONFIGURATION_KEYS = ('slot', 'kind', 'family', 'question', 'words', 'per_fold', 'mean', 'sd',
                      'se', 'difference', 'within_one_se', 'complexity')
ONE_SE_SOURCE = ('Hastie, Tibshirani & Friedman (2009), The Elements of Statistical Learning, '
                 '2nd ed., §7.10 (the one-standard-error rule)')
OPTIMISM_SOURCE = ('Tibshirani & Tibshirani (2009), A bias correction for the minimum error '
                   'rate in cross-validation, Annals of Applied Statistics 3(2): 822-829')
SELECTION_NOTE = ('Development evidence: every configuration is compared on the same '
                  'out-of-fold predictions of the development rows. The fold standard errors '
                  'ignore the overlap of the folds\' training rows (Bengio & Grandvalet 2004), '
                  'so they understate the noise: the advice errs towards stopping late, not '
                  'early. The final test, opened once, is not affected by this choice.')
_REG_RANK = {'strong': 0, 'weak': 2}
_FAMILY_RANK = {'linear': 0, 'ebm': 1, 'hgb': 2}


def _mean_sd(values: list[float]) -> tuple[float | None, float | None]:
    if not values:
        return None, None
    m = sum(values) / len(values)
    if len(values) < 2:
        return m, None
    return m, math.sqrt(sum((v - m) ** 2 for v in values) / (len(values) - 1))


def _per_fold(values: Mapping | None, metric: str) -> list[float] | None:
    if not isinstance(values, Mapping):
        return None
    cv = values.get('cross_validation') or {}
    folds = cv.get('per_fold') or []
    out = [f.get(metric) for f in folds]
    if not out or any(v is None for v in out):
        return None
    return [float(v) for v in out]


def _complexity(variant: Mapping | None, n_features: int) -> list:
    """Smaller is simpler: the family, then the number of features, then the penalty."""
    if variant is None:
        return [0, n_features, 1]
    reg = _REG_RANK.get(variant.get('strength'), 1) if variant.get('kind') == 'regularisation' \
        else 1
    return [_FAMILY_RANK.get(family_of(variant), 3), n_features, reg]


def selection(results: Mapping, state: Mapping, task: str) -> dict:
    """The candidate and the declared variants compared fold by fold (see the module
    docstring), from the view's ``results`` (current results only) and the study's
    variant decision and budget: :func:`select`."""
    evaluation_slot = 'policy.evaluation' if task == 'binary' else 'evaluate.regression'
    evaluation = results.get(evaluation_slot) or {}
    stored = (evaluation.get('values') or {}).get('model_selection') \
        if evaluation.get('current') else None
    if isinstance(stored, Mapping):
        return dict(stored)
    candidate = 'fit.logistic' if task == 'binary' else 'fit.linear'
    variants = variants_of(confirmed_value(state))
    fits = {}
    for slot in [candidate] + list(VARIANT_SLOTS[:len(variants)]):
        item = results.get(slot) or {}
        if item.get('current') and isinstance(item.get('values'), Mapping):
            fits[slot] = item['values']
    return select(fits, variants, task, budget(state), state.get('language', 'en'))


def select(fits: Mapping, variants: list, task: str, bud: Mapping,
           language: str = 'en', objectives: Mapping | None = None) -> dict:
    """``{available, metric, direction, folds, configurations, best, one_se, optimism,
    advice, budget, trials, note}``: the candidate and the ``variants`` compared on the
    per-fold metric of their fit values (``fits``: ``{slot: values}``); ``bud`` is the
    variant budget (:func:`budget`). Pure; also stored by the evaluations (WP-F1), where every
    number is a registered value."""
    first_values = next((v for v in fits.values() if isinstance(v, Mapping)), {})
    declared = ((first_values.get('cross_validation') or {}).get('objective') or {})
    if objectives:
        declared = next((v for v in objectives.values() if isinstance(v, Mapping)), declared)
    metric = declared.get('metric') or ('roc_auc' if task == 'binary' else 'mae')
    higher = declared.get('direction', 'maximize' if task == 'binary' else 'minimize') \
        == 'maximize'
    objective_selection = bool(declared)
    candidate = 'fit.logistic' if task == 'binary' else 'fit.linear'
    slots = [candidate] + list(VARIANT_SLOTS[:len(variants)])
    configs, folds = [], None
    for i, slot in enumerate(slots):
        values = fits.get(slot)
        if objectives and slot in objectives:
            objective_item = objectives[slot]
            metric_key = objective_item.get('metric')
            per_fold = [window.get(metric_key) for window in
                        objective_item.get('per_window') or []]
            point = objective_item.get('point')
            if not per_fold or any(v is None for v in per_fold) or point is None:
                per_fold = None
        elif objective_selection:
            fold_items = ((values or {}).get('cross_validation') or {}).get('per_fold') or []
            per_fold = [((item.get('objective') or {}).get('point')) for item in fold_items]
            point = (((values or {}).get('cross_validation') or {}).get('objective') or {}).get(
                'point')
            if not per_fold or any(v is None for v in per_fold) or point is None:
                per_fold = None
        else:
            per_fold = _per_fold(values, metric)
            point = None
        if per_fold is None:
            continue
        if folds is None:
            folds = len(per_fold)
        if len(per_fold) != folds:
            continue
        variant = variants[i - 1] if i else None
        n_features = len((values or {}).get('features') or [])
        fold_mean, sd = _mean_sd(per_fold)
        mean = float(point) if objective_selection else fold_mean
        configs.append({'slot': slot, 'kind': variant.get('kind') if variant else 'candidate',
                        'family': family_of(variant),
                        'question': (variant or {}).get(QUESTION_KEY),
                        'words': variant_words(variant, language) if variant else None,
                        'per_fold': per_fold, 'mean': mean, 'sd': sd,
                        'se': sd / math.sqrt(len(per_fold)) if sd is not None else None,
                        'difference': None, 'within_one_se': None,
                        'complexity': _complexity(variant, n_features)})
    bud = dict(bud)
    out = {k: None for k in SELECTION_KEYS}
    out.update(metric=metric, direction='higher' if higher else 'lower', budget=bud,
               configurations=configs, trials=len(configs), note=SELECTION_NOTE, available=False)
    if not configs or configs[0]['slot'] != candidate or not folds or folds < 2:
        out['advice'] = {'code': 'not_available', 'text': text('advice.not_available', language),
                         'texts': texts('advice.not_available')}
        return out
    out.update(available=True, folds=folds)
    base = configs[0]['per_fold']
    for c in configs[1:]:
        d = [a - b for a, b in zip(c['per_fold'], base)]
        m, sd = _mean_sd(d)
        se = sd / math.sqrt(len(d)) if sd is not None else None
        c['difference'] = {'against': candidate, 'mean': m, 'sd': sd, 'se': se,
                           'low': m - se if se is not None else None,
                           'high': m + se if se is not None else None,
                           'within_fold_noise': bool(se is not None and abs(m) <= se),
                           'definition': 'per-fold paired difference (this configuration minus '
                                         'the candidate), mean plus or minus one standard '
                                         'error'}
    sign = 1 if higher else -1
    best = max(configs, key=lambda c: (sign * c['mean'], -configs.index(c)))
    out['best'] = best['slot']
    if objective_selection and declared.get('aggregation') == 'pooled_counts':
        for c in configs:
            c['within_one_se'] = None
        out['one_se'] = {'available': False,
                         'reason': 'pooled_counts is not an equal-weight fold mean; the '
                                   'legacy one-standard-error heuristic is incoherent'}
        out['optimism'] = {'available': False,
                           'reason': 'no weighted selection-optimism estimator is implemented'}
        out['advice'] = {'code': 'objective_selected', 'stop': False, 'noise': None,
                         'largest_difference': None,
                         'text': 'Choose using the predeclared pooled-count objective.',
                         'texts': {'en': 'Choose using the predeclared pooled-count objective.',
                                   'fr': "Choisissez selon l'objectif pré-déclaré sur les "
                                         'comptages agrégés.'}}
        return out
    se_best = best['se'] or 0.0
    threshold = best['mean'] - sign * se_best
    for c in configs:
        c['within_one_se'] = bool(sign * (c['mean'] - threshold) >= -1e-12)
    eligible = [c for c in configs if c['within_one_se']]
    pick = min(eligible, key=lambda c: (c['complexity'], configs.index(c)))
    out['one_se'] = {'pick': pick['slot'], 'best': best['slot'], 'bound': threshold,
                     'se_of_best': best['se'], 'source': ONE_SE_SOURCE,
                     'text': text('one_se', language), 'texts': texts('one_se'),
                     'simplicity': 'the linear family first, then fewer features, then a '
                                   'stronger penalty; a tie keeps the candidate'}
    gaps = []
    for k in range(folds):
        fold_best = max(sign * c['per_fold'][k] for c in configs)
        gaps.append(fold_best - sign * best['per_fold'][k])
    out['optimism'] = {'estimate': sum(gaps) / folds if len(configs) > 1 else 0.0,
                       'metric': metric, 'configurations': len(configs),
                       'per_fold': gaps if len(configs) > 1 else [0.0] * folds,
                       'method': 'mean over folds of (the fold\'s best configuration minus the '
                                 'configuration best on the mean), in the direction of the '
                                 'metric',
                       'source': OPTIMISM_SOURCE, 'text': text('optimism', language),
                       'texts': texts('optimism'),
                       'note': 'Approximate: an estimate of how much the best mean owes to '
                               'having chosen it among these configurations.'}
    variants_compared = configs[1:]
    noise = configs[0]['se']
    if bud['used'] >= MAX_VARIANTS:
        code = 'budget_exhausted'
    elif not variants_compared:
        code = 'no_variant'
    elif all(c['difference']['within_fold_noise'] for c in variants_compared):
        code = 'fold_noise'
    else:
        code = 'may_continue'
    largest = max((abs(c['difference']['mean']) for c in variants_compared), default=None)
    key = {'budget_exhausted': 'advice.budget_exhausted', 'no_variant': 'advice.no_variant',
           'fold_noise': 'advice.fold_noise', 'may_continue': 'advice.may_continue'}[code]
    out['advice'] = {'code': code, 'stop': code in ('budget_exhausted', 'fold_noise'),
                     'noise': noise, 'largest_difference': largest,
                     'text': text(key, language), 'texts': texts(key)}
    return out


# --- shortlist ---------------------------------------------------------------------------------

SHORTLIST_KEYS = ('constraints', 'evidence', 'families', 'shortlist', 'recommendation',
                  'text', 'texts', 'data_contingent', 'catalogue')


def constraints_of(case_document: Mapping | None) -> dict:
    """The case's declared constraints, with ``none`` for interpretability when absent."""
    declared = (case_document or {}).get('constraints') or {}
    interp = declared.get('interpretability')
    value = interp.get('value') if isinstance(interp, Mapping) else None
    return {'interpretability': value if value in INTERPRETABILITY else 'none',
            'declared': bool(interp)}


def shortlist(case_document: Mapping | None, diag: Mapping | None, task: str,
              language: str = 'en', diag_result: str | None = None) -> dict:
    """The engine's drafted shortlist of model families (see the module docstring)."""
    cons = constraints_of(case_document)
    checks = (diag or {}).get('linear_checks') if isinstance(diag, Mapping) else None
    flags = list((checks or {}).get('flags') or [])
    families = []
    for name in FAMILIES:
        entry = CATALOGUE[name]
        allowed, why = True, None
        if name == 'hgb' and cons['interpretability'] == 'required':
            allowed, why = False, text('excluded.interpretability', language)
        motivated = name in NONLINEAR_FAMILIES and bool(flags) and allowed
        families.append({'family': name, 'model': entry['models'][task],
                         'interpretability': entry['interpretability'],
                         'implementation': entry['implementation'],
                         'diagnostics': entry['diagnostics'], 'default': entry['default'],
                         'allowed': allowed, 'excluded_reason': why, 'motivated': motivated,
                         'words': FAMILY_WORDS[_lang(language)][name]})
    if checks is None and isinstance(diag, Mapping):
        # Diagnostics computed before v0.3 (still current, ``code_compat``) have no checks.
        recommendation, key = 'rerun_diagnostics', 'shortlist.old_diagnostics'
        listed = ['linear']
    elif checks is None:
        recommendation, key = 'run_diagnostics', 'shortlist.no_diagnostics'
        listed = ['linear']
    elif not flags:
        recommendation, key = 'stay_linear', 'shortlist.stay_linear'
        listed = ['linear']
    else:
        recommendation, key = 'compare_nonlinear', 'shortlist.try_nonlinear'
        # The glass box first (it shows the shapes it fits), then the black box when the
        # case allows one.
        listed = ['linear'] + [f['family'] for f in families
                               if f['family'] in NONLINEAR_FAMILIES and f['allowed']]
    return {'constraints': cons,
            'evidence': {'source': diag_result, 'checked': checks is not None, 'flags': flags,
                         'checks': checks},
            'families': families, 'shortlist': listed, 'recommendation': recommendation,
            'text': text(key, language), 'texts': texts(key),
            'data_contingent': bool(flags),
            'catalogue': list(FAMILIES)}


def data_contingency(value: Any, diag: Mapping | None, diag_result: str | None
                     ) -> tuple[bool, dict | None]:
    """``(data_contingent, reason)`` of a ``model_variant`` proposal: a family variant
    proposed while the diagnostics of the linear fit flag a pattern was motivated by them
    (WP-F1); every other variant is a pre-declared alternative."""
    items = variants_of(value)
    informed = [v for v in items if v.get(ORIGIN_KEY) == 'diagnostic_informed']
    families = [v.get('family') for v in items if v.get('kind') == 'family']
    checks = (diag or {}).get('linear_checks') if isinstance(diag, Mapping) else None
    flags = list((checks or {}).get('flags') or [])
    if informed and not flags:
        return True, {'families': families, 'diagnostics': diag_result, 'flags': [],
                      'text': 'This challenger was declared after model evidence and is '
                              'recorded as diagnostic-informed/data-contingent.'}
    if not families or not flags:
        return False, None
    named = ', '.join(f"{f.get('check')} ({f.get('feature') or 'all rows'})" for f in flags)
    return True, {'families': families, 'diagnostics': diag_result, 'flags': flags,
                  'text': f'The family ({", ".join(families)}) is proposed after the diagnostics '
                          f'of the linear fit flagged: {named}. Its comparison is '
                          f'data-contingent: a trial chosen after seeing these rows.'}
