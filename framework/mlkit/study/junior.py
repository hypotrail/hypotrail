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
from . import assurance
from . import drafts
from . import state as st

EN, FR = 'en', 'fr'
MAX_DIGEST_WORDS = 200
ENRICH_KEYS = ('language', 'junior_digest', 'recommended', 'question', 'pause')
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
        st.MODEL_CHOICE_STEP['title']: 'Choisir le modèle',
        st.FINAL_TEST_STEP['title']: "Ouvrir une fois l'échantillon de test final",
        # Lot 2026-10-28 (EN-9).
        st.ERROR_METRIC_STEP['title']: "Choisir comment l'erreur est mesurée",
        st.ERROR_METRIC_STEP['question']:
            "L'erreur d'une prédiction est l'écart entre la valeur observée et la valeur "
            "prédite. L'erreur absolue moyenne (MAE) fait la moyenne de ces écarts ; la racine "
            "de l'erreur quadratique moyenne (RMSE) fait la moyenne de leurs carrés, puis en "
            'prend la racine : un gros raté y pèse beaucoup plus. Laquelle des deux mesure '
            "l'erreur de cette étude ? Elle est choisie maintenant, avant tout ajustement de "
            'modèle.',
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
        st.MODEL_CHOICE_STEP['question']: 'Compte tenu de la comparaison sur les données de '
                                          'développement, quel modèle retenez-vous pour la '
                                          'règle de décision ? Comparer un modèle ne le '
                                          'sélectionne pas.',
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
        # Owner session 2026-10-26 (L5, D5): the structural-first plan.
        st.STRUCTURAL_EDA_STEP['title']: 'Vérifier la structure des données',
        st.STRUCTURAL_EDA_STEP['question']: 'Quelles colonnes ont des cellules manquantes, des '
                                            'catégories rares ou des valeurs hors de leur plage '
                                            'possible ? Ce contrôle lit les lignes de '
                                            "l'échantillon de développement sans la cible : la "
                                            "préparation décidée d'après lui vient avant tout "
                                            'regard sur la cible.',
        st.STRUCTURAL_PREPROCESSING_QUESTION: 'Comment le modèle doit-il traiter les valeurs '
                                              'manquantes, les catégories rares, les valeurs '
                                              'extrêmes et les variables asymétriques ? La '
                                              'proposition lit le contrôle de qualité, qui ne '
                                              'lit pas la cible ; chaque paramètre est appris '
                                              'seulement sur les lignes sur lesquelles chaque '
                                              'modèle est ajusté.',
        st.STRUCTURAL_TRAIN_EDA_TEXTS[(st.BINARY, True)]['title']:
            "Explorer la cible sur l'échantillon de développement",
        st.STRUCTURAL_TRAIN_EDA_TEXTS[(st.BINARY, False)]['title']:
            "Explorer la cible sur le jeu d'entraînement",
        st.STRUCTURAL_TRAIN_EDA_TEXTS[(st.BINARY, True)]['question']:
            "Que montre l'échantillon de développement sur le résultat et les valeurs "
            'spéciales ? Chacune de ces analyses est un regard sur la cible : elle lit la '
            'variable à prédire, et chaque regard est compté. La préparation est déjà décidée, '
            'avant ces regards.',
        st.STRUCTURAL_TRAIN_EDA_TEXTS[(st.BINARY, False)]['question']:
            "Que montre le jeu d'entraînement sur le résultat et les valeurs spéciales ? "
            'Chacune de ces analyses est un regard sur la cible : elle lit la variable à '
            'prédire, et chaque regard est compté. La préparation est déjà décidée, avant ces '
            'regards.',
        st.STRUCTURAL_TRAIN_EDA_TEXTS[(st.REGRESSION, True)]['question']:
            "Que montre l'échantillon de développement sur la distribution de la cible et les "
            'valeurs spéciales ? Chacune de ces analyses est un regard sur la cible : elle lit '
            'la variable à prédire, et chaque regard est compté. La préparation est déjà '
            'décidée, avant ces regards.',
        st.STRUCTURAL_TRAIN_EDA_TEXTS[(st.REGRESSION, False)]['question']:
            "Que montre le jeu d'entraînement sur la distribution de la cible et les valeurs "
            'spéciales ? Chacune de ces analyses est un regard sur la cible : elle lit la '
            'variable à prédire, et chaque regard est compté. La préparation est déjà décidée, '
            'avant ces regards.',
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
              st.B1_STEPS, st.B2_BINARY_STEPS, st.B1_REGRESSION_STEPS]
    for task, steps in st.B1_STEPS_BY_TASK.items():
        texts = st.CV_STEP_TEXTS_BY_TASK[task]
        groups.append(tuple(dict(s, **texts.get(s['id'], {})) for s in steps))
    # Owner session 2026-10-26 (L5): the structural-first plan of every task and scheme.
    structural = [st.STRUCTURAL_EDA_STEP,
                  dict(st.PREPROCESSING_STEP, question=st.STRUCTURAL_PREPROCESSING_QUESTION)]
    structural += [dict(st.STEPS[3], **texts) for texts in st.STRUCTURAL_TRAIN_EDA_TEXTS.values()]
    groups.append(tuple(structural))
    groups.append((st.ERROR_METRIC_STEP,))              # lot 2026-10-28 (EN-9)
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
    if kind == 'automatic_decisions_to_review':
        return ('Étude automatique : à relire, pas encore défendable. Le mode automatique a '
                'pris ces décisions sans vos mots ; adoptez ou changez chacune avec vos propres '
                f'mots : {_named(item.get("decisions"))}.')
    if kind == 'final_test_opened_automatically':
        return ("Le test final a été ouvert automatiquement, par le mode démonstration, et non "
                "par votre décision. Son unique évaluation est conservée et l'ouverture ne peut "
                "pas être refaite ; tout changement fait depuis est marqué comme fait après le "
                'test final.')
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
    if kind == 'delayed_labels_excluded':
        # Review 2026-10-24 round 2: the term first, then an example in the study's clock.
        n = item.get('n_rows')
        clock, start = item.get('clock'), item.get('final_start')
        where = (f'{clock} {st._clock_value(start)}' if clock and start is not None
                 else 'le début du test final')
        rows = 'ligne' if n == 1 else 'lignes'
        return (f"Une étiquette tardive est un résultat connu seulement un certain temps après "
                f"la prédiction. Ici, {n} {rows} de développement avaient un résultat connu "
                f"seulement au début du test final ou après ({where}), le moment simulé de la "
                f"décision : leurs étiquettes n'étaient donc pas encore connues. Elles sont "
                f"écartées du découpage, de l'exploration du résultat, de chaque ajustement et "
                f"de ses scores de validation, du réajustement final et du prédicteur capturé. "
                f"Par exemple, une ligne prédite juste avant {where} dont le résultat arrive "
                f"après apprendrait au modèle une réponse que personne n'avait à ce moment-là.")
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
        # L7 (R17): only what is missing; a declared order says what the final test shows.
        missing = list(item.get('missing') or ('time_column', 'group_column'))
        if missing == ['time_column']:
            text = ("Les données n'ont ni colonne de temps ni ordre déclaré : l'étude ne peut "
                    'pas vérifier une dérive dans le temps.')
        elif missing == ['group_column']:
            text = ("Les données n'ont pas d'identifiant d'entité : l'étude ne peut pas "
                    "vérifier qu'une même entité apparaît dans plusieurs échantillons.")
        else:
            text = ("Les données n'ont ni colonne de temps ni identifiant d'entité : l'étude "
                    'ne peut pas vérifier une dérive dans le temps ni des entités répétées '
                    'entre les échantillons.')
        if 'ordered_by' in item:
            by = item.get('ordered_by')
            order = ("l'ordre des lignes du fichier" if by in (None, 'line')
                     else f'la colonne {by}')
            text += (f' Les lignes suivent un ordre déclaré ({order}) et le test final en '
                     'contient les dernières : il peut donc montrer un écart entre la période '
                     'de développement et la période finale, sans en expliquer l\'origine.')
        return text
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
                'validation_is_not_independent', 'delayed_labels_excluded',
                'public_data_already_explored',
                'grouped_split_unsupported', 'no_time_or_entity_identifier',
                'uncertain_features_included', 'inconclusive_without_choice',
                'interrupted_executions', 'no_causality', 'workbench_not_tracked',
                'result_integrity', 'sources_changed', 'code_changed',
                'small_validation_partition', 'capacity_exceeds_validation',
                'high_cardinality_grouping', 'capacity_assumed_for_exercise',
                'final_test_sealed', 'final_test_opening_interrupted',
                'changed_after_final_test', 'verdict_contradicts_criterion',
                'verdict_keeps_baseline_against_criterion', 'data_contingent_preprocessing',
                # L9 (R20): an automatic study.
                'automatic_decisions_to_review', 'final_test_opened_automatically')


