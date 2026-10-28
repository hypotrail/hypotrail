// Glossary terms of the panel's own copy, their hovers, and the agent-bridge modal
// (COMPANION-ADVANCED §6.6.1, §6.7, §6.8). Owned by WP-U5. Loaded after media/copy/*.js and
// before media/views/*.js (lib/html.js), so every view can use:
//
//   Hypotrail.terms.MAP                      {glossary id: [places where the copy marks it]}
//   Hypotrail.terms.mark(text, id)           a notion button for a word of the copy (v3), else text
//   Hypotrail.terms.place(root)              after a render: the open notions, in place
//   Hypotrail.askAgent(ctx, about, shown, {question?})   the "Ask the agent about this" modal
//   Hypotrail.askButton(ctx, about, shown, {label?, attrs?, question?, stage?, direct?})
//                                            its button (stage v2 unless `stage` says
//                                            otherwise, kept in reviewer mode); the one
//                                            helper of every tab (WP-I, §6.8). `direct`
//                                            (WP-E1) copies the ready question at once,
//                                            without the modal.
//
// Notions in place (ADR 0004 d13, NOT-1, NOT-2). With the learning layer on (stage v3,
// `learningLayer`), a term the copy marks is a button: pressing it (Enter, Space, a touch)
// expands, right after its block, the term first, its definition, then "In your study" with
// the study's cited example when the engine says it is `shown`; pressing it again, or Escape
// on it, folds it. Its open state is a fold of the page (`term-<id>`, FOLD-1). The first
// expansion reads `explain` once; with the layer off nothing is marked and `explain` is never
// read (LE-3). The Learn view feeds this module the `init` and `explain` messages it receives.
(function (HT) {
  'use strict';

  // Every id is a glossary id of at least one task, and is marked in the views
  // (test/learn.test.js; WP-I added the evidence and decisions marks, U5 request R4).
  const MAP = Object.freeze({
    final_test: ['now data card'],
    development_rows: ['now data card'],
    proposal: ['page proposal card'],
    base_rate: ['eda target card'],
    class_imbalance: ['eda target card'],
    distribution: ['eda distribution card'],
    target_distribution: ['eda target card'],
    exposure: ['evidence ledger'],
    stale_result: ['page waiting card'],
    validation_partition: ['evidence ledger'],
    selection_on_validation: ['evidence ledger'],
    paired_difference: ['evidence intervals'],
    confidence_interval: ['evidence intervals'],
    mae: ['evidence intervals'],
    rmse: ['evidence intervals'],
    extrapolation: ['what if residual explorer'],
  });

  const state = { layer: false, stage: 'v0', explain: null, requested: false };

  const active = () => state.layer && Boolean(HT.protocol) && HT.protocol.stageAllows(state.stage, 'v3');
  const foldId = id => `term-${id}`;

  /**
   * A term of the panel's copy (NOT-1): from stage v3 with the learning layer on, a button
   * (`aria-expanded`, a stable `data-fold-id`) that expands, in place, the term's definition
   * then "In your study" with the study's values (`explain`); below v3, or with the layer off,
   * plain text (LE-3). A term the engine's glossary does not hold (the task filter) is plain text.
   */
  function mark(text, id) {
    const t = state.explain ? state.explain.terms[id] : undefined;
    if (!active() || (state.explain && !t)) return HT.el('span', { 'data-term-text': id, text });
    const open = HT.foldOpen ? HT.foldOpen(foldId(id), false) : false;
    return HT.el('button', { type: 'button', className: 'ht-term', 'data-term': id, 'data-fold-id': foldId(id),
      'aria-expanded': open ? 'true' : 'false', text,
      onclick: () => toggle(id),
      onkeydown: e => { if (e.key === 'Escape' && HT.foldOpen(foldId(id), false)) { e.preventDefault(); e.stopPropagation(); toggle(id); } } });
  }

  function toggle(id) {
    const open = HT.foldOpen(foldId(id), false);
    HT.setFold(foldId(id), !open);
    // The learning parts read `explain` once per version (their loader); the notion asks them.
    if (!open && !state.explain && HT.terms.load && HT.terms.load()) {
      state.requested = true;
    } else if (!open && !state.explain && !state.requested) {
      state.requested = true;
      HT.send({ type: 'load', view: 'explain' });
    }
    HT.rerender();
  }

  /** The expanded notion of a term (LS-5): the term first, its definition, then the study's example. */
  function note(id, n) {
    const L = HT.copy.learn;
    const P = HT.copy.page;
    const t = state.explain ? state.explain.terms[id] : null;
    const node = HT.el('span', { className: 'ht-tdef', role: 'note', id: `note-${id}-${n}`, 'data-notion': id }, t ? [
      // L3: the glossary is the engine's, in the study language; marked when it is not the panel's.
      HT.el('dfn', { text: t.term }), ': ', HT.components.engineText(t.definition, { lang: HT.studyLanguage ? HT.studyLanguage() : null }),
      t.example ? HT.components.segments(HT.el('span', { className: 'ht-here', 'data-here': true }, [HT.el('br'), HT.el('b', { text: P.inYourStudy })]), t.example)
        : t.exampleStatus === 'needs_results' ? HT.el('span', { className: 'muted' }, [HT.el('br'), L.exampleNeeded]) : null,
    ] : [HT.el('span', { className: 'muted', 'aria-busy': 'true', text: P.notionsReading })]);
    return node;
  }

  /** After a render: each open term's notion goes right after the block that holds its button. */
  function place(root) {
    if (!root || !active()) return;
    let n = 0;
    const after = new Map();
    for (const button of root.querySelectorAll('button.ht-term[data-term]')) {
      const id = button.getAttribute('data-term');
      if (!HT.foldOpen(foldId(id), false)) continue;
      n += 1;
      const block = button.closest('p, h3, h4, li, blockquote, .ht-facts, td, th, .ht-head-line') || button.parentElement;
      const box = note(id, n);
      button.setAttribute('aria-controls', box.id);
      const last = after.get(block) || block;
      last.after(box);
      after.set(block, box);
    }
  }

  HT.terms = {
    MAP,
    mark,
    place,
    /** From the `init` message: the stage and the learning-layer preference. */
    configure({ stage, learningLayer }) {
      state.stage = stage;
      state.layer = learningLayer === true;
      if (!active()) state.explain = null;
    },
    /** From the `view_data` of `explain` (an ExplainModel), or null. */
    setExplain(model) {
      state.explain = active() ? model : null;
      state.requested = state.requested || Boolean(model);
    },
    /** A new revision: the next hover may read `explain` again. */
    revision() { state.requested = false; },
    explain: () => state.explain,
    active,
  };

  // --- agent bridge (§6.8) ------------------------------------------------------------------

  /**
   * The modal of "Ask the agent about this". `about` is {kind, id} (§4.2 kinds); `shown`
   * is the label the junior reads in "About" (the extension builds its own from the
   * snapshot). The question field starts empty, may stay empty, and is not the words of a
   * decision card. Only {about, question, mode} is sent; the extension copies the text.
   * `question` is sent when the field stays empty (What if?: "Could you evaluate ...").
   */
  async function askAgent(ctx, about, shown, { question: fallback = '' } = {}) {
    const L = HT.copy.learn;
    const area = HT.wordsArea({ kind: 'askDraft', id: 'ht-ask-question', 'aria-describedby': 'ht-ask-hint', maxlength: '2000' });
    const body = HT.el('div', { 'data-ask-modal': true }, [
      HT.el('p', {}, [HT.el('strong', { text: `${L.askAbout}: ` }),
        HT.el('span', { 'data-ask-about': `${about.kind}:${about.id}`, text: L.aboutLine(about.kind, about.id, shown || '') })]),
      HT.el('label', { for: 'ht-ask-question', text: L.askQuestion }),
      area,
      HT.el('p', { id: 'ht-ask-hint', className: 'muted', text: L.askHint }),
    ]);
    const actions = [{ label: L.askCopy, value: 'copy', primary: true }];
    if (ctx.chatInsert === true) actions.push({ label: L.askInsert, value: 'insert' });
    const mode = await HT.modal({ title: L.askTitle, body, actions });
    if (mode !== 'copy' && mode !== 'insert') return false;
    const question = String(area.value.trim() ? area.value : fallback || '').slice(0, 2000);
    const sent = HT.send({ type: 'ask_agent', about: { kind: about.kind, id: String(about.id).slice(0, 100) }, question, mode });
    if (sent && ctx.ui) ctx.ui.set('askDraft', undefined);
    return sent;
  }

  /**
   * WP-E1 (v0.3): a ready question, copied at once (no modal, no field). The extension
   * builds the text from the fixed template of lib/bridge.js and puts it on the clipboard;
   * nothing is sent and nothing is written to the study.
   */
  function copyQuestion(about, question) {
    return HT.send({ type: 'ask_agent', about: { kind: about.kind, id: String(about.id).slice(0, 100) },
      question: String(question || '').slice(0, 2000), mode: 'copy' });
  }

  function askButton(ctx, about, shown, { label = null, attrs = {}, question = '', stage = 'v2', direct = false } = {}) {
    if (!ctx.atLeast(stage)) return null;
    return HT.el('button', { type: 'button', className: 'secondary', 'data-ask': `${about.kind}:${about.id}`, ...attrs,
      // A v0 control is gated by nothing: it carries no data-stage (a later-stage marker).
      'data-stage': stage === 'v0' ? null : stage,
      'data-ask-direct': direct ? 'true' : null, text: label || HT.copy.learn.ask,
      onclick: () => { if (direct) copyQuestion(about, question); else askAgent(ctx, about, shown, { question }); } });
  }

  HT.askAgent = askAgent;
  HT.askButton = askButton;
})(globalThis.Hypotrail = globalThis.Hypotrail || {});
