'use strict';
// The extension's own words in English and French (v0.3, WP-K, R21; French register "vous",
// owner decision 2026-10-21): VS Code notifications, the quick pick and dialogs of the
// extension, and the notices the handlers post to the panel. The panel's copy lives in
// media/copy and media/copy-fr; the refusal explanations in lib/refusals.js (both languages,
// chosen by the panel). English is the source language.
//
// The language follows the setting `hypotrail.companion.language`: `en` or `fr`, else
// (`auto`) the open study's language, else, before any study is read, the language of VS
// Code's own display. The header toggle of the panel is view state the extension never sees
// (WP-E2 decision E2.9), so a notice follows the setting, not the toggle.
//
//   resolve(setting, studyLanguage, displayLanguage) -> 'en' | 'fr'
//   say(lang, key, ...args) -> the text (English when the key has no French)

const LANGUAGES = ['en', 'fr'];

function resolve(setting, studyLanguage = null, displayLanguage = null) {
  if (LANGUAGES.includes(setting)) return setting;
  if (LANGUAGES.includes(studyLanguage)) return studyLanguage;
  return typeof displayLanguage === 'string' && /^fr\b/i.test(displayLanguage) ? 'fr' : 'en';
}

const EN = {
  // extension.js
  disabled: 'Companion disabled (feature flag)',
  trust: 'The Hypotrail companion runs the study CLI, so it needs a trusted workspace.',
  notInStage: 'This is not available in the current stage of the companion (hypotrail.companion.stage).',
  invalidLink: 'This Hypotrail link is not valid.',
  cannotOpen: message => `Cannot open the study: ${message}`,
  failed: message => `Hypotrail companion: ${message}`,
  pickFolder: 'Pick another folder...',
  chooseTitle: 'Hypotrail: choose a study',
  choosePlaceholder: 'A folder holding .hypotrail/agent.json',
  openLabel: 'Open this study',
  openTitle: 'Hypotrail: pick a study folder (it holds .hypotrail/agent.json)',
  exportHere: 'Export here',
  goTitle: 'Hypotrail: go to a result',
  goPrompt: 'The result id, or its first 8 or more characters, as the report shows it.',
  panelTitle: 'Hypotrail study',
  panelTitleReviewer: 'Hypotrail study (reviewer)',
  // handlers/evidence.js (go to a result)
  resultsUnreadable: message => `The results of this study could not be read: ${message}`,
  severalResults: prefix => `Several results start with ${prefix}. Paste more characters of the id.`,
  noResult: (prefix, truncated) => `No result of this study starts with ${prefix}.${truncated ? ' Older results are not listed; paste the whole id.' : ''}`,
  // handlers/overview.js
  artifactMissing: rel => `${rel} does not exist yet.`,
  artifactTop: rel => `${rel} does not name this result; it opens at the top.`,
  reviewerWorkbench: 'Read-only reviewer mode: the workbench is not opened for editing. Nothing was started.',
  notebookMissing: rel => `${rel} does not exist yet. Nothing was started.`,
  noMarimoCommand: rel => `The panel cannot build the Marimo command for ${rel} from this study's engine. Open the file, or ask the agent for the command. Nothing was started.`,
  noTerminal: 'This host cannot open a terminal. Nothing was started.',
  terminalReused: (terminal, rel) => `The terminal "${terminal}" already runs ${rel}; it is shown again.`,
  terminalStarted: (mode, rel, terminal) => `Started "marimo ${mode}" for ${rel} in the terminal "${terminal}". Stop it with Ctrl+C in that terminal.`,
  // handlers/eda.js (W4, a chart of the engine's catalog)
  edaUnread: 'The list of charts could not be read, so nothing was run.',
  edaMoved: 'The study changed since this list of charts was shown. Read it again; nothing was run.',
  edaNotInCatalog: 'This chart is not in the engine\'s EDA catalog for this study. Nothing was run.',
  edaNotRunnable: 'The engine cannot run this chart yet. Nothing was run.',
  // handlers/whatif.js
  previewNotAsked: message => `The preview could not be asked: ${message}.`,
  previewFailed: message => `The preview could not be computed: ${message}`,
  notDraftable: value => `${value} is not a value the panel can draft. Nothing was recorded.`,
  draftUnreadable: message => `The draft could not be read: ${message}`,
  // handlers/learn.js
  exportCancelled: 'No folder was chosen. Nothing was exported.',
  exportStale: 'The study changed since the panel showed it. Read the panel again, then export. Nothing was exported.',
  notLastExport: 'That folder is not the last export of this panel. Nothing was opened.',
  learningOff: 'The learning layer is off (hypotrail.companion.learningLayer). Nothing was stored.',
  learningUnknown: 'The learning layer does not know that item. Nothing was stored.',
  // bridge.js (what happened to the copied question)
  copied: 'Copied. Paste it into the chat with your assistant.',
  inserted: 'Inserted into the chat input, not sent. Read it, then send it yourself.',
  fellBack: 'The chat input could not be opened, so the question was copied instead. Paste it into the chat with your assistant.',
  copyFailed: 'The question could not be copied. Nothing was sent.',
  // controller.js (outcome lines)
  unknownOutcome: 'The outcome is unknown: the refreshed panel shows whether anything was recorded.',
  reviewerRefusal: 'Read-only reviewer mode.',
  busyRefusal: 'Another request is in progress.',
  notPromoted: 'The result was computed but not used: the study changed while it ran. Nothing in the study changed.',
  notAvailable: 'Not available in this stage.',
  replayed: '(replayed, no effect)',
  executionUnknown: 'An execution has an unknown outcome.',
};