# --- data card lines -------------------------------------------------------------------------

def final_test_line(final: Mapping, lang: str) -> str:
    if final.get('status') == 'absent':
        return _t(lang, 'This study has no final test: it was created before the final test '
                        'existed, so every row is a development row.',
                  "Cette étude n'a pas d'échantillon de test final : elle a été créée avant "
                  "qu'il existe, donc chaque ligne est une ligne de développement.")
    return _t(lang, f'{final.get("rows")} rows are set aside as the final test. This view '
                    f'does not read them; the local source file remains accessible.',
              f"{final.get('rows')} lignes sont mises de côté comme échantillon de test final "
              "(holdout). Cette vue ne les lit pas ; le fichier source local reste accessible.")


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


def structure_lines(duplicates: Mapping, groups: list, lang: str) -> list[str]:
    """R38: the data card's lines on rows identical in what describes them and on the
    declared groups, known before the split (``data --json`` ``development``)."""
    out = []
    twins = duplicates.get('identical_feature_rows')
    if isinstance(twins, int) and twins:
        out.append(_t(lang, f'{twins} development rows are identical to another row on every '
                            'column that describes them (their target may differ): split '
                            'apart, a row is predicted from its twin.',
                      f"{twins} lignes de l'échantillon de développement sont identiques à une "
                      "autre sur toutes les colonnes qui les décrivent (leur cible peut "
                      "différer) : séparée de sa jumelle, une ligne est prédite à partir "
                      "d'elle."))
    for g in groups or []:
        n, rows = g.get('groups'), g.get('rows_in_repeated_groups')
        if not isinstance(n, int):
            continue
        out.append(_t(lang, f'{g["column"]}: {n} distinct values; {rows} rows share their value '
                            'with another row, so the folds can put a group on both sides.',
                      f'{g["column"]} : {n} valeurs distinctes ; {rows} lignes partagent leur '
                      'valeur avec une autre ligne : les plis peuvent mettre un même groupe '
                      'des deux côtés.'))
    return out


DATA_NOTE_FR = ("Ce sont uniquement des lignes de l'échantillon de développement ; "
                "l'échantillon de test final reste scellé. La fiche montre le sens des colonnes "
                'et quelques lignes, jamais la fréquence du résultat : elle est explorée après '
                'le découpage. ' + assurance.protection_notice('fr'))
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
    availability = ((view.get('decisions') or {}).get('feature_availability') or {})
    kept = availability.get('value') if isinstance(availability.get('value'), Mapping) else None
    return {'dev': dev, 'holdout': holdout, 'target': target, 'positive': positive,
            'unit': unit, 'folds': folds, 'cv': st.uses_cross_validation(state),
            'state': state,
            # Owner session 2026-10-26 (L5, R12, D8): a declared calendar year kept under a
            # temporal evaluation.
            'calendar': (drafts.calendar_advisory(case, state, kept, view.get('language') or EN)
                         if isinstance(state, Mapping) else None)}


def _fact(view: Mapping, fact_id: str):
    for items in ((view.get('facts') or {}).get('by_status') or {}).values():
        for item in items:
            if item.get('id') == fact_id:
                return item
    return None


def case_fact(view: Mapping, state: Mapping, fact_id: str, lang: str) -> dict | None:
    """A case fact of the view (``{id, value, source}``) with its ``value`` in ``lang``: the
    French form the case's translation sidecar gives in a French study (L3, D4 A,
    :mod:`mlkit.study.l10n`), else the case's own words."""
    fact = _fact(view, fact_id)
    if not fact or lang == EN:
        return fact
    french = ((((view.get('case_texts') or {}).get('facts') or {}).get(fact_id)) or {}) \
        .get(lang)
    return {**fact, 'value': french} if french else fact


