"""Junior-ready payloads (v0.3, WP-C; remarks R15, R18, R19, R21, R30, R36, R37).

Two jobs, both pure (no file, no pandas, numpy, or scikit-learn):

1. **The study language.** English is the source; every engine text written for the junior
   has a French variant, chosen by the study language (``state.language_of``): the step
   titles and questions (:func:`step_text`, keyed by their English source so a new English
   text without a translation fails the tests), the limits (:func:`limit_fr`), the data card
   lines (:func:`data_card_fr`). The word functions of :mod:`mlkit.study.audience` take the
   language too. Terms follow the glossary verbatim (``term`` and ``term_fr``): "jeu
   d'entraînement", "jeu de validation", "pli", "validation croisée à k plis", "prédictions
   hors pli", "échantillon de test final (holdout)", "échantillon de développement".

2. **What the agent relays** (:func:`enrich`, called by ``view.build``). ``next_action``
   gains ``junior_digest`` (at most :data:`MAX_DIGEST_WORDS` words, in the study language:
   the statistical term first, then this study's example), ``recommended`` (the engine's
   default with a one-line why, or null) and ``question`` (the one question to ask, or null
   when nothing is asked), plus ``language``; at the success criterion,
   ``criterion_options`` (:func:`mlkit.study.criterion.options`); at the feature
   availability, ``default_value`` drafted from the case. The agent relays these instead of
   composing, which cuts its reads per pause. No result id appears in these texts.
"""
from __future__ import annotations

import copy
from typing import Any, Mapping

from . import audience
from . import state as st

EN, FR = 'en', 'fr'
MAX_DIGEST_WORDS = 200
ENRICH_KEYS = ('language', 'junior_digest', 'recommended', 'question')
RECOMMENDED_KEYS = ('value', 'why')


def _t(lang: str, en: str, fr: str) -> str:
    return fr if lang == FR else en


def _pct(x: float, lang: str) -> str:
    text = f'{100 * x:.1f}'
    return f'{text.replace(".", ",")} %' if lang == FR else f'{text}%'


def _int(n: int, lang: str) -> str:
    text = f'{n:,}'
    return text.replace(',', ' ') if lang == FR else text


# --- step titles and questions in French ----------------------------------------------------

