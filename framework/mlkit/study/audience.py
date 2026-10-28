"""Who a message of the engine is written for (v0.2a, WP-A1; CLI-CONTRACT §3.3).

Every sentence the engine emits for a surface carries ``audience``:

* ``junior``: the text may be shown to the junior as it is. It speaks to them in the
  second person or neutrally, and names no command, flag, decision id, or field;
* ``agent``: the text instructs the assistant ("Show the restatement and record the user's
  own words") or describes the junior in the third person. A surface never shows it to the
  junior; the junior variant next to it (``junior_message`` or ``junior_text``) is written
  for them.

The functions here are pure and additive: they never change an existing key, they add
``audience`` and the junior variant. Free of pandas, numpy, and scikit-learn.

v0.3 (WP-C, R21, R36, R37): English is the source language. Every junior variant is
written in the study language (``state.language_of``): the word functions take ``lang``
(``en`` by default) and their French words live next to the English ones here; the French
sentences of the steps and the limits live in :mod:`mlkit.study.junior`.
"""
from __future__ import annotations

import re
from typing import Mapping

JUNIOR, AGENT = 'junior', 'agent'
AUDIENCES = (JUNIOR, AGENT)

# Decisions in words, for the junior (a regression study's model choice included).
DECISION_WORDS = {'prediction_time': 'the prediction moment',
                  'feature_availability': 'the feature availability', 'split': 'the split',
                  'policy': 'the decision policy', 'model_choice': 'the model choice',
                  'conclusion': 'the conclusion',
                  # v0.2a (WP-A4)
                  'success_criterion': 'the success criterion',
                  'preprocessing': 'the preparation of the variables',
                  # v0.2b (WP-B1)
                  'model_variant': 'the variant to compare',
                  'final_test': 'the opening of the final test',
                  # Lot 2026-10-28 (EN-9)
                  'error_metric': 'the error measure'}
# Plan steps in words (the steps without a decision of their own).
STEP_WORDS = {'train_eda': 'the exploration of the data', 'models': 'the model fits',
              'discover_data': 'the discovery of the data'}


# v0.3 (WP-C): the same words in French, with the glossary's usual French terms.
DECISION_WORDS_FR = {'prediction_time': 'le moment de la prédiction',
                     'feature_availability': 'la disponibilité des variables',
                     'split': 'le découpage des données', 'policy': 'la règle de décision',
                     'model_choice': 'le choix du modèle', 'conclusion': 'la conclusion',
                     'success_criterion': 'le critère de succès',
                     'preprocessing': 'la préparation des variables',
                     'model_variant': 'la variante à comparer',
                     'final_test': "l'ouverture de l'échantillon de test final",
                     'error_metric': "la mesure de l'erreur"}
STEP_WORDS_FR = {'train_eda': "l'exploration des données", 'models': "l'ajustement des modèles",
                 'discover_data': 'la découverte des données'}
EN, FR = 'en', 'fr'


def decision_words(decision_id, lang: str = EN) -> str:
    if lang == FR:
        return DECISION_WORDS_FR.get(decision_id) or STEP_WORDS_FR.get(decision_id) \
            or ' '.join(str(decision_id).split('_'))
    return DECISION_WORDS.get(decision_id) or STEP_WORDS.get(decision_id) \
        or ' '.join(str(decision_id).split('_'))


# v0.2a (WP-A7): activities in words, for the junior (an activity id is a raw token). A
# regression study never runs ``policy.*``, so no word here names a decision rule there.
ACTIVITY_WORDS = {'split': 'the split', 'eda.target_rate': 'the outcome rate',
                  'eda.target_summary': 'the target summary',
                  'eda.special_values': 'the special-value check',
                  'eda.rate_by': 'an outcome rate by group',
                  'eda.mean_by': 'a target mean by group',
                  'eda.distribution': 'the distribution of a column',
                  'eda.quality': 'the data quality check',
                  'eda.single_feature_signal': 'the single-feature signal check',
                  'fit.baseline': 'the baseline model', 'fit.logistic': 'the logistic model',
                  'fit.linear': 'the linear model', 'policy.evaluate': 'the policy evaluation',
                  'policy.evaluation': 'the policy evaluation',
                  'evaluate.regression': 'the model comparison',
                  # v0.2b (WP-B1)
                  'fit.variant': 'the variant model',
                  'final_test.evaluation': 'the final test evaluation',
                  # Review round 3 (E3-3): named when they must be run again.
                  'diag.binary': 'the development diagnostics',
                  'diag.regression': 'the development diagnostics',
                  'predictor.capture': 'the captured model'}


