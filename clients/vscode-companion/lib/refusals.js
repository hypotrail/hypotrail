'use strict';
// What the panel says, for a junior, next to the engine's own refusal message, which is
// always shown verbatim (COMPANION-ADVANCED INV-8, CW.8). These sentences explain what
// happened and that nothing was recorded; they never suggest words to type (the junior's
// confirmation must stay their own): no example reply, no quotation, no wording to copy.
//
// v0 table, extended by WP-U2 with `export_target_exists` (CLI-CONTRACT-COMPANION §12) and
// the refusal contexts of W4 (run an EDA request), W6 (acknowledge an interruption), and
// W7 (export). The context comes from the payload's `command`, so the frozen
// `describe(payload)` signature of the controller is unchanged. The confirmation reasons
// stay: the engine's preview of a confirmation (`preview effects`) can name them. The
// `propose` context went with W3 (v0.3 narrowing, ADR 0004 amendment).

const NOTHING = 'Nothing was recorded.';

const BY_REASON = {
  missing_user_words: 'Your reply was empty.',
  bare_acknowledgement: 'Your reply only acknowledged the proposal; it did not say, in your words, what you are deciding.',
  negative_reply: 'Your reply reads as a refusal, a hesitation, or a reservation, so it was not taken as a confirmation. If you disagree, say so in the chat or withdraw the proposal.',
  unrelated_reply: 'Your reply does not read as an answer to this proposal: it does not agree with it while talking about it.',
  proposal_not_found: 'This proposal does not exist any more.',
  proposal_withdrawn: 'This proposal was withdrawn.',
  proposal_superseded: 'A newer proposal replaced this one.',
  proposal_confirmed: 'This proposal is already confirmed.',
  same_request: 'This proposal cannot be confirmed by the request that created it.',
  proposal_stale: 'A decision this proposal rests on changed since it was made; it needs a new proposal.',
  delegation_needs_basis: 'Your reply hands the choice to the assistant. A delegation is recorded in the chat, not in this panel.',
  not_a_delegation: 'The engine did not read this reply as a delegation.',
  restatement_not_default: 'The proposal does not state that it is the assistant\'s recommended default.',
  delegation_not_given_at_this_pause: 'This decision needs your own words or a delegation given at this pause, in the chat.',
  // v0.3 (WP-B): the opening of the final test is never delegated.
  delegation_not_allowed: 'This decision is never delegated: it is recorded only in your own words, in the chat.',
  // ADR 0005 (guided confirmation).
  question_reply: 'Your reply asks a question, so it was not taken as a confirmation. Ask it in the chat first.',
  conditional_reply: 'Your reply sets a condition, keeps a reservation, or accepts only part of the proposal, so it was not taken as a confirmation. Settle it in the chat first.',
  // CLI-CONTRACT-COMPANION §13 (WP-0): a reserved command of an engine that predates it.
  not_implemented: 'The study engine in this environment does not have this command yet.',
};