const FR = {
  disabled: 'Compagnon désactivé (option de fonctionnalité)',
  trust: "Le compagnon Hypotrail exécute la CLI de l'étude : il lui faut un espace de travail approuvé.",
  notInStage: "Ce n'est pas disponible à l'étape actuelle du compagnon (hypotrail.companion.stage).",
  invalidLink: "Ce lien Hypotrail n'est pas valide.",
  cannotOpen: message => `Impossible d'ouvrir l'étude : ${message}`,
  failed: message => `Compagnon Hypotrail : ${message}`,
  pickFolder: 'Choisir un autre dossier...',
  chooseTitle: 'Hypotrail : choisir une étude',
  choosePlaceholder: 'Un dossier qui contient .hypotrail/agent.json',
  openLabel: 'Ouvrir cette étude',
  openTitle: "Hypotrail : choisir le dossier d'une étude (il contient .hypotrail/agent.json)",
  exportHere: 'Exporter ici',
  goTitle: 'Hypotrail : aller à un résultat',
  goPrompt: "L'identifiant du résultat, ou ses 8 premiers caractères ou plus, tel que le rapport l'affiche.",
  panelTitle: 'Étude Hypotrail',
  panelTitleReviewer: 'Étude Hypotrail (relecture)',
  resultsUnreadable: message => `Les résultats de cette étude n'ont pas pu être lus : ${message}`,
  severalResults: prefix => `Plusieurs résultats commencent par ${prefix}. Collez plus de caractères de l'identifiant.`,
  noResult: (prefix, truncated) => `Aucun résultat de cette étude ne commence par ${prefix}.${truncated ? " Les résultats plus anciens ne sont pas listés : collez l'identifiant entier." : ''}`,
  artifactMissing: rel => `${rel} n'existe pas encore.`,
  artifactTop: rel => `${rel} ne nomme pas ce résultat ; il s'ouvre au début.`,
  reviewerWorkbench: "Mode relecture, en lecture seule : l'atelier ne s'ouvre pas en édition. Rien n'a été lancé.",
  notebookMissing: rel => `${rel} n'existe pas encore. Rien n'a été lancé.`,
  noMarimoCommand: rel => `Le panneau ne peut pas construire la commande Marimo pour ${rel} à partir du moteur de cette étude. Ouvrez le fichier, ou demandez la commande à l'agent. Rien n'a été lancé.`,
  noTerminal: "Cet hôte ne peut pas ouvrir de terminal. Rien n'a été lancé.",
  terminalReused: (terminal, rel) => `Le terminal « ${terminal} » exécute déjà ${rel} ; il est affiché de nouveau.`,
  terminalStarted: (mode, rel, terminal) => `« marimo ${mode} » a été lancé pour ${rel} dans le terminal « ${terminal} ». Arrêtez-le avec Ctrl+C dans ce terminal.`,
  edaUnread: "La liste des graphiques n'a pas pu être lue : rien n'a été lancé.",
  edaMoved: "L'étude a changé depuis l'affichage de cette liste de graphiques. Relisez-la ; rien n'a été lancé.",
  edaNotInCatalog: "Ce graphique n'est pas dans le catalogue d'EDA du moteur pour cette étude. Rien n'a été lancé.",
  edaNotRunnable: "Le moteur ne peut pas encore lancer ce graphique. Rien n'a été lancé.",
  previewNotAsked: message => `L'aperçu n'a pas pu être demandé : ${message}.`,
  previewFailed: message => `L'aperçu n'a pas pu être calculé : ${message}`,
  notDraftable: value => `${value} n'est pas une valeur que le panneau peut préparer. Rien n'a été enregistré.`,
  draftUnreadable: message => `Le brouillon n'a pas pu être lu : ${message}`,
  exportCancelled: "Aucun dossier n'a été choisi. Rien n'a été exporté.",
  exportStale: "L'étude a changé depuis l'affichage du panneau. Relisez le panneau, puis exportez. Rien n'a été exporté.",
  notLastExport: "Ce dossier n'est pas le dernier export de ce panneau. Rien n'a été ouvert.",
  learningOff: "La couche d'apprentissage est désactivée (hypotrail.companion.learningLayer). Rien n'a été enregistré.",
  learningUnknown: "La couche d'apprentissage ne connaît pas cet élément. Rien n'a été enregistré.",
  copied: "Copié. Collez-le dans le chat avec votre assistant.",
  inserted: "Inséré dans la saisie du chat, pas envoyé. Relisez-le, puis envoyez-le vous-même.",
  fellBack: "La saisie du chat n'a pas pu s'ouvrir, la question a donc été copiée. Collez-la dans le chat avec votre assistant.",
  copyFailed: "La question n'a pas pu être copiée. Rien n'a été envoyé.",
  unknownOutcome: "L'issue est inconnue : le panneau actualisé montre si quelque chose a été enregistré.",
  reviewerRefusal: 'Mode relecture, en lecture seule.',
  busyRefusal: 'Une autre requête est en cours.',
  notPromoted: "Le résultat a été calculé mais pas retenu : l'étude a changé pendant le calcul. Rien n'a changé dans l'étude.",
  notAvailable: "Pas disponible à cette étape.",
  replayed: '(rejouée, sans effet)',
  executionUnknown: 'Une exécution a une issue inconnue.',
};

const TABLES = { en: EN, fr: FR };

function say(lang, key, ...args) {
  const table = TABLES[lang] || EN;
  const entry = Object.prototype.hasOwnProperty.call(table, key) ? table[key] : EN[key];
  if (entry === undefined) throw new Error(`no text for ${key}`);
  return typeof entry === 'function' ? entry(...args) : entry;
}

module.exports = { resolve, say, LANGUAGES, EN, FR };