def _steps_fr() -> dict[str, str]:
    S = {s['id']: s for s in st.STEPS}
    R = {s['id']: s for s in st.REGRESSION_STEPS}
    cv, rcv = st.CV_STEP_TEXTS, st.REGRESSION_CV_STEP_TEXTS
    b1_final_regression = next(s for s in st.B1_REGRESSION_STEPS if s['id'] == st.FINAL_TEST)
    return {
        # titles
        S['prediction_time']['title']: 'Définir le moment de la prédiction',
        S['feature_availability']['title']: 'Décider quelles variables sont disponibles au '
                                            'moment de la prédiction',
        S['split']['title']: 'Découper les données avant de les explorer',
        S['train_eda']['title']: "Explorer le jeu d'entraînement",
        S['models']['title']: 'Ajuster un modèle de référence et un modèle logistique',
        S['policy']['title']: 'Choisir une règle de décision',
        S['conclusion']['title']: 'Conclure avec mesure',
        R['models']['title']: 'Ajuster une moyenne de référence et un modèle linéaire',
        R['model_choice']['title']: 'Choisir le modèle',
        st.DISCOVER_STEP['title']: 'Découvrir les données',
        st.SUCCESS_STEP['title']: 'Fixer le critère de succès avant de voir un modèle',
        st.PREPROCESSING_STEP['title']: 'Décider comment le modèle prépare les variables',
        st.VARIANT_STEP['title']: 'Choisir les variantes à comparer',
        st.FINAL_TEST_STEP['title']: "Ouvrir une fois l'échantillon de test final",
        cv['train_eda']['title']: "Explorer l'échantillon de développement",
        # questions
        S['prediction_time']['question']: 'À quel moment la prédiction est-elle faite, et '
                                          "qu'est-ce qui est connu à ce moment-là ?",
        S['feature_availability']['question']: 'Quelles variables sont connues au moment de la '
                                               'prédiction, et lesquelles faut-il exclure ?',
        S['split']['question']: "Comment les lignes sont-elles réparties entre le jeu "
                                "d'entraînement et le jeu de validation, avant toute "
                                'exploration de la cible ?',
        S['train_eda']['question']: "Que montre le jeu d'entraînement sur le résultat et les "
                                    'valeurs spéciales ? Les autres explorations (la vue '
                                    "d'ensemble de la qualité, les taux par variable, les "
                                    "distributions, le signal d'une variable seule) répondent "
                                    "chacune à une question posée d'abord ; chaque regard sur "
                                    'le résultat est compté.',
        S['models']['question']: 'De combien un modèle simple fait-il mieux qu\'un modèle de '
                                 'référence constant, sur le jeu de validation ?',
        S['policy']['question']: 'Quelle règle transforme les scores en actions (un seuil, une '
                                 'capacité ou une part), et que coûte-t-elle et que '
                                 'rapporte-t-elle ?',
        S['conclusion']['question']: 'Que peut-on dire, pour quel usage, et avec quelles '
                                     'limites ? Garder le modèle de référence est un résultat '
                                     'valable.',
        R['train_eda']['question']: "Que montre le jeu d'entraînement sur la distribution de "
                                    'la cible et les valeurs spéciales ? Les autres '
                                    "explorations (la vue d'ensemble de la qualité, les "
                                    'moyennes par variable, les distributions, le signal '
                                    "d'une variable seule) répondent chacune à une question "
                                    "posée d'abord ; chaque regard sur la cible est compté.",
        R['models']['question']: "Quelles prédictions la moyenne du jeu d'entraînement et un "
                                 'modèle linéaire donnent-ils pour le jeu de validation ?',
        R['model_choice']['question']: 'Le modèle linéaire réduit-il assez l\'erreur de '
                                       'validation de la moyenne de référence, dans l\'unité '
                                       'de la cible, pour être adopté, compte tenu des '
                                       'intervalles appariés et des résidus ?',
        st.DISCOVER_STEP['question']: 'Que décrit une ligne, quelles colonnes y a-t-il et que '
                                      'signifie chacune, et à quoi ressemblent quelques '
                                      'lignes ?',
        st.SUCCESS_STEP['question']: 'La précision est la part des lignes sélectionnées par une '
                                     'règle qui se révèlent positives ; le rappel est la part '
                                     'de toutes les lignes positives que la règle atteint. Le '
                                     'modèle de référence donne le même score à chaque ligne, '
                                     'donc sa précision est le taux de base. La règle dit sur '
                                     'quelles lignes vous agissez : la meilleure part ou le '
                                     'meilleur nombre de scores, ou les lignes au-dessus d\'un '
                                     'seuil de score. Avec un nombre fixé de lignes, précision, '
                                     'rappel et lift classent les modèles de la même façon ; '
                                     'avec un seuil, ils diffèrent. Choisissez d\'abord la '
                                     'métrique. '
                                     'Combien de points de pourcentage au-dessus du modèle de '
                                     'référence, à la règle que vous adopterez, rendraient le '
                                     'modèle utile ? Le critère est fixé maintenant, avant '
                                     'tout ajustement de modèle.',
        st.REGRESSION_SUCCESS_STEP['question']: "L'erreur absolue moyenne (MAE) est la taille "
                                                "moyenne de l'erreur d'une prédiction, dans "
                                                "l'unité de la cible. La moyenne de référence "
                                                'prédit, pour chaque ligne du jeu de '
                                                'validation, la moyenne de la cible sur le jeu '
                                                "d'entraînement. De combien l'erreur de "
                                                'validation du modèle doit-elle être plus '
                                                'petite que celle de la moyenne de référence '
                                                'pour qu\'il soit utile ? Le critère est fixé '
                                                'maintenant, avant tout ajustement de modèle.',
        st.PREPROCESSING_STEP['question']: 'Comment le modèle doit-il traiter les valeurs '
                                           'manquantes, les catégories rares, les valeurs '
                                           'extrêmes et les variables asymétriques ? Chaque '
                                           "paramètre est appris sur le jeu d'entraînement "
                                           'seulement.',
        st.VARIANT_STEP['question']: 'Quelles variantes du modèle candidat, trois au plus et '
                                     'chacune avec la question à laquelle elle répond, comparer '
                                     'avec lui sous la même évaluation : la pénalité choisie '
                                     'par validation croisée imbriquée, une régularisation plus '
                                     'forte ou plus faible, le modèle sans un groupe de '
                                     'variables, ou une autre famille de modèles quand les '
                                     'diagnostics montrent une forme que le modèle linéaire ne '
                                     'suit pas ?',
        st.FINAL_TEST_STEP['question']: 'Maintenant que le modèle et la règle sont choisis, '
                                        "ouvrez-vous l'échantillon de test final scellé, une "
                                        'seule fois, pour mesurer la configuration choisie '
                                        "sur des lignes que rien n'a vues ? Ensuite, tout "
                                        "changement est fait après le test final.",
        b1_final_regression['question']: 'Maintenant que le modèle est choisi, ouvrez-vous '
                                         "l'échantillon de test final scellé, une seule fois, "
                                         "pour le mesurer sur des lignes que rien n'a vues ? "
                                         'Ensuite, tout changement est fait après le test '
                                         'final.',
        cv['split']['question']: "Comment l'échantillon de développement est-il découpé en "
                                 'plis pour la validation croisée à k plis, avant toute '
                                 'exploration de la cible ? Chaque pli est à son tour le pli '
                                 'de validation, prédit par un modèle ajusté sur les autres '
                                 "plis, les plis d'entraînement.",
        cv['train_eda']['question']: "Que montre l'échantillon de développement sur le "
                                     'résultat et les valeurs spéciales ? Les autres '
                                     "explorations (la vue d'ensemble de la qualité, les taux "
                                     'par variable, les distributions, le signal d\'une '
                                     'variable seule) répondent chacune à une question posée '
                                     "d'abord ; chaque regard sur le résultat est compté.",
        cv['preprocessing']['question']: 'Comment le modèle doit-il traiter les valeurs '
                                         'manquantes, les catégories rares, les valeurs '
                                         'extrêmes et les variables asymétriques ? Chaque '
                                         "paramètre est appris seulement sur les plis "
                                         "d'entraînement de chaque modèle, jamais sur son pli "
                                         'de validation.',
        cv['models']['question']: "De combien un modèle simple fait-il mieux qu'un modèle de "
                                  'référence constant, mesuré hors pli sur l\'échantillon de '
                                  'développement ?',
        rcv['success_criterion']['question']: "L'erreur absolue moyenne (MAE) est la taille "
                                              "moyenne de l'erreur d'une prédiction, dans "
                                              "l'unité de la cible. La moyenne de référence "
                                              "prédit, pour chaque ligne d'un pli de "
                                              'validation, la moyenne des plis '
                                              "d'entraînement. De "
                                              "combien l'erreur hors pli du modèle doit-elle "
                                              'être plus petite que celle de la moyenne de '
                                              "référence pour qu'il soit utile ? Le critère est "
                                              'fixé maintenant, avant tout ajustement de '
                                              'modèle.',
        rcv['train_eda']['question']: "Que montre l'échantillon de développement sur la "
                                      'distribution de la cible et les valeurs spéciales ? Les '
                                      "autres explorations (la vue d'ensemble de la qualité, "
                                      'les moyennes par variable, les distributions, le signal '
                                      "d'une variable seule) répondent chacune à une question "
                                      "posée d'abord ; chaque regard sur la cible est compté.",
        rcv['models']['question']: 'Quelles prédictions la moyenne de référence et un modèle '
                                   "linéaire donnent-ils pour chaque ligne de l'échantillon de "
                                   'développement, prédite hors pli ?',
        rcv['model_choice']['question']: 'Le modèle linéaire réduit-il assez l\'erreur hors pli '
                                         'de la moyenne de référence, dans l\'unité de la '
                                         'cible, pour être adopté, compte tenu des intervalles '
                                         'appariés et des résidus ?',
    }


_STEPS_FR: dict[str, str] | None = None


def step_text(text: str, lang: str = EN) -> str:
    """A step title or question in ``lang`` (its English source when ``lang`` is English or
    no translation exists; the tests require one for every step text)."""
    global _STEPS_FR
    if lang != FR:
        return text
    if _STEPS_FR is None:
        _STEPS_FR = _steps_fr()
    return _STEPS_FR.get(text, text)


def all_step_texts() -> list[str]:
    """Every English step title and question of every plan variant (for the tests)."""
    groups = [st.STEPS, st.REGRESSION_STEPS, st.FULL_STEPS, st.FULL_REGRESSION_STEPS,
              st.B1_STEPS, st.B1_REGRESSION_STEPS]
    for task, steps in st.B1_STEPS_BY_TASK.items():
        texts = st.CV_STEP_TEXTS_BY_TASK[task]
        groups.append(tuple(dict(s, **texts.get(s['id'], {})) for s in steps))
    out: list[str] = []
    for g in groups:
        for s in g:
            for k in ('title', 'question'):
                if s[k] not in out:
                    out.append(s[k])
    return out