def _unit_of(state) -> str | None:
    """The unit of a regression study's target (the case's), or None."""
    from .case import case_of
    try:
        case = case_of(state)
    except Exception:                    # noqa: BLE001 - a case that cannot be read: no unit
        return None
    return case.target_unit if case.task == st.REGRESSION else None


def _recommended(action: Mapping, view: Mapping, state: Mapping, lang: str) -> dict | None:
    """The engine's default for the decision ``action`` proposes, with a one-line why."""
    if action.get('kind') != 'propose':
        return None
    decision = action.get('decision')
    value = action.get('default_value')
    if decision == 'prediction_time':
        # L3 (R4, T4): the case's moment in the study language when the case translates it.
        fact = case_fact(view, state, 'prediction_time', lang)
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
    drafted = action.get('recommended')
    if decision in (st.PREPROCESSING, st.MODEL_VARIANT) and isinstance(drafted, Mapping) \
            and drafted.get('value') == value:
        # Owner session 2026-10-26 (L5, R5, R13): the view drafted it from the evidence
        # (:mod:`mlkit.study.drafts`), with its why (and, for the preparation, its reasons).
        return copy.deepcopy(dict(drafted))
    if decision == 'policy':
        return {'value': copy.deepcopy(value),
                'why': POLICY_WHY[_policy_source(value, view, state)][lang == FR]}
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
            'validation.') + (_t(lang, f' Here k = {value["folds"]}: {value["folds"]} folds.',
                                 f' Ici k = {value["folds"]} : {value["folds"]} plis.')
                              if isinstance(value, Mapping) and isinstance(value.get('folds'), int)
                              and not isinstance(value.get('folds'), bool) else ''),
        'preprocessing': _t(
            # R39: "no indicator" says what it means (missing cells are still imputed).
            lang, 'The default changes nothing (no missing-value indicator column, missing '
                  'cells still imputed; no grouping, no cap, no transform), so the results '
                  'stay comparable and nothing is tuned on the outcome.',
            'Le choix par défaut ne change rien (pas de colonne indicatrice de valeur '
            'manquante, les cellules manquantes restant imputées ; ni regroupement, ni '
            'plafond, ni transformation) : les résultats restent comparables et rien n\'est '
            'ajusté sur le résultat.'),
        'model_variant': _t(
            lang, 'The penalty chosen by nested cross-validation is the simplest check that '
                  'the candidate is not fitting noise; it counts as one trial of the budget of '
                  'three.',
            'La pénalité choisie par validation croisée imbriquée est le contrôle le plus '
            'simple que le candidat n\'apprend pas du bruit ; elle compte comme un essai du '
            'budget de trois.'),
        # Lot 2026-10-28 (EN-10).
        st.ERROR_METRIC: _t(
            lang, 'The MAE: every error weighs the same, and it reads in '
                  f'{_unit_of(state) or "the unit of the target"}. The RMSE is the alternative: '
                  'one big miss weighs much more; choose it if one big miss costs much more '
                  'than several small ones.',
            "La MAE : chaque erreur pèse pareil, et elle se lit en "
            f"{_unit_of(state) or 'unité de la cible'}. La RMSE est l'autre choix : un gros "
            'raté y pèse beaucoup plus ; à choisir si un gros raté coûte bien plus que '
            'plusieurs petits.'),
        'final_test': _t(
            lang, 'This is the configuration you chose; the holdout (final test) measures it '
                  'once.',
            "C'est la configuration que vous avez choisie ; l'échantillon de test final (holdout) "
            'la mesure une fois.'),
    }.get(decision)
    if why is None:
        return None
    return {'value': copy.deepcopy(value), 'why': why}


# Round 5 (review E, R5E-4): why the policy proposal carries its rule, by where the rule
# comes from (:func:`_policy_source`), as (English, French).
POLICY_WHY = {
    'criterion': ('The success criterion you confirmed fixes this rule: the policy adopts '
                  'the rule the criterion is measured at.',
                  'Le critère de succès que vous avez confirmé fixe cette règle : la règle '
                  'adoptée est celle à laquelle le critère est mesuré.'),
    'scenario': ('The teaching scenario assumes this share of the scored rows; a real team '
                 'would give its own capacity.',
                 'Le scénario pédagogique suppose cette part des lignes notées ; une vraie '
                 'équipe donnerait sa propre capacité.'),
    'engine': ('The engine evaluated a few shares of the scored rows because no capacity was '
               'given; this one is its default, the share its development diagnostics use, not '
               'a figure from a team. Name your team\'s own capacity if you know it.',
               "Le moteur a évalué quelques parts des lignes notées, faute de capacité "
               "donnée ; celle-ci est son choix par défaut, la part qu'utilisent ses "
               "diagnostics de développement, et non un chiffre fourni par une équipe. "
               "Indiquez la capacité de votre équipe si vous la connaissez."),
    # Review round 6 (area E, R6E-3): a rule named for this study, not the engine's default.
    'evaluated': ('This rule was named for this study\'s policy evaluation, which measured it: '
                  'it comes from your side, not from an engine default. Keep it if it is your '
                  'team\'s, or name the rule your team can act on.',
                  "Cette règle a été nommée pour l'évaluation de la règle de décision de cette "
                  "étude, qui l'a mesurée : elle vient de votre côté, pas d'un choix par défaut "
                  "du moteur. Gardez-la si c'est celle de votre équipe, ou indiquez la règle "
                  "qu'elle peut appliquer."),
    'proposal': ('This rule was proposed earlier in this study; it is proposed again because '
                 'something it rests on changed. It is not an engine default: keep it, or name '
                 'the rule your team can act on.',
                 "Cette règle a déjà été proposée dans cette étude ; elle est proposée à nouveau "
                 "parce qu'un élément dont elle dépend a changé. Ce n'est pas un choix par "
                 "défaut du moteur : gardez-la, ou indiquez la règle que votre équipe peut "
                 'appliquer.'),
}


