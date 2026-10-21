'use strict';
// Bridge handler (COMPANION-ADVANCED §6.8, stage v2): `ask_agent`. Owned by WP-U5.
//
// The webview sends only `{about: {kind, id}, question, mode}`. The text is built here
// with the fixed template of lib/bridge.js, from the last snapshot (and, for a result, an
// `evidence` read; for a term, the cached `explain` read), so it can never carry the
// junior's draft words, a restatement, or a study value. Nothing is sent to a chat or a
// model: the text goes to the clipboard, or, behind the hidden `chatInsert` setting, into
// the chat input without submitting (decision CA.8). Allowed in reviewer mode (§3.3).

const bridge = require('../bridge');
const NOTICE_KEYS = new Map([[bridge.COPIED, 'copied'], [bridge.INSERTED, 'inserted'], [bridge.FELL_BACK, 'fellBack'],
  [bridge.FAILED, 'copyFailed']]);
const { toExplainModel } = require('../models/explain');
const { expectSchema, list, str } = require('../models/common');

/** Results of `evidence`, identifiers and currency only (the bridge's own cache key). */
function toBridgeResults(payload) {
  const p = expectSchema(payload, 'hypotrail.evidence/1');
  return { revision: p.revision, results: list(p.results).map(r => ({ resultId: str(r && r.result_id),
    activity: str(r && r.activity), current: Boolean(r && r.current === true && r.integrity === 'ok') })) };
}

async function context(message, ctx) {
  const { kind } = message.about;
  if (kind === 'result') {
    const out = await ctx.read('bridge:evidence', ctx.cli.READS.evidence(ctx.agent), toBridgeResults);
    return out.ok ? { results: out.model.results } : {};
  }
  if (kind === 'term' && ctx.stageAtLeast('v3') && ctx.settings.learningLayer !== false) {
    const out = await ctx.read('explain', ctx.cli.READS.explain(ctx.agent), toExplainModel);
    return out.ok ? { terms: out.model.terms } : {};
  }
  return {};
}

async function askAgent(message, ctx) {
  const snapshot = ctx.snapshot();
  let extra = {};
  try { extra = await context(message, ctx); } catch (e) { ctx.log(e); extra = {}; }
  const text = bridge.template({ studyDir: ctx.agent.studyDir, revision: snapshot ? snapshot.revision : null,
    about: message.about, label: bridge.labelOf(message.about, snapshot, extra), question: message.question });
  const done = await bridge.deliver(text, { mode: message.mode, chatInsert: ctx.settings.chatInsert === true, host: ctx.host });
  // v0.3 (WP-K, R21): what happened, in the extension's language (lib/l10n.js).
  const key = NOTICE_KEYS.get(done.notice);
  ctx.post({ type: 'notice', politeness: done.channel ? 'polite' : 'assertive', text: key && ctx.say ? ctx.say(key) : done.notice });
  return done;
}

module.exports = { types: { ask_agent: askAgent }, loads: {}, toBridgeResults };