ACTIVITY_WORDS_FR = {'split': 'le découpage', 'eda.target_rate': 'le taux de résultat positif',
                     'eda.target_summary': 'le résumé de la cible',
                     'eda.special_values': 'la vérification des valeurs spéciales',
                     'eda.rate_by': 'un taux de résultat positif par groupe',
                     'eda.mean_by': 'une moyenne de la cible par groupe',
                     'eda.distribution': "la distribution d'une colonne",
                     'eda.quality': 'le contrôle de qualité des données',
                     'eda.single_feature_signal': "le signal d'une variable seule",
                     'fit.baseline': 'le modèle de référence',
                     'fit.logistic': 'le modèle logistique', 'fit.linear': 'le modèle linéaire',
                     'policy.evaluate': "l'évaluation de la règle",
                     'policy.evaluation': "l'évaluation de la règle",
                     'evaluate.regression': 'la comparaison des modèles',
                     'fit.variant': 'le modèle variante',
                     'final_test.evaluation': "l'évaluation sur l'échantillon de test final",
                     'diag.binary': 'les diagnostics de développement',
                     'diag.regression': 'les diagnostics de développement',
                     'predictor.capture': 'le modèle capturé'}


def activity_words(activity, lang: str = EN) -> str:
    """An activity id (or a slot, ``eda.rate_by:job``) in words: "an outcome rate by group
    (job)"; an unknown activity reads "an analysis"."""
    base, sep, column = str(activity or '').partition(':')
    if base == 'fit.variant' and column in ('2', '3'):
        # v0.3 (WP-F1): the second and third variants, in words.
        if lang == FR:
            return {'2': 'la deuxième variante', '3': 'la troisième variante'}[column]
        return {'2': 'the second variant model', '3': 'the third variant model'}[column]
    words = (ACTIVITY_WORDS_FR.get(base, 'une analyse') if lang == FR
             else ACTIVITY_WORDS.get(base, 'an analysis'))
    return f'{words} ({column})' if sep and column else words


# Recorded values in words (v0.2a, WP-A7): a rule, a model slot, a verdict. The numbers are
# the value's own; nothing is computed.
MODEL_WORDS = {'fit.linear': 'the linear model', 'fit.baseline': 'the mean baseline',
               'fit.logistic': 'the logistic model', 'fit.variant': 'the variant',
               # v0.3 (WP-F1)
               'fit.variant:2': 'the second variant', 'fit.variant:3': 'the third variant'}
VERDICT_WORDS = {'adopt_policy': 'adopt the policy', 'adopt_model': 'adopt the chosen model',
                 'keep_baseline': 'keep the baseline', 'inconclusive': 'inconclusive'}
MODEL_WORDS_FR = {'fit.linear': 'le modèle linéaire', 'fit.baseline': 'la référence (prédire la moyenne)',
                  'fit.logistic': 'le modèle logistique', 'fit.variant': 'la variante',
                  # v0.3 (WP-F1)
                  'fit.variant:2': 'la deuxième variante',
                  'fit.variant:3': 'la troisième variante'}
VERDICT_WORDS_FR = {'adopt_policy': 'adopter la règle', 'adopt_model': 'adopter le modèle choisi',
                    'keep_baseline': 'garder le modèle de référence',
                    'inconclusive': 'non concluant'}


def verdict_words(verdict, lang: str = EN) -> str:
    table = VERDICT_WORDS_FR if lang == FR else VERDICT_WORDS
    return table.get(verdict, ' '.join(str(verdict or '').split('_')))


def rule_words(rule, lang: str = EN) -> str:
    """``capacity:100`` as "select the top 100 by score", ``threshold:0.2`` as "select every
    row scored 0.2 or more"; anything else as it is. B6c (Low): the words fit every case
    (a call, an email, an inspection), so they never name one action."""
    kind, _, k = str(rule).partition(':')
    if lang == FR:
        if kind == 'capacity' and k:
            return f'sélectionner les {k} meilleurs scores'
        if kind == 'threshold' and k:
            return f'sélectionner chaque ligne de score {k} ou plus'
        if kind == 'share' and k:
            return f'sélectionner les {share_percent(k, lang)} meilleurs scores'
        return str(rule)
    if kind == 'capacity' and k:
        return f'select the top {k} by score'
    if kind == 'threshold' and k:
        return f'select every row scored {k} or more'
    if kind == 'share' and k:
        return f'select the top {share_percent(k)} by score'
    return str(rule)


