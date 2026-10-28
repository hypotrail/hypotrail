// Traduction française de media/copy/figures.js (lot P, remarques R34 à R53 ; ADR 0004
// décision 14). Mêmes clés ; aucun chiffre hors des paramètres, aucun point d'exclamation.
(function (HT) {
  'use strict';
  HT.copyFr = HT.copyFr || {};
  HT.copyFr.figures = {
    lookAt: 'Pour répondre, regardez',
    figuresOf: 'Les figures de cette étape',
    noChart: 'Pas de graphique pour ce point.',
    stageLine: stage => `Les figures de chaque étape apparaissent à partir de l'étape ${stage}.`,
    reading: 'Lecture des figures...',
    frames: {
      structural: '◇ lecture structurelle, sans la cible',
      target: '◐ exploration de la cible · un regard, compté',
      development: '◐ preuve de développement · hors pli, a servi à choisir',
      final: '● preuve finale · mesurée une fois',
      method: "◇ comment l'étude est menée · aucun résultat",
    },

    quality: {
      title: 'Chaque colonne des lignes de développement : son étendue, son asymétrie, ses cases manquantes',
      columns: { column: 'Colonne', range: 'Étendue (centile bas, médiane, centile haut)', skew: 'Asymétrie', missing: 'Manquantes', verdict: 'Verdict' },
      changed: 'modifiée',
      kept: 'pas de changement',
      noVerdict: "Le moteur ne donne pas ici de verdict par colonne : ce sont les chiffres que le brouillon a lus.",
      threshold: t => `borne ${t}`,
      concl: (changed, n) => (changed ? `Le brouillon modifie ${changed} ; les ${n} autres colonnes gardent la préparation fixe, sur les mêmes chiffres.`
        : `Aucune colonne n'est modifiée : les ${n} colonnes gardent la préparation fixe, sur les mêmes chiffres.`),
      rows: n => `${n} lignes de développement, la cible n'est pas lue`,
      category: 'catégorie',
      indicator: 'Le brouillon ajoute aussi une colonne indicatrice des cases manquantes, pour les colonnes qui en ont.',
    },

    residuals: {
      scatterTitle: model => `Observé contre prédit, hors pli · ${model}`,
      x: 'prédit', y: 'observé', diagonal: 'prédiction parfaite',
      sample: (shown, n) => `${shown} des ${n} lignes de développement, régulièrement espacées dans l'ordre des prédictions.`,
      byFeature: (column, model) => `Résidu moyen selon ${column} · ${model}`,
      bias: (model, value) => `Résidu moyen de ${model} : ${value} ; au-dessus de zéro, le modèle prédit trop bas en moyenne.`,
      bend: 'Un résidu qui change de signe le long d\'une colonne est une courbe que le modèle linéaire manque.',
    },
    budget: {
      title: "Budget d'essais",
      line: (used, max) => `${used} variantes sur ${max} utilisées`,
      why: "Chaque variante essayée sur les mêmes lignes est une chance de plus d'obtenir un bon chiffre par hasard : le budget la borne.",
    },

    perFold: {
      title: metric => `${metric} de chaque configuration, pli par pli (points) et leur moyenne (anneau)`,
      reading: "Une ligne par configuration : chaque point est un pli dans l'ordre du temps, l'anneau la moyenne sur les plis. L'écart entre les points dit ce que les plis montrent du bruit.",
      numbers: 'Les chiffres en tableau',
      mean: 'moyenne',
    },
    intervalKind: {
      bootstrap: level => ` (intervalle bootstrap, ${level})`,
      oneSe: ' (moyenne ± une erreur type sur les plis)',
    },

    diagrams: {
      partition: {
        title: 'Comment les lignes sont réparties',
        development: n => `${n} lignes de développement`,
        sealed: n => `${n} lignes de test final, scellées`,
        opened: n => `${n} lignes de test final, lues une fois`,
        methods: { quantile_stratified: 'tirées au hasard dans des quantiles, pour que les lignes scellées ressemblent aux autres',
          random: 'tirées au hasard', temporal: "les lignes les plus récentes, dans l'ordre du temps" },
        reading: "Les lignes scellées sont mises de côté à la création : aucun graphique, aucun modèle et aucun choix ne les lit avant que le test final soit ouvert une fois, dans le chat.",
      },
      folds: {
        title: ordered => (ordered ? "Validation croisée : les lignes de développement en blocs dans l'ordre du temps" : 'Validation croisée : les lignes de développement en blocs'),
        block: i => `pli ${i}`,
        reading: "Chaque bloc est prédit par un modèle ajusté sur les autres blocs, années ultérieures comprises ; chaque ligne de développement est prédite une fois, hors pli.",
        span: (lo, hi) => `${lo} à ${hi}`,
      },
      pipeline: {
        title: 'La préparation, apprise dans chaque pli',
        steps: { column: 'colonnes', impute: 'cases manquantes', transform: 'log, plafond, regroupement', model: 'modèle' },
        columnText: 'les colonnes gardées',
        modelText: 'ajusté sur les autres plis',
        log: cols => `log : ${cols}`,
        caps: cols => `plafond : ${cols}`,
        indicator: 'un indicateur des cases manquantes',
        none: 'pas de changement',
        reading: "Chaque pli apprend sa préparation sur les lignes des autres plis seulement, puis l'applique aux lignes qu'il prédit : les lignes prédites ne façonnent jamais leur propre préparation.",
      },
      oneSe: {
        title: metric => `La règle d'une erreur type sur ${metric}`,
        band: 'meilleure + une erreur type',
        best: 'meilleure',
        picked: 'gardée : la plus simple dans la bande',
        reading: "Les configurations dont la moyenne tombe dans la bande ne se distinguent pas de la meilleure sur ces plis ; la règle garde la plus simple d'entre elles. C'est une règle de l'outil, pas votre décision.",
      },
      ledger: {
        title: "Registre d'exposition : quand la cible a été regardée",
        look: 'un regard sur la cible',
        opening: 'le test final ouvert',
        now: 'maintenant',
        revision: r => `révision ${r}`,
        reading: "Chaque regard sur la cible est compté ; le test final s'ouvre une fois. Changer le découpage plus tard ne rend pas invisible ce qui a été vu.",
        none: 'Aucun regard sur la cible enregistré pour l\'instant.',
      },
    },

    devFinal: {
      title: 'Développement et test final, côte à côte',
      configuration: 'Configuration',
      development: 'Développement (hors pli, a servi à choisir)',
      final: 'Test final (lu une fois)',
      difference: chosen => `Différence : ${chosen} moins la référence`,
      criterion: 'Votre critère de succès',
      notMeasured: 'non mesuré : le test final ne mesure que le modèle choisi',
      chosen: 'choisi',
      chart: metric => `${metric} avec son intervalle, développement (◐) et test final (●), sur une même échelle`,
      bound: 'la borne du critère sur le test final',
      met: 'atteint', notMet: 'non atteint', uncertain: 'incertain',
      criterionCell: (bound, verdict) => `erreur d'au plus ${bound} : ${verdict}`,
    },
    conclusionParts: {
      establishes: "Ce que l'étude établit",
      notEstablish: "Ce qu'elle n'établit pas",
      next: 'Et après',
    },
    after: {
      handoffLead: 'Le dossier de passation rassemble vos décisions, les résultats cités et les limites pour un relecteur.',
      handoffWhere: 'Vous choisissez un dossier parent ; les fichiers écrits sont listés dans le tiroir Livrables.',
      azureTitle: "Plan d'export Azure ML",
      azureLead: "Lecture seule : le plan liste les fichiers que l'export écrirait ; rien n'est écrit pour le lire.",
      azureFiles: n => `${n} fichiers`,
      azureKinds: { added: 'ajoutés', adapted: 'adaptés', rendered: 'rendus', preserved: 'repris du gabarit', generated: 'générés',
        copied: 'copiés', shared: 'partagés' },
      azureFamilies: { linear: 'régression linéaire', logistic: 'régression logistique', ridge: 'régression ridge', ebm: 'Explainable Boosting Machine',
        hgb: "boosting d'arbres" },
      azureModel: family => `Modèle : ${family}`,
      azureTemplate: (id, version) => `Gabarit : ${id} ${version}`,
      azureStatus: (config, artifact) => `Configuration : ${config} · fichier du modèle : ${artifact}`,
      azureMissing: n => `${n} champs restent à remplir par l'équipe (espace de travail, calcul, identité)`,
      azureCloud: "Jamais exécuté dans le cloud : aucune tâche ni aucun point de terminaison Azure n'est lancé depuis ce panneau ni depuis ces exports.",
      azureFilesFold: 'Les fichiers du plan',
      azureButton: 'Exporter le projet Azure ML',
      azureHint: "Vous choisissez un dossier hors de l'étude ; l'étude n'enregistre rien.",
      azureNotSupported: "L'export Azure ML n'est pas disponible pour ce modèle.",
      azureReading: "Lecture du plan d'export...",
      azureOut: path => `Écrit dans ${path}`,
      azureDone: n => `${n} fichiers écrits.`,
      exportPlanLater: stage => `Le plan d'export Azure ML apparaît ici à partir de l'étape ${stage} ; demandez-le dans le chat en attendant.`,
    },

    whatif: {
      open: 'Ouvrir Et si ? dans un onglet large',
      openHint: "Un onglet d'éditeur en lecture seule : rien n'y est enregistré.",
      tabTitle: 'Et si ? · lecture seule',
      calm: "Un aperçu sur des chiffres déjà calculés : rien n'est enregistré.",
      why: 'Pourquoi ça compte',
      whyBody: "Une règle ou un modèle changé après avoir vu les chiffres de validation devient un choix dépendant des résultats. L'étude le marque, que vous soyez passé par Et si ? ou non ; cet aperçu n'enregistre et ne décide rien : le chat décide.",
      residualTitle: 'Explorateur des résidus',
      largestTitle: model => `Les plus grandes erreurs · ${model}`,
      largestColumns: { row: 'ligne', observed: 'observé', predicted: 'prédit', residual: 'résidu' },
      configuration: 'Configuration',
      noDiagnostics: "Aucun diagnostic enregistré pour l'instant : l'explorateur des résidus apparaît une fois les modèles diagnostiqués.",
      byYearMissing: "Pas de graphique par année du modèle : les diagnostics n'enregistrent pas de résidu selon cette colonne.",
    },

    contingent: {
      line: 'Choisi après avoir vu des résultats : noté comme dépendant des données.',
      why: 'Pourquoi c\'est noté',
    },

    running: "Calcul en cours, lancé depuis le chat. Le résultat s'affichera ici ; rien à répondre maintenant.",
    runningWhat: what => `En calcul : ${what}.`,
    limits: {
      prediction_time: 'Rien n\'est mesuré pour l\'instant : le moment de la prédiction fixe les colonnes utilisables.',
      feature_availability: "Rien n'est mesuré pour l'instant : une colonne connue seulement après la prédiction trahirait la réponse.",
      split: "Rien n'est mesuré pour l'instant : le découpage décide quelles lignes jugeront les modèles.",
      success_criterion: "Aucun modèle n'est vu pour l'instant : le critère est fixé avant tout chiffre d'un modèle.",
      structural_eda: "Ce contrôle lit les lignes de développement sans la cible : ce n'est pas un regard sur la réponse.",
      preprocessing: 'La préparation repose sur la structure des lignes de développement, pas sur la cible.',
      train_eda: 'Ces graphiques lisent la cible des lignes de développement : chaque regard est compté.',
      final_test: 'Le test final est lu une fois, pour le modèle choisi : il juge le choix, il ne le fait pas.',
      conclusion: "Le test final établit comment le modèle choisi s'en sort sur des lignes jamais vues ; il n'établit ni la performance future ni une cause.",
    },

    fallbackHeadlines: {
      discover_data: (rows, dev, sealed) => (rows ? `${rows} lignes lues : ${dev} pour développer, ${sealed} scellées pour le test final.` : 'La fiche des données a été lue.'),
      structural_eda: 'La structure des lignes de développement a été vérifiée.',
      train_eda: 'La cible a été explorée sur les lignes de développement.',
      models: 'La référence et le modèle candidat ont été ajustés et comparés hors pli.',
      default: 'Fait.',
    },

    decidedBy: { own: 'décidé par vous', automatic: 'enregistré par le mode automatique', delegated: "délégué à l'assistant" },
    decision: 'Décision : ',
    figuresInPath: 'Ses figures',
  };
})(globalThis.Hypotrail = globalThis.Hypotrail || {});