# --- limits in French ------------------------------------------------------------------------

def _named(ids, lang=FR) -> str:
    return audience.join((audience.decision_words(d, lang) for d in ids or []), lang)


def limit_fr(item: Mapping) -> str:
    """The French junior text of a ``not_yet_defensible`` item (every id the engine emits;
    an unknown id gets a neutral sentence, never English)."""
    kind = item.get('id')
    cols = ', '.join(str(c) for c in item.get('features') or [])
    if kind == 'unconfirmed_decisions':
        return f'Pas encore confirmé par vous : {_named(item.get("decisions"))}.'
    if kind == 'open_holds':
        return ("Vous avez posé une condition qui n'est pas encore levée : rien de ce qu'elle "
                'couvre ne peut être confirmé tant que vos propres mots ne la lèvent pas : '
                f'{_named(item.get("decisions"))}.')
    if kind == 'conclusion_outdated':
        return ('La conclusion a été confirmée avant qu\'une décision qu\'elle résume ne '
                'change : son texte peut ne plus décrire l\'étude ; on vous demandera de la '
                'confirmer à nouveau.')
    if kind == 'delegated_decisions':
        return ("Vous avez délégué ces décisions à la recommandation de l'assistant ; elles "
                f'ne sont donc pas votre propre jugement : {_named(item.get("decisions"))}.')
    if kind == 'stale_results':
        return ('Certains résultats ne sont plus à jour et sont recalculés avant d\'être '
                'cités.')
    if kind == 'adopted_rule_not_evaluated':
        rules = audience.join((audience.rule_words(r, FR) for r in item.get('rules') or []),
                              FR)
        return (f"La règle adoptée ({rules}) n'a pas d'évaluation à jour ; ses chiffres seront "
                'cités de nouveau une fois réévaluée.')
    if kind == 'validation_is_not_independent':
        text = str(item.get('text') or '')
        if text.startswith('Out-of-fold'):
            what = ('les modèles et la variante' if 'the models and the variant' in text
                    and 'rule' not in text else 'les modèles, la variante et la règle')
            return (f'Les prédictions hors pli de l\'échantillon de développement servent à '
                    f'comparer {what} : ce sont des résultats de développement, pas une preuve '
                    'indépendante de la performance future. Seul l\'échantillon de test final '
                    'scellé, ouvert une fois, l\'est.')
        if 'compare the models and to choose' in text:
            return ('Le jeu de validation sert à comparer les modèles et à en choisir un : ses '
                    "erreurs ne sont donc pas une preuve indépendante de l'erreur future.")
        return ('Le jeu de validation sert à comparer les modèles et à choisir la règle et son '
                'seuil ou sa capacité : ses résultats ne sont donc pas une preuve indépendante '
                'de la performance future.')
    if kind == 'public_data_already_explored':
        return ("Les données ont été explorées ou publiées avant cette étude : ses lignes ne "
                "sont pas inédites.")
    if kind == 'grouped_split_unsupported':
        col = item.get('column')
        if 'fold' in str(item.get('text') or ''):
            return (f'Des lignes qui partagent une valeur de {col} peuvent tomber dans '
                    'plusieurs plis : cette version ne regroupe pas les plis selon cette '
                    'colonne, elle compte les valeurs partagées. Une ligne prédite hors pli '
                    "n'est alors pas indépendante des lignes de son groupe vues par le modèle.")
        return (f'Des lignes qui partagent une valeur de {col} peuvent tomber dans les deux '
                'jeux : cette version ne fait pas de découpage groupé, elle compte les valeurs '
                'partagées. Le jeu de validation n\'est alors pas indépendant du jeu '
                "d'entraînement pour ces groupes.")
    if kind == 'no_time_or_entity_identifier':
        return ("Les données n'ont ni colonne de temps ni identifiant d'entité : l'étude ne "
                'peut pas vérifier une dérive dans le temps ni des entités répétées entre les '
                'échantillons.')
    if kind == 'uncertain_features_included':
        return ('Ces variables sont utilisées alors que leur disponibilité au moment de la '
                f'prédiction est incertaine : {cols}. Vérifiez qu\'elles sont connues à ce '
                'moment-là.')
    if kind == 'inconclusive_without_choice':
        return ("La conclusion est non concluante et rien n'est adopté : l'étude ne recommande "
                "encore aucune action ; elle note pourquoi et ce qui permettrait de trancher.")
    if kind == 'interrupted_executions':
        return 'Une exécution a un résultat inconnu.'
    if kind == 'no_causality':
        return ('Des associations dans des données observées ne montrent pas qu\'agir sur une '
                'variable changerait le résultat.')
    if kind == 'workbench_not_tracked':
        return ("Les essais faits dans l'atelier (workbench) ne sont pas enregistrés et ne sont "
                'pas des décisions.')
    if kind == 'result_integrity':
        return ('Certains résultats enregistrés échouent à leur contrôle d\'intégrité et ne '
                'peuvent pas être cités.')
    if kind == 'sources_changed':
        return ('Le fichier du cas ou des données a changé depuis le début de l\'étude : aucun '
                'résultat ne décrit le fichier actuel. Commencez une nouvelle étude sur les '
                'nouvelles données.')
    if kind == 'code_changed':
        return ('Le code de certaines analyses a changé après leur calcul : ces résultats ne '
                'peuvent pas être cités avant d\'être recalculés.')
    if kind == 'small_validation_partition':
        return ('Le jeu de validation est petit : chaque chiffre de validation repose sur peu '
                'de lignes, son intervalle est large, et un écart entre modèles peut être dû '
                'au hasard.')
    if kind == 'capacity_exceeds_validation':
        return ('Une capacité au moins aussi grande que le jeu de validation sélectionne toutes '
                'les lignes : ses chiffres décrivent « tout sélectionner », pas un classement.')
    if kind == 'high_cardinality_grouping':
        return ('Une colonne à nombreuses valeurs est montrée par ses plus grands groupes, les '
                'autres regroupés en un seul : un taux ou une moyenne de ce groupe mélange '
                'beaucoup de petits groupes.')
    if kind == 'capacity_assumed_for_exercise':
        share = item.get('share')
        pct = audience.share_percent(share, FR) if share is not None else ''
        return (f'Capacité supposée pour l\'exercice : agir sur les {pct} meilleurs scores est '
                "une hypothèse du scénario pédagogique, pas un chiffre d'une équipe réelle. "
                "Avec une vraie équipe, demandez combien elle peut traiter et évaluez cette "
                'capacité.')
    if kind == 'final_test_sealed':
        return ("L'échantillon de test final est encore scellé : chaque chiffre jusqu'ici est "
                'un résultat de développement, mesuré sur des lignes qui ont servi à explorer, '
                'ajuster et choisir.')
    if kind == 'final_test_opening_interrupted':
        return ("L'échantillon de test final a été ouvert mais son évaluation n'a pas été "
                "enregistrée : il ne peut pas être rouvert, l'étude n'a donc pas de preuve "
                'finale.')
    if kind == 'changed_after_final_test':
        changed = _named(item.get('changed'))
        return (f"Quelque chose a changé après l'ouverture du test final ({changed}) : le test "
                "final ne mesure plus ce que l'étude contient, et n'en est plus une preuve "
                'indépendante.')
    if kind == 'verdict_contradicts_criterion':
        why = ("le gain n'atteint pas le minimum fixé avant les modèles"
               if item.get('status') == 'not_met' else
               "l'intervalle apparié du gain contient 0")
        return ('La conclusion adopte alors que le critère de succès fixé avant les modèles '
                f"n'est pas atteint : {why}.")
    if kind == 'verdict_keeps_baseline_against_criterion':
        return ('La conclusion garde le modèle de référence alors que le critère de succès est '
                'atteint sur le test final : dites pourquoi (un coût, un risque, une limite que '
                'le critère ne capture pas), ou reconsidérez le verdict.')
    if kind == 'data_contingent_preprocessing':
        return ('La préparation des variables a été choisie après avoir regardé le résultat '
                'dans les données de développement : les chiffres de développement peuvent '
                'être un peu optimistes.')
    return "Une limite de l'étude est décrite dans le rapport."


