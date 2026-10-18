// Glossary terms of the panel's own copy, their hovers, and the agent-bridge modal
// (COMPANION-ADVANCED §6.6.1, §6.7, §6.8). Owned by WP-U5. Loaded after media/copy/*.js and
// before media/views/*.js (lib/html.js), so every view can use:
//
//   Hypotrail.terms.MAP                      {glossary id: [places where the copy marks it]}
//   Hypotrail.terms.mark(text, id)           a <span data-term="id"> for a word of the copy
//   Hypotrail.askAgent(ctx, about, shown)    the "Ask the agent about this" modal
//   Hypotrail.askButton(ctx, about, shown)   its button (stage v2, kept in reviewer mode)
//
// Hovers. With the learning layer on (stage v3, `learningLayer`), every `[data-term]` in the
// panel whose id is in `explain.terms` (the task filter) gets a tooltip on hover and on
// focus: the term in bold first, then its definition, then the study's cited example when
// the engine says it is `shown`. Escape closes it (core.js tooltip host). A term absent
// from `explain.terms` is not marked. The first hover reads `explain` once; with the layer
// off nothing is marked and `explain` is never read (LE-3). The Learn view feeds this
// module the `init` and `explain` messages it receives (media/views/learn.js).
(function (HT) {
  'use strict';

  // Every id is a glossary id of at least one task (test/learn.test.js).
  const MAP = Object.freeze({
    confirmed_decision: ['learn.layer intro'],
    proposal: ['decisions cards'],
    base_rate: ['eda target card'],
    exposure: ['evidence ledger'],
    stale_result: ['evidence registry'],
    validation_partition: ['evidence ledger'],
    selection_on_validation: ['evidence ledger'],
    paired_difference: ['evidence intervals'],
    confidence_interval: ['evidence intervals'],
    mae: ['what if residual explorer'],
    rmse: ['what if residual explorer'],
    extrapolation: ['what if residual explorer'],
  });

  const state = { layer: false, stage: 'v0', explain: null, requested: false };
  const attached = new WeakSet();

  const active = () => state.layer && Boolean(HT.protocol) && HT.protocol.stageAllows(state.stage, 'v3');

  function content(t) {
    const L = HT.copy.learn;
    return HT.el('div', { 'data-tooltip-term': true }, [
      HT.el('strong', { text: t.term }),
      HT.el('p', { className: 'ht-term-definition', text: t.definition }),
      t.example ? HT.components.segments(HT.el('p', { className: 'ht-term-example' }), t.example)
        : t.exampleStatus === 'needs_results' ? HT.el('p', { className: 'muted', text: L.exampleNeeded }) : null,
    ]);
  }

  function attach(node) {
    if (!node || !node.getAttribute || attached.has(node)) return;
    const t = active() && state.explain ? state.explain.terms[node.getAttribute('data-term')] : null;
    if (!t) return;               // not in this task's glossary: not marked
    attached.add(node);
    node.classList.add('ht-term');
    HT.tooltip.attach(node, () => content(t));
  }

  function scan(root) {
    if (!root || !root.querySelectorAll) return;
    if (root.hasAttribute && root.hasAttribute('data-term')) attach(root);
    for (const node of root.querySelectorAll('[data-term]')) attach(node);
  }

  function requestOnce(event) {
    if (!active() || state.explain || state.requested) return;
    const target = event.target && event.target.closest ? event.target.closest('[data-term]') : null;
    if (!target) return;
    state.requested = true;
    HT.send({ type: 'load', view: 'explain' });
  }

  function start() {
    if (typeof document === 'undefined') return;
    const app = document.getElementById('app');
    if (!app || typeof MutationObserver !== 'function') return;
    new MutationObserver(records => {
      for (const r of records) for (const n of r.addedNodes) if (n.nodeType === 1) scan(n);
    }).observe(app, { childList: true, subtree: true });
    document.addEventListener('mouseover', requestOnce);
    document.addEventListener('focusin', requestOnce);
  }

  HT.terms = {
    MAP,
    mark: (text, id) => HT.el('span', { 'data-term': id, text }),
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
    content,
  };

  // --- agent bridge (§6.8) ------------------------------------------------------------------

  /**
   * The modal of "Ask the agent about this". `about` is {kind, id} (§4.2 kinds); `shown`
   * is the label the junior reads in "About" (the extension builds its own from the
   * snapshot). The question field starts empty, may stay empty, and is not the words of a
   * decision card. Only {about, question, mode} is sent; the extension copies the text.
   */
  async function askAgent(ctx, about, shown) {
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
    const question = String(area.value || '').slice(0, 2000);
    const sent = HT.send({ type: 'ask_agent', about: { kind: about.kind, id: String(about.id).slice(0, 100) }, question, mode });
    if (sent && ctx.ui) ctx.ui.set('askDraft', undefined);
    return sent;
  }

  function askButton(ctx, about, shown) {
    if (!ctx.atLeast('v2')) return null;
    return HT.el('button', { type: 'button', className: 'secondary', 'data-ask': `${about.kind}:${about.id}`, 'data-stage': 'v2',
      text: HT.copy.learn.ask, onclick: () => { askAgent(ctx, about, shown); } });
  }

  HT.askAgent = askAgent;
  HT.askButton = askButton;
  start();
})(globalThis.Hypotrail = globalThis.Hypotrail || {});