const BY_CODE = {
  stale_revision: 'The study changed after the panel showed it. The panel has been refreshed: read the proposal again before answering.',
  decision_on_hold: 'This decision is on hold in your own words. Resolve the hold in the chat before confirming.',
  precondition_missing: 'An earlier step must be confirmed first.',
  dataset_changed: 'The case or dataset files changed since the study was created. Start a new study.',
  invalid_value: 'The proposed value is not valid for this decision.',
  study_busy: 'Another command is writing to the study. Try again in a moment.',
  idempotency_conflict: 'This request id was already used for another request.',
  unknown_proposal: 'This proposal does not exist.',
  proposal_not_open: 'This proposal is not open any more.',
  read_only: 'This process is read-only (HYPOTRAIL_READ_ONLY=1).',
  study_missing: 'The study state is missing.',
  integrity_error: 'The study state does not match its digest. Do not edit `.hypotrail/` by hand.',
  invalid_arguments: 'The CLI refused the arguments of this request.',
  internal_error: 'The CLI failed unexpectedly.',
  unsupported_capability: 'The study engine does not support this request.',
  export_target_exists: 'The chosen folder already holds files, so the engine wrote nothing there. Choose an empty folder or a new one.',
  unknown_result: 'The study has no result with this id.',
  unknown_decision: 'The engine does not know this decision.',
  literal_number_in_text: 'The engine found a number in the proposal text that it cannot trace to a current result.',
  causal_or_forecast_wording: 'The engine found causal or forecast wording in the proposal text.',
  misattributed_delegation: 'The engine found a recommended default credited to the analyst in the proposal text.',
  interrupted_execution_pending: 'An execution has an unknown outcome, so the engine runs nothing until it is acknowledged in your words (Overview, Health).',
  execution_in_progress: 'The same computation is already running.',
  unknown_execution: 'The engine does not list this execution as interrupted any more.',
  invalid_request: 'The engine refused the form of this request.',
  invalid_command: 'The engine does not accept this request.',
  // ADR 0005; v0.3 (WP-B, R27): only the training mode needs a reason for a trade-off.
  reason_required: 'In the training mode this decision is a trade-off, so the engine records it only with your reason, in your own words.',
  // ADR 0005, v0.2b (WP-B2): the training mode.
  paraphrase_required: 'In the training mode, a confirmation says in your own words what the proposal decides, not only that you agree. The lines below name what your reply does not say yet.',
  // WP-A9 (H3): also a stop in the guided mode until the point is raised in the chat.
  words_contradict_value: 'Your words and the proposal disagree about a variable, so the engine stopped the confirmation. Settle which one you mean in the chat.',
  // v0.2b (WP-B1, WP-B5): the final test is opened once.
  final_test_already_opened: 'The final test was already opened. It is opened only once: a later change is shown as made after it and is never measured on it again.',
};

// Explanations that depend on the write that was refused (the payload's `command`). A
// `run` refusal about an execution (ambiguous words, unknown execution) is an
// acknowledgement (W6); any other `run` refusal is an EDA request (W4).
const BY_CONTEXT = {
  run: {
    stale_revision: 'The study changed after the panel showed it. The panel has been refreshed: look at the list again before asking for a chart.',
    precondition_missing: 'An earlier step of the plan must be done before this chart can be computed.',
    invalid_value: 'The engine does not accept this column for this chart.',
  },
  acknowledge: {
    stale_revision: 'The study changed after the panel showed it. The panel has been refreshed: read the execution again before acknowledging it.',
    missing_user_words: 'Your acknowledgement was empty.',
    bare_acknowledgement: 'Your reply only acknowledged the interruption; it did not say, in your words, what you know about it.',
    negative_reply: 'Your reply reads as a refusal or a hesitation, so it was not taken as an acknowledgement.',
    unrelated_reply: 'Your reply shares no word with the interrupted execution, so it cannot be read as an acknowledgement of it.',
  },
  export: {
    read_only: 'This process is read-only (HYPOTRAIL_READ_ONLY=1), so the engine exported nothing.',
  },
};

// An engine older than `export --expected-revision` (CR.6) refuses the option itself
// (`invalid_arguments` whose message names it). The panel never exports without it.
const OLDER_ENGINE_EXPORT = 'The study engine in this environment is older than this panel: it does not know the ' +
  'revision check of an export (--expected-revision), so it exported nothing. Update the hypotrail engine of this ' +
  'environment, then export again.';

// v0.3 (WP-K, R21): the same explanations in French ("vous", owner decision 2026-10-21).
// `describe` returns both; the panel shows the one of its language. The engine's own
// message stays verbatim, in the engine's language.
const NOTHING_FR = "Rien n'a été enregistré.";