# The ids :func:`limit_fr` translates (the tests check that the engine emits no other).
LIMIT_IDS_FR = ('unconfirmed_decisions', 'open_holds', 'conclusion_outdated',
                'delegated_decisions', 'stale_results', 'adopted_rule_not_evaluated',
                'validation_is_not_independent', 'public_data_already_explored',
                'grouped_split_unsupported', 'no_time_or_entity_identifier',
                'uncertain_features_included', 'inconclusive_without_choice',
                'interrupted_executions', 'no_causality', 'workbench_not_tracked',
                'result_integrity', 'sources_changed', 'code_changed',
                'small_validation_partition', 'capacity_exceeds_validation',
                'high_cardinality_grouping', 'capacity_assumed_for_exercise',
                'final_test_sealed', 'final_test_opening_interrupted',
                'changed_after_final_test', 'verdict_contradicts_criterion',
                'verdict_keeps_baseline_against_criterion', 'data_contingent_preprocessing')


# --- data card lines -------------------------------------------------------------------------

def final_test_line(final: Mapping, lang: str) -> str:
    if final.get('status') == 'absent':
        return _t(lang, 'This study has no final test: it was created before the final test '
                        'existed, so every row is a development row.',
                  "Cette étude n'a pas d'échantillon de test final : elle a été créée avant "
                  "qu'il existe, donc chaque ligne est une ligne de développement.")
    return _t(lang, f'{final.get("rows")} rows are set aside as the final test and stay '
                    f'sealed: nothing here reads them.',
              f"{final.get('rows')} lignes sont mises de côté comme échantillon de test final "
              "(holdout) et restent scellées : rien ici ne les lit.")


def duplicates_line(out: Mapping, group_policy: bool, lang: str) -> str:
    if not out.get('n_groups'):
        return _t(lang, 'No two development rows are identical.',
                  "Aucune ligne de l'échantillon de développement n'est identique à une autre.")
    if group_policy:
        return _t(lang, f'{out["n_rows"]} development rows form {out["n_groups"]} groups of '
                        f'identical rows. Each group is treated as one entity: its rows always '
                        f'stay together on one side of every split.',
                  f"{out['n_rows']} lignes de l'échantillon de développement forment "
                  f"{out['n_groups']} groupes de lignes identiques. Chaque groupe est traité "
                  'comme une seule entité : ses lignes restent toujours ensemble du même côté '
                  'de chaque découpage.')
    return _t(lang, f'{out["n_rows"]} development rows form {out["n_groups"]} groups of '
                    f'identical rows.',
              f"{out['n_rows']} lignes de l'échantillon de développement forment "
              f"{out['n_groups']} groupes de lignes identiques.")


DATA_NOTE_FR = ("Ce sont uniquement des lignes de l'échantillon de développement ; "
                "l'échantillon de test final reste scellé. La fiche montre le sens des colonnes "
                'et quelques lignes, jamais la fréquence du résultat : elle est explorée après '
                'le découpage.')
UNGROUPED_FR = 'Autres colonnes'


# --- the feature availability drafted from the case -----------------------------------------

# The case's availability statement and the decision status it drafts: a doubt about the
# timing is a leakage risk, so a doubtful or undocumented column is drafted as excluded.
AVAILABILITY_DRAFT = {'available_at_prediction': 'available_at_prediction',
                      'not_available': 'not_available', 'uncertain': 'uncertain_excluded',
                      'unknown': 'uncertain_excluded'}


def availability_draft(case) -> dict | None:
    """``{feature: status}`` for every candidate feature, from the case's availability
    statements (:data:`AVAILABILITY_DRAFT`), or None without a case."""
    if case is None:
        return None
    out = {}
    for v in case.document['variables']:
        if v.get('role') != 'feature':
            continue
        out[v['name']] = AVAILABILITY_DRAFT.get((v.get('availability') or {}).get('value'),
                                                'uncertain_excluded')
    return out or None


# --- next_action: digest, recommended, question ---------------------------------------------

def _words(text: str) -> int:
    return len(text.split())


def _fit(parts: list[str]) -> str:
    """The parts joined, dropping trailing parts until at most :data:`MAX_DIGEST_WORDS`."""
    parts = [p for p in parts if p]
    while len(parts) > 1 and _words(' '.join(parts)) > MAX_DIGEST_WORDS:
        parts.pop()
    text = ' '.join(parts)
    if _words(text) > MAX_DIGEST_WORDS:
        text = ' '.join(text.split()[:MAX_DIGEST_WORDS])
    return text