# B6c (Low): the cross-validation methods in words.
CV_METHOD_WORDS = {'kfold_stratified': 'stratified on the outcome',
                   'kfold_quantile': 'stratified on target quantiles',
                   # v0.3 (WP-C, R15): "folds", never home-made "blocks".
                   'temporal_folds': 'folds in time order'}
CV_METHOD_WORDS_FR = {'kfold_stratified': 'stratifiée sur le résultat',
                      'kfold_quantile': 'stratifiée sur les quantiles de la cible',
                      'temporal_folds': "plis dans l'ordre du temps"}


def share_percent(p, lang: str = EN) -> str:
    """``0.1`` (or ``"0.1"``) as ``10%``, ``0.125`` as ``12.5%`` (French ``10 %``,
    ``12,5 %``)."""
    pct = 100 * float(p)
    text = f'{pct:.0f}' if abs(pct - round(pct)) < 1e-9 else f'{pct:g}'
    return f'{text.replace(".", ",")} %' if lang == FR else f'{text}%'


def policy_words(value, lang: str = EN) -> str:
    """A policy value in words (WP-B1: with the model its rule applies to when it is the
    variant): "call the top 100 by score, with the variant"."""
    rule, sep, model = str(value).partition('@')
    words = rule_words(rule, lang)
    if not (sep and model):
        return words
    return (f'{words}, avec {model_words(model, lang)}' if lang == FR
            else f'{words}, with {model_words(model)}')


def variant_words(value, lang: str = EN) -> str:
    """A ``model_variant`` value in words (WP-B1; v0.3, WP-F1: a list of variants, each in
    words, :func:`mlkit.study.trials.value_words`)."""
    if not isinstance(value, Mapping):
        return str(value)
    from . import trials
    if trials.is_list_value(value) or value.get('kind') in ('tuned', 'family'):
        return trials.value_words(value, lang)
    if value.get('kind') == 'regularisation':
        if lang == FR:
            return {'weak': 'une régularisation plus faible',
                    'strong': 'une régularisation plus forte'}.get(
                value.get('strength'), 'une autre régularisation')
        return {'weak': 'weaker regularisation', 'strong': 'stronger regularisation'}.get(
            value.get('strength'), 'another regularisation')
    if value.get('kind') == 'drop_group':
        return (f'sans le groupe « {value.get("group")} »' if lang == FR
                else f'without the group "{value.get("group")}"')
    return str(value.get('kind'))


def model_words(slot, lang: str = EN) -> str:
    table = MODEL_WORDS_FR if lang == FR else MODEL_WORDS
    return table.get(str(slot), ' '.join(str(slot).replace('fit.', '').split('_')))


_PLAN_REF = re.compile(r'\s*\(§\s*3\.7 row \d+(?::[^)]*)?\)')


def reason_words(reason, lang: str = EN) -> str:
    """B6c (Low): a staleness or reconfirmation reason in the junior's words: no internal
    reference ("§3.7 row 5: policy.parameter"), decisions and activities in words. In French
    (WP-C) only the decision or the activity is named: the rest of an engine reason is
    English."""
    text = _PLAN_REF.sub('', str(reason or '')).strip()
    m = re.match(r'([a-z_]+) changed\b', text)
    if m and m.group(1) in DECISION_WORDS:
        if lang == FR:
            return _capital(f'{decision_words(m.group(1), lang)} a changé')
        return _capital(f'{decision_words(m.group(1))} changed{text[m.end():]}')
    m = re.fullmatch(r'code of activity ([\w.:]+) changed', text)
    if m:
        if lang == FR:
            return _capital(f'le code de {activity_words(m.group(1), lang)} a changé')
        return _capital(f'the code of {activity_words(m.group(1))} changed')
    if lang == FR:
        return 'Un élément dont elle dépend a changé'
    return text