def _policy_source(value, view: Mapping, state: Mapping) -> str:
    """Where a proposed policy rule comes from: ``criterion`` (the rule a review-v1 success
    criterion fixes), ``scenario`` (the case's assumed share), ``proposal`` (the rule of the
    policy decision or of a policy proposal, proposed again: round 6, R6E-3), ``evaluated``
    (a rule named for the current policy evaluation, whose rules are not the engine's own
    list: R6E-3), or ``engine`` (the engine's recommended share, when the evaluation ran on
    the engine's shares or there is none)."""
    from . import assurance
    from . import records as rec
    rule = rec.policy_rule(value)
    if assurance.profile(state) == 'review-v1':
        crit = ((state['decisions'].get(st.SUCCESS_CRITERION) or {}).get('value') or {})
        fixed = (crit.get('selection') or {}).get('rule') if isinstance(crit, Mapping) else None
        if isinstance(fixed, str) and rec.canonical_rule(fixed) == rule:
            return 'criterion'
    share = (((view.get('scenario_defaults') or {}).get('capacity_share') or {})
             .get('value'))
    if share is not None and rec.canonical_rule(f'share:{share}') == rule:
        return 'scenario'
    decision = (state.get('decisions') or {}).get('policy') or {}
    earlier = [rec.policy_rule(decision.get('value'))] if decision.get('status') in (
        'confirmed', 'reconfirm_required', 'proposed') else []
    earlier += [rec.policy_rule(p.get('value'))
                for p in (state.get('proposals') or {}).values()
                if p.get('decision_id') == 'policy' and p.get('status') == 'open']
    if rule is not None and rule in earlier:
        return 'proposal'
    params = (((view.get('results') or {}).get('policy.evaluation') or {}).get('params')
              or {})
    named = params.get('rules') if isinstance(params.get('rules'), list) else (
        [params['rule']] if params.get('rule') is not None else [])
    named = [rec.canonical_rule(r) or str(r) for r in named]
    from .view import RECOMMENDED_RULES
    if rule in named and set(named) != set(RECOMMENDED_RULES):
        return 'evaluated'
    return 'engine'


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
        why = _t(lang, f'The middle option, {pct}% less error than the reference (predict the '
                       'mean): a moderate bar chosen by convention, not from the costs of this '
                       'case. Keep it, or name the minimum your team needs.',
                 f"L'option du milieu, {pct} % d'erreur en moins que la référence (prédire la "
                 'moyenne) : un seuil modéré, choisi par convention et non à partir des coûts '
                 "de ce cas. Gardez-le, ou indiquez le minimum dont votre équipe a besoin.")
        bar = value.get('business_max_error')
        if isinstance(bar, (int, float)):
            # R67: the business bar of the use-case brief, judged with the minimum.
            from .cite import format_value
            why += _t(lang, ' The business bar is the current method\'s error, '
                            f'{format_value(bar, "f1", "en")} from the use-case brief: both '
                            'levels are fixed now and judged on the final test.',
                      " La barre métier est l'erreur de la méthode actuelle, "
                      f'{format_value(bar, "f1", "fr")} selon la fiche du cas d\'usage : les '
                      'deux niveaux sont fixés maintenant et jugés sur le test final.')
        if any(m.get('metric') == 'rmse_reduction' for m in options.get('metrics') or []):
            # R46: the metric is a decision; MAE is proposed by default, and why.
            why += _t(lang, ' The metric is the mean absolute error (MAE): every error weighs '
                            'the same and it reads in the unit of the target. Choose the RMSE '
                            'instead if one big miss is much worse than '
                            'several small ones.',
                      " La métrique est l'erreur absolue moyenne (MAE) : chaque erreur pèse "
                      "autant et elle se lit dans l'unité de la cible. Choisissez plutôt la "
                      'RMSE si une grosse erreur est bien pire que plusieurs '
                      'petites.')
        return {'value': value, 'why': why}
    default = options.get('default_metric')
    if isinstance(default, str) and default != value.get('metric'):
        value['metric'] = default
        if isinstance(value.get('selection'), Mapping):
            # R5E-6: a review-v1 value measures the selection on the metric it names.
            from .criterion import SELECTION_METRIC
            value['selection'] = {**value['selection'],
                                  'metric': SELECTION_METRIC.get(default, 'precision')}
    points = value.get('min_points')
    per = middle.get('per_1000')
    extra = (_t(lang, f' On {SCALE_1000} actions, about {per["extra"]} more positives than the '
                      'baseline.',
                f' Sur {SCALE_1000_FR} actions, environ {per["extra"]} positifs de plus que le '
                'modèle de référence.')
             if isinstance(per, Mapping) and isinstance(per.get('extra'), int) else '')
    metric = audience_metric(value['metric'], lang)
    rule = (value.get('selection') or {}).get('rule')
    if isinstance(rule, str):
        # R5E-6: a review-v1 criterion names the rule it is measured at.
        extra += _t(lang, f' It is measured at the rule: {audience.rule_words(rule)}.',
                    f' Il est mesuré à la règle : {audience.rule_words(rule, FR)}.')
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


