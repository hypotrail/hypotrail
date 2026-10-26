"""The French words of a French study's HTML report (owner session 2026-10-26, L3, R4).

The report's labels, steps and definitions come from the content files, in French for a French
study (``report_fr.yaml``, ``steps_fr.yaml``, the glossary's ``*_fr`` entries, the
``fr_labels`` of ``activities.yaml``). The charts and the diagnostics also write fixed
English phrases of their own (axis titles, figure captions, legends, table heads, notes
around cited numbers: ``render_charts``, ``render_diagnostics``, ``render_html``). This
module gives each of them its French form, applied to the report body of a French study
(:func:`french`): every text node and every ``aria-label`` and ``title`` that is exactly one
of these phrases, or one of their patterns, is replaced; everything else is left as written
(cited numbers are their own elements, so a phrase around a number is a text node of its own;
the case's statements, identifiers and the junior's words are left untouched). An English
report is never changed.

``test_l3_language.py`` renders French reports and checks that no English sentence is left,
so a new English phrase in a renderer needs its line here.
"""
from __future__ import annotations

import html
import re
from typing import Callable

# Exact phrases (a whole text node, an aria-label or a title, stripped of its surrounding
# spaces, which are kept).
EXACT = {
    # render_html
    'Decision the study supports': "Décision que l'étude appuie",
    'Intended use': 'Usage prévu',
    'Prediction moment': 'Moment de la prédiction',
    'Statements of the case are never decisions: each one keeps its status and source.':
        "Les énoncés du cas ne sont jamais des décisions : chacun garde son statut et sa "
        "source.",
    'Structure': 'Structure',
    'Source:': 'Source :',
    'not available': 'non disponible',
    'not recorded': 'non enregistré',
    'Method.': 'Méthode.',
    'Decision.': 'Décision.',
    'Interpretation.': 'Interprétation.',
    'Consequence.': 'Conséquence.',
    'Question.': 'Question.',
    'Rows read:': 'Lignes lues :',
    'tied rows': 'lignes ex aequo',
    'of them selected': 'sélectionnées',
    'Intervals:': 'Intervalles :',
    'percentile intervals.': 'intervalles des percentiles.',
    'Rule': 'Règle',
    'Model': 'Modèle',
    'Metric': 'Mesure',
    'Difference': 'Écart',
    'Interval': 'Intervalle',
    'Tie at the cut': 'Ex aequo au seuil',
    'Unit:': 'Unité :',
    '. Unit:': '. Unité :',
    'Mean (bias)': 'Moyenne (biais)',
    'Standard deviation': 'Écart-type',
    '5th percentile': '5e percentile',
    'First quartile': 'Premier quartile',
    'Median': 'Médiane',
    'Third quartile': 'Troisième quartile',
    '95th percentile': '95e percentile',
    'Value': 'Valeur',
    'Rows': 'Lignes',
    'Too few rows to read alone': 'Trop peu de lignes pour être lu seul',
    'Value path': 'Chemin de la valeur',
    'Full id': 'Identifiant complet',
    '; partition': ' ; partition',
    '; parameters': ' ; paramètres',
    '; code fingerprint': ' ; empreinte du code',
    '; environment': ' ; environnement',
    'Purposes recorded:': 'Finalités enregistrées :',
    '. Validation rows used for selection: yes.':
        '. Lignes de validation utilisées pour la sélection : oui.',
    '. Validation rows used for selection: no.':
        '. Lignes de validation utilisées pour la sélection : non.',
    'Historical record': 'Historique',
    'Historical results remain inspectable and are not current adoption evidence.':
        "Les résultats historiques restent consultables et ne sont pas des preuves actuelles "
        "pour une adoption.",
    'Final-test drift: decisions or results changed after the final test was opened; '
    'current development evidence is kept separate from that historical final measure.':
        "Dérive après le test final : des décisions ou des résultats ont changé après "
        "l'ouverture du test final ; les preuves de développement actuelles restent séparées "
        "de cette mesure finale historique.",
    'Final test': 'Test final',
    '. Case:': '. Cas :',
    'Data exposure': 'Exposition des données',
    'Second variant': 'Deuxième variante',
    'Third variant': 'Troisième variante',
    ': mean residual': ' : résidu moyen',
    ': MAE': ' : MAE',
    'Variable': 'Variable',
    # render_charts
    'Other outcome': 'Autre résultat',
    'Mean': 'Moyenne',
    'with its interval': 'avec son intervalle',
    'to': 'à',
    'to the': 'au',
    'interval': 'intervalle',
    'Positive rate': 'Taux de positifs',
    'Mean of the target': 'Moyenne de la cible',
    'Range chance alone draws': 'Étendue que le hasard seul produit',
    'The spread between groups is larger than every one of the shuffles of the target: a '
    'pattern unlikely to be chance alone.':
        "L'écart entre les groupes est plus grand que chacun des mélanges de la cible : un "
        "motif qui a peu de chances de venir du seul hasard.",
    'The spread between groups stays within what shuffling the target draws: it is not '
    'distinguishable from chance.':
        "L'écart entre les groupes reste dans ce que le mélange de la cible produit : il ne se "
        "distingue pas du hasard.",
    'Intervals: 95% level.': 'Intervalles : niveau de 95 %.',
    'level.': 'de niveau.',
    'Area under the ROC curve': 'Aire sous la courbe ROC',
    'Share of variance explained': 'Part de variance expliquée',
    'Used by the model': 'Utilisée par le modèle',
    'Strong enough to question': 'Assez forte pour poser la question',
    'Not used by the model': 'Non utilisée par le modèle',
    'Check legitimacy': 'Vérifier la légitimité',
    'chance': 'hasard',
    'Which feature alone carries a strong signal?': 'Quelle variable seule porte un signal fort ?',
    'Model (logistic, the candidate)': 'Modèle (logistique, le candidat)',
    'Model (the variant, adopted with the rule)': 'Modèle (la variante, adoptée avec la règle)',
    'Model (the second variant, adopted with the rule)':
        'Modèle (la deuxième variante, adoptée avec la règle)',
    'Model (the third variant, adopted with the rule)':
        'Modèle (la troisième variante, adoptée avec la règle)',
    'Baseline': 'Modèle de référence',
    'Baseline (no ranking, average count)': 'Modèle de référence (sans classement, effectif moyen)',
    'Positive rows found among the selected rows':
        'Lignes positives trouvées parmi les lignes sélectionnées',
    'rows selected': 'lignes sélectionnées',
    'positive rows in all': 'lignes positives en tout',
    'Out-of-fold predictions of the development rows':
        'Prédictions hors pli des lignes de développement',
    'Out-of-fold predictions of the development rows, each rule applied within each fold. The '
    'rule is chosen on these rows, so these counts are optimistic and are not a forecast. The '
    'dashed line is every positive row of the development rows.':
        "Prédictions hors pli des lignes de développement, chaque règle appliquée dans chaque "
        "pli. La règle est choisie sur ces lignes : ces effectifs sont donc optimistes et ne sont "
        "pas une prévision. Le trait pointillé représente toutes les lignes positives des lignes "
        "de développement.",
    'Out-of-fold predictions of the development rows. The rule is chosen on these rows, so '
    'these counts are optimistic and are not a forecast. The dashed line is every positive row '
    'of the development rows.':
        "Prédictions hors pli des lignes de développement. La règle est choisie sur ces lignes : "
        "ces effectifs sont donc optimistes et ne sont pas une prévision. Le trait pointillé "
        "représente toutes les lignes positives des lignes de développement.",
    'Validation rows. The rule is chosen on these rows, so these counts are optimistic and are '
    'not a forecast. The dashed line is every positive row of the validation rows.':
        "Lignes de validation. La règle est choisie sur ces lignes : ces effectifs sont donc "
        "optimistes et ne sont pas une prévision. Le trait pointillé représente toutes les "
        "lignes positives du jeu de validation.",
    'Among the rows each rule selects, how many positive rows does the model find, compared '
    'with the baseline?':
        'Parmi les lignes que chaque règle sélectionne, combien de lignes positives le modèle '
        'trouve-t-il, comparé au modèle de référence ?',
    'Linear model': 'Modèle linéaire',
    'Mean baseline': 'Moyenne de référence',
    'median': 'médiane',
    'Bin of the column': 'Classe de la colonne',
    'Rows in the bin or group': 'Lignes de la classe ou du groupe',
    'Exact zeros, apart': 'Zéros exacts, à part',
    'Exactly zero': 'Exactement zéro',
    'Special values and missing cells': 'Valeurs spéciales et cellules manquantes',
    'Group with few rows': 'Groupe de peu de lignes',
    'Missing': 'Manquant',
    'The outcome is not read.': "Le résultat n'est pas lu.",
    'The column is skewed: its exact zeros are counted apart and its positive values are binned '
    'on a logarithmic scale, each bin closed on the left.':
        "La colonne est asymétrique : ses zéros exacts sont comptés à part et ses valeurs "
        "positives sont réparties en classes sur une échelle logarithmique, chaque classe "
        "fermée à gauche.",
    'rows read) on the axis; the count of rows at the end of each bar.':
        "lignes lues) sur l'axe ; l'effectif de lignes au bout de chaque barre.",
    'Association between each pair of predictors': 'Association entre chaque paire de prédicteurs',
    'Positive association': 'Association positive',
    'Negative association': 'Association négative',
    'At or above the collinearity level (outlined)': 'Au niveau de colinéarité ou au-dessus (entourée)',
    'Columns are in the same order as the rows, grouped so that associated predictors sit '
    'together; a darker cell is a stronger association.':
        "Les colonnes sont dans le même ordre que les lignes, regroupées pour que les "
        "prédicteurs associés soient côte à côte ; une cellule plus foncée est une association "
        "plus forte.",
    'The target is not read: this is not a look at the outcome. A flagged pair only asks '
    'whether both predictors are needed.':
        "La cible n'est pas lue : ce n'est pas un regard sur le résultat. Une paire signalée "
        "demande seulement si les deux prédicteurs sont nécessaires.",
    'in size:': 'en valeur absolue :',
    'in size.': 'en valeur absolue.',
    'Which predictors carry nearly the same information?':
        'Quels prédicteurs portent presque la même information ?',
    # render_diagnostics
    'Gain curve': 'Courbe de gain',
    'Diagonal: acting at random. AUC': 'Diagonale : agir au hasard. AUC',
    ', average precision': ', précision moyenne',
    'If the team acts on the best-scored rows first, what share of all positive rows does it '
    'find?':
        "Si l'équipe agit d'abord sur les lignes aux meilleurs scores, quelle part de toutes "
        "les lignes positives trouve-t-elle ?",
    'the rule': 'la règle',
    'Share of the rows acted on, best scores first':
        "Part des lignes sur lesquelles on agit, meilleurs scores d'abord",
    'Share of the positive rows found': 'Part des lignes positives trouvées',
    'Acting at random': 'Agir au hasard',
    'Calibration': 'Calibration',
    'One circle per bin of rows with similar scores, with the interval of its observed rate. '
    'Diagonal: a score that reads as a probability. Brier score':
        "Un cercle par classe de lignes aux scores proches, avec l'intervalle de son taux "
        "observé. Diagonale : un score qui se lit comme une probabilité. Score de Brier",
    ', against': ', contre',
    'for the constant base rate (lower is better).':
        'pour le taux de base constant (plus bas est meilleur).',
    'When the model gives rows a score, do about that share of them turn out positive?':
        "Quand le modèle donne un score à des lignes, à peu près cette part d'entre elles se "
        "révèle-t-elle positive ?",
    'Bin': 'Classe',
    'Mean score of the bin': 'Score moyen de la classe',
    'Observed positive rate of the bin': 'Taux de positifs observé de la classe',
    'Bin and its interval': 'Classe et son intervalle',
    'Precision': 'Précision',
    ', recall': ', rappel',
    ', specificity': ', spécificité',
    ', on': ', sur',
    'rows.': 'lignes.',
    'rows,': 'lignes,',
    'Scale:': 'Échelle :',
    'bootstrap refits on': 'réajustements bootstrap sur',
    'Wald intervals from a robust (sandwich) standard error.':
        "intervalles de Wald à partir d'une erreur type robuste (sandwich).",
    'Row': 'Ligne',
    'Score': 'Score',
    'Observed': 'Observé',
    'Predicted': 'Prédit',
    'Residual': 'Résidu',
    'AUC': 'AUC',
    'Average precision': 'Précision moyenne',
    'Brier score': 'Score de Brier',
    'Precision at the rule': 'Précision avec la règle',
    'Recall at the rule': 'Rappel avec la règle',
    'Positive': 'Positif',
    'Negative': 'Négatif',
    'Residuals against the prediction': 'Résidus en fonction de la prédiction',
    'Mean residual by bin': 'Résidu moyen par classe',
    'Predicted value': 'Valeur prédite',
    'Residual (observed minus predicted)': 'Résidu (observé moins prédit)',
    'One row': 'Une ligne',
    'Mean residual by bin of predictions': 'Résidu moyen par classe de prédictions',
    'Points: rows (': 'Points : lignes (',
    'shown of': 'affichées sur',
    '); line: the mean residual of each bin of predictions. Rank correlation of the size of the '
    'residual with the prediction:':
        ') ; trait : le résidu moyen de chaque classe de prédictions. Corrélation de rang de la '
        'taille du résidu avec la prédiction :',
    'Are the errors centred on zero across the range of the predictions, and do they widen?':
        "Les erreurs sont-elles centrées sur zéro sur toute l'étendue des prédictions, et "
        "s'élargissent-elles ?",
    'Predicted against observed values': 'Valeurs prédites en fonction des valeurs observées',
    'Observed value': 'Valeur observée',
    'Diagonal: a perfect prediction. Mean absolute error':
        'Diagonale : une prédiction parfaite. Erreur absolue moyenne',
    'How close are the predictions to the observed values?':
        'À quel point les prédictions sont-elles proches des valeurs observées ?',
    'Quantile-quantile plot of the residuals': 'Graphique quantile-quantile des résidus',
    'Quantile of a normal distribution': "Quantile d'une distribution normale",
    'Quantile of the standardised residuals': 'Quantile des résidus standardisés',
    'Skewness': 'Asymétrie',
    ', excess kurtosis': ', excès de kurtosis',
    '(both near zero for normal residuals).': '(tous deux proches de zéro pour des résidus normaux).',
    'Do the residuals look normal, as prediction intervals would assume?':
        "Les résidus semblent-ils normaux, comme le supposeraient des intervalles de "
        "prédiction ?",
    'Excess kurtosis': 'Excès de kurtosis',
    'Rank correlation': 'Corrélation de rang',
    '; spread of the residuals in the top third of the predictions over the bottom third:':
        ' ; dispersion des résidus dans le tiers supérieur des prédictions rapportée au tiers '
        'inférieur :',
    'MAE': 'MAE',
    'RMSE': 'RMSE',
    'Mean residual': 'Résidu moyen',
    'Mean residual (bias)': 'Résidu moyen (biais)',
    'Residual standard deviation': 'Écart-type des résidus',
    'Rank correlation of the error size with the prediction':
        "Corrélation de rang de la taille de l'erreur avec la prédiction",
    'Mean score': 'Score moyen',
    'Observed rate [interval]': 'Taux observé [intervalle]',
    'Score outside the interval': "Score hors de l'intervalle",
    'Term': 'Terme',
    'Coefficient [interval]': 'Coefficient [intervalle]',
    'Interval excludes zero': "L'intervalle exclut zéro",
    'Positive rows': 'Lignes positives',
    'Selected': 'Sélectionnées',
    'Precision [interval]': 'Précision [intervalle]',
    'Recall [interval]': 'Rappel [intervalle]',
    'Value or bin': 'Valeur ou classe',
    'Recall': 'Rappel',
    'Volume': 'Volume',
    'Volume share': 'Part du volume',
    'Positive rows reached': 'Lignes positives atteintes',
    'percentile intervals. Unit:': 'intervalles des percentiles. Unité :',
    'found': 'trouvées',
    '· result': '· résultat',
    # Stored sentences of the results the report shows (registered values, English; the
    # engine modules that write them are fingerprinted and not edited, plan §2.3).
    'penalty chosen by nested cross-validation': 'pénalité choisie par validation croisée '
                                                 'imbriquée',
    'weaker regularisation': 'régularisation plus faible',
    'stronger regularisation': 'régularisation plus forte',
    'the variant': 'la variante',
    'the second variant model': 'la deuxième variante',
    'the third variant model': 'la troisième variante',
    'the linear model': 'le modèle linéaire',
    'the logistic model': 'le modèle logistique',
    'an Explainable Boosting Machine': 'une Explainable Boosting Machine (EBM)',
    'histogram gradient boosting': 'le gradient boosting par histogrammes',
    'The model predicts the target on its own scale (no transform of the target), so no '
    "retransformation correction such as Duan's smearing applies. Smearing is not implemented: "
    'a log-transformed target would need it.':
        "Le modèle prédit la cible sur sa propre échelle (sans transformation de la cible), donc "
        "aucune correction de retransformation comme le smearing de Duan ne s'applique. Le "
        "smearing n'est pas implémenté : une cible transformée par logarithme en aurait besoin.",
    'The quantile-quantile points compare the standardised residuals with a normal '
    'distribution. Normality is not needed for the mean error or the coefficients with this '
    'many rows (Lumley et al. 2002); it matters for prediction intervals, which this study does '
    'not give.':
        "Les points quantile-quantile comparent les résidus standardisés à une distribution "
        "normale. La normalité n'est pas nécessaire pour l'erreur moyenne ni pour les "
        "coefficients avec autant de lignes (Lumley et al. 2002) ; elle compte pour des "
        "intervalles de prédiction, que cette étude ne donne pas.",
    'The coefficients and their intervals come from the same prepared rows and the same '
    'penalised fit.':
        "Les coefficients et leurs intervalles viennent des mêmes lignes préparées et du même "
        "ajustement pénalisé.",
    'Coefficients of the model fitted on these rows, with Wald intervals from a robust '
    '(sandwich) standard error: the approximation of how much each coefficient would move if '
    'the rows were drawn again, the preparation of the variables kept as fitted. Associations '
    'given the other variables, never effects.':
        "Coefficients du modèle ajusté sur ces lignes, avec des intervalles de Wald à partir "
        "d'une erreur type robuste (sandwich) : l'approximation de combien chaque coefficient "
        "bougerait si les lignes étaient tirées à nouveau, la préparation des variables gardée "
        "telle qu'ajustée. Des associations compte tenu des autres variables, jamais des effets.",
    'The fit is penalised: its coefficients are pulled towards zero, so the intervals describe '
    'the spread of the penalised estimate, centred on a value that is itself shrunk; they are '
    'not exact confidence intervals of an unpenalised coefficient, and a coefficient of a rare '
    'category can be shrunk well inside its interval.':
        "L'ajustement est pénalisé : ses coefficients sont tirés vers zéro, donc les intervalles "
        "décrivent la dispersion de l'estimation pénalisée, centrée sur une valeur elle-même "
        "réduite ; ce ne sont pas des intervalles de confiance exacts d'un coefficient non "
        "pénalisé, et le coefficient d'une catégorie rare peut être réduit bien à l'intérieur de "
        "son intervalle.",
    'Flagged when the rank correlation of the absolute residual with the prediction is at least '
    '0.2 in size, or the residual standard deviation of the top third of the predictions is '
    'more than 1.5 times (or less than 1/1.5 of) that of the bottom third':
        "Signalé quand la corrélation de rang du résidu absolu avec la prédiction atteint au "
        "moins 0.2 en valeur absolue, ou quand l'écart-type des résidus du tiers supérieur des "
        "prédictions dépasse 1.5 fois (ou est inférieur à 1/1.5 de) celui du tiers inférieur",
    'An error that grows with the prediction makes one interval width wrong for every row; the '
    'mean error stays a fair summary.':
        "Une erreur qui grandit avec la prédiction rend fausse une largeur d'intervalle unique "
        "pour chaque ligne ; l'erreur moyenne reste un résumé honnête.",
    '. An error that grows with the prediction makes one interval width wrong for every row; '
    'the mean error stays a fair summary.':
        ". Une erreur qui grandit avec la prédiction rend fausse une largeur d'intervalle unique "
        "pour chaque ligne ; l'erreur moyenne reste un résumé honnête.",
    'Rows whose selection at the rule disagrees with the outcome, with the feature values as '
    'written in the file. Examples to read, not a sample.':
        "Lignes dont la sélection par la règle ne correspond pas au résultat, avec les valeurs "
        "des variables telles qu'écrites dans le fichier. Des exemples à lire, pas un "
        "échantillon.",
    'per standard deviation of the training rows (numeric) or per category (one-hot); '
    'associations, not effects':
        "par écart-type des lignes d'entraînement (numérique) ou par catégorie (one-hot) ; des "
        "associations, pas des effets",
    'per standard deviation of the development rows (numeric) or per category (one-hot); '
    'associations, not effects':
        "par écart-type des lignes de développement (numérique) ou par catégorie (one-hot) ; "
        "des associations, pas des effets",
    'target units per standard deviation of the training rows (numeric) or per category '
    '(one-hot, not identifiable one by one); associations, not effects':
        "unités de la cible par écart-type des lignes d'entraînement (numérique) ou par "
        "catégorie (one-hot, non identifiables une par une) ; des associations, pas des effets",
    'target units per standard deviation of the development rows (numeric) or per category '
    '(one-hot, not identifiable one by one); associations, not effects':
        "unités de la cible par écart-type des lignes de développement (numérique) ou par "
        "catégorie (one-hot, non identifiables une par une) ; des associations, pas des effets",
}

