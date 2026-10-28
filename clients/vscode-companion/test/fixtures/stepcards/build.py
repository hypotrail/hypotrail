"""Hand-made step-card digests of the Auto MPG study (lot 2026-10-28), for the panel's tests.

The engine package lands ``texts.<lang>.step_cards``, ``case_display``, ``case_brief`` and the
other keys of docs/plans/LOT-2026-10-28-SPEC.md §7.2 and §9 in parallel; until the integrator
recaptures them from the real engine (``fixtures/capture.py``), these fixtures follow the spec's
example by hand. Each one starts from a captured summary of the cross-validated Auto MPG study
(``captured/summary.regression.cv.*``), inserts the new step "Error measure" (R60, 14 steps),
moves the plan to one step, and adds the step cards in both languages with the readings of the
approved mockup (docs/plans/mockups/panel-all-steps-fr.html). The numbers of the readings are the
mockup's; the charts read the registered values of ``captured/evidence.regression.cv.done``.

Run ``python3 build.py`` from this folder to rewrite the fixtures. Nothing here is a recorded
human decision: the decisions of the done steps are the captured study's.
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
CAPTURED = HERE.parent / 'captured'

PLAN = ['discover_data', 'prediction_time', 'feature_availability', 'split', 'error_metric', 'success_criterion',
        'structural_eda', 'preprocessing', 'train_eda', 'models', 'model_variant', 'model_choice', 'final_test', 'conclusion']
MOMENT = {s: m for m, steps in [('frame', PLAN[:6]), ('evidence', PLAN[6:9]), ('compare', PLAN[9:12]), ('conclude', PLAN[12:])] for s in steps}
MOMENT_TITLES = {'en': {'frame': 'Frame the change', 'evidence': 'Prepare evidence', 'compare': 'Work and compare', 'conclude': 'Conclude and hand over'},
                 'fr': {'frame': 'Cadrer le changement', 'evidence': 'Préparer les preuves', 'compare': 'Travailler et comparer', 'conclude': 'Conclure et transmettre'}}
NAMES = {
    'en': ['Data', 'Prediction moment', 'Available variables', 'Split', 'Error measure', 'Success criterion', 'Quality check', 'Preparation',
           'Exploration', 'Models', 'Variants', 'Model choice', 'Final test', 'Conclusion'],
    'fr': ['Données', 'Moment de la prédiction', 'Variables disponibles', 'Découpage', "Mesure de l'erreur", 'Critère de succès',
           'Contrôle de qualité', 'Préparation', 'Exploration', 'Modèles', 'Variantes', 'Choix du modèle', 'Test final', 'Conclusion'],
}
SHORT = {'en': ['Data', 'Moment', 'Variables', 'Split', 'Measure', 'Criterion', 'Quality', 'Preparation', 'Explore', 'Models', 'Variants', 'Choice',
                'Final test', 'Conclusion'],
         'fr': ['Données', 'Moment', 'Variables', 'Découpage', 'Mesure', 'Critère', 'Qualité', 'Préparation', 'Exploration', 'Modèles', 'Variantes',
                'Choix', 'Test final', 'Conclusion']}
PLAN_TITLES = {'error_metric': {'en': 'Choose how the error is measured', 'fr': "Choisir comment l'erreur est mesurée"}}

# The registered results the questions read (slots of the captured study).
DONE = json.loads((CAPTURED / 'summary.regression.cv.done.json').read_text())['payload']
RID = {slot: r['result_id'] for slot, r in DONE['results'].items() if r.get('current')}
REVISION = DONE['revision']


def frame(evidence, en, fr):
    return {'evidence': evidence, 'rows': {'en': en, 'fr': fr}}


# --- the timeline and the variables board (EN-18, §8.6) ------------------------------------------
MILESTONES = [('design', 'Engine designed', 'Moteur conçu'), ('body', 'Body and weight fixed', 'Carrosserie et poids fixés'),
              ('tests', 'Performance tests', 'Essais de performance'), ('measured', 'Fuel use measured (mpg)', 'Consommation mesurée (mpg)')]
GROUPS = {'engine': ('Engine', 'Moteur'), 'body': ('Body and performance', 'Carrosserie et performances'), 'model': ('Model', 'Modèle'),
          'outcome': ('Outcome', 'Résultat')}
COLUMNS = [  # column, en name, fr name, group, known_at, state, reason en, reason fr
    ('cylinders', 'cylinders', 'cylindres', 'engine', 'design', 'kept', None, None),
    ('displacement', 'displacement', 'cylindrée', 'engine', 'design', 'kept', None, None),
    ('horsepower', 'horsepower', 'puissance', 'engine', 'design', 'kept', None, None),
    ('weight', 'weight', 'poids', 'body', 'body', 'kept', None, None),
    ('acceleration', 'acceleration', 'accélération', 'body', None, 'excluded',
     'availability at the prediction moment not documented', 'disponibilité au moment de la prédiction non documentée'),
    ('origin', 'origin', 'origine', 'model', 'design', 'kept', None, None),
    ('model_year', 'model year', 'année du modèle', 'model', None, 'not_feature', 'orders the split', 'ordre du découpage'),
    ('car_name', 'name', 'nom', 'model', None, 'not_feature', 'identifier', 'identifiant'),
    ('mpg', 'mpg', 'mpg', 'outcome', 'measured', 'not_feature', 'the target', 'la cible'),
]
CASE_DISPLAY = {'columns': {c: {'en': en, 'fr': fr} for c, en, fr, *_ in COLUMNS}}


def timeline(lang, decided):
    i = 0 if lang == 'en' else 1
    feats = [c for c in COLUMNS if c[5] != 'not_feature']
    positions = []
    for k, (mid, *_) in enumerate(MILESTONES[:-1]):
        known = {m[0] for m in MILESTONES[:k + 1]}
        positions.append({'after': mid,
                          'kept': [c[0] for c in feats if c[4] in known],
                          'dropped': [c[0] for c in feats if c[4] and c[4] not in known],
                          'uncertain': [c[0] for c in feats if c[4] is None]})
    return {'milestones': [{'id': m[0], 'label': m[1 + i]} for m in MILESTONES], 'moment_after': 'body', 'slider': True,
            'decided': decided, 'status': 'scenario_assumption', 'positions': positions,
            'columns': [{'column': c[0], 'name': c[1 + i], 'group': GROUPS[c[3]][i], 'known_at': c[4], 'uncertain': c[4] is None and c[5] != 'not_feature',
                         'state': c[5], 'reason': (c[6], c[7])[i]} for c in COLUMNS]}


STRATA = [{'stratum': k + 1, 'development': d, 'sealed': 16} for k, d in enumerate([64, 64, 64, 63, 63])]


def strata(opened):
    return {'total': 398, 'development': 318, 'sealed': 80, 'method': 'quantile_stratified', 'bins': 5, 'strata': STRATA, 'opened': opened}


def folds(lang, computed):
    order = 'model year' if lang == 'en' else 'année du modèle'
    blocks = [{'fold': f, 'n_rows': n, 'min': lo, 'max': hi} for f, n, lo, hi in
              [(1, 64, 70, 72), (2, 64, 72, 75), (3, 64, 75, 78), (4, 63, 78, 80), (5, 63, 80, 82)]]
    return {'illustrative': not computed, 'k': 5, 'n_rows': 318, 'order_column': order, 'sealed': 80, 'blocks': blocks if computed else None}


def metric(lang):
    return {'illustrative': True, 'errors': [1, 1, 1, 1, 6], 'squares': [1, 1, 1, 1, 36], 'mae': 2.0, 'mean_square': 8.0, 'rmse': 2.8284271247,
            'unit': 'mpg', 'unit_note': '25 mpg ≈ 9.4 L/100 km' if lang == 'en' else '25 mpg ≈ 9,4 L/100 km'}


def criterion_bars(lang):
    en = lang == 'en'
    return {'illustrative': True, 'unit': 'mpg', 'axis_label': 'mean error (mpg) · made-up example' if en else 'erreur moyenne (mpg) · exemple fictif',
            'bars': [{'id': 'reference', 'label': 'reference' if en else 'référence', 'note': 'predict the mean' if en else 'prédire la moyenne', 'value': 7.0, 'tone': 'grey'},
                     {'id': 'minimum', 'label': 'criterion 10%' if en else 'critère 10 %', 'note': 'statistical minimum' if en else 'minimum statistique', 'value': 6.3, 'tone': 'acc'},
                     {'id': 'current', 'label': 'current method' if en else 'méthode actuelle', 'note': 'manual estimate' if en else 'estimation manuelle', 'value': 4.5, 'tone': 'orange'},
                     {'id': 'target', 'label': "PO's target" if en else 'objectif du PO', 'note': '"clearly better"' if en else '« nettement mieux »', 'value': 3.5, 'tone': 'leaf'}]}


def bias_period(lang):
    return {'unit': 'mpg', 'groups': [{'label': lbl, 'mean_residual': v} for lbl, v in
                                      [('1970–72', -2.46), ('1973–75', -1.2), ('1976–78', 0.3), ('1979–80', 2.1), ('1981–82', 5.27)]]}


# --- the steps: picture, prepares, questions (both languages), limit, next, decision ------------------
def T(en, fr):
    return {'en': en, 'fr': fr}


def Q(qid, text, source, chart, fr_, reading, how, trap, *, chart_data=None, others=(), verdict=None, status=None):
    return {'id': qid, 'text': text, 'source': source, 'chart': chart, 'chart_data': chart_data, 'other_charts': list(others),
            'frame': fr_, 'reading': reading, 'folds': {'how': how, 'trap': trap}, 'verdict': verdict, 'status': status}


def R(see, conclude, cannot):
    return {'see': see, 'conclude': conclude, 'cannot': cannot}


def res(slot):
    return {'kind': 'result', 'slot': slot, 'key': None}


STEPS = {
    'discover_data': dict(
        picture=('row_card', T('One row = one car model of one model year. Its columns describe its technical sheet; mpg is the value to predict.',
                               "Une ligne = un modèle de voiture d'une année de modèle. Ses colonnes décrivent sa fiche technique ; mpg est la valeur à prédire."),
                 T('Before any decision, check that the data describe the question: what a row is, which columns, which structural anomalies. Nothing is measured here.',
                   "Avant toute décision, on vérifie que les données décrivent bien la question : qui est une ligne, quelles colonnes, quelles anomalies de structure. Rien n'est mesuré ici."), None),
        prepares=T('These answers prepare the step Prediction moment: knowing what each column describes.',
                   "Ces réponses préparent l'étape Moment de la prédiction : savoir ce que chaque colonne décrit."),
        questions=[
            Q('data.row', T('What does one row describe, and what do the columns say?', 'Que décrit une ligne, et que disent les colonnes ?'),
              {'kind': 'digest', 'slot': None, 'key': 'sample'}, 'sample_table',
              frame('structure', 'Structure, plus a preview of 8 rows with the target: a counted look (looks: 1)',
                    'plus un aperçu de 8 lignes, cible comprise : un regard compté (regards : 1)'),
              T(R('One row describes a car model for one year: 9 columns, mpg the target among them; horsepower holds 6 "?".',
                  'Each row is a car to predict, described by its technical sheet: the data answer the question asked. The "?" are a structural anomaly, handled at the quality check.',
                  'Eight rows do not describe the 318: they show the shape of the data, not its spread. Seeing their mpg is already a look at the target.'),
                R('Une ligne décrit un modèle de voiture pour une année : 9 colonnes, dont mpg, la cible ; la puissance contient 6 « ? ».',
                  "Chaque ligne est une voiture à prédire, décrite par sa fiche technique : les données répondent à la question posée. Les « ? » sont une anomalie de structure, traitée au contrôle de qualité.",
                  "Huit lignes ne décrivent pas les 318 : elles montrent la forme des données, pas leur répartition. Voir leur mpg est déjà un regard sur la cible.")),
              T('One row per car; the ochre column is the target. "?" is written as is in the file: a missing value.',
                "Une ligne par voiture ; la colonne ocre est la cible. « ? » est écrit tel quel dans le fichier : une valeur manquante."),
              T('The file is sorted by year: its first rows do not look like the others. The preview is drawn at random for that reason.',
                "Le fichier est trié par année : ses premières lignes ne ressemblent pas aux autres. L'aperçu est tiré au hasard pour cette raison."),
              status='answered'),
            Q('data.structure', T('Could a split separate a car from its twin?', 'Un découpage pourrait-il séparer une voiture de sa jumelle ?'),
              {'kind': 'digest', 'slot': None, 'key': 'data_structure'}, 'structure_bars',
              frame('structure', 'structure · development rows', 'structure · lignes de développement'),
              T(R('254 distinct car names for 318 development rows; 107 rows share their name with another; 0 exact duplicate.',
                  'A model comes back from one year to the next: a split can put a row in training and its twin in validation, which would flatter the error a little.',
                  'The same name does not prove the same car: the sheet can change from one year to the next. The count does not say by how much the error would be flattered.'),
                R('254 noms de voiture distincts pour 318 lignes de développement ; 107 lignes partagent leur nom avec une autre ; 0 doublon exact.',
                  "Un même modèle revient d'une année à l'autre : un découpage peut placer une ligne en entraînement et sa jumelle en validation, ce qui flatterait un peu l'erreur.",
                  "Un même nom ne prouve pas une même voiture : la fiche peut changer d'une année à l'autre. Le compte ne dit pas de combien l'erreur serait flattée.")),
              T('Each bar counts rows; the orange bar: rows whose name also appears on another row.',
                "Chaque barre compte des lignes ; la barre orange : les lignes dont le nom apparaît aussi sur une autre ligne."),
              T('Zero exact duplicate does not mean zero repeated car: two rows can differ by one column.',
                "Zéro doublon exact ne veut pas dire zéro voiture répétée : deux lignes peuvent différer d'une seule colonne."),
              status='answered'),
        ],
        limit=T('Nothing is measured yet: no model, no performance figure. The only look at the target is the preview, counted.',
                "Rien n'est encore mesuré : ni modèle ni chiffre de performance. Le seul regard sur la cible est l'aperçu, compté."),
        next=T('Next: the prediction moment. It fixes which columns may be used.', "Ensuite : le moment de la prédiction. Il fixe quelles colonnes on a le droit d'utiliser."),
        decision=T('Data card read; moving on to the prediction moment.', 'Fiche lue ; on passe au moment de la prédiction.'),
    ),
    'prediction_time': dict(
        picture=('moment_timeline', T('Predicting means standing at a moment. Only the columns known before it may serve; mpg is measured only after.',
                                      "Prédire, c'est se placer à un moment. Seules les colonnes connues avant ce moment peuvent servir ; mpg n'est mesuré qu'après."),
                 T('A column known after the moment would be a leak. The milestones of Auto MPG are an assumption of the teaching scenario.',
                   "Une colonne connue après le moment serait une fuite. Les jalons d'Auto MPG sont une hypothèse du scénario pédagogique."), 'timeline'),
        prepares=T('This answer prepares the step Available variables: the list of permitted columns.',
                   "Cette réponse prépare l'étape Variables disponibles : la liste des colonnes permises."),
        questions=[
            Q('moment.when', T('At which moment is the prediction made, and what is known then?', 'À quel moment la prédiction est-elle faite, et que sait-on alors ?'),
              {'kind': 'case', 'slot': None, 'key': 'prediction_time'}, 'moment_timeline',
              frame('none', 'case metadata, no value', 'métadonnées du cas, aucune valeur'),
              T(R('At the proposed moment, 5 columns are known; acceleration is in the "?" lane; mpg is measured only at the last milestone.',
                  'The moment fixes the list of permitted columns: earlier, weight leaves the list; later, no column enters it here. Acceleration does not depend on the slider: its date is not documented.',
                  'These milestones are a scenario assumption, not a fact of the data: the timeline does not prove when each column was known.'),
                R("Au moment proposé, 5 colonnes sont connues ; l'accélération est dans la voie « ? » ; mpg n'est mesuré qu'au dernier jalon.",
                  "Le moment fixe la liste des colonnes permises : plus tôt, le poids sort de la liste ; plus tard, aucune colonne n'y entre ici. L'accélération ne dépend pas du curseur : sa date n'est pas documentée.",
                  'Ces jalons sont une hypothèse du scénario, pas un fait des données : la frise ne prouve pas quand chaque colonne était connue.')),
              T('Move the slider: the columns left of the moment are known, those right of it not yet.', "Déplacez le curseur : les colonnes à gauche du moment sont connues, celles à droite ne le sont pas encore."),
              T('The milestones are evenly spaced for reading: the distances are not durations.', 'Les jalons sont régulièrement espacés pour la lisibilité : les distances ne sont pas des durées.'),
              chart_data='timeline', status='answered'),
        ],
        limit=T('The moment is a scenario assumption: the data documentation does not establish it.', "Le moment est une hypothèse du scénario : la documentation des données ne l'établit pas."),
        next=T('Next: the available variables, column by column, on the same timeline.', 'Ensuite : les variables disponibles, colonne par colonne, sur la même frise.'),
        decision=T('When the technical characteristics are fixed, before fuel use is measured.', 'Quand les caractéristiques techniques sont fixées, avant de mesurer la consommation.'),
    ),
    'feature_availability': dict(
        picture=('variables_board', T('Three kinds of columns: those the model will read, those excluded, and those that are not variables.',
                                      "Trois sortes de colonnes : celles que le modèle lira, celles qu'on exclut, et celles qui ne sont pas des variables."),
                 T('The target is not a variable; an identifier neither. The model year orders the split.',
                   "La cible n'est pas une variable ; un identifiant non plus. L'année du modèle sert à ordonner le découpage."), None),
        prepares=T('This answer prepares the Split and the Models: what each model may read.', 'Cette réponse prépare le Découpage et les Modèles : ce que chaque modèle aura le droit de lire.'),
        questions=[
            Q('variables.kept', T('Which variables are known at the moment, which are excluded, and why?', 'Quelles variables sont connues au moment, lesquelles sont exclues, et pourquoi ?'),
              {'kind': 'decision', 'slot': None, 'key': 'feature_availability'}, 'variables_board',
              frame('none', 'availability declared by the case, no value', 'disponibilité déclarée par le cas, aucune valeur'),
              T(R('5 columns kept, 1 excluded, acceleration, and 3 that are not variables: mpg, the name and the model year.',
                  'The models will read only the 5 columns known at the prediction moment. Excluding an uncertain column may cost a little accuracy; including it would rest the model on information perhaps missing at the moment.',
                  'The board does not say how much acceleration would have helped: it is not measured. Nor whether the 5 kept columns suffice.'),
                R("5 colonnes gardées, 1 exclue, l'accélération, et 3 qui ne sont pas des variables : mpg, le nom et l'année du modèle.",
                  "Les modèles ne liront que les 5 colonnes connues au moment de la prédiction. Exclure une colonne incertaine peut coûter un peu de précision ; l'inclure ferait reposer le modèle sur une information peut-être absente au moment voulu.",
                  "Le tableau ne dit pas combien l'accélération aurait aidé : on ne le mesure pas. Ni si les 5 colonnes gardées suffisent.")),
              T('✓ the model reads it; ✕ excluded, with its reason; — not a variable.', '✓ : le modèle la lira ; ✕ : exclue, avec sa raison ; — : pas une variable.'),
              T('The groups come from the case: they say nothing of a column\'s importance.', "Les groupes viennent du cas : ils ne disent rien de l'importance d'une colonne."),
              chart_data='timeline', status='answered'),
        ],
        limit=T('Availability comes from the scenario, not from a check of the data.', "La disponibilité vient du scénario, pas d'un contrôle des données."),
        next=T('Next: the split, which sets rows aside before any look at their results.', "Ensuite : le découpage, qui met des lignes de côté avant tout regard sur leurs résultats."),
        decision=T('Keep cylinders, displacement, horsepower, weight and origin; exclude acceleration.', "Garder cylindres, cylindrée, puissance, poids et origine ; exclure l'accélération."),
    ),
    'split': dict(
        picture=('partition_strip', T('Set rows aside before any look. 80 rows sealed for the end; the 318 others, cut in blocks, serve to compare.',
                                      'Mettre des lignes de côté avant tout regard. 80 lignes scellées pour la fin ; les 318 autres, découpées en blocs, servent à comparer.'),
                 T('Cross-validation with k folds: the development rows in k blocks; each block is predicted by a model fitted on the others. Here k = 5, in model-year order.',
                   "Validation croisée à k plis : les lignes de développement en k blocs ; chaque bloc est prédit par un modèle entraîné sur les autres. Ici k = 5, dans l'ordre de l'année du modèle."),
                 {'development': 318, 'sealed': 80}),
        prepares=T('These answers prepare every later measure: on which rows each error is computed.', 'Ces réponses préparent toutes les mesures suivantes : sur quelles lignes chaque erreur sera calculée.'),
        questions=[
            Q('split.sealed', T('Which rows are sealed, and how were they drawn?', 'Quelles lignes sont scellées, et comment ont-elles été tirées ?'),
              {'kind': 'digest', 'slot': None, 'key': 'final_test'}, 'partition_strata',
              frame('structure', 'row counts only, no value of mpg', 'comptes de lignes seulement, aucune valeur de mpg'),
              T(R('The 80 sealed rows were drawn at random in 5 bins of mpg, 16 per bin; the 318 others are the development rows.',
                  'The final test covers the whole range of the target: its figure will not come from an easy corner of the data.',
                  'These 80 rows come from the same period, 1970–82: they say nothing of later cars. The drawing shows no value of mpg.'),
                R('Les 80 lignes scellées ont été tirées au hasard dans 5 tranches de mpg, 16 par tranche ; les 318 autres sont les lignes de développement.',
                  "Le test final couvre toute l'étendue de la cible, des voitures peu sobres aux plus sobres : son chiffre ne viendra pas d'un coin facile des données.",
                  "Ces 80 lignes viennent de la même période, 1970–82 : elles ne disent rien des voitures d'après. Le dessin ne montre aucune valeur de mpg : on ne les regarde pas.")),
              T('One column per bin of the target; purple: drawn for the final test; grey: development rows.', 'Une colonne par tranche de la cible ; violet : tirées pour le test final ; gris : lignes de développement.'),
              T('The bins show no bounds, on purpose: showing them would already be a look at the target.', 'Les tranches n\'ont pas de bornes affichées, à dessein : les montrer serait déjà un regard sur la cible.'),
              chart_data='strata', status='answered'),
            Q('split.folds', T('How will each development row be predicted?', 'Comment chaque ligne de développement sera-t-elle prédite ?'),
              res('split'), 'folds',
              frame('structure', 'cross-validation with 5 folds · blocks in model-year order', "validation croisée à 5 plis · blocs dans l'ordre de l'année du modèle"),
              T(R('The 318 development rows in 5 blocks: 64, 64, 64, 63 and 63 rows, from 1970–72 to 1980–82; the 80 sealed rows stay aside.',
                  'Each block is predicted by a model fitted on the four others, later years included: the error will say the stability from one period to another, not a forecast of the future.',
                  'Five blocks are not five independent samples: the gap from one block to another is indicative.'),
                R('Les 318 lignes de développement en 5 blocs : 64, 64, 64, 63 et 63 lignes, de 1970–72 à 1980–82 ; les 80 scellées restent à part.',
                  "Chaque bloc est prédit par un modèle entraîné sur les quatre autres, années suivantes comprises : l'erreur mesurée dira la stabilité d'une période à l'autre, pas une prévision du futur.",
                  "Cinq blocs ne sont pas cinq échantillons indépendants : l'écart d'un bloc à l'autre est indicatif. Et le découpage ne rend pas « jamais vues » les 8 lignes de l'aperçu.")),
              T('One row per round; the ochre block is predicted, the grey ones serve to learn.', 'Une rangée par tour ; le bloc ocre est prédit, les gris servent à apprendre.'),
              T('Years overlap from one block to the next: a block cuts a year when the counts require it.', "Les années se chevauchent d'un bloc à l'autre : un bloc coupe une année quand les comptes l'exigent."),
              chart_data='folds', status='answered'),
        ],
        limit=T('The 80 sealed rows are a protocol followed by the tool and by you, not a lock.', "Les 80 lignes scellées sont un protocole suivi par l'outil et par vous, pas un verrou."),
        next=T('Next: the error measure, chosen before seeing any figure.', "Ensuite : la mesure de l'erreur, choisie avant de voir le moindre chiffre."),
        decision=T('Cross-validation with 5 folds in model-year order; 80 sealed rows.', "Validation croisée à 5 plis dans l'ordre de l'année du modèle ; 80 lignes scellées."),
    ),
    'error_metric': dict(
        picture=('error_gap', T("A prediction's error: the gap between observed and predicted. What remains is how to sum up the gaps of every car.",
                                "L'erreur d'une prédiction : l'écart entre l'observé et le prédit. Reste à choisir comment résumer les écarts de toutes les voitures."),
                 T('Mean absolute error (MAE): the mean of the gaps, without sign. Root mean squared error (RMSE): the root of the mean of the squared gaps; a big gap weighs much more.',
                   "Erreur absolue moyenne (MAE) : la moyenne des écarts, sans signe. Racine de l'erreur quadratique moyenne (RMSE) : la racine de la moyenne des écarts au carré ; un gros écart y pèse beaucoup plus."), None),
        prepares=T('This answer prepares the Success criterion: the measure it will be set on.', 'Cette réponse prépare le Critère de succès : la mesure sur laquelle il sera fixé.'),
        questions=[
            Q('metric.weigh', T('Does one big miss cost much more than several small ones?', 'Un gros raté coûte-t-il beaucoup plus que plusieurs petits ?'),
              {'kind': 'illustration', 'slot': None, 'key': 'METRIC_EXAMPLE_ERRORS'}, 'metric_bars',
              frame('illustration', 'made-up example, no data of the study, no look', "exemple fictif, aucune donnée de l'étude, aucun regard"),
              T(R('Five made-up errors: 1, 1, 1, 1 and 6 mpg. Their mean is 2; the mean of the squares is 8, its root ≈ 2.83.',
                  'The one big miss makes 6 of the 10 of the sum of gaps, but 36 of the 40 of the sum of squares. The decision depends on a business question.',
                  'The example is made up: it says nothing of the errors the models will make on Auto MPG.'),
                R('Cinq erreurs fictives : 1, 1, 1, 1 et 6 mpg. Leur moyenne vaut 2 ; la moyenne des carrés vaut 8, sa racine ≈ 2,83.',
                  "Le seul gros raté fait 6 sur 10 de la somme des écarts, mais 36 sur 40 de la somme des carrés. La décision dépend d'une question métier : un gros raté coûte-t-il bien plus que plusieurs petits ?",
                  "L'exemple est fictif : il ne dit rien des erreurs que feront les modèles sur Auto MPG, ni laquelle des deux mesures les départagera.")),
              T('Left, the gaps; the green line is their mean. Right, the same squared: the 6 becomes 36.', "À gauche, les écarts ; la ligne verte est leur moyenne. À droite, les mêmes au carré : le 6 devient 36."),
              T('The two panels do not share a vertical scale: compare the written values, not the heights.', "Les deux panneaux n'ont pas la même échelle verticale : comparez les valeurs écrites, pas les hauteurs."),
              chart_data='metric', status='answered'),
        ],
        limit=T('The measure does not say which error is acceptable: that is the next step.', "La mesure ne dit pas quelle erreur est acceptable : c'est l'étape suivante."),
        next=T('Next: the success criterion, a bar set on this measure before any model.', 'Ensuite : le critère de succès, une barre fixée sur cette mesure avant tout modèle.'),
        decision=T('Mean absolute error (MAE): every error weighs the same, and it reads in mpg.', "Erreur absolue moyenne (MAE) : chaque erreur pèse pareil, et elle se lit en mpg."),
    ),
    'success_criterion': dict(
        picture=('criterion_bar', T('Set the bar before seeing a figure. The model will have to err clearly less than the reference, which always predicts the mean.',
                                    'Fixer la barre avant de voir un chiffre. Le modèle devra se tromper nettement moins que la référence, qui prédit toujours la moyenne.'),
                 T('The reference (predict the mean) is the most naive model. The criterion says how much better a model must do to count; it is judged on the final test.',
                   'La référence (prédire la moyenne) est le modèle le plus naïf. Le critère dit de combien un modèle doit faire mieux pour compter ; il sera jugé sur le test final.'), None),
        prepares=T('This answer prepares the Final test and the Conclusion: the bar they will judge.', 'Cette réponse prépare le Test final et la Conclusion : la barre qu\'ils jugeront.'),
        questions=[
            Q('criterion.bar', T("How much smaller than the reference's error must the model's be, and what does that mean for the business?",
                                 "De combien l'erreur du modèle doit-elle être plus petite que celle de la référence, et que veut dire ce seuil pour le métier ?"),
              {'kind': 'case', 'slot': None, 'key': 'case_brief'}, 'bars',
              frame('illustration', "no figure of the study: a made-up example and the PO's figures", "aucun chiffre de l'étude : exemple fictif et chiffres du PO"),
              T(R("If the reference erred by 7 mpg, the 10% criterion would ask for 6.3 mpg or less. The current manual estimate errs by about 4.5 mpg (PO's figure); the PO aims at about 3.5.",
                  'The 10% criterion is a statistical minimum: a model can meet it while staying worse than the current method. For the business, the useful bar is the current method.',
                  "These figures are an example: the reference's real error is known only at the step Models, and the manual method's comes from the PO, not from these data."),
                R("Si la référence se trompait de 7 mpg, le critère de 10 % demanderait 6,3 mpg ou moins. L'estimation manuelle actuelle se trompe d'environ 4,5 mpg (chiffre du PO) ; le PO vise environ 3,5.",
                  "Le critère de 10 % est un minimum statistique : un modèle peut l'atteindre tout en restant moins bon que la méthode actuelle. Pour le métier, la barre utile est la méthode actuelle.",
                  "Ces chiffres sont un exemple : l'erreur réelle de la référence ne sera connue qu'à l'étape Modèles, et celle de la méthode manuelle vient du PO, pas de ces données.")),
              T('Each bar: a mean error in mpg; shorter is better. The ochre bar is the minimum set here; the last two come from the use-case brief.',
                "Chaque barre : une erreur moyenne en mpg ; plus courte, c'est mieux. La barre ocre est le minimum fixé ici ; les deux dernières viennent de la fiche du cas d'usage."),
              T('A relative share depends on the reference: 10% of a weak reference is still a low bar.', 'Un pourcentage relatif dépend de la référence : 10 % d\'une référence faible reste une barre basse.'),
              chart_data='criterion', status='answered'),
        ],
        limit=T('Meeting the criterion will not say the model suffices for every use: that is a business question.', "Atteindre le critère ne dira pas que le modèle suffit pour tout usage : c'est une question métier."),
        next=T('Next: the quality check, column by column, without looking at the target.', 'Ensuite : le contrôle de qualité, colonne par colonne, sans regarder la cible.'),
        decision=T('At least 10% less mean absolute error than the reference (predict the mean), judged on the final test.',
                   "Au moins 10 % d'erreur absolue moyenne en moins que la référence (prédire la moyenne), jugé sur le test final."),
    ),
    'structural_eda': dict(
        picture=('quality_checks', T('Four checks per column: empty cells, rare categories, long tails, out-of-range values. Each has its bound, set in advance.',
                                     "Quatre contrôles par colonne : cellules vides, catégories rares, longues traînes, valeurs hors plage. Chacun a son seuil, fixé d'avance."),
                 T('The checks read the columns of the technical sheet, never mpg. A crossed bound triggers a preparation proposal; it changes nothing on its own.',
                   'Les contrôles lisent les colonnes de la fiche technique, jamais mpg. Un seuil franchi déclenche une proposition de préparation ; il ne change rien tout seul.'), None),
        prepares=T('These answers prepare the Preparation: which columns to transform, and why.', 'Ces réponses préparent la Préparation : quelles colonnes transformer, et pourquoi.'),
        questions=[
            Q('quality.missing', T('Which columns have missing cells?', 'Quelles colonnes ont des cellules manquantes ?'), res('eda.quality'), 'bars',
              frame('structure', '318 development rows, columns of the technical sheet', '318 lignes de développement, colonnes de la fiche technique'),
              T(R('One column only has missing cells: horsepower, 6 "?" out of 318 rows, 1.9%.',
                  'The "?" must be read as missing, else the column would be read as text. Their share is small: how they are replaced will weigh little on the error.',
                  'The chart does not say why these 6 values are missing, nor whether they are missing at random.'),
                R('Une seule colonne a des cellules manquantes : la puissance, 6 « ? » sur 318 lignes, soit 1,9 %.',
                  'Les « ? » doivent être lus comme manquants, sinon la colonne serait lue comme du texte. Leur part est faible : la façon de les remplacer pèsera peu sur l\'erreur.',
                  'Le graphique ne dit pas pourquoi ces 6 valeurs manquent, ni si elles manquent au hasard.')),
              T('One bar per column: the share of empty cells.', 'Une barre par colonne : la part de cellules vides.'),
              T('A very short bar is still a problem if the column is read as text: one "?" suffices.', 'Une barre très courte reste un problème si la colonne est lue comme du texte : un seul « ? » suffit.'),
              verdict='missing', status='answered'),
            Q('quality.shape', T('Which columns are skewed, long-tailed or have rare categories?', 'Quelles colonnes sont asymétriques, à longue traîne ou à catégories rares ?'),
              {'kind': 'digest', 'slot': None, 'key': 'quality_verdicts'}, 'verdicts_table',
              frame('structure', 'per column · verdict and bound', 'vue par colonne · verdict et seuil'),
              T(R('Horsepower crosses the skewness bound: 1.05 for a bound of 1; the other columns stay under their bounds.',
                  'One column only calls for a transformation: the preparation will bear on horsepower.',
                  'A crossed bound does not say a transformation will reduce the error: only the models will measure it.'),
                R("La puissance dépasse le seuil d'asymétrie : 1,05 pour un seuil de 1 ; les autres colonnes restent sous leurs seuils.",
                  'Une seule colonne appelle une transformation : la préparation portera sur la puissance. Les autres n\'ont pas de motif de changement enregistré.',
                  "Un seuil franchi ne dit pas qu'une transformation réduira l'erreur : seuls les modèles le mesureront.")),
              T('One row per check; the transformed column first.', 'Une ligne par contrôle ; la colonne transformée vient d\'abord.'),
              T('Skewness sums up a shape in one number; two columns at 0.9 and 1.1 look more alike than their verdicts.',
                "L'asymétrie résume la forme en un nombre ; deux colonnes à 0,9 et 1,1 se ressemblent plus que leurs verdicts."),
              verdict='skew', status='answered'),
        ],
        limit=T('A structural check: it does not read mpg and says nothing of the models\' error.', "Contrôle de structure : il ne lit pas mpg et ne dit rien de l'erreur des modèles."),
        next=T('Next: the preparation, column by column, with the reason for each change and each status quo.', 'Ensuite : la préparation, colonne par colonne, avec la raison de chaque changement et de chaque statu quo.'),
        decision=None,
    ),
    'preprocessing': dict(
        picture=('log_before_after', T('A long tail can crush a straight line. The log tightens the large values; the distribution becomes more symmetric.',
                                       'Une longue traîne peut écraser une droite. Le log resserre les grandes valeurs ; la distribution devient plus symétrique.'),
                 T('Each transformation is learned on the training part of each fold, then applied to the predicted part.',
                   'Chaque transformation est apprise sur la partie entraînement de chaque pli, puis appliquée à la partie prédite.'), None),
        prepares=T('These answers prepare the Models: the columns as they will read them.', 'Ces réponses préparent les Modèles : les colonnes telles qu\'ils les liront.'),
        questions=[
            Q('prep.changed', T('Which columns get a transformation, and why?', 'Quelles colonnes reçoivent une transformation, et pourquoi ?'),
              res('eda.distribution:horsepower'), 'distribution_before_after',
              frame('structure', '318 development rows, without the target', '318 lignes de développement, sans la cible'),
              T(R('Horsepower has a tail of high values, skewness 1.05; the log makes it nearly symmetric.',
                  'The log tightens the large horsepowers, which would otherwise weigh much on a line.',
                  'The histogram does not look at mpg: it does not say whether the log will reduce the error.'),
                R('La puissance a une traîne de valeurs hautes, asymétrie 1,05 ; après le log, la distribution est presque symétrique.',
                  'Le log resserre les grandes puissances, qui pèseraient sinon beaucoup sur une droite. La médiane des 6 manquants est apprise sur la partie entraînement de chaque pli.',
                  "L'histogramme ne regarde pas mpg : il ne dit pas si le log réduira l'erreur. Seuls les modèles le mesureront.")),
              T('The raw horsepower, before the log.', 'La puissance brute, avant le log.'),
              T('A log axis reads in ratios, not in differences of horsepower.', 'Un axe en log se lit en rapports, pas en différences de chevaux.'),
              status='answered'),
            Q('prep.unchanged', T('Why are the other columns left as they are?', 'Pourquoi les autres colonnes restent-elles telles quelles ?'),
              {'kind': 'digest', 'slot': None, 'key': 'quality_verdicts'}, 'verdicts_table',
              frame('structure', 'unchanged columns · value and bound', 'colonnes inchangées · valeur et seuil'),
              T(R('Displacement, weight and cylinders stay under the skewness bound; origin has no rare category.',
                  'These columns enter the models as they are: no rule asks to change them.',
                  '"Under the bound" does not mean "without effect": a transformation could still change the error.'),
                R("Cylindrée, poids et cylindres restent sous le seuil d'asymétrie ; l'origine n'a pas de catégorie rare.",
                  "Ces colonnes entrent dans les modèles telles qu'elles sont : aucune règle ne demande de les changer. Un changement sans motif enregistré serait un choix fait à l'œil.",
                  '« Sous le seuil » ne veut pas dire « sans effet » : une transformation pourrait quand même changer l\'erreur.')),
              T('One row per column left as is, with the rule that leaves it.', 'Une ligne par colonne laissée telle quelle, avec la règle qui la laisse.'),
              T('A "no change" is a decision like any other: it has its reason, here the bound.', 'Un « aucun changement » est une décision comme une autre : il a sa raison, ici le seuil.'),
              status='answered'),
        ],
        limit=T('The preparation is learned on the development rows; the final test receives it as is.', 'La préparation est apprise sur les lignes de développement ; le test final la reçoit telle quelle.'),
        next=T('Next: the exploration, the first counted look at the target.', "Ensuite : l'exploration, le premier regard compté sur la cible."),
        decision=T('Median for the missing values, log of horsepower; the other columns as they are.', 'Médiane pour les manquants, log de la puissance ; les autres colonnes telles quelles.'),
    ),
    'train_eda': dict(
        picture=('trend_reading', T('Read the target along a variable. One point per car; the trend line follows the general shape, straight or curved.',
                                    'Lire la cible selon une variable. Un point par voiture ; la courbe de tendance suit la forme générale, droite ou courbe.'),
                 T('The trend line follows the points locally, without assuming a line. If it bends, a straight relation will not suffice.',
                   'La courbe de tendance suit les points localement, sans supposer une droite. Si elle se plie, une relation droite ne suffira pas.'), None),
        prepares=T('These answers prepare the Models: which shape they will have to follow.', 'Ces réponses préparent les Modèles : quelle forme ils auront à suivre.'),
        questions=[
            Q('explore.target', T('How is mpg distributed?', 'Comment se répartit mpg ?'), res('eda.target_summary'), 'histogram',
              frame('development', 'development rows (318) · look at the target, counted (looks: 4)', 'lignes de développement (318) · regard sur la cible, compté (regards : 4)'),
              T(R('mpg goes from 9 to 46.6, median 23, over 318 cars.',
                  'Most cars are between 17 and 29 mpg, with a tail towards very frugal cars. An error of a few mpg weighs more on a thirsty car than on a frugal one.',
                  'This chart says nothing of the link between mpg and the other columns, nor of cars outside 1970–82.'),
                R('mpg va de 9 à 46,6, médiane 23, sur 318 voitures.',
                  "La plupart des voitures sont entre 17 et 29 mpg, avec une traîne vers les voitures très sobres. Une erreur de quelques mpg pèse plus sur une voiture peu sobre que sur une voiture sobre.",
                  'Ce graphique ne dit rien du lien entre mpg et les autres colonnes, ni des voitures hors de 1970–82.')),
              T('The box covers the middle half of the cars; the line marks the median.', 'La boîte couvre la moitié centrale des voitures ; le trait marque la médiane.'),
              T('A summary in five numbers hides bumps a histogram would show.', 'Un résumé en cinq nombres cache des bosses qu\'un histogramme montrerait.'),
              others=[{'slot': 'eda.special_values', 'chart': 'bars'}], status='answered'),
            Q('explore.features', T('Which variables move with mpg, straight or curved?', 'Quelles variables bougent avec mpg, en droite ou en courbe ?'),
              res('eda.mean_by:weight'), 'trend_by_bins',
              frame('development', 'mean of mpg by bins of weight', 'moyenne de mpg par tranche de poids'),
              T(R('Heavier, fewer mpg: from 33.18 in the lightest bin down, flattening in the heaviest.',
                  'Weight carries one of the strongest signals, but the relation is not straight: a line on raw weight would err in the same direction at both ends.',
                  'This link is not a cause: heavy cars also have big engines.'),
                R('Plus lourd, moins de mpg : de 33,18 dans la tranche la plus légère vers le bas, la tendance s\'aplatit pour les plus lourdes.',
                  'Le poids porte l\'un des signaux les plus forts, mais la relation n\'est pas droite : une droite sur le poids brut se tromperait dans le même sens aux deux bouts.',
                  "Ce lien n'est pas une cause : les voitures lourdes ont aussi de gros moteurs. Il décrit ces voitures-ci, pas l'effet d'alléger une voiture donnée.")),
              T('One point per bin of weight, with its interval; the dashed line is the overall mean.', 'Un point par tranche de poids, avec son intervalle ; le pointillé est la moyenne générale.'),
              T('Bins at the edges hold few cars: their points move more.', 'Les tranches aux bords comptent peu de voitures : leurs points bougent plus.'),
              others=[{'slot': f'eda.mean_by:{c}', 'chart': 'trend_by_bins'} for c in ['horsepower', 'displacement', 'cylinders', 'origin']], status='answered'),
            Q('explore.redundant', T('Do some variables say the same thing?', 'Certaines variables disent-elles la même chose ?'), res('eda.correlation'), 'correlation',
              frame('structure', 'correlation between predictors · without the target', 'corrélation entre prédicteurs · sans la cible'),
              T(R('Weight, displacement, cylinders and horsepower are strongly linked: from 0.81 to 0.95.',
                  'These four columns describe almost the same thing, the size of the engine and of the car. Their separate coefficients will be unstable.',
                  'A strong correlation does not say which counts most, nor whether to remove one.'),
                R('Poids, cylindrée, cylindres et puissance sont très liés : de 0,81 à 0,95.',
                  'Ces quatre colonnes décrivent presque la même chose, la taille du moteur et de la voiture. Une prédiction peut rester bonne, mais leurs coefficients séparés seront instables.',
                  "Une forte corrélation ne dit pas laquelle compte le plus, ni s'il faut en retirer une.")),
              T('Each cell crosses two variables; dark blue: they rise together; orange: one rises when the other falls.',
                "Chaque case croise deux variables ; bleu foncé : elles montent ensemble ; orange : l'une monte quand l'autre baisse."),
              T('A correlation sums up a straight trend: two columns linked in a curve can show a modest number.',
                'Une corrélation résume une tendance droite : deux colonnes liées en courbe peuvent afficher un nombre modeste.'),
              status='answered'),
        ],
        limit=T('Development evidence: these charts choose nothing, and each look at the target is counted.', 'Preuve de développement : ces graphiques ne choisissent rien, et chaque regard sur la cible est compté.'),
        next=T('Next: the models. The reference and the linear model first.', "Ensuite : les modèles. La référence et le modèle linéaire d'abord."),
        decision=T('Exploration read: the charts on the target, looks counted.', 'Exploration lue : les graphiques sur la cible, regards comptés.'),
    ),
    'models': dict(
        picture=('mean_vs_line', T('Two simple models first. The reference always predicts the mean: a flat line. The linear model draws a line through the points.',
                                   'Deux modèles simples d\'abord. La référence prédit toujours la moyenne : une ligne plate. Le modèle linéaire trace une droite à travers les points.'),
                 T('The reference is the bar any model must beat. The linear model is simple and readable; its errors will show what a more flexible shape should correct.',
                   'La référence est la barre que tout modèle doit battre. Le modèle linéaire est simple et lisible ; ses erreurs montreront ce qu\'une forme plus souple devrait corriger.'), None),
        prepares=T('These answers prepare the Variants: what the linear model misses.', 'Ces réponses préparent les Variantes : ce que le modèle linéaire rate.'),
        questions=[
            Q('models.beat', T('Does the linear model err less than the reference, out of fold?', 'Le modèle linéaire se trompe-t-il moins que la référence, hors pli ?'),
              res('fit.linear'), 'model_dots',
              frame('development', 'out of fold, 318 cars, 5 blocks · used to choose', 'hors pli, 318 voitures, 5 blocs · a servi à choisir'),
              T(R('Out of fold, the linear model errs by 3.64 mpg, the reference by 7.17.',
                  'The linear model errs about half as much as predicting the mean: it learns something from the technical sheets.',
                  'These figures served to compare: they are a little optimistic.'),
                R('Hors pli, le linéaire se trompe de 3,64 mpg, la référence de 7,17.',
                  "Le modèle linéaire se trompe environ deux fois moins que prédire la moyenne : il apprend quelque chose des fiches techniques. Le critère, lui, ne sera jugé que sur le test final.",
                  'Ces chiffres ont servi à comparer : ils sont un peu optimistes. Ils ne disent pas si une forme plus souple ferait mieux.')),
              T('Small circles: one fold each; disc: the mean.', 'Petits cercles : un pli chacun ; disque : la moyenne.'),
              T('The 5 folds are not independent: their spread underestimates the real uncertainty.', 'Les 5 plis ne sont pas indépendants : leur dispersion sous-estime l\'incertitude réelle.'),
              status='answered'),
            Q('models.where', T('Where does the linear model err?', 'Où le modèle linéaire se trompe-t-il ?'), res('diag.regression'), 'observed_predicted',
              frame('development', 'observed against predicted, out of fold · equal axes', 'observé contre prédit, hors pli · axes égaux'),
              T(R('On the cars predicted out of fold, the points leave the diagonal at both ends.',
                  'The errors are not spread at random: they grow at the extremes of mpg. The step Variants examines this pattern.',
                  'This cloud does not say which variable causes the gap.'),
                R("Sur les voitures prédites hors pli, les points s'écartent de la diagonale aux deux bouts.",
                  "Les erreurs ne sont pas réparties au hasard : elles grandissent aux extrêmes de mpg. L'étape Variantes examine ce motif, variable par variable.",
                  'Ce nuage ne dit pas quelle variable cause l\'écart, ni si un autre modèle le corrigerait.')),
              T('One point per car: predicted across, observed up, on the same scale.', 'Un point par voiture : prédit en bas, observé à gauche, sur la même échelle.'),
              T('Both axes share a scale: without it, the diagonal would not be y = x.', 'Les deux axes ont la même échelle : sans cela, la diagonale ne serait pas y = x.'),
              status='answered'),
        ],
        limit=T('These figures served to choose: they are optimistic, and the final test stays sealed.', 'Ces chiffres ont servi à choisir : ils sont optimistes, et le test final reste scellé.'),
        next=T('Next: the variants, under the same evaluation.', 'Ensuite : les variantes, sous la même évaluation.'),
        decision=T('Reference and linear model fitted; moving on to the variants.', 'Référence et modèle linéaire ajustés ; on passe aux variantes.'),
    ),
    'model_variant': dict(
        picture=('line_misses_curve', T('A line can miss a curve. A variant tries a more flexible shape, under the same evaluation.',
                                        'Une droite peut rater une courbe. Une variante essaie une forme plus souple, sous la même évaluation.'),
                 T('Ridge: the same line, with restrained coefficients. EBM: one learned curve per variable, added up.',
                   'Ridge : la même droite, avec des coefficients retenus. EBM : une courbe apprise par variable, additionnées ; plus souple, encore lisible.'), None),
        prepares=T('These answers prepare the choice of the variants to compare.', 'Ces réponses préparent le choix des variantes à comparer.'),
        questions=[
            Q('variants.shape', T("Do the linear model's errors draw a shape?", 'Les erreurs du modèle linéaire dessinent-elles une forme ?'), res('diag.regression'), 'residual_by_feature',
              frame('development', 'errors of the linear model along horsepower, out of fold', 'erreurs du modèle linéaire selon la puissance, hors pli'),
              T(R('The errors bend along horsepower: the line errs in the same direction at both ends.',
                  'The line misses a curve. A variant helps on this point only if it can follow a curve; the comparison will measure whether it does.',
                  'A shape in the errors does not guarantee another model will do better on average.'),
                R('Les erreurs se plient le long de la puissance : la droite se trompe dans le même sens aux deux bouts.',
                  "La droite rate une courbe. Une variante n'aide sur ce point que si elle peut suivre une courbe ; la comparaison mesurera si elle le fait.",
                  "Une forme dans les erreurs ne garantit pas qu'un autre modèle fera mieux en moyenne : seul l'écart apparié le dira.")),
              T('One point per bin: its mean error, observed minus predicted.', 'Un point par tranche : son erreur moyenne, observé moins prédit.'),
              T('Bins at the edges hold few cars.', 'Les tranches aux bords comptent peu de voitures.'), status='answered'),
            Q('variants.period', T('Is the error stable from one period to the next?', "L'erreur est-elle stable d'une période à l'autre ?"), res('diag.regression'), 'bias_by_period',
              frame('development', 'mean bias per period, out of fold', 'biais moyen par période, hors pli'),
              T(R('The bias goes from −2.46 mpg (1970–72) to +5.27 (1981–82).',
                  'The model errs in a direction that changes with the years: a limit to write in the conclusion.',
                  'With 5 blocks, it is a signal, not a proof; nothing says how the model would behave after 1982.'),
                R('Le biais passe de −2,46 mpg (1970–72) à +5,27 (1981–82).',
                  'Le modèle se trompe dans un sens qui change avec les années : une limite à écrire dans la conclusion.',
                  "Avec 5 blocs, c'est un signal, pas une preuve ; rien ne dit comment le modèle se comporterait après 1982.")),
              T('Each bar: the mean error of the cars of a period; right of zero: the model predicts too few mpg.', "Chaque barre : l'erreur moyenne des voitures d'une période ; à droite de zéro : le modèle prédit trop peu de mpg."),
              T('Periods do not hold the same number of cars: a bar of a small period moves more.', 'Les périodes ne comptent pas le même nombre de voitures : une barre de petite période bouge plus.'),
              chart_data='bias', status='answered'),
        ],
        limit=T('These diagnostics come from rows used to choose: they are optimistic.', 'Ces diagnostics viennent des lignes qui servent à choisir : ils sont optimistes, et le test final reste scellé.'),
        next=T('Next: the model choice, on the paired gap and the one-standard-error rule.', "Ensuite : le choix du modèle, sur l'écart apparié et la règle d'une erreur type."),
        decision=T('Compare the linear model with a ridge (tuned penalty) and an EBM.', 'Comparer le modèle linéaire à une ridge (pénalité réglée) et à un EBM.'),
    ),
    'model_choice': dict(
        picture=('one_se_rule', T('The simplest that holds the comparison. Among the configurations within one standard error of the best, the rule names the simplest.',
                                  "Le plus simple qui tient la comparaison. Parmi les configurations à moins d'une erreur type de la meilleure, la règle désigne la plus simple."),
                 T('The one-standard-error rule is a rule of the tool, not your decision: it names, you choose in the chat.',
                   "La règle d'une erreur type est une règle de l'outil, pas votre décision : elle désigne, vous choisissez dans le chat."), None),
        prepares=T('These answers prepare the Final test: the configuration read there, once.', 'Ces réponses préparent le Test final : la configuration qui y sera lue, une fois.'),
        questions=[
            Q('choice.best', T('Which configuration errs least, and is the gap larger than the noise?', "Quelle configuration se trompe le moins, et l'écart dépasse-t-il le bruit ?"),
              res('evaluate.regression'), 'paired_intervals',
              frame('development', 'out of fold, 318 cars, 5 blocks · used to choose', 'hors pli, 318 voitures, 5 blocs · a servi à choisir'),
              T(R('Paired gap, ± one standard error: EBM − linear −0.24; ridge − linear −0.01 [−0.04; +0.03].',
                  'The most flexible configuration errs less than the simplest. The decision weighs a few tenths of mpg against simplicity.',
                  'The paired gap says the difference exists on these 318 cars, not that it matters for the use.'),
                R('Écart apparié, ± une erreur type : EBM − linéaire −0,24 ; ridge − linéaire −0,01 [−0,04 ; +0,03].',
                  "La configuration la plus souple se trompe moins que la plus simple. La décision pèse quelques dixièmes de mpg contre la simplicité.",
                  "L'écart apparié dit que la différence existe sur ces 318 voitures, pas qu'elle compte pour l'usage, ni qu'elle tiendra sur le test final.")),
              T('Each point: the error difference, variant minus linear, on the same cars; left of zero, the variant errs less.',
                "Chaque point : la différence d'erreur, variante moins linéaire, sur les mêmes voitures ; à gauche de zéro, la variante se trompe moins."),
              T('The bar covers ± one standard error, not a 95% interval: it is shorter.', 'Le trait couvre ± une erreur type, pas un intervalle à 95 % : il est plus court.'),
              others=[{'slot': 'evaluate.regression', 'chart': 'per_fold_dots'}], verdict='criterion', status='answered'),
            Q('choice.simplest', T('Which is the simplest within one standard error of the best?', "Quelle est la plus simple à moins d'une erreur type de la meilleure ?"),
              res('evaluate.regression'), 'one_se_rule',
              frame('development', "one-standard-error rule · the study's values", "règle d'une erreur type · valeurs de l'étude"),
              T(R('Best error: 3.36. The linear model, 3.64, is under 3.97; the ridge, 3.64, too.',
                  'The rule names the simplest of the configurations within one standard error of the best. It is a rule of the tool, not a decision.',
                  'The rule does not say the configurations are equal: the paired gap says otherwise.'),
                R('Meilleure erreur : 3,36. Le linéaire, 3,64, est sous 3,97 ; la ridge, 3,64, aussi.',
                  "La règle désigne la plus simple des configurations à moins d'une erreur type de la meilleure. C'est une règle de l'outil, pas une décision : elle ignore si quelques dixièmes de mpg comptent pour votre usage.",
                  "La règle ne dit pas que les configurations se valent : l'écart apparié dit le contraire. Ni laquelle tiendra le mieux sur le test final.")),
              T('The ochre band goes from the best error to one standard error above.', "La bande ocre va de la meilleure erreur à une erreur type au-dessus."),
              T('Being in the band does not mean "equivalent": it is a simplicity bound, not a test.', 'Être dans la bande ne veut pas dire « équivalent » : c\'est un seuil de simplicité, pas un test.'),
              status='answered'),
        ],
        limit=T('Not yet claimable: the error on cars never used. The final test will measure it, once.', "Pas encore affirmable : l'erreur sur des voitures jamais utilisées. Le test final la mesurera, une fois."),
        next=T('Next: the final test, opened once, in the chat, when you decide it.', "Ensuite : le test final, ouvert une fois, dans le chat, quand vous l'aurez décidé."),
        decision=T('The linear model, which the one-standard-error rule named.', "Le modèle linéaire, que la règle d'une erreur type désignait."),
    ),
    'final_test': dict(
        picture=('sealed_once', T('The only independent figure. 80 cars set aside at the start, read once, with the chosen model.',
                                  'Le seul chiffre indépendant. 80 voitures mises de côté au départ, lues une fois, avec le modèle choisi.'),
                 T('The development figures served to choose: they are a little optimistic. The final test influenced no choice; once opened, it does not close.',
                   "Les chiffres de développement ont servi à choisir : ils sont un peu optimistes. Le test final n'a influencé aucun choix ; une fois ouvert, il ne se referme pas."),
                 {'development': 318, 'sealed': 80}),
        prepares=T('This answer prepares the Conclusion: the figure it may claim.', "Cette réponse prépare la Conclusion : le chiffre qu'elle pourra affirmer."),
        questions=[
            Q('final.what', T('What will the opening measure, and on which rows?', "Que mesure l'ouverture, et sur quelles lignes ?"), {'kind': 'digest', 'slot': None, 'key': 'final_test'},
              'partition_strata', frame('final', '80 cars of the same period (1970–82) · measured once', '80 voitures de la même période (1970–82) · mesurée une fois'),
              T(R('The 80 sealed rows, 16 per bin of the target, read once with the linear model refitted on the 318 development rows.',
                  'This figure influenced no choice: it is the only independent measure of the study.',
                  'The 80 rows come from 1970–82: they say nothing of cars after 1982.'),
                R('Les 80 lignes scellées, 16 par tranche de la cible, lues une fois avec le modèle linéaire réentraîné sur les 318 lignes de développement.',
                  "Ce chiffre n'aura influencé aucun choix : c'est la seule mesure indépendante de l'étude.",
                  "Les 80 lignes viennent de 1970–82 : elles ne disent rien des voitures d'après 1982.")),
              T('The same draw as at the split; the outlined purple cells are the rows read.', 'Le même tirage qu\'au découpage ; les cases violettes cerclées sont les lignes lues.'),
              T('Opening once does not protect from an earlier look: the study counts those of the preview.', "Ouvrir une fois ne protège pas d'un regard antérieur : l'étude compte ceux de l'aperçu."),
              chart_data='strata_opened', status='answered'),
        ],
        limit=T('One draw, from the same period: the final figure says the error on these cars, not on future cars.', 'Un seul tirage, de la même période : le chiffre final dit l\'erreur sur ces voitures-là, pas sur des voitures futures.'),
        next=T('Next: the conclusion, with this figure and its limits.', 'Ensuite : la conclusion, avec ce chiffre et ses limites.'),
        decision=T('Final test opened once, with the linear model refitted on the 318 rows.', 'Test final ouvert une fois, avec le modèle linéaire réentraîné sur les 318 lignes.'),
    ),
    'conclusion': dict(
        picture=('dev_vs_final', T('Two frames, one scale. The development served to choose; the final test, read once, says what the study may claim.',
                                   'Deux cadres, une seule échelle. Le développement a servi à choisir ; le test final, lu une fois, dit ce que l\'étude peut affirmer.'),
                 T('A measured conclusion states the final figure, the population it applies to, and what it does not say.',
                   'Une conclusion mesurée dit le chiffre final, la population à laquelle il s\'applique, et ce qu\'il ne dit pas.'), None),
        prepares=T('These answers form the conclusion of the study.', "Ces réponses forment la conclusion de l'étude."),
        questions=[
            Q('conclusion.beat', T('Does the model beat the reference on the final test?', 'Le modèle bat-il la référence sur le test final ?'), res('final_test.evaluation'), 'dev_vs_final',
              frame('final', 'measured once · with the development evidence for comparison', 'mesurée une fois · avec la preuve de développement pour comparaison'),
              T(R('Final test: linear 2.79 mpg [2.31; 3.30], reference 6.64 [5.76; 7.51]; criterion bound 5.97.',
                  'The model errs about half as much as the reference on cars never used, and under the criterion bound.',
                  '80 cars is few: the interval spans about one mpg.'),
                R('Test final : linéaire 2,79 mpg [2,31 ; 3,30], référence 6,64 [5,76 ; 7,51] ; borne du critère 5,97.',
                  'Le modèle se trompe deux fois moins que la référence sur des voitures jamais utilisées, et sous la borne du critère.',
                  "80 voitures, c'est peu : l'intervalle couvre un mpg. Un chiffre final plus bas ne prouve pas que le modèle est meilleur qu'en développement.")),
              T('Circle: development; disc: final test; line: interval.', 'Cercle : développement ; disque : test final ; trait : intervalle.'),
              T('The criterion bound is computed on the final test; it does not apply to the circles.', 'La borne du critère est calculée sur le test final ; elle ne s\'applique pas aux cercles.'),
              status='answered'),
            Q('conclusion.criterion', T('Is your criterion met?', 'Votre critère est-il atteint ?'), res('final_test.evaluation'), 'criterion_gauge',
              frame('final', 'error reduction on the final test, against the reference', "réduction d'erreur sur le test final, contre la référence"),
              T(R('Reduction of 58.0% [44.6; 71.4], above the minimum of 10%.',
                  'The criterion set before any model is met, even at the low end of the interval.',
                  'Meeting the minimum does not say the model suffices for every use: that is a business question.'),
                R('Réduction de 58,0 % [44,6 ; 71,4], au-dessus du minimum de 10 %.',
                  "Le critère fixé avant tout modèle est atteint, même au bas de l'intervalle.",
                  "Atteindre le minimum ne dit pas que le modèle suffit pour tout usage : c'est une question métier.")),
              T('The point: the measured reduction; the line: its interval; the green line: the minimum.', 'Le point : la réduction mesurée ; le trait : son intervalle ; la ligne verte : le minimum.'),
              T('A 10% minimum is a low bar: a wide margin does not measure usefulness.', "Un minimum de 10 % est une barre basse : un dépassement large ne mesure pas l'utilité."),
              verdict='final', status='answered'),
        ],
        limit=T('Nothing on cars after 1982; weight is associated with fuel use, the model does not say why.', "Rien sur les voitures d'après 1982 ; le poids est associé à la consommation, le modèle ne dit pas pourquoi."),
        next=T('And after: present the conclusion to your partner, the handoff pack, or the Azure ML export.', "Et après : présenter la conclusion à votre binôme, le dossier de passation, ou l'export Azure ML."),
        decision=T('Adopt the linear model: 2.79 mpg of error on the final test, criterion met, with its limits.', "Adopter le modèle linéaire : 2,79 mpg d'erreur sur le test final, critère atteint, avec ses limites."),
    ),
}

NO_CHART = {}
VERDICTS = {
    'missing': lambda lang: None,
    'skew': lambda lang: {'label': 'over its limit' if lang == 'en' else 'seuil dépassé', 'met': False, 'value': 1.0522043350803072, 'bound': 1.0,
                          'result_id': RID['eda.quality'], 'path': 'ranges.2.skewness'},
    'criterion': lambda lang: {'label': 'criterion met by all three, in development' if lang == 'en' else 'critère atteint par les trois, en développement',
                               'met': True, 'value': 3.64, 'bound': 6.45, 'result_id': RID['evaluate.regression'], 'path': 'models.[fit.linear].mae'},
    'final': lambda lang: {'label': 'met' if lang == 'en' else 'atteint', 'met': True, 'value': 0.5795888359952259, 'bound': 0.1,
                           'result_id': RID['final_test.evaluation'], 'path': 'criterion.gain'},
}

NUM = re.compile(r'[−+-]?\d+(?:[.,]\d+)?')


def cites_of(text, rid, slot):
    out = []
    for i, m in enumerate(NUM.finditer(text or '')):
        raw = m.group(0)
        try:
            value = float(raw.replace('−', '-').replace(',', '.'))
        except ValueError:
            continue
        out.append({'name': f'n{i + 1}', 'result_id': rid, 'path': f'engine:EXAMPLE' if rid is None else 'values', 'value': value, 'text': raw})
    return out


def chart_data_of(kind, lang, state_index):
    if kind == 'timeline':
        return timeline(lang, state_index > PLAN.index('prediction_time'))
    if kind == 'strata':
        return strata(False)
    if kind == 'strata_opened':
        return strata(True)
    if kind == 'folds':
        return folds(lang, computed=state_index > PLAN.index('split'))
    if kind == 'metric':
        return metric(lang)
    if kind == 'criterion':
        return criterion_bars(lang)
    if kind == 'bias':
        return bias_period(lang)
    return None


def card(step, lang, state, current_index, results):
    i = PLAN.index(step)
    spec = STEPS[step]
    kind, caption, more, data = spec['picture']
    pic_data = data
    if kind in ('moment_timeline', 'variables_board') and data == 'timeline':
        pic_data = timeline(lang, current_index > PLAN.index('prediction_time'))
    out = {
        'step': step, 'n': i + 1, 'name': NAMES[lang][i], 'short': SHORT[lang][i], 'moment': MOMENT_TITLES[lang][MOMENT[step]], 'state': state,
        'picture': {'kind': kind, 'caption': caption[lang], 'more': more[lang],
                    'illustrative': kind not in ('partition_strip', 'sealed_once', 'variables_board', 'moment_timeline'),
                    'data': pic_data if isinstance(pic_data, dict) else None},
        'prepares': spec['prepares'][lang],
        'questions': [],
        'no_chart': None,
        'limit': spec['limit'][lang], 'next': spec['next'][lang],
        'decision': None,
    }
    if state == 'upcoming':
        return out
    for n, q in enumerate(spec['questions']):
        slot = q['source'].get('slot')
        rid = RID.get(slot) if slot else None
        status = q['status']
        if slot and slot not in results:
            # EN-20: a question drawn from `chart_data` (the split's folds before the split
            # result) is answered, illustrative; the others wait for their result.
            status, rid = ('answered', None) if q['chart_data'] else ('pending', None)
        reading = q['reading'][lang] if status != 'pending' else None
        illustration = q['frame']['evidence'] in ('illustration', 'none')
        cite_rid = None if illustration else rid or (RID.get('eda.quality') if q['source'].get('key') == 'quality_verdicts' else None)
        others = []
        for o in q['other_charts']:
            ors = o['slot']
            others.append({'slot': ors, 'chart': o['chart'], 'result_id': RID.get(ors) if ors in results else None,
                           'result_revision': REVISION if ors in results else None, 'status': 'answered' if ors in results else 'pending'})
        out['questions'].append({
            'id': q['id'], 'n': n + 1, 'text': q['text'][lang], 'source': q['source'], 'chart': q['chart'],
            'chart_data': chart_data_of(q['chart_data'], lang, current_index) if q['chart_data'] else None,
            'other_charts': others,
            'frame': {'evidence': q['frame']['evidence'], 'rows': q['frame']['rows'][lang]},
            'status': status, 'result_id': rid, 'result_revision': REVISION if rid else None,
            'reading': reading,
            'cites': cites_of(reading['see'], cite_rid, slot) if reading else [],
            'verdict': VERDICTS[q['verdict']](lang) if q['verdict'] and status == 'answered' else None,
            'folds': {'how': q['folds']['how'][lang], 'trap': q['folds']['trap'][lang]},
        })
    if state == 'done' and spec['decision']:
        out['decision'] = {'decision_id': step if step not in ('discover_data', 'train_eda', 'models', 'structural_eda') else None,
                           'words': spec['decision'][lang], 'basis': 'restated', 'who': 'you'}
    return out


def step_cards(lang, current, results):
    ci = PLAN.index(current) if current else len(PLAN)
    steps = []
    for i, s in enumerate(PLAN):
        state = 'done' if i < ci else 'current' if i == ci else 'upcoming'
        steps.append(card(s, lang, state, ci, results))
    return {'schema': 'hypotrail.step_cards/1', 'current': current, 'total': len(PLAN), 'steps': steps}


CASE_BRIEF = {
    'source': {'en': 'Confluence, space "Vehicle product" · written by the PO', 'fr': 'Confluence, espace « Produit véhicules » · rédigée par le PO'},
    'fictitious': True,
    'problem': {'en': 'The Design team must announce the fuel use of a new model as soon as its technical sheet is validated, about six months before road tests. Today an engineer estimates it by hand from a close model; mean gap observed: about 4.5 mpg.',
                'fr': "L'équipe Conception doit annoncer la consommation d'un nouveau modèle dès que sa fiche technique est validée, environ six mois avant les essais sur route. Aujourd'hui, un ingénieur l'estime à la main en comparant avec un modèle proche ; écart moyen constaté : environ 4,5 mpg."},
    'decision': {'en': 'Which prototypes go first to fuel-use tests (about twenty a year), and which provisional figure the first product sheets show.',
                 'fr': 'Quels prototypes envoyer d\'abord aux essais de consommation (une vingtaine d\'essais par an), et quel chiffre provisoire afficher dans les premières fiches produit.'},
    'objective': {'en': 'Estimate fuel use from the technical sheet alone, clearly better than the manual estimate (aim at about 3.5 mpg of mean gap), with a range.',
                  'fr': "Estimer la consommation à partir de la fiche technique seule, nettement mieux que l'estimation manuelle (viser environ 3,5 mpg d'écart moyen), avec une fourchette."},
    'production': {'en': 'A prediction service called by the design tool at each new sheet; the estimate is reviewed by an engineer before any use; the model is refitted every year.',
                   'fr': "Un service de prédiction appelé par l'outil de conception à chaque nouvelle fiche ; l'estimation et sa fourchette sont relues par un ingénieur avant tout usage ; le modèle est réentraîné chaque année avec les nouveaux essais."},
    'data_provenance': {'en': 'Real: the "Auto MPG" data set of the UCI Machine Learning Repository: 398 car models sold in the United States from 1970 to 1982. In the scenario: it serves as history while the internal test warehouse is extracted.',
                        'fr': "Réel : le jeu « Auto MPG » du UCI Machine Learning Repository : 398 modèles de voitures vendus aux États-Unis de 1970 à 1982. Dans le scénario : il sert d'historique en attendant l'extraction de l'entrepôt interne des essais. Les données sont publiques et déjà très explorées."},
    'users_and_cost_of_error': {'en': 'Design engineers and the product manager. Announcing too low a fuel use exposes to a public correction; too high an estimate may wrongly drop a prototype.',
                                'fr': "Les ingénieurs de conception et le chef de produit. Annoncer une consommation trop basse expose à une correction publique ; une estimation trop haute peut faire écarter à tort un prototype des essais."},
    'out_of_scope_and_risks': {'en': 'Out of scope: the official homologation; explaining the causes of fuel use. Risks: recent cars differ from old ones; the data stop in 1982.',
                               'fr': "Hors périmètre : l'homologation officielle ; expliquer les causes de la consommation. Risques : les voitures récentes diffèrent des anciennes ; les données s'arrêtent en 1982."},
    'links': {'prediction_moment': {'en': 'The prediction moment will be the validation of the technical sheet (step 2).', 'fr': 'Le moment de la prédiction sera la validation de la fiche technique (étape 2).'},
              'error_measure': {'en': 'The error measure must reflect this cost (step 5).', 'fr': "La mesure de l'erreur devra refléter ce coût (étape 5)."},
              'conclusion': {'en': 'The conclusion will say whether the estimate beats the current method.', 'fr': "La conclusion dira si l'estimation fait mieux que la méthode actuelle."}},
    'current_method_error': {'value': 4.5, 'unit': 'mpg'},
    'target_error': {'value': 3.5, 'unit': 'mpg'},
}

QUESTIONS = {  # the chat's question and options per state (the engine's, EN-13; mockup wording)
    'discover_data': ({'en': 'The data card is shown. Shall we move on to the prediction moment?', 'fr': 'La fiche des données est affichée. On passe au moment de la prédiction ?'},
                      {'en': {'continue': 'Move on to the prediction moment', 'explain': 'Explain first'}, 'fr': {'continue': 'On passe au moment de la prédiction', 'explain': "Expliquer d'abord"}}),
    'train_eda': ({'en': "The exploration's charts are shown. Shall we move on to the models?", 'fr': "Les graphiques de l'exploration sont affichés. On passe aux modèles ?"},
                  {'en': {'continue': 'Move on to the models', 'explain': 'Explain first'}, 'fr': {'continue': 'On passe aux modèles', 'explain': "Expliquer d'abord"}}),
    'prediction_time': ({'en': 'Prediction moment: when the technical characteristics are fixed, before fuel use is measured?',
                         'fr': 'Moment de la prédiction : quand les caractéristiques techniques sont fixées, avant de mesurer la consommation ?'}, None),
    'split': ({'en': 'Split: a cross-validation with 5 folds, in model-year order, on the 318 development rows?',
               'fr': "Découpage : une validation croisée à 5 plis, dans l'ordre de l'année du modèle, sur les 318 lignes de développement ?"}, None),
    'error_metric': ({'en': 'Which error measure do we keep: the mean absolute error (MAE)?', 'fr': "Quelle mesure de l'erreur retient-on : l'erreur absolue moyenne (MAE) ?"},
                     {'en': {'adopt': 'I adopt the MAE', 'change': 'Change: the RMSE', 'explain': 'Explain first'},
                      'fr': {'adopt': "J'adopte la MAE", 'change': 'Changer : la RMSE', 'explain': "Expliquer d'abord"}}),
    'success_criterion': ({'en': 'Success criterion: at least 10% less mean absolute error than the reference (predict the mean), judged on the final test?',
                           'fr': "Critère de succès : au moins 10 % d'erreur absolue moyenne en moins que la référence (prédire la moyenne), jugé sur le test final ?"}, None),
    'conclusion': ({'en': 'Conclusion: adopt the linear model, 2.79 mpg of error on the final test, with its limits?',
                    'fr': "Conclusion : adopter le modèle linéaire, 2,79 mpg d'erreur sur le test final, avec ses limites ?"}, None),
}
DEFAULT_OPTIONS = {'en': {'adopt': 'I adopt', 'change': 'Change something', 'explain': 'Explain first'},
                   'fr': {'adopt': "J'adopte", 'change': 'Changer quelque chose', 'explain': "Expliquer d'abord"}}
PROPOSAL_VALUES = {
    'prediction_time': 'when the technical characteristics of a new model are fixed, before its fuel efficiency is measured',
    'split': {'folds': 5, 'method': 'temporal_folds', 'seed': 20261017},
    'error_metric': {'metric': 'mae'},
    'success_criterion': {'metric': 'mae_reduction', 'min_share': 0.1},
    'conclusion': {'text': 'The development evidence and the final test, opened once, are what the study can cite.', 'verdict': 'adopt_model'},
}
DEFENSIBILITY_DONE = ['unconfirmed_decisions', 'final_test_sealed']


def load(name):
    return json.loads((CAPTURED / f'summary.regression.cv.{name}.json').read_text())['payload']


def with_plan(p, current):
    ci = PLAN.index(current) if current else len(PLAN)
    old = {row['id']: row for row in p['plan']}
    rows = []
    for i, s in enumerate(PLAN):
        row = dict(old.get(s, {'id': s, 'title': PLAN_TITLES.get(s, {}).get('en', s)}))
        row['status'] = 'done' if i < ci else ('awaiting_confirmation' if s in PROPOSAL_VALUES else 'ready') if i == ci else 'blocked'
        rows.append(row)
    p['plan'] = rows
    p['current_step'] = current
    for m in p['moments']:
        if m['id'] == 'frame' and 'error_metric' not in m['steps']:
            m['steps'].insert(m['steps'].index('success_criterion'), 'error_metric')
    for lang in ('en', 'fr'):
        t = p['texts'][lang]
        if 'plan' in t and isinstance(t['plan'], dict):
            t['plan']['error_metric'] = PLAN_TITLES['error_metric'][lang]


def state(name, base, current, note):
    p = copy.deepcopy(load(base))
    with_plan(p, current)
    ci = PLAN.index(current) if current else len(PLAN)
    done_steps = set(PLAN[:ci])
    # Results: those of the done steps and of the current one (from the end of the captured study).
    keep = done_steps | ({current} if current else set())
    p['results'] = {slot: r for slot, r in DONE['results'].items() if r.get('step') in keep}
    if current == 'split':
        # The split is proposed, not computed: its folds are drawn as equal blocks (EN-20).
        p['results'].pop('split', None)
    p['decisions'] = {k: v for k, v in p['decisions'].items() if k in done_steps or k not in PLAN}
    if 'error_metric' in done_steps:
        p['decisions']['error_metric'] = {'status': 'confirmed', 'value': {'metric': 'mae'}, 'basis': 'restated', 'delegation_scope': None,
                                          'user_words': 'Yes, the MAE', 'reason': None, 'open_proposals': [], 'feature_basis': None}
    p['open_proposals'] = []
    if current in PROPOSAL_VALUES:
        pid = f'p_{ci + 1}'
        p['open_proposals'] = [{'proposal_id': pid, 'decision_id': current, 'value': PROPOSAL_VALUES[current],
                                'restatement': QUESTIONS[current][0]['en'], 'revision': p['revision'], 'origin': {'channel': 'chat'},
                                'data_contingent': False, 'evidence': []}]
        p['next_action'] = {'kind': 'await_user_words', 'proposal_id': pid, 'decision': current, 'message': 'Ask the closed question.', 'audience': 'agent',
                            'junior_message': 'A proposal waits for your answer.', 'language': 'en', 'recommended': None,
                            'question': QUESTIONS[current][0]['en']}
    elif current == 'discover_data':
        p['next_action'] = {'kind': 'show_data_card', 'step': 'discover_data', 'message': 'Show the data card.', 'audience': 'agent',
                            'junior_message': 'Look at the data card.', 'language': 'en', 'recommended': None, 'question': QUESTIONS[current][0]['en']}
    elif current == 'train_eda':
        p['next_action'] = {'kind': 'read_exploration', 'step': 'train_eda', 'message': 'Ask with a picker; on continue run then.command.', 'audience': 'agent',
                            'junior_message': "The exploration's charts are shown.", 'language': 'en', 'recommended': None,
                            'question': QUESTIONS[current][0]['en'],
                            'then': {'kind': 'run', 'activity': 'fit.baseline', 'command': 'hypotrail run fit.baseline'},
                            'pause': {'options': ['continue', 'explain'], 'option_labels': QUESTIONS[current][1]['en']}}
    for lang in ('en', 'fr'):
        t = p['texts'][lang]
        if current in QUESTIONS:
            q, opts = QUESTIONS[current]
            t['question'] = q[lang]
            t['options'] = (opts or DEFAULT_OPTIONS)[lang]
            t['options_note'] = None
        t['step_cards'] = step_cards(lang, current, p['results'])
    if ci <= PLAN.index('models'):
        p['criterion_configurations'] = None
        p['ledger'] = copy.deepcopy(load('preparation')['ledger'])
        if ci > PLAN.index('train_eda'):
            p['ledger']['target_looks'] = {'eda': 3, 'sample': 1, 'total': 4}
    p['headlines'] = {k: v for k, v in (p.get('headlines') or {}).items() if k in done_steps}
    for lang in ('en', 'fr'):
        if isinstance(p['texts'][lang].get('headlines'), dict):
            p['texts'][lang]['headlines'] = {k: v for k, v in p['texts'][lang]['headlines'].items() if k in done_steps}
    p['case_display'] = CASE_DISPLAY
    p['case_brief'] = CASE_BRIEF
    d = p.get('defensibility')
    if d:
        for item in d['items']:
            if item['severity'] == 'not_final':
                item['done'] = item['id'] in DEFENSIBILITY_DONE and current is None
    about = {'schema': 'hypotrail.summary/1', 'task': 'regression', 'exit_code': 0, 'source': 'hand-made',
             'argv': ['status', '--summary', '--digest', '--json'],
             'note': f'Lot 2026-10-28 (hand-made from captured/summary.regression.cv.{base}, spec §7.2): {note}'}
    (HERE / f'summary.{name}.json').write_text(json.dumps({'about': about, 'payload': p}, ensure_ascii=False, indent=1) + '\n')


STATES = [
    ('data', 'preparation', 'discover_data', 'step 1, the data card shown'),
    ('moment', 'preparation', 'prediction_time', 'step 2, the prediction moment proposed'),
    ('split', 'preparation', 'split', 'step 4, the split proposed, folds drawn before the split result'),
    ('metric', 'preparation', 'error_metric', 'step 5, the error measure proposed'),
    ('criterion', 'preparation', 'success_criterion', 'step 6, the success criterion proposed'),
    ('exploration', 'preparation', 'train_eda', 'step 9, the pause after the exploration'),
    ('choice', 'choice', 'model_choice', 'step 12, the model choice'),
    ('conclusion', 'done', 'conclusion', 'step 14, the conclusion proposed'),
    ('done', 'done', None, 'the end, every step done'),
]

if __name__ == '__main__':
    for args in STATES:
        state(*args)
    print('wrote', len(STATES), 'fixtures')