def _k_folds(action: Mapping) -> int | None:
    """The number of folds of the split value an action proposes or waits on, else None."""
    for value in (action.get('default_value'), (action.get('recommended') or {}).get('value')
                  if isinstance(action.get('recommended'), Mapping) else None):
        folds = value.get('folds') if isinstance(value, Mapping) else None
        if isinstance(folds, int) and not isinstance(folds, bool) and folds > 1:
            return folds
    return None


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
    if kind == 'resolve_hold':
        # Review round 6 (area E): the condition the junior set, in their own words.
        return _t(lang, 'Is the condition you set met now?',
                  'La condition que vous avez posée est-elle remplie maintenant ?')
    if kind == 'show_data_card':
        # Lot 2026-10-28 (EN-13, R54): the question says what is shown and names the next
        # step by its full name.
        return _t(lang, 'The data card is shown. Shall we move on to the prediction moment?',
                  'La fiche des données est affichée. On passe au moment de la prédiction ?')
    if kind == 'read_exploration':
        # Lot 2026-10-28 (EN-12, R61): the pause after the exploration.
        return _t(lang, "The exploration's charts are shown. Shall we move on to the models?",
                  "Les graphiques de l'exploration sont affichés. On passe aux modèles ?")
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
        # R36: k is stated (the folds of the drafted value) when it is known.
        'split': (_t(lang, f'Do you evaluate with this {_k_folds(action)}-fold cross-validation '
                           f'(k = {_k_folds(action)})?',
                     f'Évaluez-vous avec cette validation croisée à {_k_folds(action)} plis '
                     f'(k = {_k_folds(action)}) ?') if _k_folds(action) else
                  _t(lang, 'Do you evaluate with this k-fold cross-validation?',
                     'Évaluez-vous avec cette validation croisée à k plis ?')) if cv else
        _t(lang, 'How should the rows be divided between the training set and the validation '
                 'set?',
           "Comment répartir les lignes entre le jeu d'entraînement et le jeu de validation ?"),
        'success_criterion': (_t(lang, 'Which metric, and which minimum gain over the '
                                       'baseline, would make the model worth using?',
                                 'Quelle métrique, et quel gain minimum sur le modèle de '
                                 'référence, rendraient le modèle utile ?')
                              if task == st.BINARY else
                              # R46: the metric is part of the question (MAE or RMSE).
                              _t(lang, 'Which error (MAE by default, or RMSE), and which minimum '
                                       'reduction of the baseline\'s error, would make the '
                                       'model worth using?',
                                 'Quelle erreur (la MAE par défaut, ou la RMSE), et quelle '
                                 'réduction minimale de l\'erreur de référence, rendraient le '
                                 'modèle utile ?')),
        'preprocessing': (_t(lang, 'Do you keep this preparation, drafted from the quality '
                                   'check, or the default, or change one parameter for a '
                                   'reason you can state?',
                             "Gardez-vous cette préparation, établie d'après le contrôle de "
                             'qualité, ou la préparation par défaut, ou changez-vous un '
                             'paramètre pour une raison que vous pouvez énoncer ?')
                          if action.get('alternatives') else
                          _t(lang, 'Do you keep the default preparation, or change one '
                                   'parameter for a reason you can state?',
                             'Gardez-vous la préparation par défaut, ou changez-vous un '
                             'paramètre pour une raison que vous pouvez énoncer ?')),
        # Lot 2026-10-28 (EN-10, R54): the question names the drafted measure.
        st.ERROR_METRIC: _t(lang, 'Which error measure do we keep: the mean absolute error '
                                  '(MAE)?',
                            "Quelle mesure de l'erreur retient-on : l'erreur absolue moyenne "
                            '(MAE) ?'),
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


def _looks_sentence(view: Mapping, lang: str) -> str:
    """Owner session 2026-10-26 (L5, R7): the data-contingent stamp of a preparation in the
    junior's words: the term "look at the target" first, then this study's looks (none: the
    preparation is not data-contingent; some: why it is recorded, not a mistake)."""
    looks = view.get('eda_looks') or {}
    count = looks.get('target_looks') or 0
    if not count:
        return _t(lang, 'Look at the target: an analysis that reads the variable to predict. '
                        'None has come before this preparation, so it is not data-contingent.',
                  'Regard sur la cible : une analyse qui lit la variable à prédire. Aucun '
                  "n'a précédé cette préparation : elle n'est donc pas dépendante des "
                  'données.')
    return drafts.contingency_text(count, looks.get('by_activity') or {}, 0, lang)


def _digest_propose(decision: str, view: Mapping, ctx: dict, lang: str,
                    action: Mapping) -> list[str]:
    dev, holdout, folds = ctx['dev'], ctx['holdout'], ctx['folds']
    target, positive, unit = ctx['target'], ctx['positive'], ctx['unit']
    if decision == 'prediction_time':
        fact = case_fact(view, ctx['state'], 'prediction_time', lang)
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
                # Owner session 2026-10-26 (L5, R5): what the fixed pipeline already does.
                drafts.PIPELINE_SENTENCE[FR if lang == FR else EN],
                # L5 (R7): the stamp explained, the term "look at the target" first.
                _looks_sentence(view, lang)]
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
                # Owner session 2026-10-26 (L5, R14, R12): the families as the junior knows
                # them, why no random forest, and the calendar-year advisory.
                drafts.families_sentence(lang) if families else '',
                ctx.get('calendar') or '',
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
            words, words_fr = audience.policy_words(share), audience.policy_words(share, FR)
            source = _policy_source(share, view, ctx.get('state') or {'decisions': {}})
            out.append({'criterion': _t(lang, f'Your success criterion fixes the rule: {words}.',
                                        f'Votre critère de succès fixe la règle : {words_fr}.'),
                        'scenario': _t(lang, f'The scenario assumes: {words}.',
                                       f'Le scénario suppose : {words_fr}.'),
                        'engine': _t(lang, f'The engine proposes: {words}.',
                                     f'Le moteur propose : {words_fr}.'),
                        # Round 6 (R6E-3): where the rule comes from, truly.
                        'evaluated': _t(lang, f'The rule named for this study: {words}.',
                                        f'La règle nommée pour cette étude : {words_fr}.'),
                        'proposal': _t(lang, f'Proposed again: {words}.',
                                       f'Proposée à nouveau : {words_fr}.')}[source])
        return out
    if decision == 'model_choice':
        if view.get('task') == st.BINARY:
            return [_t(lang, 'Model choice: retain the logistic candidate or one confirmed '
                             'variant, using their comparison on the same development folds. '
                             'Comparing a model does not select it.',
                       'Choix du modèle : retenir le candidat logistique ou une variante '
                       'confirmée, d’après leur comparaison sur les mêmes plis de '
                       'développement. Comparer un modèle ne le sélectionne pas.'),
                    _criterion_status_words(view, lang) or '']
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
                          'their meaning, and eight development rows drawn at random, target '
                          'included: a look at the target, counted in the exposure ledger. '
                          'Nothing is decided at this step.',
                    'La fiche des données montre ce que décrit une ligne, les colonnes '
                    'regroupées avec leur sens, et huit lignes de développement tirées au '
                    'hasard, cible comprise : un regard sur la cible, compté au registre '
                    'd\'exposition. Rien n\'est décidé à cette étape.')]
        return _fit(parts)
    if kind == 'propose':
        parts = _digest_propose(action.get('decision'), view, ctx, lang, action)
        rec = action.get('recommended')
        if rec:
            parts.insert(1 if len(parts) > 1 else len(parts),
                         _t(lang, f'Recommended: {rec["why"]}', f'Recommandé : {rec["why"]}'))
        if action.get('not_recomputable') and junior_message:
            # Round 5 (review E, R5E-8): after the opening, why the final test cannot be
            # computed again comes first.
            parts.insert(0, junior_message)
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
        rules = [audience.rule_words(r, lang) for r in action.get('rules') or []]
        on = (_t(lang, ', on the rules: ' + '; '.join(rules),
                 ', sur les règles : ' + ' ; '.join(rules)) if len(rules) > 1 else
              _t(lang, f', on the rule: {rules[0]}', f', sur la règle : {rules[0]}')
              if rules else '')
        column = (action.get('options') or {}).get('column')
        if column and ':' not in str(activity):
            # L5: a per-column run names its column ("the distribution of a column (adr)").
            activity = f'{activity}:{column}'
        lead = _t(lang, f'Next: {audience.activity_words(activity)}, run without asking '
                        f'you{on}.',
                  f'Ensuite : {audience.activity_words(activity, FR)}, lancé sans vous '
                  f'demander{on}.')
        return _fit([lead, _run_follow_up(action, view, junior_message, lang)])
    if kind == 'done':
        return _fit([junior_message, _criterion_status_words(view, lang) or ''])
    if kind == 'reconfirm':
        decision = action.get('decision')
        reason = ((view.get('decisions') or {}).get(decision) or {}).get('reason')
        words = audience.reason_words(reason, lang) if reason else ''
        return _fit([junior_message, (words[:1].upper() + words[1:]).rstrip('.') + '.'
                     if words else ''])
    return _fit([junior_message])