_ROWS = r'(?P<rows>the development rows|development rows|the training rows|training rows|' \
        r'the validation rows|validation rows|the out-of-fold predictions|out-of-fold predictions)'
_ROWS_FR = {'development rows': 'les lignes de développement',
            'training rows': "les lignes d'entraînement",
            'validation rows': 'les lignes de validation',
            'out-of-fold predictions': 'les prédictions hors pli'}


def _rows(m: re.Match) -> str:
    words = m.group('rows')
    return _ROWS_FR[words[4:] if words.startswith('the ') else words]


def _of(rows: str) -> str:
    """``de`` + the rows, contracted (des)."""
    return 'des' + rows[3:] if rows.startswith('les ') else f'de {rows}'


# ``(regex, french)``: ``french`` is a format string over the named groups (``R`` the rows
# in French, ``ofR`` with "de"), or a function of the match.
PATTERNS: list[tuple[re.Pattern, Callable[[re.Match], str] | str]] = [
    (re.compile(p), f) for p, f in [
        (r'(?P<what>Development|Training) rows by outcome',
         lambda m: f'Lignes de {"développement" if m.group("what") == "Development" else "entraînement"} '
                   'selon le résultat'.replace('de entraînement', "d'entraînement")),
        (r'Outcome (?P<label>.+)', 'Résultat {label}'),
        (rf'Positive rate on {_ROWS}:', 'Taux de positifs sur {R} :'),
        (rf'Middle half of {_ROWS}', 'Moitié centrale {ofR}'),
        (rf'Distribution of the target on {_ROWS}', 'Distribution de la cible sur {R}'),
        (rf'Box: the middle half of {_ROWS}; thick line: the median; circle: the mean',
         'Boîte : la moitié centrale {ofR} ; trait épais : la médiane ; cercle : la moyenne'),
        (rf'Dashed line: the overall value on {_ROWS}\. An association between groups, not an '
         rf'effect of the variable\.',
         "Trait pointillé : la valeur d'ensemble sur {R}. Une association entre groupes, pas un "
         "effet de la variable."),
        (rf'Dashed line: the overall value on {_ROWS}\. An association between groups, not an '
         rf'effect of the variable\. Intervals:',
         "Trait pointillé : la valeur d'ensemble sur {R}. Une association entre groupes, pas un "
         "effet de la variable. Intervalles :"),
        (r'(?P<what>Positive rate|Mean of the target) by group of (?P<column>.+)',
         lambda m: f'{"Taux de positifs" if m.group("what") == "Positive rate" else "Moyenne de la cible"} '
                   f'par groupe de {m.group("column")}'),
        (r'(?P<what>Positive rate|Mean of the target) with its interval',
         lambda m: f'{"Taux de positifs" if m.group("what") == "Positive rate" else "Moyenne de la cible"} '
                   f'avec son intervalle'),
        (r'Does the outcome differ across the groups of (?P<column>.+)\?',
         'Le résultat diffère-t-il entre les groupes de {column} ?'),
        (r'(?P<name>Area under the ROC curve|Share of variance explained) of each feature alone',
         lambda m: f'{EXACT[m.group("name")]} de chaque variable seule'),
        (rf'(?P<name>Area under the ROC curve|Share of variance explained) of a model that sees '
         rf'one feature at a time, out of fold on {_ROWS}\. A strong signal raises one question '
         rf'only: is this feature truly known at the moment of prediction\? It never selects '
         rf'features\.',
         lambda m: f"{EXACT[m.group('name')]} d'un modèle qui voit une variable à la fois, hors "
                   f"pli sur {_rows(m)}. Un signal fort ne pose qu'une question : cette variable "
                   f"est-elle vraiment connue au moment de la prédiction ? Il ne sélectionne "
                   f"jamais de variables."),
        (rf'Residuals of each model on {_ROWS}', 'Résidus de chaque modèle sur {R}'),
        (rf'Residual: observed minus predicted, on {_ROWS}\. Line: from the 5th to the 95th '
         rf'percentile; box: the middle half; thick line: the median\. A box away from the zero '
         rf'line means the model is biased on these rows\. Unit:',
         'Résidu : observé moins prédit, sur {R}. Trait : du 5e au 95e percentile ; boîte : la '
         'moitié centrale ; trait épais : la médiane. Une boîte éloignée de la ligne zéro '
         'signifie que le modèle est biaisé sur ces lignes. Unité :'),
        (rf'Residual: observed minus predicted, on {_ROWS}\. Line: from the',
         'Résidu : observé moins prédit, sur {R}. Trait : du'),
        (r'percentile; box: the middle half; thick line: the median\. A box away from the zero '
         r'line means the model is biased on these rows\. Unit:',
         'percentile ; boîte : la moitié centrale ; trait épais : la médiane. Une boîte éloignée '
         'de la ligne zéro signifie que le modèle est biaisé sur ces lignes. Unité :'),
        (rf'How far from the observed value are the predictions of each model on {_ROWS}\?',
         'À quelle distance de la valeur observée sont les prédictions de chaque modèle, sur '
         '{R} ?'),
        (r'Mean residual by (?P<column>.+)', 'Résidu moyen par {column}'),
        (rf'Mean residual \(observed minus predicted\) of {_ROWS} of each group; the value '
         rf"shown is the linear model's\. Groups with few rows are noisy\.",
         'Résidu moyen (observé moins prédit) {ofR} de chaque groupe ; la valeur montrée est '
         'celle du modèle linéaire. Les groupes de peu de lignes sont bruités.'),
        (r'Does the error drift across the values of (?P<column>.+)\?',
         "L'erreur dérive-t-elle selon les valeurs de {column} ?"),
        (rf'Distribution of (?P<column>.+) on {_ROWS}', 'Distribution de {column} sur {R}'),
        (rf'Share of {_ROWS} \(', 'Part {ofR} ('),
        (r'Pairs at or above', 'Paires au niveau'),
        (r'No pair reaches', 'Aucune paire n\'atteint'),
        (r'(?P<n>\d+) % found', '{n} % trouvées'),
        (r'Variante: (?P<what>mean residual|MAE)',
         lambda m: f'Variante : {"résidu moyen" if m.group("what") == "mean residual" else "MAE"}'),
    ]]