def join(words, lang: str = EN) -> str:
    words = list(words)
    if not words:
        return ''
    last = ' et ' if lang == FR else ' and '
    return words[0] if len(words) == 1 else ', '.join(words[:-1]) + last + words[-1]


def _capital(text: str) -> str:
    return text[:1].upper() + text[1:]



# --- next_action -------------------------------------------------------------------------

def _junior_next(action: Mapping, lang: str = EN) -> tuple[str, str]:
    """``(audience of message, junior_message)`` of one ``next_action``; the junior message
    is in ``lang`` (v0.3, WP-C)."""
    kind = action.get('kind')
    message = str(action.get('message') or '')
    fr = lang == FR
    if kind == 'outcome_unknown':
        # WP-A7: the run is named in words (the activity id is a raw token).
        if fr:
            return AGENT, (f'Une exécution de {activity_words(action.get("activity"), lang)} '
                           "s'est arrêtée avant la fin, et son résultat est inconnu. Elle n'est "
                           'pas en cours et ne redémarre pas seule ; on vous demandera avant de '
                           "l'enregistrer comme interrompue.")
        return AGENT, (f'A run of {activity_words(action.get("activity"))} stopped before it '
                       'finished, and its outcome is unknown. It is not in progress and does '
                       'not restart by itself; you will be asked before it is recorded as '
                       'interrupted.')
    if kind == 'acknowledge_interruption':
        if fr:
            named = (f'Une exécution de {activity_words(action["activity"], lang)}'
                     if action.get('activity') else 'Une exécution')
            return AGENT, (f'{named} a été interrompue et son résultat est inconnu. Elle ne '
                           "redémarre pas seule ; on vous demandera avant de l'enregistrer comme "
                           'interrompue.')
        named = (f'A run of {activity_words(action["activity"])}' if action.get('activity')
                 else 'A run')
        return AGENT, (f'{named} was interrupted and its outcome is unknown. It does not '
                       'restart by itself; you will be asked before it is recorded as '
                       'interrupted.')
    if action.get('review') and kind in ('reconfirm', 'await_user_words'):
        # L9 (R20): the review of a decision the automatic mode recorded.
        words = decision_words(action.get('decision'), lang)
        if fr:
            return AGENT, (f'La décision sur {words} a été prise par le mode automatique, sans '
                           'vos mots. Relisez-la : adoptez-la avec vos propres mots, ou dites '
                           'ce que vous changez.')
        return AGENT, (f'The decision on {words} was made by the automatic mode, without your '
                       'words. Review it: adopt it in your own words, or say what you change.')
    if kind == 'reconfirm' and action.get('decision') == 'final_test':
        # Review round 4 (E4-1): a final test confirmed but not opened, whose basis changed.
        if fr:
            return AGENT, ("Le test final est toujours scellé : aucune de ses lignes n'a été "
                           "lue. Vous aviez confirmé son ouverture, mais ce sur quoi elle "
                           "reposait a changé avant qu'il soit ouvert ; il ne s'ouvre donc "
                           "qu'après une nouvelle confirmation, avec vos propres mots, sur la "
                           "configuration que l'étude choisit maintenant.")
        return AGENT, ('The final test is still sealed: none of its rows was read. You '
                       'confirmed its opening, but what it rests on changed before it was '
                       'opened, so it opens only once you confirm it again, in your own words, '
                       'on the configuration the study now chooses.')
    if kind == 'reconfirm':
        if fr:
            return AGENT, (f'Votre réponse sur {decision_words(action.get("decision"), lang)} '
                           'doit être confirmée à nouveau : un élément dont elle dépend a '
                           'changé après votre confirmation.')
        return AGENT, (f'Your answer on {decision_words(action.get("decision"))} must be '
                       'confirmed again: something it depends on changed after you confirmed '
                       'it.')
    if kind == 'await_user_words':
        if fr:
            return AGENT, (f'Une proposition sur {decision_words(action.get("decision"), lang)} '
                           'attend votre réponse. Lisez sa reformulation et dites si vous '
                           "l'adoptez, ou ce que vous changeriez.")
        return AGENT, (f'A proposal on {decision_words(action.get("decision"))} is waiting for '
                       'your answer. Read its restatement and say whether you adopt it, or '
                       'what you would change.')
    if kind == 'resolve_hold':
        # Review round 6 (area E): a decision the junior put on hold, in their own words.
        said = str(action.get('user_words') or '').strip()
        if fr:
            return AGENT, (f'Vous avez mis {decision_words(action.get("decision"), lang)} en '
                           f'attente, avec vos mots : « {said} ». Cette condition est-elle '
                           'remplie maintenant ? Votre réponse, avec vos propres mots, lève '
                           "l'attente ou la maintient ; tant qu'elle est en attente, rien de ce "
                           "qu'elle couvre n'est confirmé.")
        return AGENT, (f'You put {decision_words(action.get("decision"))} on hold, in your '
                       f'words: "{said}". Is that condition met now? Your answer, in your own '
                       'words, lifts the hold or keeps it; while it is on hold, nothing it '
                       'covers is confirmed.')
    if kind == 'blocked':
        needed = join((decision_words(r, lang) for r in action.get('requires') or []), lang)
        if fr:
            return AGENT, (f'Cette étape attend des étapes précédentes : {needed}.' if needed
                           else 'Cette étape attend une étape précédente.')
        return AGENT, (f'This step waits for earlier steps: {needed}.' if needed
                       else 'This step waits for an earlier step.')
    if kind == 'show_data_card':
        # WP-A4 (R2): step 0, informational.
        if fr:
            return AGENT, ("D'abord, regardez les données avec l'assistant : ce que décrit une "
                           'ligne, les colonnes et ce que chacune signifie, et huit lignes '
                           "tirées au hasard. Rien n'est décidé à cette étape.")
        return AGENT, ('First, look at the data with the assistant: what one row describes, '
                       'the columns and what each one means, and eight rows drawn at random. '
                       'Nothing '
                       'is decided at this step.')
    if kind == 'read_exploration':
        # Lot 2026-10-28 (EN-12, R61): the pause after the exploration.
        if fr:
            return JUNIOR, ("Les graphiques de l'exploration sont affichés et aucun modèle "
                            "n'est encore ajusté. Lisez-les, puis dites si l'on passe aux "
                            'modèles.')
        return JUNIOR, ("The exploration's charts are shown and no model is fitted yet. Read "
                        'them, then say whether we move on to the models.')
    if kind in ('propose', 'run'):
        # The step's question, written for the junior (state.STEPS); WP-C: in French, its
        # translation (``junior.step_text``).
        if fr:
            from . import junior
            return JUNIOR, junior.step_text(message, lang)
        return JUNIOR, message
    if kind == 'done':
        if fr:
            return AGENT, ("Toutes les étapes du plan sont faites. Avant de vous appuyer sur la "
                           'conclusion, lisez les limites que le rapport énumère.')
        return AGENT, ('Every step of the plan is done. Before relying on the conclusion, read '
                       'the limits the report lists.')
    return AGENT, message