def _context(view: Mapping, state: Mapping, case) -> dict:
    """The figures and names a digest cites: development and holdout rows, folds, target."""
    final = view.get('final_test') or {}
    total = (view.get('dataset') or {}).get('rows')
    holdout = final.get('rows') if final.get('status') in ('sealed', 'opened') else None
    dev = total - holdout if isinstance(total, int) and isinstance(holdout, int) else total
    target = case.target_column if case is not None else None
    positive = case.positive_label if case is not None and getattr(case, 'task', None) \
        == 'binary' else None
    unit = case.target_unit if case is not None and getattr(case, 'task', None) \
        == 'regression' else None
    split = (view.get('decisions') or {}).get('split') or {}
    value = split.get('value') if isinstance(split.get('value'), Mapping) else None
    folds = value.get('folds') if value else None
    if folds is None:
        default = st.b1_default_value(state, 'split') if isinstance(state, Mapping) else None
        folds = (default or {}).get('folds')
    return {'dev': dev, 'holdout': holdout, 'target': target, 'positive': positive,
            'unit': unit, 'folds': folds, 'cv': st.uses_cross_validation(state)}


def _fact(view: Mapping, fact_id: str):
    for items in ((view.get('facts') or {}).get('by_status') or {}).values():
        for item in items:
            if item.get('id') == fact_id:
                return item
    return None


def _recommended(action: Mapping, view: Mapping, state: Mapping, lang: str) -> dict | None:
    """The engine's default for the decision ``action`` proposes, with a one-line why."""
    if action.get('kind') != 'propose':
        return None
    decision = action.get('decision')
    value = action.get('default_value')
    if decision == 'prediction_time':
        fact = _fact(view, 'prediction_time')
        if not fact:
            return None
        return {'value': fact['value'],
                'why': _t(lang, 'The case states this moment; confirm it fits how the score '
                                'will be used.',
                          'Le cas indique ce moment ; vérifiez qu\'il correspond à l\'usage du '
                          'score.')}
    if decision == st.SUCCESS_CRITERION:
        return _recommended_criterion(action, lang)
    if value is None:
        return None
    why = {
        'feature_availability': _t(
            lang, 'The case\'s statement for each column, with every doubtful or undocumented '
                  'column excluded: a doubt about the timing is a leakage risk.',
            'La disponibilité indiquée par le cas pour chaque colonne, chaque colonne douteuse '
            'ou non documentée étant exclue : un doute sur le moment est un risque de fuite '
            "d'information (leakage)."),
        'split': _t(
            lang, 'k-fold cross-validation uses every development row once as validation, so '
                  'the estimate rests on more rows than one validation set.',
            'La validation croisée à k plis utilise chaque ligne de développement une fois en '
            'validation : l\'estimation repose sur plus de lignes qu\'un seul jeu de '
            'validation.'),
        'preprocessing': _t(
            lang, 'The default changes nothing (no indicator, no grouping, no cap, no '
                  'transform), so the results stay comparable and nothing is tuned on the '
                  'outcome.',
            'Le choix par défaut ne change rien (ni indicateur, ni regroupement, ni plafond, '
            'ni transformation) : les résultats restent comparables et rien n\'est ajusté sur '
            'le résultat.'),
        'model_variant': _t(
            lang, 'The penalty chosen by nested cross-validation is the simplest check that '
                  'the candidate is not fitting noise; it counts as one trial of the budget of '
                  'three.',
            'La pénalité choisie par validation croisée imbriquée est le contrôle le plus '
            'simple que le candidat n\'apprend pas du bruit ; elle compte comme un essai du '
            'budget de trois.'),
        'policy': _t(
            lang, 'The teaching scenario assumes this share of the scored rows; a real team '
                  'would give its own capacity.',
            'Le scénario pédagogique suppose cette part des lignes notées ; une vraie équipe '
            'donnerait sa propre capacité.'),
        'final_test': _t(
            lang, 'This is the configuration you chose; the holdout (final test) measures it '
                  'once.',
            "C'est la configuration que vous avez choisie ; l'échantillon de test final (holdout) "
            'la mesure une fois.'),
    }.get(decision)
    if why is None:
        return None
    return {'value': copy.deepcopy(value), 'why': why}


def _recommended_criterion(action: Mapping, lang: str) -> dict | None:
    """v0.3 (WP-J): the middle option of ``criterion_options`` (+5 points of the default
    metric, or 10 % less error), said to be a convention and not a value derived from the
    case's costs, so that the criterion costs one adoption, not a question and an answer."""
    options = action.get('criterion_options') or {}
    candidates = options.get('candidates') or []
    if len(candidates) < 2 or not isinstance(candidates[1].get('value'), Mapping):
        return None
    middle = candidates[1]
    value = dict(middle['value'])
    if options.get('task') == st.REGRESSION:
        pct = round(100 * float(value['min_share']))
        why = _t(lang, f'The middle option, {pct}% less error than the mean baseline: a moderate '
                       'bar chosen by convention, not from the costs of this case. Keep it, or '
                       'name the minimum your team needs.',
                 f"L'option du milieu, {pct} % d'erreur en moins que la moyenne de référence : "
                 'un seuil modéré, choisi par convention et non à partir des coûts de ce cas. '
                 "Gardez-le, ou indiquez le minimum dont votre équipe a besoin.")
        return {'value': value, 'why': why}
    default = options.get('default_metric')
    if isinstance(default, str) and default != value.get('metric'):
        value['metric'] = default
    points = value.get('min_points')
    per = middle.get('per_1000')
    extra = (_t(lang, f' On {SCALE_1000} actions, about {per["extra"]} more positives than the '
                      'baseline.',
                f' Sur {SCALE_1000_FR} actions, environ {per["extra"]} positifs de plus que le '
                'modèle de référence.')
             if isinstance(per, Mapping) and isinstance(per.get('extra'), int) else '')
    metric = audience_metric(value['metric'], lang)
    why = _t(lang, f'The middle option, +{points} points of {metric} over the baseline: a '
                   'moderate bar chosen by convention, not from the costs of this case.'
                   f'{extra} Keep it, or name the minimum your team needs.',
             f"L'option du milieu, +{points} points de {metric} au-dessus du modèle de "
             'référence : un seuil modéré, choisi par convention et non à partir des coûts de '
             f"ce cas.{extra} Gardez-le, ou indiquez le minimum dont votre équipe a besoin.")
    return {'value': value, 'why': why}


SCALE_1000, SCALE_1000_FR = '1,000', '1 000'


def audience_metric(metric: str, lang: str) -> str:
    """The metric of a gain in words: precision or recall (précision, rappel)."""
    if metric == 'recall_gain':
        return _t(lang, 'recall', 'rappel')
    return _t(lang, 'precision', 'précision')