def _run_follow_up(action: Mapping, view: Mapping, junior_message: str, lang: str) -> str:
    """Round 5 (review E, R5E-4): what follows a run in the digest. A run asks nothing, so
    the step's question (the junior message of a plain run) is introduced for what it is:
    the decision the junior takes once the result is there, or, at a step without a
    decision, the question the result answers. Any other junior message (why the run comes
    first) is kept as it is."""
    if not junior_message.rstrip().endswith('?'):
        return junior_message
    step = next((s for s in view.get('plan') or [] if s.get('id') == action.get('step')), {})
    if step.get('decision'):
        return _t(lang, f'Once it is done, you decide: {junior_message}',
                  f'Une fois fait, c\'est vous qui décidez : {junior_message}')
    return _t(lang, f'It answers this question: {junior_message}',
              f'Il répond à cette question : {junior_message}')


# --- free choices (owner session 2026-10-26, L1, R2c) -------------------------------------

CHOICE_DECISIONS = ('model_choice', 'conclusion')
CHOICE_OPTION_KEYS = ('id', 'value', 'label')
# The verdicts in the junior's words, (English, French); ``keep_baseline`` of a regression
# study keeps the mean baseline.
VERDICT_LABELS = {'adopt_policy': ('Adopt the rule', 'Adopter la règle'),
                  'adopt_model': ('Adopt the chosen model', 'Adopter le modèle choisi'),
                  'keep_baseline': ('Keep the baseline', 'Garder le modèle de référence'),
                  'inconclusive': ('Do not conclude (inconclusive)',
                                   'Ne pas conclure (non concluant)')}
REGRESSION_KEEP_LABEL = ('Keep the mean baseline', 'Garder la moyenne de référence')
_ORDINAL_VARIANTS = {EN: ('The first variant', 'The second variant', 'The third variant'),
                     FR: ('La première variante', 'La deuxième variante',
                          'La troisième variante')}


def _model_label(slot: str, state: Mapping, lang: str) -> str:
    """A model slot in the junior's words; a variant with what it changes ("La deuxième
    variante · une Explainable Boosting Machine (EBM)")."""
    from . import trials
    if not trials.is_variant_slot(slot):
        words = audience.model_words(slot, lang)
        return words[:1].upper() + words[1:]
    variants = trials.variants_of(trials.confirmed_value(state))
    index = trials.variant_index(slot)
    head = (_ORDINAL_VARIANTS[lang if lang == FR else EN][index - 1] if len(variants) > 1
            else _t(lang, 'The variant', 'La variante'))
    if index <= len(variants):
        return f'{head} · {trials.variant_words(variants[index - 1], lang)}'
    return head


def choice_options(action: Mapping, state: Mapping, lang: str, accepts) -> list[dict] | None:
    """The values the engine accepts now at a free choice, ``[{id, value, label}]`` in the
    study language, or None: on the ``propose`` of the model choice or the conclusion when
    the engine recommends nothing (``recommended`` null). ``accepts(decision, value)`` is the
    engine's own check of a confirmation of that value
    (:func:`mlkit.study.feasibility.accepts`), so no option is one the engine refuses and no
    accepted value is missing. A conclusion's ``value`` is ``{"verdict"}``: its text is the
    junior's, written when it is proposed."""
    decision = action.get('decision')
    if action.get('kind') != 'propose' or decision not in CHOICE_DECISIONS \
            or action.get('recommended') is not None or accepts is None:
        return None
    from . import commands as cmd, preconditions
    out = []
    fr = lang == FR
    if decision == 'conclusion':
        regression = st.task_of(state) == st.REGRESSION
        for verdict in preconditions.conclusion_verdicts(state):
            if accepts(decision, {'verdict': verdict, 'text': verdict}):
                label = (REGRESSION_KEEP_LABEL if regression and verdict == 'keep_baseline'
                         else VERDICT_LABELS[verdict])[fr]
                out.append({'id': verdict, 'value': {'verdict': verdict}, 'label': label})
    else:
        for slot in cmd.model_choices(state):
            if accepts(decision, slot):
                out.append({'id': slot, 'value': slot,
                            'label': _model_label(slot, state, lang)})
    return out or None


def enrich(view: dict, state: Mapping, case=None, *, accepts=None) -> dict:
    """Add the junior-ready keys to ``view['next_action']`` in place (and return it):
    ``language``, ``junior_digest``, ``recommended``, ``question``; ``criterion_options`` at
    the success criterion; the case's availability as ``default_value`` at the feature
    availability; ``choice_options`` at a free choice (:func:`choice_options`, with the
    view's ``accepts``)."""
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
        measure = business = None
        if isinstance(state, Mapping) and st.has_error_metric(state):
            # Lot 2026-10-28 (EN-9, R67): a study deciding its error measure fixes the
            # criterion on it, with the business bar of the use-case brief by default.
            from . import case_brief
            measure = st.confirmed_error_metric(state)
            business = case_brief.business_bar(case_brief.of_state(state),
                                               measure or st.DEFAULT_ERROR_METRIC)
        action['criterion_options'] = criterion.options(
            view, lang, unit=case.target_unit if case is not None
            and getattr(case, 'task', None) == 'regression' else None,
            measure=measure, business=business)
    ctx = _context(view, state, case)
    action['language'] = lang
    recommended = _recommended(action, view, state, lang)
    if recommended and decision == 'feature_availability' and isinstance(state, Mapping):
        # Owner session 2026-10-26 (L5, R12, D8): a declared calendar year kept under a
        # temporal evaluation.
        advisory = drafts.calendar_advisory(case, state, recommended.get('value'), lang)
        if advisory:
            recommended['why'] = f'{recommended["why"]} {advisory}'
    action.pop('recommended', None)
    action['recommended'] = recommended
    action['question'] = _question(action, view, lang, ctx['cv'])
    action['junior_digest'] = _digest(action, view, state, ctx, lang)
    # Owner batch of 2026-10-28: the plan in its real order (R36, R37) and the registered
    # results that show the data facts the step cites (R40).
    action['plan_recap'] = plan_recap(view, state, action, lang)
    action['evidence'] = evidence_slots(action, view)
    choices = choice_options(action, state, lang, accepts)
    if choices:
        action['choice_options'] = choices
    return view