const BY_REASON_FR = {
  missing_user_words: 'Votre réponse était vide.',
  bare_acknowledgement: 'Votre réponse prenait seulement acte de la proposition ; elle ne disait pas, avec vos mots, ce que vous décidez.',
  negative_reply: "Votre réponse se lit comme un refus, une hésitation ou une réserve, elle n'a donc pas été prise pour une confirmation. Si vous n'êtes pas d'accord, dites-le dans le chat ou retirez la proposition.",
  unrelated_reply: "Votre réponse ne se lit pas comme une réponse à cette proposition : elle ne l'approuve pas tout en en parlant.",
  proposal_not_found: "Cette proposition n'existe plus.",
  proposal_withdrawn: 'Cette proposition a été retirée.',
  proposal_superseded: 'Une proposition plus récente a remplacé celle-ci.',
  proposal_confirmed: 'Cette proposition est déjà confirmée.',
  same_request: "Cette proposition ne peut pas être confirmée par la requête qui l'a créée.",
  proposal_stale: 'Une décision sur laquelle repose cette proposition a changé depuis : il faut une nouvelle proposition.',
  delegation_needs_basis: "Votre réponse confie le choix à l'assistant. Une délégation s'enregistre dans le chat, pas dans ce panneau.",
  not_a_delegation: "Le moteur n'a pas lu cette réponse comme une délégation.",
  restatement_not_default: "La proposition ne dit pas qu'elle est le défaut recommandé par l'assistant.",
  delegation_not_given_at_this_pause: 'Cette décision demande vos propres mots ou une délégation donnée à cette pause, dans le chat.',
  delegation_not_allowed: "Cette décision n'est jamais déléguée : elle s'enregistre seulement avec vos propres mots, dans le chat.",
  question_reply: "Votre réponse pose une question, elle n'a donc pas été prise pour une confirmation. Posez-la d'abord dans le chat.",
  conditional_reply: "Votre réponse pose une condition, garde une réserve ou n'accepte qu'une partie de la proposition, elle n'a donc pas été prise pour une confirmation. Réglez-le d'abord dans le chat.",
  not_implemented: "Le moteur d'étude de cet environnement n'a pas encore cette commande.",
};

const BY_CODE_FR = {
  stale_revision: "L'étude a changé après l'affichage du panneau. Le panneau a été actualisé : relisez la proposition avant de répondre.",
  decision_on_hold: 'Cette décision est en suspens, avec vos propres mots. Levez la suspension dans le chat avant de confirmer.',
  precondition_missing: "Une étape précédente doit d'abord être confirmée.",
  dataset_changed: "Les fichiers du cas ou des données ont changé depuis la création de l'étude. Commencez une nouvelle étude.",
  invalid_value: "La valeur proposée n'est pas valide pour cette décision.",
  study_busy: "Une autre commande écrit dans l'étude. Réessayez dans un instant.",
  idempotency_conflict: 'Cet identifiant de requête a déjà servi pour une autre requête.',
  unknown_proposal: "Cette proposition n'existe pas.",
  proposal_not_open: "Cette proposition n'est plus ouverte.",
  read_only: 'Ce processus est en lecture seule (HYPOTRAIL_READ_ONLY=1).',
  study_missing: "L'état de l'étude est manquant.",
  integrity_error: "L'état de l'étude ne correspond pas à son empreinte. Ne modifiez pas `.hypotrail/` à la main.",
  invalid_arguments: 'La CLI a refusé les arguments de cette requête.',
  internal_error: 'La CLI a échoué de façon inattendue.',
  unsupported_capability: "Le moteur d'étude ne prend pas en charge cette requête.",
  export_target_exists: "Le dossier choisi contient déjà des fichiers, le moteur n'y a donc rien écrit. Choisissez un dossier vide ou un nouveau dossier.",
  unknown_result: "L'étude n'a aucun résultat avec cet identifiant.",
  unknown_decision: 'Le moteur ne connaît pas cette décision.',
  literal_number_in_text: "Le moteur a trouvé dans le texte de la proposition un nombre qu'il ne peut relier à aucun résultat à jour.",
  causal_or_forecast_wording: 'Le moteur a trouvé dans le texte de la proposition une formulation causale ou de prévision.',
  misattributed_delegation: "Le moteur a trouvé dans le texte de la proposition un défaut recommandé attribué à l'analyste.",
  interrupted_execution_pending: "Une exécution a une issue inconnue : le moteur ne lance plus rien tant que vous n'en avez pas pris acte avec vos mots (Vue d'ensemble, Santé).",
  execution_in_progress: 'Le même calcul est déjà en cours.',
  unknown_execution: 'Le moteur ne liste plus cette exécution comme interrompue.',
  invalid_request: 'Le moteur a refusé la forme de cette requête.',
  invalid_command: "Le moteur n'accepte pas cette requête.",
  reason_required: "En mode entraînement, cette décision est un arbitrage : le moteur ne l'enregistre qu'avec votre raison, avec vos propres mots.",
  paraphrase_required: "En mode entraînement, une confirmation dit avec vos propres mots ce que la proposition décide, pas seulement que vous êtes d'accord. Les lignes ci-dessous nomment ce que votre réponse ne dit pas encore.",
  words_contradict_value: "Vos mots et la proposition ne s'accordent pas sur une variable, le moteur a donc arrêté la confirmation. Précisez dans le chat laquelle vous voulez dire.",
  final_test_already_opened: "Le test final a déjà été ouvert. Il ne s'ouvre qu'une fois : un changement ultérieur est montré comme fait après, et n'est plus jamais mesuré dessus.",
};