def next_action(action: Mapping | None, lang: str = EN) -> dict | None:
    """``action`` with ``audience`` (of its ``message``) and ``junior_message`` added.

    ``junior_message`` is always present: equal to ``message`` when that is already written
    for the junior (a step question) in an English study, a second-person sentence without
    command, flag, or id names otherwise. v0.3 (WP-C): it is written in the study language
    ``lang``; ``message`` stays the English source."""
    if action is None:
        return None
    out = dict(action)
    audience, junior = _junior_next(action, lang)
    out['audience'] = audience
    out['junior_message'] = junior
    return out


# --- not_yet_defensible ------------------------------------------------------------------

def _junior_limit(item: Mapping, lang: str = EN) -> str | None:
    """The junior variant of a limit written for the agent, or None when its text is
    already written for the junior (in English; WP-C: a French study always gets the
    French text, :func:`junior.limit_fr`)."""
    kind = item.get('id')
    if lang == FR:
        from . import junior
        return junior.limit_fr(item)
    if kind == 'unconfirmed_decisions':
        named = join(decision_words(d) for d in item.get('decisions') or [])
        return f'Not confirmed by you yet: {named}.'
    if kind == 'open_holds':
        return ('You set a condition that is not resolved yet, so nothing it covers can be '
                'confirmed until your own words resolve it: '
                + join(decision_words(d) for d in item.get('decisions') or []) + '.')
    if kind == 'conclusion_outdated':
        return ('The conclusion was confirmed before a decision it summarizes changed, so its '
                'text may no longer describe the study; you will be asked to confirm it again.')
    if kind == 'delegated_decisions':
        named = join(decision_words(d) for d in item.get('decisions') or [])
        return (f'You delegated these to the assistant\'s recommended default, so they are not '
                f'your own judgment: {named}.')
    if kind == 'automatic_decisions_to_review':
        named = join(decision_words(d) for d in item.get('decisions') or [])
        return ('Automatic study: not defensible until reviewed. The automatic mode decided '
                f'these without your words; adopt or change each one in your own words: '
                f'{named}.')
    if kind == 'final_test_opened_automatically':
        return ('The final test was opened automatically, by the demonstration mode, not by '
                'your decision. Its one evaluation stands and the opening cannot be redone; '
                'anything changed since is marked as made after the final test.')
    if kind == 'stale_results':
        return 'Some results are out of date and are computed again before they are cited.'
    if kind == 'adopted_rule_not_evaluated':
        # B6c (Low): the rule in words, never its token.
        rules = join(rule_words(r) for r in item.get('rules') or [])
        return (f'The adopted policy ({rules}) has no current evaluation; its figures are cited '
                f'again once it is evaluated again.')
    return None