# --- the plan recap (R36, R37) and the evidence of a step (R40) -----------------------------

PLAN_RECAP_WORDS = {
    EN: {'lead': 'The plan, in order: ', 'join': ', ', 'moments': '; ',
         'current': 'Current step: {step} ({n} of {total}).',
         'done': 'Every step of the plan is done.'},
    FR: {'lead': "Le plan, dans l'ordre : ", 'join': ', ', 'moments': ' ; ',
         'current': 'Étape actuelle : {step} ({n} sur {total}).',
         'done': 'Toutes les étapes du plan sont faites.'},
}


def plan_recap(view: Mapping, state: Mapping, action: Mapping | None, lang: str) -> str:
    """``next_action.plan_recap``: the study's own plan, its moments and their steps in plan
    order (the panel's short step names, ``companion_env.STEP_LABELS``), then the current
    step; never a fixed list, so a structural-first study reads Quality, Preparation,
    Exploration in that order (R36, R37)."""
    from . import companion_env as ce
    from . import view as vw
    words = PLAN_RECAP_WORDS[FR if lang == FR else EN]
    plan = list(view.get('plan') or [])
    ids = [s.get('id') for s in plan]
    try:
        moments = vw.moments(view.get('task') or st.BINARY, state)
    except Exception:                    # noqa: BLE001 - a plan without moments: one list
        moments = [{'title': '', 'steps': ids}]
    parts = []
    for m in moments:
        steps = [s for s in m.get('steps') or [] if s in ids]
        if not steps:
            continue
        names = words['join'].join(ce.step_name(s, lang) for s in steps)
        parts.append(f'{m["title"]} ({names})' if m.get('title') else names)
    text = words['lead'] + words['moments'].join(parts) + '.'
    current = ce.current_step(action, plan)
    if (action or {}).get('kind') == 'done' or current not in ids:
        return f'{text} {words["done"]}' if (action or {}).get('kind') == 'done' else text
    return f'{text} ' + words['current'].format(step=ce.step_name(current, lang),
                                                n=ids.index(current) + 1, total=len(ids))


# R43, R48 (owner batch of 2026-10-28): the one limit that fits the current step, for the
# panel's limit line (``texts.<lang>.step_limit`` of the digest).
STEP_LIMITS = {
    'frame': (
        'Nothing is measured yet: these decisions fix the protocol before any model is fitted.',
        "Rien n'est encore mesuré : ces décisions fixent le protocole avant tout modèle."),
    'structural_eda': (
        'This check reads the development rows without the target: it is not a look at the '
        'target.',
        "Ce contrôle lit les lignes de développement sans la cible : ce n'est pas un regard "
        'sur la cible.'),
    'preprocessing': (
        'The preparation is decided from target-free checks, before any look at the target.',
        'La préparation est décidée à partir de contrôles sans la cible, avant tout regard sur '
        'la cible.'),
    'train_eda': (
        'These charts read the target of the development rows: each look is counted.',
        'Ces graphiques lisent la cible des lignes de développement : chaque regard est '
        'compté.'),
    'final': (
        'The final test measures the chosen configuration once, on rows no choice used: it is '
        "the study's independent evidence. It does not establish the performance on later "
        'periods or other data, nor a causal effect.',
        "Le test final mesure une fois la configuration choisie, sur des lignes qu'aucun choix "
        "n'a utilisées : c'est la preuve indépendante de l'étude. Il n'établit ni la "
        "performance sur d'autres périodes ou d'autres données, ni un effet causal."),
}
FRAME_STEPS = ('discover_data', 'prediction_time', 'feature_availability', 'split',
               st.ERROR_METRIC, st.SUCCESS_CRITERION)


def step_limit(view: Mapping, lang: str) -> str | None:
    """The limit line of the current step (R43, R48): the framing steps measure nothing yet;
    the quality check reads no target; the exploration's charts are counted looks; the
    models, variants and choice rest on development evidence (the study's
    ``validation_is_not_independent`` limit); the final test and the conclusion say what the
    final test does and does not establish."""
    from . import companion_env as ce
    action = view.get('next_action') or {}
    plan = list(view.get('plan') or [])
    step = ce.current_step(action, plan)
    if action.get('kind') == 'done' or step == 'conclusion' or _final_opened(view):
        return STEP_LIMITS['final'][lang == FR]
    if step in FRAME_STEPS:
        return STEP_LIMITS['frame'][lang == FR]
    if step in STEP_LIMITS:
        return STEP_LIMITS[step][lang == FR]
    item = next((x for x in view.get('not_yet_defensible') or []
                 if x.get('id') == 'validation_is_not_independent'), None)
    return (item.get('junior_text') or item.get('text')) if item else None


def _final_opened(view: Mapping) -> bool:
    status = ((view.get('final_test') or {}).get('status'))
    return status == 'opened'


# The registered results each data-backed decision rests on (R40): the panel places their
# figures in Now, the report beside the decision.
EVIDENCE_SLOTS = {
    st.PREPROCESSING: ('eda.quality',),
    st.MODEL_VARIANT: ('diag.regression', 'diag.binary'),
    'model_choice': ('evaluate.regression', 'policy.evaluation', 'diag.regression',
                     'diag.binary'),
    'policy': ('policy.evaluation', 'diag.binary'),
    'conclusion': ('final_test.evaluation', 'diag.final_test'),
}


