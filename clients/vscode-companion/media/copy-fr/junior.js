// French translation of the junior copy (v0.3, WP-E2, R21). English (media/copy/junior.js) is
// the source; every key there has its counterpart here except the data tables that hold no
// text (SEVERITY, SEVERITY_ORDER, GROUP_OF_KIND, GROUP_ORDER, finalTestState, sharePercent;
// test/copy-fr.test.js lists them). The readers of recorded values (rules, splits, the
// criterion, the preparation) are the English ones with French words; the numbers are the
// recorded values' own.
(function (HT) {
  'use strict';
  const regression = task => task === 'regression';
  const str = x => (typeof x === 'string' ? x : '');
  const cap = s => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s);
  const lower = s => (s ? s.charAt(0).toLowerCase() + s.slice(1) : s);
  // The English readers of recorded values that hold no text (loaded before this file).
  const EN = HT.copy.junior;

  const decisionName = (id, task) => ({
    prediction_time: 'le moment de la prédiction',
    feature_availability: 'les variables utilisables',
    split: 'le découpage',
    policy: regression(task) ? 'la troisième décision' : 'la règle de décision',
    model_choice: 'le choix du modèle',
    success_criterion: 'le critère de succès',
    preprocessing: 'la préparation des données',
    model_variant: 'la variante à comparer',
    final_test: "l'ouverture du test final",
    conclusion: 'la conclusion',
  })[id] || String(id || '').replace(/_/g, ' ');

  const why = (id, task) => ({
    prediction_time: "Le moment de la prédiction fixe quand le score est calculé : il décide donc quelles colonnes peuvent être utilisées.",
    feature_availability: "Seules les colonnes connues au moment de la prédiction peuvent servir ; une colonne remplie plus tard ferait fuiter le résultat dans le modèle.",
    split: "Le découpage met de côté des lignes dont les modèles n'apprennent jamais, pour mesurer leurs erreurs honnêtement.",
    policy: regression(task) ? 'Cette décision transforme les résultats en action.'
      : "La règle de décision transforme les scores en action : sur quels cas agir, compte tenu de ce que l'équipe peut traiter.",
    model_choice: 'Le choix du modèle retient le modèle dont les erreurs sur les lignes de validation conviennent à votre usage.',
    success_criterion: "Le critère de succès fixe, avant de voir les résultats, de combien un modèle doit battre la référence pour valoir la peine d'être adopté.",
    preprocessing: "La préparation des données dit comment sont traités les valeurs manquantes, les catégories rares, les valeurs extrêmes et les colonnes asymétriques ; elle est apprise sur les lignes d'entraînement seulement.",
    model_variant: regression(task)
      ? "Une variante est un seul changement du modèle, comparé selon le même protocole : le choix entre les deux a un but et il est compté."
      : "Une variante est un seul changement du modèle, comme une régularisation plus forte ou un groupe de variables retiré, comparé selon le même protocole : le choix entre les deux a un but et il est compté.",
    final_test: "Le test final est l'ensemble des lignes scellées à la création de l'étude. Ouvert une fois, après les choix, il donne le seul chiffre qui n'a pas servi à choisir ; tout changement ultérieur est marqué comme fait après.",
    conclusion: "La conclusion dit ce que l'étude soutient, et ce qu'elle ne soutient pas.",
  })[id] || '';

  const MODEL_NAMES = { 'fit.logistic': 'le modèle logistique', 'fit.linear': 'le modèle linéaire', 'fit.variant': 'la variante' };
  const modelName = (slot, task) => (slot === 'fit.baseline'
    ? (regression(task) ? 'la référence moyenne' : 'la référence')
    : MODEL_NAMES[slot] || `le modèle ${str(slot).replace(/^fit\./, '').replace(/_/g, ' ')}`);

  function parse(raw) {
    if (raw && typeof raw === 'object') return raw;
    if (typeof raw !== 'string') return null;
    const t = raw.trim();
    if (t.startsWith('{') || t.startsWith('[')) {
      try { return JSON.parse(t); } catch (_) { return raw; }
    }
    return raw;
  }
  const pct = p => EN.sharePercent(p);

  function rule(value, task) {
    const [v, model] = str(value).split('@');
    const tail = model === 'fit.variant' ? ', avec la variante' : '';
    let m = v.match(/^capacity:([0-9]+)$/);
    if (m && !regression(task)) return `Retenir les ${m[1]} meilleurs scores${tail}`;
    m = v.match(/^share:([0-9.]+)$/);
    if (m && !regression(task) && pct(m[1])) return `Retenir les ${pct(m[1])} meilleurs scores${tail}`;
    m = v.match(/^threshold:([0-9.]+)$/);
    if (m && !regression(task)) return `Retenir chaque cas noté ${m[1]} ou plus${tail}`;
    return null;
  }

  function ruleShort(value) {
    const [v, model] = str(value).split('@');
    const tail = model === 'fit.variant' ? ', variante' : '';
    let m = v.match(/^share:([0-9.]+)$/);
    if (m && pct(m[1])) return `les ${pct(m[1])} premiers${tail}`;
    m = v.match(/^capacity:([0-9]+)$/);
    if (m) return `les ${m[1]} premières lignes${tail}`;
    m = v.match(/^threshold:([0-9.]+)$/);
    if (m) return `score d'au moins ${m[1]}${tail}`;
    return str(value);
  }

  function featureName(term) {
    const t = str(term);
    const m = t.match(/^([a-z]+)__(.+)$/);
    if (!m) return t;
    const [, kind, rest] = m;
    if (rest.endsWith('=?')) return `${rest.slice(0, -2)} (manquant)`;
    if (kind === 'miss') return `${rest.replace(/^missingindicator_/, '')} (manquant)`;
    if (kind === 'cat') {
      const cut = rest.lastIndexOf('_');
      return cut > 0 && cut < rest.length - 1 ? `${rest.slice(0, cut)} = ${rest.slice(cut + 1)}` : rest;
    }
    return rest;
  }

  function variant(raw) {
    const v = parse(raw);
    if (!v || typeof v !== 'object') return null;
    if (v.kind === 'regularisation') {
      return v.strength === 'weak' ? 'Comparer avec une variante moins régularisée' : 'Comparer avec une variante plus régularisée';
    }
    if (v.kind === 'drop_group') return `Comparer avec le modèle sans le groupe « ${str(v.group)} »`;
    return null;
  }

  function finalTest(raw, task) {
    const v = parse(raw);
    if (!v || typeof v !== 'object') return null;
    const r = v.rule ? rule(v.rule, task) : null;
    return `Ouvrir le test final une fois pour ${modelName(v.model, task)}${r ? ` (${r.toLowerCase()})` : ''}`;
  }

  function criterion(raw) {
    const v = parse(raw);
    if (!v || typeof v !== 'object') return null;
    // v0.3 (WP-C, R18): the criterion names its metric (precision by default, or recall).
    if (typeof v.min_points === 'number') return `N'adopter que si ${v.metric === 'recall_gain' ? 'le rappel' : 'la précision'} bat la référence d'au moins ${v.min_points} points`;
    if (typeof v.min_share === 'number') {
      return `N'adopter que si l'erreur de validation est inférieure d'au moins ${Math.round(100 * v.min_share)} % à la référence moyenne`;
    }
    return null;
  }

  function preparation(raw) {
    const v = parse(raw);
    if (!v || typeof v !== 'object') return null;
    const parts = [];
    if (v.missing && typeof v.missing === 'object') {
      const flagged = Object.keys(v.missing).filter(k => v.missing[k] === 'indicator');
      parts.push(flagged.length ? `valeurs manquantes signalées (${flagged.join(', ')})` : 'valeurs manquantes non signalées');
    } else {
      parts.push(v.missing === 'indicator' ? 'valeurs manquantes signalées' : 'valeurs manquantes non signalées');
    }
    if (v.rare_category_min_rows) parts.push(`catégories de moins de ${v.rare_category_min_rows} lignes regroupées`);
    const caps = v.caps && typeof v.caps === 'object' ? Object.keys(v.caps) : [];
    parts.push(caps.length ? `valeurs extrêmes plafonnées (${caps.join(', ')})` : 'pas de plafonnement');
    const logs = Array.isArray(v.log_transform) ? v.log_transform : [];
    parts.push(logs.length ? `échelle logarithmique pour ${logs.join(', ')}` : "pas d'échelle logarithmique");
    const text = cap(parts.join(', '));
    return v.data_contingent ? `${text} (choisi après avoir regardé le résultat)` : text;
  }

  function split(value) {
    const v = parse(value);
    if (!v || typeof v !== 'object') return null;
    const share = typeof v.validation_fraction === 'number' ? HT.format.number(v.validation_fraction, 'pct0') : null;
    if (v.method === 'stratified_random' && share) return `Découpage aléatoire stratifié, ${share} des lignes pour la validation`;
    if (v.method === 'random' && share) return `Découpage aléatoire, ${share} des lignes pour la validation`;
    if (['kfold_stratified', 'kfold_quantile', 'temporal_folds'].includes(v.method) && typeof v.folds === 'number') {
      return `Validation croisée en ${v.folds} plis : chaque ligne est prédite une fois par un modèle qui ne l'a pas vue`;
    }
    if (v.method === 'ordinal_cutoff' && v.column !== undefined) {
      return `Découpage dans l'ordre du temps : les lignes où ${v.column} vaut ${v.cutoff} ou plus servent à la validation`;
    }
    return null;
  }

  const VERDICTS = {
    adopt_policy: 'Adopter la règle de décision',
    adopt_model: 'Adopter le modèle choisi',
    keep_baseline: 'Garder la pratique actuelle',
    inconclusive: 'Non concluant',
  };

  const availabilityGroups = raw => EN.availability(raw);

  function value(decisionId, raw, task) {
    if (raw === null || raw === undefined || raw === '') return null;
    switch (decisionId) {
      case 'prediction_time': return typeof raw === 'string' ? cap(raw.trim()) : null;
      case 'feature_availability': {
        const g = availabilityGroups(raw);
        if (!g) return null;
        const parts = [`${g.available.length} disponibles`];
        if (g.uncertainIn.length) parts.push(`${g.uncertainIn.length} incertaines, gardées (${g.uncertainIn.join(', ')})`);
        if (g.uncertainOut.length) parts.push(`${g.uncertainOut.length} incertaines, retirées (${g.uncertainOut.join(', ')})`);
        parts.push(`${g.excluded.length} exclues${g.excluded.length ? ` (${g.excluded.join(', ')})` : ''}`);
        return parts.join(' · ');
      }
      case 'split': return split(raw);
      case 'success_criterion': return criterion(raw);
      case 'preprocessing': return preparation(raw);
      case 'model_variant': return variant(raw);
      case 'final_test': return finalTest(raw, task);
      case 'policy': return rule(raw, task);
      case 'model_choice': return typeof raw === 'string' && raw.startsWith('fit.') ? cap(`adopter ${modelName(raw, task)}`) : null;
      case 'conclusion': {
        const v = parse(raw);
        if (!v || typeof v !== 'object') return null;
        const verdict = regression(task) && v.verdict === 'adopt_policy' ? null : VERDICTS[v.verdict] || null;
        const text = str(v.text).trim();
        return [verdict, text].filter(Boolean).join(' : ') || null;
      }
      default: return null;
    }
  }

  const nextMove = {
    eyebrow: 'Votre prochaine action',
    await_user_words: { title: name => `Répondre à la proposition sur ${name}`, action: 'Voir la proposition',
      lead: "L'assistant l'a proposé dans le chat. Répondez dans le chat : adoptez la décision ou dites ce que vous changez.",
      leadTraining: "L'assistant l'a proposé dans le chat. Répondez dans le chat, avec vos mots : dites ce qu'elle décide, ou ce que vous changez." },
    reconfirm: { title: name => `Confirmer de nouveau ${name}`, action: 'Ouvrir dans Décisions',
      lead: "Quelque chose sur quoi elle repose a changé : votre réponse précédente ne vaut plus tant que vous ne la confirmez pas de nouveau." },
    acknowledge_interruption: { title: () => "Une exécution s'est arrêtée avant la fin", action: "Aller à l'exécution",
      lead: "Son issue est inconnue. Dites avec vos mots que vous le savez ; rien ne redémarre tout seul." },
    outcome_unknown: { title: () => "Une exécution s'est arrêtée avant la fin", action: "Aller à l'exécution",
      lead: "Son issue est inconnue. Elle n'est pas en cours et ne redémarre pas toute seule." },
    propose: { title: step => `Étape suivante : ${step}`, action: null,
      lead: "Rien ne vous attend ici. L'assistant propose cette étape dans le chat." },
    run: { title: step => `Étape suivante : ${step}`, action: null,
      lead: "Rien ne vous attend ici. L'assistant mène cette étape dans le chat." },
    blocked: { title: step => `Étape suivante : ${step}`, action: null,
      lead: "Cette étape attend une étape antérieure. L'assistant vous guide dans le chat." },
    done: { title: () => 'Toutes les étapes sont faites', action: null,
      lead: "Le rapport et le notebook portent l'étude. Relisez-les avant de les transmettre." },
    other: { title: () => 'Continuer dans le chat', action: null, lead: "L'assistant guide l'étape suivante dans le chat." },
    finalTest: {
      await: { title: () => 'Ouvrir le test final, dans le chat', action: null,
        lead: "Une proposition d'ouvrir le test final attend votre réponse. Donnez-la dans le chat : le test final ne s'ouvre qu'une fois, et ce panneau n'a aucune commande pour cela.",
        leadTraining: "Une proposition d'ouvrir le test final attend votre réponse. Donnez-la dans le chat, avec vos mots et votre raison : le test final ne s'ouvre qu'une fois, et ce panneau n'a aucune commande pour cela." },
      propose: { title: () => 'Étape suivante : ouvrir le test final une fois', action: null,
        lead: "Quand le modèle et la règle sont arrêtés, dites dans le chat que vous ouvrez le test final. Il ne s'ouvre qu'une fois ; rien n'y est plus mesuré ensuite.",
        leadTraining: "Quand le modèle et la règle sont arrêtés, dites dans le chat que vous ouvrez le test final et pourquoi. Il ne s'ouvre qu'une fois ; rien n'y est plus mesuré ensuite." },
      what: (model, rule2) => `Il mesurerait ${model}${rule2 ? ` avec la règle : ${rule2.charAt(0).toLowerCase()}${rule2.slice(1)}` : ''}, une fois, sur des lignes que personne n'a regardées.`,
    },
    proposalSaid: 'La proposition dit',
    proposedValue: 'En bref',
    whyTitle: 'Pourquoi cela compte',
    supporting: 'Ce qui la soutient',
    inChat: "À ce stade du panneau, répondez dans le chat ; le panneau montre où en est l'étude.",
    details: 'Détails',
    engineSays: "L'instruction du moteur à l'assistant",
    engineLabel: 'Valeur enregistrée',
  };

  const severityLabel = { blocking: 'bloquant', caveat: 'réserve', sealed: 'pas définitif', context: 'contexte' };

  const limitText = {
    unconfirmed_decisions: "Certaines décisions ne sont pas encore confirmées par vous.",
    open_holds: "Une condition que vous avez posée est encore ouverte.",
    conclusion_outdated: "La conclusion ne correspond plus à l'étude ; elle demande de nouveau votre réponse, dans le chat.",
    inconclusive_without_choice: "L'étude n'est pas concluante et aucun choix n'est confirmé.",
    adopted_rule_not_evaluated: "La règle adoptée n'a pas d'évaluation à jour.",
    interrupted_executions: "Une exécution a une issue inconnue.",
    result_integrity: "Un résultat enregistré a échoué à son contrôle d'intégrité ; il n'est pas cité.",
    sources_changed: "Le cas ou les données ont changé depuis le début de l'étude ; aucun résultat n'est à jour.",
    stale_results: "Certains résultats sont périmés et ne sont pas cités.",
    code_changed: "Le code du moteur derrière certains résultats a changé ; ils ne sont pas à jour.",
    uncertain_features_included: "Certaines variables sont utilisées alors qu'elles ne sont peut-être pas connues au moment de la prédiction.",
    delegated_decisions: "Certaines décisions ont été laissées à la valeur par défaut de l'assistant plutôt que décidées par vous.",
    small_validation_partition: "Les lignes de validation sont peu nombreuses : les chiffres peuvent beaucoup varier.",
    capacity_exceeds_validation: "Une règle retient toutes les lignes de validation : elle ne dit rien sur le choix.",
    high_cardinality_grouping: "Certaines valeurs rares ont été regroupées dans un graphique.",
    grouped_split_unsupported: "Des lignes liées peuvent tomber des deux côtés du découpage.",
    validation_is_not_independent: "Les lignes de validation ont servi à choisir : leurs chiffres ne sont pas une preuve indépendante.",
    public_data_already_explored: "Les données ont été publiées et explorées auparavant ; leurs lignes ne sont pas inédites.",
    no_time_or_entity_identifier: "Les données n'ont ni date ni identifiant d'entité : la dérive et les entités répétées ne peuvent pas être vérifiées.",
    no_causality: "L'étude montre des associations ; elle ne mesure pas l'effet d'une action.",
    workbench_not_tracked: "Votre établi n'est pas suivi : rien de ce qu'il contient ne compte comme preuve.",
    final_test_sealed: "Le test final est encore scellé : chaque chiffre jusqu'ici vient des lignes de développement qui ont servi à choisir.",
    changed_after_final_test: "Quelque chose a changé après l'ouverture du test final : il ne mesure plus ce que l'étude contient maintenant.",
    final_test_opening_interrupted: "L'ouverture du test final s'est arrêtée avant l'enregistrement de son résultat ; le test final est consommé et ne peut pas être rouvert.",
    capacity_assumed_for_exercise: "La part des cas ciblés est une hypothèse du scénario pédagogique, pas un chiffre d'une équipe.",
    verdict_contradicts_criterion: "La conclusion adopte alors que le critère de succès n'est pas atteint.",
    verdict_keeps_baseline_against_criterion: "La conclusion garde la référence alors que le critère de succès est atteint sur le test final ; dites pourquoi.",
  };
  const limitFallback = id => `${cap(String(id || '').replace(/_/g, ' '))}.`;

  const groups = {
    needs: 'vous attend', resolved: 'réglé', evaluated: 'réévalué', deliverables: 'livrables', other: 'autre',
  };

  const ACTIVITY = {
    split: 'Le découpage', 'eda.target_rate': 'Le taux de résultat', 'eda.target_summary': 'Le résumé de la cible',
    'eda.special_values': 'La vérification des valeurs spéciales', 'eda.rate_by': 'Un taux de résultat par groupe',
    'eda.mean_by': 'Une moyenne de la cible par groupe', 'eda.distribution': 'Une distribution', 'fit.baseline': 'Le modèle de référence',
    'fit.logistic': 'Le modèle logistique', 'fit.linear': 'Le modèle linéaire', 'policy.evaluate': "L'évaluation de la règle de décision",
    'evaluate.regression': 'La comparaison des modèles',
    'eda.quality': 'La vérification de la qualité des données', 'eda.single_feature_signal': 'La vérification du signal par variable',
    'eda.correlation': 'La matrice de corrélation',
  };
  ACTIVITY['policy.evaluation'] = ACTIVITY['policy.evaluate'];
  const activity = (a, task) => {
    const key = str(a).split(':')[0];
    return (regression(task) && key.startsWith('policy.') ? 'Une évaluation' : ACTIVITY[key]) || 'Un résultat';
  };

  function digestText(item, task, note) {
    const words = note && note.userWords ? ` « ${note.userWords} »` : '';
    const name = decisionName(item.decisionId, task);
    const col = item.column ? ` de ${item.column}` : str(item.slot).includes(':') ? ` de ${str(item.slot).split(':')[1]}` : '';
    const act = item.activity || item.slot;
    switch (item.kind) {
      case 'proposed': return `Une proposition a été faite sur ${name}.`;
      case 'confirmed': return item.basis === 'delegated_default'
        ? `${cap(name)} : laissé à la valeur par défaut de l'assistant.` : `Vous avez confirmé ${name} avec vos mots.`;
      case 'withdrawn': return `La proposition sur ${name} a été retirée.`;
      case 'hold_recorded': return `Vous avez mis ${name} en suspens :${words || ' une condition à vous'}.`;
      case 'hold_resolved': return note && note.resolutionWords
        ? `Votre condition sur ${name},${words}, a été levée avec vos mots : « ${note.resolutionWords} ».`
        : `Votre condition sur ${name} a été levée.`;
      case 'result_added': return `Calculé : ${lower(activity(act, task))}${col}.`;
      case 'result_replaced': return `Recalculé : ${lower(activity(act, task))}${col}.`;
      case 'run_failed': return `Échec : ${lower(activity(act, task))}${col} ; rien n'a été enregistré.`;
      case 'run_interrupted': return `Arrêt avant la fin : ${lower(activity(act, task))}${col}.`;
      case 'interruption_acknowledged': return "Vous avez pris acte d'une exécution dont l'issue est inconnue.";
      default: return null;
    }
  }

  function decidedLine(model) {
    const task = model && model.task;
    const plan = Array.isArray(model && model.plan) ? model.plan : [];
    const parts = plan.filter(s => model.decisions && model.decisions[s.id]
      && ['confirmed', 'reconfirm_required'].includes(model.decisions[s.id].status)).map(s => {
      const d = model.decisions[s.id];
      const words = value(s.id, d.value, task) || str(d.value);
      return `${decisionName(s.id, task)} : ${words}${d.status === 'reconfirm_required' ? ' (à confirmer de nouveau)' : ''}`;
    });
    return `Décidé : ${parts.length ? parts.join(' ; ') : "rien pour l'instant"}.`;
  }

  const modes = {
    title: 'Comment vos réponses sont lues',
    names: { guided: 'guidé', training: 'entraînement', express: 'express' },
    line: name => `Cette étude utilise le mode ${name}.`,
    rules: (mode, task, hasFinal) => {
      const choice = regression(task) ? 'le choix du modèle' : 'la règle de décision';
      // v0.3 (WP-E3): the French rules follow the English ones of ADR 0005 as amended (an
      // endorsement suffices in the guided and express modes; a reason only in training).
      const opening = hasFinal ? (mode === 'training' ? "L'ouverture du test final demande aussi votre raison, et vous la donnez dans le chat uniquement."
        : "L'ouverture du test final se décide dans le chat uniquement.") : null;
      if (mode === 'training') {
        return [
          "Une réponse dit avec vos mots ce que décide la proposition, ses points clés, pas seulement que vous êtes d'accord.",
          "Quand un point clé manque, la confirmation est arrêtée et les points manquants sont nommés, sans mots à recopier.",
          `Pour ${choice} et la conclusion, donnez aussi votre raison avec un mot comme « parce que ».`,
          opening,
          "Des mots qui gardent une variable que la proposition retire, ou l'inverse, arrêtent la confirmation.",
        ].filter(Boolean);
      }
      if (mode === 'express') {
        return [
          'Une réponse adopte la proposition ouverte, comme en mode guidé ; une raison est facultative.',
          "Une fois que vous le dites dans le chat, le critère de succès et la préparation des données peuvent être laissés à la valeur par défaut recommandée par l'assistant ; ils restent marqués comme non décidés par vous.",
          `${choice.charAt(0).toUpperCase()}${choice.slice(1)} et la conclusion sont toujours à vous, jamais délégués.`,
          opening,
        ].filter(Boolean);
      }
      return [
        "Une réponse adopte la proposition ouverte : « oui, je l'adopte » suffit, ou un oui bref à la question « Adoptez-vous cette décision ? ».",
        "Ce n'est pas une réponse si elle pose une question ou garde une condition comme « oui, mais » ou « sauf si ».",
        `Une raison est facultative, aussi pour ${choice} et la conclusion ; sans raison, l'enregistrement indique « aucune raison donnée ».`,
        opening,
        "Quand l'assistant soulève un point sur votre raison, vous pouvez garder vos mots ; le point est enregistré à côté.",
      ].filter(Boolean);
    },
    change: "Le mode ne change que dans le chat : le rendre plus strict ne demande pas de mots, le rendre moins strict demande vos mots nommant le mode. Ce panneau ne peut pas le changer.",
  };

  const METHOD = {
    stratified: 'la même part de chaque résultat',
    quantile_stratified: 'la même part de chaque tranche de la cible',
    temporal: "les lignes les plus récentes dans l'ordre du temps",
  };
  const SLOTS = {
    split: 'le découpage', 'policy.evaluation': "l'évaluation de la règle de décision", 'evaluate.regression': 'la comparaison des modèles',
    'fit.baseline': 'la référence', 'fit.logistic': 'le modèle logistique', 'fit.linear': 'le modèle linéaire', 'fit.variant': 'la variante',
  };
  function changedName(id, task) {
    const key = str(id);
    if (SLOTS[key]) return regression(task) && key === 'policy.evaluation' ? 'une évaluation' : SLOTS[key];
    return decisionName(key, task);
  }
  const finalTestCopy = {
    eyebrow: 'Test final',
    titles: {
      sealed: 'Test final scellé', opened: 'Test final ouvert une fois', changed: "Test final ouvert, puis l'étude a changé",
      interrupted: "L'ouverture du test final s'est arrêtée", absent: 'Pas de test final',
    },
    sealed: (rows, method) => `${rows} lignes ont été mises de côté à la création de l'étude${METHOD[method] ? `, ${METHOD[method]}` : ''}. Personne ne les a lues : aucun graphique, ajustement ni évaluation ne les utilise.`,
    sealedNext: "Elles s'ouvrent une fois, dans le chat, après le choix du modèle et de la règle. D'ici là, chaque chiffre vient des lignes de développement qui ont servi à choisir : il est donc optimiste.",
    opened: rev => `Ouvert une fois, à la révision ${rev}, avec vos mots :`,
    measured: (model, rule2) => `Il a mesuré ${model}${rule2 ? `, ${rule2.charAt(0).toLowerCase()}${rule2.slice(1)}` : ''}, sur des lignes que personne n'avait regardées.`,
    changed: names => `Modifié après l'ouverture : ${names}. Le test final a mesuré ce que contenait l'étude alors, pas ce qu'elle contient maintenant ; il n'est pas rouvert.`,
    interrupted: "L'ouverture a commencé mais aucun résultat n'a été enregistré. Le test final est consommé : il n'est pas ouvert une seconde fois.",
    absent: "Cette étude a été créée avant qu'un test final soit mis de côté : chaque chiffre vient de lignes que l'étude a déjà utilisées.",
    criterion: 'Critère de succès sur le test final : ',
    trials: n => `Configurations évaluées : ${n}.`,
    trialsWhy: "Chaque modèle ou variante essayé sur les mêmes lignes est une chance de plus d'obtenir un bon chiffre par chance. Le compte est une transparence : plus il y a de configurations, plus le meilleur chiffre de développement est optimiste.",
  };

  HT.copyFr = HT.copyFr || {};
  HT.copyFr.junior = {
    decidedLine, ruleShort, featureName, modes, finalTest: finalTestCopy, changedName,
    decisionName, why, value, modelName, nextMove,
    severityLabel, limitText, limitFallback, groups, digestText,
    digestFallback: "L'étude a changé.",
    deliverablesUpToDate: 'Le rapport et le notebook sont à jour.',
    deliverablesBehind: "Le rapport ou le notebook est en retard sur l'étude.",
  };
})(globalThis.Hypotrail = globalThis.Hypotrail || {});