# The limits whose English ``text`` is written for the agent (their junior variant differs).
AGENT_LIMITS = ('unconfirmed_decisions', 'open_holds', 'conclusion_outdated',
                'delegated_decisions', 'stale_results', 'adopted_rule_not_evaluated',
                # L9 (R20): written about the junior; their variants speak to them.
                'automatic_decisions_to_review', 'final_test_opened_automatically')


# Contract P1.11 (CLI-CONTRACT §17.2.2): the severity of each ``not_yet_defensible`` id, which
# the study panel's header pill reads (``status --summary --digest`` ``defensibility``), moved
# from the panel's own table (``media/copy/junior.js`` ``SEVERITY``). ``blocking``: the study
# cannot be defended while it holds; ``caveat``: a limit of the evidence; ``not_final``: a
# step not done yet; ``context``: always true of such a study. An id not listed is a
# ``caveat``. Two ids depend on the item (``panel_digest``): ``unconfirmed_decisions`` is
# blocking when one of its decisions was reopened, ``stale_results`` when a decision cites
# them. (Kept here, not in ``governance``, whose source is part of every fit's code
# fingerprint: editing it would make every existing study's results stale.)
BLOCKING, CAVEAT, NOT_FINAL, CONTEXT = 'blocking', 'caveat', 'not_final', 'context'
SEVERITIES = (BLOCKING, CAVEAT, NOT_FINAL, CONTEXT)
LIMIT_SEVERITY = {
    'sources_changed': BLOCKING, 'result_integrity': BLOCKING,
    'interrupted_executions': BLOCKING, 'stale_results': BLOCKING, 'code_changed': BLOCKING,
    'automatic_decisions_to_review': BLOCKING, 'open_holds': BLOCKING,
    'conclusion_outdated': BLOCKING, 'changed_after_final_test': BLOCKING,
    'final_test_opening_interrupted': BLOCKING, 'inconclusive_without_choice': BLOCKING,
    'adopted_rule_not_evaluated': BLOCKING, 'verdict_contradicts_criterion': BLOCKING,
    'uncertain_features_included': CAVEAT, 'delegated_decisions': CAVEAT,
    'small_validation_partition': CAVEAT, 'capacity_exceeds_validation': CAVEAT,
    'high_cardinality_grouping': CAVEAT, 'grouped_split_unsupported': CAVEAT,
    'delayed_labels_excluded': CAVEAT, 'capacity_assumed_for_exercise': CAVEAT,
    'verdict_keeps_baseline_against_criterion': CAVEAT,
    'data_contingent_preprocessing': CAVEAT, 'final_test_opened_automatically': CAVEAT,
    'unconfirmed_decisions': NOT_FINAL, 'final_test_sealed': NOT_FINAL,
    'validation_is_not_independent': NOT_FINAL,
    'public_data_already_explored': CONTEXT, 'no_time_or_entity_identifier': CONTEXT,
    'no_causality': CONTEXT, 'workbench_not_tracked': CONTEXT,
}