def _question(action: Mapping, view: Mapping, lang: str, cv: bool = False) -> str | None:
    kind = action.get('kind')
    decision = action.get('decision')
    mode = view.get('mode') or st.DEFAULT_MODE
    if kind == 'await_user_words':
        if mode == st.TRAINING:
            return _t(lang, 'In your own words, what do you keep, and why?',
                      'Avec vos mots, que retenez-vous, et pourquoi ?')
        return _t(lang, 'Do you adopt this decision?', 'Adoptez-vous cette décision ?')
    if kind == 'reconfirm':
        return _t(lang, f'Do you confirm {audience.decision_words(decision)} again?',
                  f'Confirmez-vous à nouveau {audience.decision_words(decision, FR)} ?')
    if kind in ('outcome_unknown', 'acknowledge_interruption'):
        return _t(lang, 'May this run be recorded as interrupted?',
                  'Peut-on enregistrer cette exécution comme interrompue ?')
    if kind == 'show_data_card':
        return _t(lang, 'Shall we look at the data card together?',
                  'On regarde ensemble la fiche des données ?')
    if kind != 'propose':
        return None
    task = view.get('task') or st.BINARY
    questions = {
        'prediction_time': _t(lang, 'At what moment is the score computed and acted on?',
                              'À quel moment le score est-il calculé et utilisé ?'),
        'feature_availability': _t(lang, 'Which columns are known at that moment, and which '
                                         'must be excluded?',
                                   'Quelles colonnes sont connues à ce moment-là, et lesquelles '
                                   'faut-il exclure ?'),
        'split': _t(lang, 'Do you evaluate with this k-fold cross-validation?',
                    'Évaluez-vous avec cette validation croisée à k plis ?') if cv else
        _t(lang, 'How should the rows be divided between the training set and the validation '
                 'set?',
           "Comment répartir les lignes entre le jeu d'entraînement et le jeu de validation ?"),
        'success_criterion': (_t(lang, 'Which metric, and which minimum gain over the '
                                       'baseline, would make the model worth using?',
                                 'Quelle métrique, et quel gain minimum sur le modèle de '
                                 'référence, rendraient le modèle utile ?')
                              if task == st.BINARY else
                              _t(lang, 'Which minimum reduction of the baseline\'s error would '
                                       'make the model worth using?',
                                 'Quelle réduction minimale de l\'erreur de référence rendrait '
                                 'le modèle utile ?')),
        'preprocessing': _t(lang, 'Do you keep the default preparation, or change one '
                                  'parameter for a reason you can state?',
                            'Gardez-vous la préparation par défaut, ou changez-vous un '
                            'paramètre pour une raison que vous pouvez énoncer ?'),
        'model_variant': _t(lang, 'Which variants, at most three, should be compared with '
                                  'the candidate, and which question does each answer?',
                            'Quelles variantes, trois au plus, comparer au candidat, et à '
                            'quelle question chacune répond-elle ?'),
        'policy': _t(lang, 'Which rule turns the scores into actions?',
                     'Quelle règle transforme les scores en actions ?'),
        'model_choice': _t(lang, 'Which model do you choose, given the errors and their '
                                 'intervals?',
                           'Quel modèle choisissez-vous, compte tenu des erreurs et de leurs '
                           'intervalles ?'),
        'final_test': _t(lang, 'Do you open the holdout (final test) now, once?',
                         "Ouvrez-vous maintenant l'échantillon de test final (holdout), une "
                         'seule fois ?'),
        'conclusion': _t(lang, 'What do you conclude, for which use, and with which limits?',
                         'Que concluez-vous, pour quel usage, et avec quelles limites ?'),
    }
    return questions.get(decision)


def _criterion_status_words(view: Mapping, lang: str) -> str | None:
    crit = view.get('criterion') or {}
    status = crit.get('judged_status')
    if not status or status == 'not_assessed':
        return None
    where = (_t(lang, 'on the holdout (final test)', "sur l'échantillon de test final")
             if crit.get('judged_on') == 'final_test' else
             _t(lang, 'on the development set', "sur l'échantillon de développement"))
    words = {'met': _t(lang, 'met', 'atteint'), 'not_met': _t(lang, 'not met', 'non atteint'),
             'uncertain': _t(lang, 'uncertain (its confidence interval includes 0)',
                             'incertain (son intervalle de confiance contient 0)')}[status]
    return _t(lang, f'The success criterion is {words} {where}.',
              f'Le critère de succès est {words} {where}.')


