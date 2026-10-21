'use strict';
// Learn handler (COMPANION-ADVANCED §6.6, §10; stage v3). Owned by WP-U5.
//
//   loads:  explain (the learning layer's text), session_report (the observed-session report)
//   types:  learn_set (seen cards, predictions, prefs: globalState only, lib/localstore.js),
//           export_handoff (W7), navigate_external (reveal the last export folder)
//   onReady: learn_state for this study
//
// A prediction answer goes to globalState and nowhere else: learn_set never reads or
// writes the study, never calls ctx.write, and never runs the CLI except the cached
// `explain` read that validates the ids against the engine's own lists (LE-1).

const path = require('path');
const { toExplainModel } = require('../models/explain');
const { toSessionReportModel } = require('../models/session_report');
const { createStore } = require('../localstore');

const WARNINGS = {
  report_not_current: 'the report was not current, so it is not in the pack',
  open_proposals: 'some proposals are still open',
  open_holds: 'some decisions are on hold',
  interrupted_executions: 'an execution was interrupted or has an unknown outcome',
  sources_changed: 'the sources changed since some results were computed',
  unconfirmed_decisions: 'some decisions are not confirmed',
};

// Per panel session (one controller context): cards already counted, the last export folder.
const sessions = new WeakMap();
function session(ctx) {
  if (!sessions.has(ctx)) sessions.set(ctx, { seen: new Set(), lastExport: null });
  return sessions.get(ctx);
}

const storeOf = ctx => createStore(ctx.host && ctx.host.globalState ? ctx.host.globalState : null, ctx.agent.studyDir);
const layerOn = ctx => ctx.stageAtLeast('v3') && ctx.settings.learningLayer !== false;

function postState(ctx, state) {
  ctx.post({ type: 'learn_state', prefs: state.prefs, seen: state.seen, predictions: state.predictions });
}

/** The export warnings (CLI-CONTRACT-COMPANION §7) in words: `recorded.warnings` of W7. */
function warningWords(codes) {
  return (codes || []).map(c => WARNINGS[c] || String(c).replace(/_/g, ' '));
}

/** The sentence the Learn view shows for those words ('' when there are none). */
function warningsText(codes) {
  const words = warningWords(codes);
  return words.length ? `The pack is incomplete: ${words.join('; ')}.` : '';
}

async function learnSet(message, ctx) {
  if (!layerOn(ctx)) {
    ctx.post({ type: 'notice', politeness: 'polite', text: ctx.say('learningOff') });
    return;
  }
  const store = storeOf(ctx);
  if (message.key === 'reset_predictions') {
    postState(ctx, await store.resetPredictions());
    return;
  }
  if (message.key === 'prefs') {
    postState(ctx, await store.setPrefs(message.value));
    return;
  }
  // `seen` and `prediction` name an item of the engine's own lists, never free text.
  const explain = await ctx.read('explain', ctx.cli.READS.explain(ctx.agent), toExplainModel);
  const model = explain.ok ? explain.model : null;
  if (message.key === 'seen') {
    const [scope, id] = message.id.split(':');
    const known = model && (scope === 'term' ? Boolean(model.terms[id]) : scope === model.task && Boolean(model.steps[id]));
    if (!known) return ctx.post({ type: 'notice', politeness: 'polite', text: ctx.say('learningUnknown') });
    const mine = session(ctx);
    if (!mine.seen.has(message.id)) {
      mine.seen.add(message.id);
      postState(ctx, await store.markSeen(message.id));
    } else {
      postState(ctx, store.state());
    }
    return;
  }
  const question = model && model.predictions.find(q => q.id === message.id);
  if (!question || !question.choices.some(c => c.id === message.value)) {
    ctx.post({ type: 'notice', politeness: 'polite', text: ctx.say('learningUnknown') });
    return;
  }
  postState(ctx, await store.setPrediction(message.id, message.value));
}

/**
 * W7. The outcome's `out` and "Open folder" are the folder the engine answered, never one
 * the panel computed (review finding; the engine's `out`).
 */
async function exportHandoff(message, ctx) {
  const snapshot = ctx.snapshot();
  if (!snapshot || snapshot.revision !== message.revision) return ctx.invalid('W7', ctx.say('exportStale'), 'handoff');
  const fallback = path.join(ctx.agent.studyDir, 'handoff');
  const parent = ctx.host && typeof ctx.host.pickFolder === 'function' ? await ctx.host.pickFolder(fallback) : null;
  if (!parent) {
    ctx.post({ type: 'outcome', op: 'W7', kind: 'cancelled', target: 'handoff', message: ctx.say('exportCancelled') });
    return null;
  }
  const outcome = await ctx.write('W7', {
    target: 'handoff',
    // Always with `--expected-revision` (CR.6): an engine that does not know the option
    // refuses the export, and lib/refusals.js says that the engine is older (no retry).
    argv: () => ctx.cli.WRITES.W7(ctx.agent, { parent, revision: message.revision }),
    record: payload => {
      const codes = Array.isArray(payload.warnings) ? payload.warnings.filter(w => typeof w === 'string') : [];
      const files = (Array.isArray(payload.files) ? payload.files : [])
        .filter(f => f && typeof f.path === 'string' && Number.isInteger(f.bytes) && f.bytes >= 0)
        .map(f => ({ path: f.path, bytes: f.bytes }));
      // The warnings travel in the outcome (WP-I, U5 request R3), shown with the files.
      return { files, out: typeof payload.out === 'string' ? payload.out : null, warnings: warningWords(codes) };
    },
  });
  if (outcome && (outcome.kind === 'ok' || outcome.kind === 'ok_with_problems') && outcome.recorded && outcome.recorded.out) {
    session(ctx).lastExport = outcome.recorded.out;
  }
  return outcome;
}

async function navigateExternal(message, ctx) {
  const last = session(ctx).lastExport;
  if (message.kind !== 'reveal_export' || !last || message.path !== last) {
    ctx.post({ type: 'notice', politeness: 'assertive', text: ctx.say('notLastExport') });
    return;
  }
  await ctx.host.revealInOS(last);
}

async function onReady(ctx) {
  if (!layerOn(ctx)) return;
  postState(ctx, storeOf(ctx).state());
}

module.exports = {
  types: { learn_set: learnSet, export_handoff: exportHandoff, navigate_external: navigateExternal },
  loads: {
    // The learning layer off: the controller refuses the load and `explain` is never read (LE-3).
    explain: { stage: 'v3', when: settings => settings.learningLayer !== false, key: () => 'explain',
      argv: (cli, agent) => cli.READS.explain(agent), model: toExplainModel },
    session_report: { stage: 'v3', key: () => 'session_report', argv: (cli, agent) => cli.READS.session_report(agent),
      model: toSessionReportModel },
  },
  onReady,
  warningsText,
  warningWords,
  WARNINGS,
};