const BY_CONTEXT_FR = {
  run: {
    stale_revision: "L'étude a changé après l'affichage du panneau. Le panneau a été actualisé : regardez de nouveau la liste avant de demander un graphique.",
    precondition_missing: 'Une étape précédente du plan doit être faite avant que ce graphique puisse être calculé.',
    invalid_value: "Le moteur n'accepte pas cette colonne pour ce graphique.",
  },
  acknowledge: {
    stale_revision: "L'étude a changé après l'affichage du panneau. Le panneau a été actualisé : relisez l'exécution avant d'en prendre acte.",
    missing_user_words: "Votre prise d'acte était vide.",
    bare_acknowledgement: "Votre réponse prenait seulement acte de l'interruption ; elle ne disait pas, avec vos mots, ce que vous en savez.",
    negative_reply: "Votre réponse se lit comme un refus ou une hésitation, elle n'a donc pas été prise pour une prise d'acte.",
    unrelated_reply: "Votre réponse n'a aucun mot en commun avec l'exécution interrompue : elle ne peut pas se lire comme une prise d'acte.",
  },
  export: {
    read_only: "Ce processus est en lecture seule (HYPOTRAIL_READ_ONLY=1), le moteur n'a donc rien exporté.",
  },
};

const OLDER_ENGINE_EXPORT_FR = "Le moteur d'étude de cet environnement est plus ancien que ce panneau : il ne connaît pas " +
  "la vérification de révision d'un export (--expected-revision), il n'a donc rien exporté. Mettez à jour le moteur " +
  'hypotrail de cet environnement, puis exportez de nouveau.';
const REFUSED = 'The engine refused this request.';
const REFUSED_FR = 'Le moteur a refusé cette requête.';

/** True for an older engine's refusal of `export --expected-revision` (CR.6). */
function olderEngineExport(context, code, message) {
  return context === 'export' && code === 'invalid_arguments' && /--expected-revision/.test(message);
}

/** The refusal context of a payload: run, acknowledge, export, or null. */
function contextOf(payload, code, reason, details) {
  const command = typeof (payload && payload.command) === 'string' ? payload.command : '';
  if (command.startsWith('export')) return 'export';
  if (command === 'run') {
    const aboutExecution = code === 'ambiguous_confirmation' || code === 'unknown_execution' ||
      (typeof details.execution_id === 'string' && code !== 'execution_in_progress');
    return aboutExecution ? 'acknowledge' : 'run';
  }
  return null;
}

/** {code, reason, engineMessage, human, details} for a `hypotrail.error/1` payload. */
function describe(payload) {
  const error = (payload && payload.error) || {};
  const code = typeof error.code === 'string' ? error.code : 'unknown_error';
  const details = error.details && typeof error.details === 'object' ? error.details : {};
  const reason = typeof details.reason === 'string' ? details.reason : null;
  const where = contextOf(payload, code, reason, details);
  const older = olderEngineExport(where, code, String(error.message || ''));
  const explain = (byContext, byReason, byCode, olderText, refused) => {
    const context = byContext[where] || {};
    return older ? olderText
      : (reason && context[reason]) || context[code] || (reason && byReason[reason]) || byCode[code] || refused;
  };
  const human = explain(BY_CONTEXT, BY_REASON, BY_CODE, OLDER_ENGINE_EXPORT, REFUSED);
  const humanFr = explain(BY_CONTEXT_FR, BY_REASON_FR, BY_CODE_FR, OLDER_ENGINE_EXPORT_FR, REFUSED_FR);
  return {
    code, reason,
    engineMessage: typeof error.message === 'string' ? error.message : '',
    human: `${human} ${NOTHING}`,
    details: summariseDetails(code, details),
    // v0.3 (WP-K): the French panel's explanation and detail lines (the panel picks by language).
    humanFr: `${humanFr} ${NOTHING_FR}`,
    detailsFr: summariseDetails(code, details, 'fr'),
  };
}