def limit(item: Mapping, lang: str = EN) -> dict:
    """A ``not_yet_defensible`` item with ``audience`` (of its ``text``) and
    ``junior_text``: the text itself when it is written for the junior, its junior
    variant otherwise. v0.3 (WP-C): ``junior_text`` is in the study language ``lang``;
    ``audience`` still describes the English ``text``."""
    out = dict(item)
    junior = _junior_limit(item, lang)
    out['audience'] = AGENT if item.get('id') in AGENT_LIMITS else JUNIOR
    out['junior_text'] = junior if junior is not None else str(item.get('text') or '')
    return out


def junior_text(item: Mapping, lang: str = EN) -> str:
    """The text of a limit that may be shown to the junior."""
    if item.get('junior_text'):
        return item['junior_text']
    junior = _junior_limit(item, lang)
    return junior if junior is not None else str(item.get('text') or '')


# --- deliverables ------------------------------------------------------------------------

ARTIFACT_WORDS = {'report': 'the report', 'notebook': 'the generated notebook',
                  'editable': 'the editable study notebook',
                  'workbench': 'the workbench'}
ARTIFACT_WORDS_FR = {'report': 'le rapport', 'notebook': 'le notebook généré',
                     'editable': "le notebook éditable de l'étude",
                     'workbench': "l'atelier (workbench)"}


def artifact(name: str, item: Mapping, lang: str = EN) -> dict:
    """``{audience, junior_message}`` of a deliverable's ``message`` (``currency.message``):
    it names paths and asks for a render, so it is written for the agent."""
    status = item.get('status')
    if lang == FR:
        label = ARTIFACT_WORDS_FR.get(name, ' '.join(str(name).split('_')))
        if name == 'editable':
            junior = (f"{_capital(label)} suit le notebook généré jusqu'à votre première "
                      "modification ; ensuite il n'est jamais écrasé et ne constitue pas "
                      "une preuve officielle.")
        elif item.get('generated') is False or name == 'workbench':
            junior = (f"{_capital(label)} est votre espace libre : il est créé une fois, jamais "
                      "écrasé, et n'est pas suivi par l'étude.")
        elif status == 'ok':
            junior = f'{_capital(label)} est à jour.'
        elif status == 'not_rendered':
            junior = f"{_capital(label)} n'a pas encore été écrit."
        elif status == 'failed':
            junior = (f'La dernière mise à jour de « {label} » a échoué ; ne vous y fiez '
                      "pas tant qu'il n'est pas réécrit.")
        else:
            junior = (f"{_capital(label)} n'est plus à jour : l'étude a changé après son "
                      "écriture. Ne vous y fiez pas tant qu'il n'est pas réécrit.")
        return {'audience': AGENT, 'junior_message': junior}
    label = ARTIFACT_WORDS.get(name, ' '.join(str(name).split('_')))
    if name == 'editable':
        junior = (f'{_capital(label)} follows the generated notebook until your first edit; '
                  'after that it is never overwritten and is not official evidence.')
    elif item.get('generated') is False or name == 'workbench':
        junior = (f'{_capital(label)} is your free space: it is created once, never '
                  'overwritten, and not tracked by the study.')
    elif status == 'ok':
        junior = f'{_capital(label)} is up to date.'
    elif status == 'not_rendered':
        junior = f'{_capital(label)} has not been written yet.'
    elif status == 'failed':
        junior = (f'The last update of {label} failed; do not rely on it until it is '
                  'written again.')
    else:
        junior = (f'{_capital(label)} is out of date: the study changed after it was '
                  'written. Do not rely on it until it is written again.')
    return {'audience': AGENT, 'junior_message': junior}


def annotate_view(view: dict) -> dict:
    """Annotate a built view in place: ``next_action`` and every
    ``not_yet_defensible`` item get their audience (used by :func:`mlkit.study.view.build`)."""
    lang = view.get('language') or EN
    view['next_action'] = next_action(view.get('next_action'), lang)
    view['not_yet_defensible'] = [limit(x, lang) for x in view.get('not_yet_defensible') or []]
    return view


__all__ = ['JUNIOR', 'AGENT', 'AUDIENCES', 'next_action', 'limit', 'junior_text', 'artifact',
           'annotate_view', 'decision_words', 'join', 'activity_words', 'rule_words',
           'model_words', 'VERDICT_WORDS', 'policy_words', 'variant_words', 'verdict_words',
           'EN', 'FR']