def fragment(text: str) -> str | None:
    """The French form of one English phrase of the report (stripped), or None."""
    if text in EXACT:
        return EXACT[text]
    from . import l10n
    french = l10n.eda_text(text, l10n.FR)        # a question an EDA or diagnostics result asks
    if french is not None:
        return french
    for pattern, out in PATTERNS:
        m = pattern.fullmatch(text)
        if m is None:
            continue
        if callable(out):
            return out(m)
        fields = dict(m.groupdict())
        if fields.get('rows'):
            fields['R'] = _rows(m)
            fields['ofR'] = _of(fields['R'])
        return out.format(**fields)
    return None


def _replace(raw: str, quote: bool) -> str:
    text = html.unescape(raw)
    stripped = text.strip()
    if not stripped:
        return raw
    french = fragment(stripped)
    if french is None:
        return raw
    lead = text[:len(text) - len(text.lstrip())]
    tail = text[len(text.rstrip()):]
    return html.escape(lead + french + tail, quote=quote)


# A text node and the tag just before it.
_TEXT = re.compile(r'(<[^<>]*)>([^<>]+)(?=<)')
_ATTR = re.compile(r'\b(aria-label|title)="([^"]*)"')
# Opening tags whose text is never translated: the case's statements and the junior's words
# (``q``), code, cited numbers (``data``), and recorded literals (identifiers, categories,
# values, the case).
_KEEP = re.compile(r'^<(?:q|code|data|pre)\b|data-literal="(?:case|identifier|user_words|'
                   r'category|environment|parameter|decision_value|revision|setting|'
                   r'structure|final_test|data_card)"')


def _text(m: re.Match) -> str:
    tag, text = m.group(1), m.group(2)
    if not tag.startswith('</') and _KEEP.search(tag):
        return m.group(0)
    return f'{tag}>{_replace(text, False)}'


def french(body: str) -> str:
    """``body`` (report HTML) with the renderers' English phrases in French."""
    out = _TEXT.sub(_text, body)
    return _ATTR.sub(lambda m: f'{m.group(1)}="{_replace(m.group(2), True)}"', out)


__all__ = ['EXACT', 'PATTERNS', 'fragment', 'french']