const DETAIL_LINES = {
  en: {
    readByPanel: r => `Revision read by the panel: ${r}`,
    current: r => `Current revision: ${r}`,
    changedAt: (r, action, about) => `Changed at revision ${r}: ${action}${about ? ' (' + about + ')' : ''}`,
    onHold: (id, words) => `On hold (${id}): "${words}"`,
    missing: m => `Missing: ${m}`,
    folder: p => `Folder: ${p}`,
    notSaid: h => `Not said yet: ${h}`,
    disagree: v => `Your words and the proposal disagree about ${v}`,
    openedAt: r => `Opened at revision ${r}`,
    unknownOutcome: (id, activity) => `Unknown outcome: ${id}${activity ? ' (' + activity + ')' : ''}`,
  },
  fr: {
    readByPanel: r => `Révision lue par le panneau : ${r}`,
    current: r => `Révision actuelle : ${r}`,
    changedAt: (r, action, about) => `Modifié à la révision ${r} : ${action}${about ? ' (' + about + ')' : ''}`,
    onHold: (id, words) => `En suspens (${id}) : « ${words} »`,
    missing: m => `Manquant : ${m}`,
    folder: p => `Dossier : ${p}`,
    notSaid: h => `Pas encore dit : ${h}`,
    disagree: v => `Vos mots et la proposition ne s'accordent pas sur ${v}`,
    openedAt: r => `Ouvert à la révision ${r}`,
    unknownOutcome: (id, activity) => `Issue inconnue : ${id}${activity ? ' (' + activity + ')' : ''}`,
  },
};

/** A few safe, flat lines from the refusal details (the full payload stays in the CLI). */
function summariseDetails(code, details, lang = 'en') {
  const L = DETAIL_LINES[lang] || DETAIL_LINES.en;
  const lines = [];
  if (code === 'stale_revision') {
    if (Number.isInteger(details.expected_revision)) lines.push(L.readByPanel(details.expected_revision));
    if (Number.isInteger(details.current_revision)) lines.push(L.current(details.current_revision));
    for (const change of Array.isArray(details.changes_since) ? details.changes_since.slice(0, 10) : []) {
      const params = (change && change.params) || {};
      const about = params.decision_id || params.proposal_id || params.note_id || '';
      lines.push(L.changedAt(change && change.revision, change && change.action, about));
    }
  }
  if (code === 'decision_on_hold') {
    for (const note of Array.isArray(details.notes) ? details.notes : []) {
      lines.push(L.onHold(note && note.note_id, note && note.user_words));
    }
  }
  if (code === 'precondition_missing' && Array.isArray(details.missing)) {
    for (const m of details.missing.slice(0, 10)) {
      lines.push(L.missing(typeof m === 'string' ? m : (m && (m.text || m.decision || m.id || JSON.stringify(m)))));
    }
  }
  if (code === 'export_target_exists' && typeof details.path === 'string') lines.push(L.folder(details.path));
  if (code === 'paraphrase_required' && Array.isArray(details.missing)) {
    for (const m of details.missing.slice(0, 10)) {
      if (m && typeof m.hint === 'string') lines.push(L.notSaid(m.hint));
    }
  }
  if (code === 'words_contradict_value' && Array.isArray(details.warnings)) {
    for (const w of details.warnings.slice(0, 10)) {
      if (w && typeof w.variable === 'string') lines.push(L.disagree(w.variable));
    }
  }
  if (code === 'final_test_already_opened' && details.opening && typeof details.opening === 'object') {
    if (Number.isInteger(details.opening.revision)) lines.push(L.openedAt(details.opening.revision));
  }
  if (code === 'interrupted_execution_pending' && Array.isArray(details.interrupted)) {
    for (const e of details.interrupted.slice(0, 10)) {
      const id = typeof e === 'string' ? e : (e && e.execution_id);
      if (id) lines.push(L.unknownOutcome(id, e && e.activity));
    }
  }
  return lines.map(l => String(l));
}

module.exports = { describe, contextOf, BY_REASON, BY_CODE, BY_CONTEXT, NOTHING, OLDER_ENGINE_EXPORT,
  BY_REASON_FR, BY_CODE_FR, BY_CONTEXT_FR, NOTHING_FR, OLDER_ENGINE_EXPORT_FR };
