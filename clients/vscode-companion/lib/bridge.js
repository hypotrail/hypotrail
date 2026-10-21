'use strict';
// Agent bridge (COMPANION-ADVANCED §6.8): "Ask the agent about this". The panel prepares a
// question for the junior's chat and puts it on the clipboard. It never sends anything:
// there is no language-model call, no chat submission, and no option that submits.
//
// - The text is a fixed English template. It cites the object by kind and identifier
//   (a result id prefix, a decision id, a proposal id, a step id, ...) and an engine label
//   of identifiers and statuses only. It never includes the junior's draft confirmation
//   words, a restatement, a rationale, or a study value: the webview sends only
//   {kind, id} and the typed question, and the label is built here from the snapshot.
// - Copy uses the clipboard only. "Insert into the chat" exists only when the hidden
//   setting `chatInsert` is true (decision CA.8: not contributed, default false); then it
//   runs `workbench.action.chat.open` with `isPartialQuery: true`, and falls back to the
//   clipboard, saying so, when the command throws or is missing (AB-2).
//
// Owned by WP-U5. Pure apart from the `host` functions it is given.

const path = require('path');

const INSERT_COMMAND = 'workbench.action.chat.open';
const DEFAULT_QUESTION = 'Can you explain this and what it means for my study?';
const CLOSING = 'This is a question, not a confirmation of anything.';
const COPIED = 'Copied. Paste it into the chat with your assistant.';
const INSERTED = 'Inserted into the chat input, not sent. Read it, then send it yourself.';
const FELL_BACK = 'The chat input could not be opened, so the question was copied instead. Paste it into the chat with your assistant.';
const FAILED = 'The question could not be copied. Nothing was sent.';
const MAX_QUESTION = 2000;
const RESULT_ID = /^[0-9a-f]{8,64}$/;

const isPlain = x => Boolean(x) && typeof x === 'object' && !Array.isArray(x);
const oneLine = text => String(text).replace(/\s+/g, ' ').trim();

/** The engine label of a cited object: identifiers and statuses only, never a value. */
function labelOf(about, snapshot, { results = null, terms = null } = {}) {
  const snap = isPlain(snapshot) ? snapshot : {};
  const plan = Array.isArray(snap.plan) ? snap.plan : [];
  const proposals = Array.isArray(snap.proposals) ? snap.proposals : [];
  const decisions = isPlain(snap.decisions) ? snap.decisions : {};
  switch (about.kind) {
    case 'proposal': {
      const p = proposals.find(x => x.proposalId === about.id);
      return p ? `decision ${p.decisionId}, open` : 'not open in the panel';
    }
    case 'decision': {
      const open = proposals.filter(x => x.decisionId === about.id).map(x => `proposal ${x.proposalId}, open`);
      if (open.length) return open.join('; ');
      const d = decisions[about.id];
      return d && d.status ? d.status.replace(/_/g, ' ') : '';
    }
    case 'step': {
      const s = plan.find(x => x.id === about.id);
      return s ? `${oneLine(s.title)}, ${String(s.status).replace(/_/g, ' ')}` : '';
    }
    case 'limit': {
      const nyd = isPlain(snap.notYetDefensible) ? snap.notYetDefensible : {};
      const known = (Array.isArray(nyd.top) ? nyd.top : []).some(x => x.id === about.id);
      return known ? 'not yet defensible' : '';
    }
    case 'execution': {
      const ex = isPlain(snap.executions) ? snap.executions : {};
      for (const [group, label] of [['interrupted', 'interrupted'], ['suspected', 'outcome unknown'], ['late', 'late'],
        ['active', 'running']]) {
        if ((Array.isArray(ex[group]) ? ex[group] : []).some(e => e && e.executionId === about.id)) return label;
      }
      return '';
    }
    case 'result': {
      const r = Array.isArray(results) ? results.find(x => x && typeof x.resultId === 'string' && x.resultId.startsWith(about.id)) : null;
      return r ? [r.activity, r.current ? 'current' : 'not current'].filter(Boolean).join(', ') : '';
    }
    case 'term': {
      const t = isPlain(terms) ? terms[about.id] : null;
      return t && t.term ? `glossary: ${oneLine(t.term)}` : 'glossary';
    }
    default:
      return '';
  }
}

/** The identifier as the template shows it: the first 8 characters of a result id. */
function shownId(about) {
  return about.kind === 'result' && RESULT_ID.test(about.id) ? about.id.slice(0, 8) : about.id;
}

/**
 * The prepared text (§6.8), one fixed template:
 *   Question about my Hypotrail study (<study folder name>), revision <N>.
 *   About: <kind> <id> (<label>).
 *   My question: <typed question, or the default question>
 *   This is a question, not a confirmation of anything.
 */
function template({ studyDir, revision, about, label = '', question = '' }) {
  if (!isPlain(about) || typeof about.kind !== 'string' || typeof about.id !== 'string') throw new Error('about {kind, id}');
  const folder = path.basename(String(studyDir || '')) || 'study';
  const typed = typeof question === 'string' ? question.slice(0, MAX_QUESTION).trim() : '';
  const tag = oneLine(label);
  return [
    `Question about my Hypotrail study (${oneLine(folder)}), revision ${Number.isInteger(revision) ? revision : '?'}.`,
    `About: ${about.kind} ${oneLine(shownId(about))}${tag ? ` (${tag})` : ''}.`,
    `My question: ${typed || DEFAULT_QUESTION}`,
    CLOSING,
  ].join('\n');
}

/**
 * Deliver the text. `mode` is `copy` or `insert`; `insert` is honoured only when
 * `chatInsert` is true. Resolves {channel: 'clipboard' | 'chat' | null, notice}.
 * The only commands this ever runs are the clipboard write and, behind `chatInsert`, the
 * chat open with `isPartialQuery: true`; no option that submits is ever passed.
 */
async function deliver(text, { mode, chatInsert = false, host = {} }) {
  const copy = async notice => {
    try {
      if (typeof host.writeClipboard !== 'function') throw new Error('no clipboard');
      await host.writeClipboard(text);
      return { channel: 'clipboard', notice };
    } catch (_) {
      return { channel: null, notice: FAILED };
    }
  };
  if (mode === 'insert' && chatInsert === true) {
    try {
      if (typeof host.executeCommand !== 'function') throw new Error('no command host');
      await host.executeCommand(INSERT_COMMAND, { query: text, isPartialQuery: true });
      return { channel: 'chat', notice: INSERTED };
    } catch (_) {
      return copy(FELL_BACK);
    }
  }
  return copy(COPIED);
}

module.exports = { labelOf, template, deliver, shownId, INSERT_COMMAND, DEFAULT_QUESTION, CLOSING, COPIED, INSERTED,
  FELL_BACK, FAILED, MAX_QUESTION };