def evidence_slots(action: Mapping, view: Mapping, decision: str | None = None) -> list[str]:
    """The slots of the current results (integrity ok) that show the data facts a proposal
    of ``decision`` (default: the action's) cites (R40): the quality check and the
    distributions of the columns a drafted preparation names, the linear model's diagnostics
    for the variants, the evaluation and its diagnostics for the model choice or the rule,
    the final evaluation and its diagnostics for the conclusion. Empty for a decision that
    rests on no data (the moment, the availability, the split, the criterion) and for a
    run."""
    action = action or {}
    decision = decision or action.get('decision')
    if action.get('kind') == 'done':
        decision = 'conclusion'
    if action.get('kind') == 'run' or decision not in EVIDENCE_SLOTS:
        return []
    results = view.get('results') or {}

    def usable(slot):
        item = results.get(slot) or {}
        return bool(item.get('current')) and item.get('integrity', 'ok') == 'ok'
    slots = [s for s in EVIDENCE_SLOTS[decision] if usable(s)]
    if decision == st.PREPROCESSING:
        columns = [r.get('column') for r in
                   ((action.get('recommended') or {}).get('reasons') or [])
                   if isinstance(action.get('recommended'), Mapping)]
        value = action.get('default_value')
        if isinstance(value, Mapping):
            columns += list(value.get('log_transform') or [])
            for key in ('caps', 'missing', 'rare_category_min_rows'):
                if isinstance(value.get(key), Mapping):
                    columns += list(value[key])
        for column in dict.fromkeys(c for c in columns if isinstance(c, str)):
            slot = f'eda.distribution:{column}'
            if usable(slot) and slot not in slots:
                slots.append(slot)
    return slots


# --- the study panel's texts (contract P1, CLI-CONTRACT §17.2.3) ----------------------------

# The fixed words of a step's headline (``panel_digest.headlines``): a headline holds the
# decision's value in words, these words, and figures of current results formatted by
# ``cite.format_value``; nothing else.
HEADLINES = {
    # The line holds no step name: the panel prints the step's short name beside it.
    'en': {'line': '{text}.', 'join': '; ',
           'against': '{metric} {value} against {baseline} for the baseline',
           'error': 'mean absolute error', 'precision': 'precision',
           'quality': '{rows} development rows checked, {duplicates} duplicated',
           'target_rate': 'outcome rate {value} on the explored rows',
           'target_mean': 'mean target {value} on the explored rows'},
    'fr': {'line': '{text}.', 'join': ' ; ',
           'against': '{metric} {value} contre {baseline} pour le modèle de référence',
           'error': 'erreur absolue moyenne', 'precision': 'précision',
           'quality': '{rows} lignes de développement vérifiées, {duplicates} en double',
           'target_rate': 'taux de résultat positif {value} sur les lignes explorées',
           'target_mean': 'cible moyenne {value} sur les lignes explorées'},
}
# ``texts.*.options_note`` (``junior.options_note``).
OPTIONS_NOTES = {
    'en': {'choice': 'From the simplest to the most flexible; the order is not a '
                     'recommendation.',
           'recommended': 'Recommended: {value}.', 'none': 'No recommendation.'},
    'fr': {'choice': "Du plus simple au plus souple ; l'ordre n'est pas une recommandation.",
           'recommended': 'Recommandé : {value}.', 'none': 'Sans recommandation.'},
}


def options_note(view: Mapping, action: Mapping, lang: str = 'en') -> str | None:
    """One sentence on the options' order and the recommendation (``texts.*.options_note``):
    a free choice's options go from the simplest to the most flexible and none is
    recommended; a recommended value is named, with its why; a review recommends nothing;
    null otherwise (no question, or nothing to say)."""
    from . import automation_words
    lang = lang if lang in OPTIONS_NOTES else 'en'
    notes = OPTIONS_NOTES[lang]
    pause = action.get('pause') or {}
    if action.get('kind') in ('run', 'blocked', 'done', 'outcome_unknown'):
        return None
    if pause.get('kind') == 'choice':
        return notes['choice']
    recommended = action.get('recommended')
    if isinstance(recommended, Mapping) and recommended.get('value') is not None:
        words = automation_words.value_words({**view, 'language': lang},
                                             action.get('decision'), recommended['value'])
        why = str(recommended.get('why') or '').strip()
        return ' '.join(filter(None, (notes['recommended'].format(value=words), why)))
    if pause.get('kind') == 'decision' and pause.get('recommended_option') is None:
        return notes['none']
    return None


# Contract P1.13 (CLI-CONTRACT §17.2.6): a rule or a model choice proposed as a change after
# an evaluation of the earlier value was seen.
CHANGED_AFTER_VALIDATION = 'changed_after_validation'
CHANGED_AFTER_VALIDATION_TEXT = {
    'en': {'policy': 'This rule is proposed after you saw how the earlier one did on the '
                     'validation rows: a change guided by those figures makes them slightly '
                     'optimistic. It is recorded, not refused.',
           'model_choice': 'This model is proposed after you saw how the earlier one did on '
                           'the validation rows: a change guided by those figures makes them '
                           'slightly optimistic. It is recorded, not refused.'},
    'fr': {'policy': 'Cette règle est proposée après que vous avez vu les résultats de la '
                     'précédente sur les lignes de validation : un changement guidé par ces '
                     'chiffres les rend un peu optimistes. Il est enregistré, pas refusé.',
           'model_choice': 'Ce modèle est proposé après que vous avez vu les résultats du '
                           'précédent sur les lignes de validation : un changement guidé par '
                           'ces chiffres les rend un peu optimistes. Il est enregistré, pas '
                           'refusé.'},
}


def changed_after_validation_text(decision_id: str | None, lang: str = 'en') -> str:
    """The junior's sentence of a rule or model changed after its evaluation was seen."""
    table = CHANGED_AFTER_VALIDATION_TEXT.get(lang, CHANGED_AFTER_VALIDATION_TEXT['en'])
    return table['model_choice' if decision_id == 'model_choice' else 'policy']


__all__ = ['step_text', 'all_step_texts', 'limit_fr', 'LIMIT_IDS_FR', 'enrich',
           'availability_draft', 'final_test_line', 'duplicates_line', 'MAX_DIGEST_WORDS',
           'choice_options', 'CHOICE_OPTION_KEYS']