def _digest_propose(decision: str, view: Mapping, ctx: dict, lang: str,
                    action: Mapping) -> list[str]:
    dev, holdout, folds = ctx['dev'], ctx['holdout'], ctx['folds']
    target, positive, unit = ctx['target'], ctx['positive'], ctx['unit']
    if decision == 'prediction_time':
        fact = _fact(view, 'prediction_time')
        said = (_t(lang, f'The case states: "{fact["value"]}".',
                   f'Le cas indique : « {fact["value"]} ».') if fact else '')
        return [_t(lang, 'Prediction time: the moment when the score is computed and acted on. '
                         'Only information known at that moment may enter the model; anything '
                         'recorded later would leak the outcome.',
                   'Moment de la prédiction (prediction time) : le moment où le score est '
                   'calculé et utilisé. Seules les informations connues à ce moment peuvent '
                   'entrer dans le modèle ; une information enregistrée plus tard ferait fuir '
                   'le résultat.'), said]
    if decision == 'feature_availability':
        draft = action.get('default_value') or {}
        counts = {k: sum(1 for v in draft.values() if v == k) for k in
                  ('available_at_prediction', 'not_available', 'uncertain_excluded')}
        doubtful = sorted(f for f, v in draft.items() if v == 'uncertain_excluded')
        out = [_t(lang, 'Feature availability: whether a column is known at the prediction '
                        'moment. A column known only later is leakage: it makes the model look '
                        'better on past data than it can be in use.',
                  'Disponibilité des variables (feature availability) : savoir si une colonne '
                  'est connue au moment de la prédiction. Une colonne connue seulement plus '
                  "tard est une fuite d'information (leakage) : le modèle paraît meilleur sur "
                  'le passé qu\'il ne peut l\'être en usage.')]
        if draft:
            out.append(_t(lang, f'From the case: {counts["available_at_prediction"]} columns '
                                f'available, {counts["not_available"]} not available, '
                                f'{counts["uncertain_excluded"]} doubtful.',
                          f'Selon le cas, colonnes disponibles : '
                          f'{counts["available_at_prediction"]} ; non disponibles : '
                          f'{counts["not_available"]} ; douteuses : '
                          f'{counts["uncertain_excluded"]}.'))
            if doubtful:
                out.append(_t(lang, 'Doubtful: ' + ', '.join(doubtful[:8]) + '.',
                              'Douteuses : ' + ', '.join(doubtful[:8]) + '.'))
        return out
    if decision == 'split':
        if ctx['cv']:
            return [_t(lang, f'k-fold cross-validation: the development set ({_int(dev, lang)} '
                             f'rows) is divided into {folds} folds; each fold is in turn the '
                             f'validation fold, predicted by a model fitted on the other folds, '
                             f'the training folds. Every development row gets one out-of-fold '
                             f'prediction.' if isinstance(dev, int) else
                             f'k-fold cross-validation: the development set is divided into '
                             f'{folds} folds; each fold is in turn the validation fold, predicted '
                             f'by a model fitted on the training folds.',
                       f'Validation croisée à k plis (k-fold cross-validation) : '
                       f"l'échantillon de développement ({_int(dev, lang)} lignes) est découpé "
                       f'en {folds} plis ; chaque pli est à son tour le pli de validation, '
                       f'prédit par un modèle ajusté sur les autres plis, les plis '
                       f"d'entraînement. Chaque ligne de développement reçoit une prédiction "
                       f'hors pli.' if isinstance(dev, int) else
                       f'Validation croisée à k plis : l\'échantillon de développement est '
                       f'découpé en {folds} plis ; chaque pli est à son tour le pli de '
                       f"validation, prédit par un modèle ajusté sur les plis d'entraînement."),
                    _holdout_sentence(holdout, lang)]
        return [_t(lang, 'Training set and validation set: the models learn on the training set '
                         'and are compared on the validation set, rows they did not see. The '
                         'split is fixed before any look at the outcome.',
                   "Jeu d'entraînement et jeu de validation : les modèles apprennent sur le "
                   "jeu d'entraînement et sont comparés sur le jeu de validation, des lignes "
                   "qu'ils n'ont pas vues. Le découpage est fixé avant tout regard sur le "
                   'résultat.'), _holdout_sentence(holdout, lang)]
    if decision == 'success_criterion':
        opts = action.get('criterion_options') or {}
        out = [_t(lang, 'Success criterion: a metric and a minimum, fixed now, before any '
                        'model, so the result cannot move the bar.',
                  'Critère de succès (success criterion) : une métrique et un minimum, fixés '
                  'maintenant, avant tout modèle, pour que le résultat ne puisse pas déplacer '
                  'la barre.')]
        if opts.get('reference'):
            out.append(opts['reference']['text'])
        out.append(opts.get('text') or '')
        if opts.get('equivalence') and opts.get('action') != 'threshold':
            out.append(_t(lang, 'At a fixed number of actions, precision, recall and lift rank '
                                'models the same way.',
                          "À nombre d'actions fixé, précision, rappel et lift classent les "
                          'modèles de la même façon.'))
        cands = [c['text'] for c in opts.get('candidates') or [] if c.get('per_1000')]
        if cands:
            out.append(opts.get('illustrative') or '')
            out += cands
        else:
            out += [c['text'] for c in opts.get('candidates') or []]
        out.append(_t(lang, 'AUC and average precision (AP) judge the ranking: diagnostics, '
                            'not a criterion.',
                      "L'AUC et l'average precision (AP) jugent le classement : des "
                      'diagnostics, pas un critère.') if view.get('task') != st.REGRESSION
                   else '')
        return out
    if decision == 'preprocessing':
        where = (_t(lang, 'the training folds of each model', "les plis d'entraînement de "
                                                              'chaque modèle')
                 if ctx['cv'] else _t(lang, 'the training set', "le jeu d'entraînement"))
        return [_t(lang, f'Preparation of the variables (preprocessing): how the model treats '
                         f'missing values, rare categories, extreme values and skewed '
                         f'variables. Every parameter is learnt on {where} only.',
                   f'Préparation des variables (preprocessing) : comment le modèle traite les '
                   f'valeurs manquantes, les catégories rares, les valeurs extrêmes et les '
                   f'variables asymétriques. Chaque paramètre est appris sur {where} '
                   f'seulement.'),
                _t(lang, 'A choice made after looking at the outcome is a data-contingent '
                         'decision: allowed, but recorded, because it makes the development '
                         'figures slightly optimistic.',
                   'Un choix fait après avoir regardé le résultat est une décision dépendante '
                   'des données : permise, mais enregistrée, car elle rend les chiffres de '
                   'développement un peu optimistes.')]
    if decision == 'model_variant':
        trials = (view.get('trials') or {}).get('count')
        families = (view.get('model_families') or {})
        shortlist = families.get('texts', {}).get(lang) if families else None
        return [_t(lang, 'Variant: one change of the candidate model (the penalty chosen by '
                         'nested cross-validation, a stronger or weaker regularisation, the '
                         'model without one group of variables, or another model family), '
                         'compared under the same evaluation; at most three, each with its '
                         'question. Each configuration compared on the same rows is a trial; '
                         'the more trials, the more the best of them may owe to chance.',
                   'Variante : un seul changement du modèle candidat (la pénalité choisie par '
                   'validation croisée imbriquée, une régularisation plus forte ou plus faible, '
                   'le modèle sans un groupe de variables, ou une autre famille de modèles), '
                   'comparé sous la même évaluation ; trois au plus, chacune avec sa question. '
                   'Chaque configuration comparée sur les mêmes lignes est un essai ; plus il y '
                   'a d\'essais, plus le meilleur peut devoir au hasard.'),
                shortlist or '',
                _t(lang, f'Trials so far: {trials}.', f'Essais jusqu\'ici : {trials}.')
                if isinstance(trials, int) else '']
    if decision == 'policy':
        share = action.get('default_value')
        out = [_t(lang, 'Decision rule (policy): the rule that turns scores into actions, a '
                        'threshold on the score, a fixed capacity, or a share of the scored '
                        'rows. Precision and recall at the rule say what it gains.',
                  'Règle de décision (policy) : la règle qui transforme les scores en actions, '
                  'un seuil sur le score, une capacité fixe, ou une part des lignes notées. La '
                  'précision et le rappel à cette règle disent ce qu\'elle rapporte.')]
        if isinstance(share, str):
            out.append(_t(lang, f'The scenario assumes: {audience.policy_words(share)}.',
                          f'Le scénario suppose : {audience.policy_words(share, FR)}.'))
        return out
    if decision == 'model_choice':
        return [_t(lang, 'Model choice: keep the mean baseline or adopt the linear model, read '
                         'on the mean absolute error (MAE) and its paired interval.',
                   'Choix du modèle : garder la moyenne de référence ou adopter le modèle '
                   "linéaire, lu sur l'erreur absolue moyenne (MAE) et son intervalle "
                   'apparié.'), _criterion_status_words(view, lang) or '']
    if decision == 'final_test':
        return [_t(lang, 'Holdout (final test): rows sealed since the start. Opened once, it '
                         'measures the chosen configuration on rows no choice used; it is the '
                         'study\'s only independent evidence. After the opening, any change is '
                         'reported as made after the final test.',
                   "Échantillon de test final (holdout) : des lignes scellées depuis le "
                   "début. Ouvert une seule fois, il mesure la configuration choisie sur des "
                   "lignes qu'aucun choix n'a utilisées ; c'est la seule preuve indépendante de "
                   "l'étude. Après l'ouverture, tout changement est signalé comme fait après le "
                   'test final.'),
                _t(lang, f'It holds {_int(holdout, lang)} rows.',
                   f'Il contient {_int(holdout, lang)} lignes.')
                if isinstance(holdout, int) else '']
    if decision == 'conclusion':
        return [_t(lang, 'Conclusion: what the study can say, for which use, and with which '
                         'limits. Keeping the baseline is a valid result. Final figures come '
                         'first, development figures next to them, labelled as such.',
                   "Conclusion : ce que l'étude peut dire, pour quel usage, et avec quelles "
                   'limites. Garder le modèle de référence est un résultat valable. Les '
                   'chiffres du test final viennent d\'abord, ceux du développement à côté, '
                   'signalés comme tels.'),
                _criterion_status_words(view, lang) or '']
    return []


def _holdout_sentence(holdout, lang: str) -> str:
    if not isinstance(holdout, int):
        return ''
    return _t(lang, f'The holdout (final test), {_int(holdout, lang)} rows, stays sealed and is '
                    f'opened once at the end.',
              f"L'échantillon de test final (holdout), {_int(holdout, lang)} lignes, reste "
              f'scellé et ne sera ouvert qu\'une fois, à la fin.')


def _digest(action: Mapping, view: Mapping, state: Mapping, ctx: dict, lang: str) -> str:
    kind = action.get('kind')
    junior_message = str(action.get('junior_message') or '')
    if kind == 'show_data_card':
        target = ctx['target']
        positive = (_t(lang, f' (positive: {ctx["positive"]})', f' (positif : {ctx["positive"]})')
                    if ctx['positive'] is not None else
                    (f' ({ctx["unit"]})' if ctx['unit'] else ''))
        parts = [_t(lang, 'Step 0, discover the data. The development set is the rows the study '
                          'may explore and use to choose' +
                          (f': {_int(ctx["dev"], lang)} rows.' if isinstance(ctx['dev'], int)
                           else '.'),
                    "Étape 0, découvrir les données. L'échantillon de développement est "
                    "l'ensemble des lignes que l'étude peut explorer et utiliser pour choisir" +
                    (f' : {_int(ctx["dev"], lang)} lignes.' if isinstance(ctx['dev'], int)
                     else '.')),
                 _holdout_sentence(ctx['holdout'], lang),
                 _t(lang, f'The target is {target}{positive}.', f'La cible est {target}{positive}.')
                 if target else '',
                 _t(lang, 'The data card shows what one row describes, the columns grouped with '
                          'their meaning, and five example rows. Nothing is decided at this '
                          'step.',
                    'La fiche des données montre ce que décrit une ligne, les colonnes '
                    'regroupées avec leur sens, et cinq lignes d\'exemple. Rien n\'est décidé à '
                    'cette étape.')]
        return _fit(parts)
    if kind == 'propose':
        parts = _digest_propose(action.get('decision'), view, ctx, lang, action)
        rec = action.get('recommended')
        if rec:
            parts.insert(1 if len(parts) > 1 else len(parts),
                         _t(lang, f'Recommended: {rec["why"]}', f'Recommandé : {rec["why"]}'))
        return _fit(parts or [junior_message])
    if kind == 'await_user_words':
        proposal = next((p for p in view.get('open_proposals') or []
                         if p.get('proposal_id') == action.get('proposal_id')), None)
        label = (proposal or {}).get('label') or ''
        decision = action.get('decision')
        mode = view.get('mode') or st.DEFAULT_MODE
        head = _t(lang, f'Proposal on {audience.decision_words(decision)}: "{label}"',
                  f'Proposition sur {audience.decision_words(decision, FR)} : « {label} »') \
            if label else junior_message
        if mode == st.TRAINING:
            tail = _t(lang, 'Reply in your own words: what you keep and why.',
                      'Répondez avec vos mots : ce que vous retenez et pourquoi.')
        else:
            tail = _t(lang, 'If it suits you, say that you adopt it; otherwise say what you '
                            'change.',
                      'Si elle vous convient, dites que vous l\'adoptez ; sinon dites ce que '
                      'vous changez.')
        return _fit([head, tail])
    if kind == 'run':
        activity = action.get('activity')
        return _fit([_t(lang, f'Next: {audience.activity_words(activity)}, run without asking '
                              f'you.',
                        f'Ensuite : {audience.activity_words(activity, FR)}, lancé sans vous '
                        f'demander.'), junior_message])
    if kind == 'done':
        return _fit([junior_message, _criterion_status_words(view, lang) or ''])
    if kind == 'reconfirm':
        decision = action.get('decision')
        reason = ((view.get('decisions') or {}).get(decision) or {}).get('reason')
        words = audience.reason_words(reason, lang) if reason else ''
        return _fit([junior_message, (words[:1].upper() + words[1:]).rstrip('.') + '.'
                     if words else ''])
    return _fit([junior_message])


def enrich(view: dict, state: Mapping, case=None) -> dict:
    """Add the junior-ready keys to ``view['next_action']`` in place (and return it):
    ``language``, ``junior_digest``, ``recommended``, ``question``; ``criterion_options`` at
    the success criterion; the case's availability as ``default_value`` at the feature
    availability."""
    action = view.get('next_action')
    if not isinstance(action, dict):
        return view
    lang = view.get('language') or EN
    decision = action.get('decision')
    if action.get('kind') == 'propose' and decision == 'feature_availability' \
            and 'default_value' not in action:
        draft = availability_draft(case)
        if draft:
            action['default_value'] = draft
    if action.get('kind') in ('propose', 'await_user_words') \
            and decision == st.SUCCESS_CRITERION:
        from . import criterion
        action['criterion_options'] = criterion.options(
            view, lang, unit=case.target_unit if case is not None
            and getattr(case, 'task', None) == 'regression' else None)
    ctx = _context(view, state, case)
    action['language'] = lang
    action['recommended'] = _recommended(action, view, state, lang)
    action['question'] = _question(action, view, lang, ctx['cv'])
    action['junior_digest'] = _digest(action, view, state, ctx, lang)
    return view


__all__ = ['step_text', 'all_step_texts', 'limit_fr', 'LIMIT_IDS_FR', 'enrich',
           'availability_draft', 'final_test_line', 'duplicates_line', 'MAX_DIGEST_WORDS']
