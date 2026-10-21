// Decisions view (COMPANION-ADVANCED §6.2). Owned by WP-U2.
//
//   v0  the pending decision cards, read only, and the open holds;
//   v1  the Decisions tab: cards with the pause, the holds and resolved conditions, and
//       "If you confirm" in words (the engine's `preview effects`, read when a card becomes
//       visible, at most three at once); the reconfirmation queue; the history, newest
//       first (R25);
//   v2  evidence chips on the cards and "Ask the agent" on the queue.
//
// v0.3 narrowing (WP-E1; ADR 0004 amendment, owner decision R23, integrator decision I2):
// the panel records no decision. There is no words field, no "Confirm" and no "Withdraw":
// each card says "Answer in the chat" and offers "Ask the agent about this", which copies a
// ready question to the clipboard (at every stage). The proposal id, the revision and the
// origin are under "Details" (R22). There is no delegation control (INV-4). Study text is
// always set as text (INV-9).
(function (HT) {
  'use strict';
  const el = HT.el;
  const str = x => (typeof x === 'string' ? x : '');
  const arr = x => (Array.isArray(x) ? x : []);
  const MAX_EFFECT_READS = 3;
  const DRAFT_DECISIONS = ['policy', 'model_choice'];
  const EVALUATION_SLOT = { policy: 'policy.evaluation', model_choice: 'evaluate.regression' };

  // View state: never a decision, never a number of the study. Effects are the engine's
  // previews per proposal and version (revision, currency, Refresh epoch; CR.1);
  // `effectsEpoch` is the epoch each preview was asked at.
  const view = {
    ctx: null, effects: {}, asked: {}, inflight: new Set(), waiting: [], requested: {}, effectsEpoch: {},
    observer: null,
  };

  const copyOf = ctx => ctx.copy.decisions;
  const taskOf = ctx => (ctx.snapshot && ctx.snapshot.task) || ctx.task || null;
  const rid8 = id => str(id).slice(0, 8);
  const J = () => HT.copy.junior;

  /** A decision value in words (WP-A5); the recorded value in its hover, never lost. */
  function readable(ctx, decisionId, raw, attrs) {
    const words = J().value(decisionId, raw, taskOf(ctx));
    return el('span', { className: words ? 'ht-value-words' : 'ht-mono', 'data-value-raw': str(raw),
      title: words && str(raw) ? `${J().nextMove.engineLabel}: ${str(raw)}` : null, ...(attrs || {}), text: words || str(raw) });
  }

  /** Slot names of the engine in words (fit.logistic -> the logistic model). */
  function slotWords(ctx, slot) {
    const s = str(slot);
    if (s.startsWith('fit.')) return J().modelName(s, taskOf(ctx));
    const words = { split: 'the split', 'policy.evaluation': 'the decision-rule evaluation', 'evaluate.regression': 'the model comparison' };
    return words[s] || s.replace(/[._:]/g, ' ');
  }

  /**
   * WP-A7 (ADR 0005): the confirmation mode of the study and what counts as an answer, read
   * only. The mode changes in the chat with the junior's words (`mode set`, not a W1-W7
   * write), so the panel shows it and never offers to change it.
   */
  function modeSection(model, ctx, c) {
    const mode = str(model.mode);
    if (!mode) return null;
    const M = J().modes;
    const name = c.modeNames[mode] || mode;
    // WP-B5: every mode says what counts as an answer (ADR 0005, decision 8).
    const known = ['guided', 'training', 'express'].includes(mode);
    const finalTest = arr(model.plan).some(s => s.id === 'final_test');
    return el('section', { className: 'card dc-mode', 'aria-labelledby': 'h-dc-mode', 'data-mode': mode }, [
      el('h3', { id: 'h-dc-mode', text: c.modeTitle }),
      el('p', {}, [el('span', { className: 'ht-status ht-st-needs', 'data-mode-chip': mode, text: name }), ' ', c.modeLine(name)]),
      known ? el('ul', { className: 'dc-mode-rules' }, M.rules(mode, taskOf(ctx), finalTest).map(t => el('li', { text: t })))
        : el('p', { className: 'muted', text: c.modeOther }),
      el('p', { className: 'muted', 'data-mode-change': true, text: known ? M.change : c.modeChange }),
    ]);
  }

  /** WP-A7: the basis of a confirmation as a chip of one vocabulary, its meaning in the hover. */
  function basisChip(c, basis, scope, channel) {
    const b = str(basis) || 'explicit';
    const label = b === 'delegated_default' ? c.basis(b, scope) : (c.basisChip[b] || b);
    return el('span', { className: 'dc-basis-cell' }, [
      el('span', { className: `ht-status dc-basis ${b === 'delegated_default' ? 'ht-st-stale dc-delegated' : 'ht-st-ok'}`,
        'data-basis': b, title: c.basisHelp[b] || null, text: label }),
      channel ? el('span', { className: 'muted dc-channel', 'data-channel': channel, text: ` ${c.channelWords(channel)}` }) : null,
    ]);
  }

  function section(id, title, children, attrs) {
    return el('section', { 'aria-labelledby': id, ...(attrs || {}) }, [el('h2', { id, text: title }), ...children]);
  }

  // --- reads ----------------------------------------------------------------------------

  /** Ask once per version for a data view this tab shows (decisions, evidence; CR.1). */
  function ensureLoad(ctx, name) {
    if (ctx.fresh(ctx.data(name))) return;
    const key = `${name}@${ctx.version()}`;
    if (view.requested[key]) return;
    view.requested[key] = true;
    ctx.load(name);
  }

  function retryLoad(ctx, name) {
    delete view.requested[`${name}@${ctx.version()}`];
    ctx.retry(name);
    ensureLoad(ctx, name);
  }

  /** Request the engine's preview of one card, at most three reads at once. */
  function wantEffects(pid) {
    const ctx = view.ctx;
    if (!ctx || !ctx.snapshot || !ctx.atLeast('v1')) return;
    const rev = ctx.snapshot.revision;
    if (ctx.fresh(view.effects[pid])) return;
    const key = `${pid}@${ctx.version()}`;
    if (view.asked[key] || view.inflight.has(pid)) return;
    if (view.inflight.size >= MAX_EFFECT_READS) {
      if (!view.waiting.includes(pid)) view.waiting.push(pid);
      return;
    }
    view.asked[key] = true;
    view.inflight.add(pid);
    view.effectsEpoch[pid] = ctx.epoch();
    ctx.send({ type: 'preview_effects', proposalId: pid, revision: rev });
  }

  function drainEffects() {
    while (view.waiting.length && view.inflight.size < MAX_EFFECT_READS) wantEffects(view.waiting.shift());
  }

  /** Observe the cards; a visible card asks for its preview. */
  function observeCards(cards) {
    if (view.observer) view.observer.disconnect();
    view.observer = null;
    if (!cards.length) return;
    if (typeof IntersectionObserver !== 'function') {
      for (const card of cards) wantEffects(card.dataset.proposalCard);
      return;
    }
    view.observer = new IntersectionObserver(entries => {
      for (const entry of entries) if (entry.isIntersecting) wantEffects(entry.target.dataset.proposalCard);
    });
    for (const card of cards) view.observer.observe(card);
  }

  // --- small parts ----------------------------------------------------------------------

  function pauseOf(ctx, decisionId) {
    const step = arr(ctx.snapshot.plan).find(s => s.id === decisionId);
    return step && Number.isInteger(step.pause) ? step.pause : null;
  }

  /** Status groups of an availability value shown as text (the summary holds it as JSON). */
  function availabilityGroups(decisionId, value) {
    if (decisionId !== 'feature_availability') return null;
    let parsed = null;
    try { parsed = JSON.parse(value); } catch (_) { return null; }
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return null;
    const entries = Object.entries(parsed).filter(([, v]) => typeof v === 'string');
    if (!entries.length) return null;
    const order = ['available_at_prediction', 'uncertain_included', 'uncertain_excluded', 'not_available'];
    const statuses = [...order, ...new Set(entries.map(([, v]) => v).filter(v => !order.includes(v)))];
    return statuses.map(status => ({ status, columns: entries.filter(([, v]) => v === status).map(([k]) => k) }))
      .filter(g => g.columns.length);
  }

  function groupsList(groups, c) {
    return el('ul', { className: 'dc-groups', 'data-value-groups': true }, groups.map(g =>
      el('li', { 'data-status': g.status }, [el('span', { className: 'dc-group', text: `${c.availability[g.status] || g.status}: ` }),
        el('code', { text: g.columns.join(', ') })])));
  }

  function groupsText(groups, c) {
    return groups.map(g => `${c.availability[g.status] || g.status}: ${g.columns.join(', ')}`).join('; ');
  }

  /** Recorded words in quotes, as text (the quotes are part of the text, not CSS). */
  function quote(text) {
    return el('span', { className: 'dc-quoted' }, ['“', el('span', { 'data-quoted': true, text: str(text) }), '”']);
  }

  /** Evidence chips (v2): only current results of the evidence read, never a guess. */
  function evidenceChips(p, ctx, c) {
    const data = ctx.data('evidence');
    const model = data && data.model;
    if (!model) return null;
    const results = arr(model.results).filter(r => r && (r.current === true) && (r.integrity === undefined || r.integrity === 'ok'));
    const idOf = r => str(r.resultId || r.result_id);
    const slotOf = r => str(r.slot);
    const chips = [];
    const resultChip = r => el('button', { type: 'button', className: 'dc-chip', 'data-evidence-chip': idOf(r),
      title: c.evidenceChip(str(r.activity) || slotOf(r), rid8(idOf(r))),
      text: c.evidenceChipWords(slotWords(ctx, slotOf(r) || str(r.activity))),
      onclick: () => ctx.navigate({ tab: 'evidence', kind: 'result', id: idOf(r) }) });
    const id = p.decisionId;
    if (EVALUATION_SLOT[id]) {
      const r = results.find(x => slotOf(x) === EVALUATION_SLOT[id] && idOf(x));
      if (r) chips.push(resultChip(r));
      if (id === 'policy') {
        // The paired precision difference of the proposed rule, from the EvidenceModel's
        // uncertainty of the current policy evaluation (lib/models/evidence.js; WP-I
        // reconciled U2 with U3). Shown only when the engine evaluated that rule.
        const u = model.uncertainty && model.uncertainty.kind === 'policy' ? model.uncertainty : null;
        const rule = u ? arr(u.rules).find(x => x && x.rule === str(p.value)) : null;
        const metric = rule ? arr(rule.metrics).find(x => x && x.metric === 'precision') : null;
        const d = metric && metric.delta;
        if (d && typeof d.point === 'number' && typeof d.low === 'number' && typeof d.high === 'number') {
          const f = x => `${x > 0 ? '+' : ''}${ctx.format.number(x, 'pct1')}`;
          chips.push(el('span', { className: 'dc-chip dc-chip-static', 'data-evidence-delta': true },
            [ctx.components.cited(c.precisionDelta(f(d.point), f(d.low), f(d.high)), { resultId: u.resultId, path: d.path, value: d.point })]));
        }
      }
      chips.push(el('button', { type: 'button', className: 'dc-chip', 'data-explore': id, text: c.explore(taskOf(ctx)),
        onclick: () => ctx.navigate({ tab: 'whatif', kind: 'decision', id }) }));
    } else if (id === 'split') {
      const r = results.find(x => slotOf(x) === 'split' && idOf(x));
      if (r) chips.push(resultChip(r));
    } else if (id === 'feature_availability') {
      for (const r of results.filter(x => slotOf(x).startsWith('eda.') && idOf(x))) chips.push(resultChip(r));
    }
    if (!chips.length) return null;
    return el('div', { className: 'dc-evidence', 'data-stage': 'v2', 'data-evidence': p.proposalId }, [
      el('h4', { text: c.evidenceTitle }), el('div', { className: 'dc-chips' }, chips)]);
  }

  function names(list, c) {
    return list.length ? list.join(c.and) : c.nothing;
  }

  /** One effect in words: "To confirm again: the conclusion". */
  function effectLine(kind, title, body) {
    return el('li', { className: `dc-effect dc-effect-${kind}`, 'data-effects-box': kind }, [
      el('span', { className: 'dc-box-title', text: `${title}: ` }), body]);
  }

  /**
   * "If you confirm" (v1), from the engine's preview only, in words (R22): what a
   * confirmation would invalidate, or "Confirming changes nothing already done." when it
   * invalidates nothing. What stays current and what is regenerated are under Details.
   */
  function effectsSection(p, ctx, c) {
    const id = p.proposalId;
    const entry = view.effects[id];
    const fresh = ctx.fresh(entry);
    const titleId = `effects-${id}`;
    const wrap = parts => el('div', { className: 'dc-effects', 'aria-labelledby': titleId, 'data-effects': id }, parts);
    // WP-B5: the opening of the final test is answered in the chat; its preview says so.
    const parts = [el('h4', { id: titleId, text: str(p.decisionId) === 'final_test' ? c.effectsTitleOpening : c.effectsTitle })];
    if (!entry) {
      parts.push(el('p', { className: 'muted', 'aria-busy': 'true', 'data-effects-loading': true, text: c.effectsLoading }));
      return wrap(parts);
    }
    if (!fresh) parts.push(el('p', { className: 'muted', 'aria-busy': 'true', 'data-effects-updating': true, text: c.effectsUpdating }));
    const m = entry.model;
    if (!m.available) {
      parts.push(el('p', { className: 'muted', 'data-effects-missing': true }, [c.effectsMissing, ' ', str(m.message)]));
      return wrap(parts);
    }
    const naming = c.decisionNames(taskOf(ctx));
    const reconfirm = arr(m.reconfirm).map(r => naming[r.id] || str(r.title) || str(r.id));
    const stale = arr(m.stale).map(x => slotWords(ctx, x));
    const refit = arr(m.refit).map(x => slotWords(ctx, x));
    const invalidated = [];
    if (reconfirm.length) invalidated.push(effectLine('reconfirm', c.toConfirmAgain, names(reconfirm, c)));
    if (stale.length) invalidated.push(effectLine('stale', c.becomesStale, stale.join(', ')));
    if (refit.length) invalidated.push(effectLine('refit', c.refitted, refit.join(', ')));
    if (invalidated.length) {
      parts.push(el('ul', { className: 'dc-effects-list', 'data-effects-invalidated': String(invalidated.length) }, invalidated));
    } else {
      parts.push(el('p', { 'data-effects-nothing': true, text: c.effectsNothing }));
    }
    if (m.supersedesProposal) parts.push(el('p', { 'data-supersedes': m.supersedesProposal, text: c.supersedesOpen }));
    if (arr(m.blocked).length) {
      parts.push(el('div', { id: `blocked-${id}`, role: 'status', className: 'dc-blocked', 'data-blocked': id }, [
        el('p', { className: 'dc-box-title', text: c.blockedTitle }),
        el('ul', {}, arr(m.blocked).map(b => el('li', { 'data-blocked-code': str(b.code),
          title: `${str(b.code)}${b.reason ? ' (' + str(b.reason) + ')' : ''}` }, [
          el('span', { 'data-engine-message': true, text: str(b.message) })]))),
      ]));
    }
    if (arr(m.notes).length) parts.push(el('ul', { className: 'muted dc-notes' }, arr(m.notes).map(n => el('li', { text: str(n) }))));
    // What stays current, what is regenerated, and the engine's note (layer 2): Details.
    const kept = m.kept.fitsAllKept ? c.keptFits : names(arr(m.kept.slots).map(x => slotWords(ctx, x)), c);
    parts.push(el('details', { className: 'ht-details', 'data-effects-details': id }, [el('summary', { text: c.details }),
      el('ul', { className: 'dc-effects-list' }, [
        effectLine('kept', c.kept, kept),
        effectLine('regenerated', c.regenerated, names(arr(m.regenerated).map(n => c.artefactNames[n] || n), c)),
      ]),
      m.firstConfirmation ? el('p', { className: 'muted', 'data-effects-first': true, text: c.effectsFirst }) : null,
      m.note ? el('p', { className: 'muted dc-caption', 'data-effects-note': true, text: str(m.note) }) : null]));
    return wrap(parts);
  }

  // --- the pending decision card (read only) ---------------------------------------------

  /**
   * v0.3 (WP-K): on a variant proposal, the trial budget (a replaced variant still counts)
   * and the engine's family shortlist, read from the full view (`trials`), so the junior
   * sees what answering spends before answering in the chat. Read only.
   */
  function trialsNote(ctx, c) {
    const entry = ctx.data('trials');
    const m = entry && entry.model;
    if (!m || (!m.budget && !m.families)) return null;
    const T = HT.copy.evidence.variants;
    const b = m.budget;
    const lang = HT.language ? HT.language() : 'en';
    const texts = m.families && m.families.texts;
    const text = texts ? texts[lang] || texts.en : null;
    return el('div', { className: 'ht-note dc-trials', role: 'note', 'data-trials-note': b ? `${b.used}/${b.max}` : 'shortlist' }, [
      el('div', {}, [
        el('p', { className: 'title', text: c.trialsTitle }),
        b ? el('p', { 'data-trial-budget': `${b.used}/${b.max}`, text: T.budgetLine(ctx.format.number(b.used, 'int'),
          ctx.format.number(b.max, 'int'), ctx.format.number(b.remaining ?? Math.max(0, b.max - b.used), 'int')) }) : null,
        b ? el('p', { className: 'muted', text: T.budgetWhy }) : null,
        text ? ctx.components.engineText(text, { lang: texts[lang] ? lang : 'en', tag: 'p', attrs: { 'data-shortlist-text': m.families.recommendation || '' } }) : null,
      ]),
    ]);
  }

  function proposalCard(p, model, ctx, c) {
    const id = str(p.proposalId);
    const v1 = ctx.atLeast('v1');
    const task = taskOf(ctx);
    // WP-B5: the opening of the final test has its own note (it is opened once, in the chat).
    const opening = str(p.decisionId) === 'final_test';
    const groups = v1 ? availabilityGroups(p.decisionId, str(p.value)) : null;
    const pause = v1 ? pauseOf(ctx, p.decisionId) : null;
    const holds = arr(p.holds).map(h => el('p', { className: 'hold dc-hold', 'data-hold': str(h.noteId) },
      [c.holdOpen, quote(h.userWords), c.holdSentence]));
    const resolved = v1 ? arr(p.resolvedNotes).map(n => el('p', { className: 'dc-resolved', 'data-resolved-note': str(n.noteId) },
      [c.holdResolved, quote(n.userWords), ' → ', quote(n.resolutionWords || '')])) : [];
    const fromPanel = p.origin && p.origin.channel === 'webview';
    const revision = Number.isInteger(p.revision) ? p.revision : null;

    const head = el('div', { className: 'dc-head' }, [
      el('div', { className: 'dc-head-main' }, [
        pause ? el('span', { className: 'dc-pill', 'data-pause': pause, text: c.pause(pause, task) }) : null,
        el('h3', { id: `title-${id}`, text: str(p.decisionTitle) }),
      ]),
    ]);

    const card = el('article', { className: 'card dc-card', 'data-proposal-card': id, 'data-decision': str(p.decisionId),
      'data-nav': `proposal:${id}`, 'aria-labelledby': `title-${id}` }, [
      head,
      // The restatement block (R14, R22): what the assistant proposes, then the value in words.
      el('div', { className: 'dc-restatement', 'data-restatement-block': id }, [
        el('p', { className: 'dc-lead', text: c.restatedAs }),
        el('blockquote', { text: str(p.restatement), 'data-restatement': id }),
        el('div', { className: 'dc-value' }, [el('p', { 'data-proposed-value': id }, [c.proposedValue, readable(ctx, p.decisionId, p.value)]),
          groups ? groupsList(groups, c) : null]),
      ]),
      v1 && ctx.atLeast('v2') ? evidenceChips(p, ctx, c) : null,
      str(p.decisionId) === 'model_variant' && ctx.atLeast('v2') ? trialsNote(ctx, c) : null,
      ...holds,
      ...resolved,
      v1 ? effectsSection(p, ctx, c) : null,
      opening ? el('div', { className: 'hold dc-final-chat', role: 'note', 'data-final-test-chat': id }, [
        el('p', { className: 'title', text: c.finalTestTitle }),
        // v0.3 (WP-E3): own words and a reason only in the training mode (ADR 0005, decision 8).
        el('p', { text: str(model.mode) === 'training' ? c.finalTestBodyTraining : c.finalTestBody }),
        el('p', { className: 'muted', text: c.finalTestOnce }),
      ]) : el('div', { className: 'dc-answer', role: 'note', 'data-answer-in-chat': id }, [
        el('p', { className: 'title', text: c.answerInChat }),
        el('p', { className: 'muted', text: c.answerInChatHint }),
      ]),
      el('div', { className: 'dc-actions' }, [
        // The shared agent-bridge helper of media/terms.js: a ready question, copied (§6.8).
        HT.askButton(ctx, { kind: 'proposal', id }, c.askAbout(str(p.decisionTitle)),
          { label: c.ask, attrs: { 'data-ask-proposal': id }, question: c.askQuestion, stage: 'v0', direct: true }),
      ]),
      // Internal details (R22): the proposal id, the revision it was made at, its origin,
      // and the recorded value.
      el('details', { className: 'ht-details', 'data-value-details': id }, [el('summary', { text: c.details }),
        el('p', { 'data-made-at': id, text: c.madeAt(id, revision) }),
        // The glossary term "proposal" (§6.7): marked only when the learning layer is on.
        el('p', { 'data-origin': fromPanel ? 'webview' : 'agent' }, [HT.terms.mark(fromPanel ? c.byPanel : c.byAgent, 'proposal')]),
        el('p', {}, [c.recordedValue, el('code', { text: str(p.value) })])]),
    ]);
    // A deep link to the decision (CLI-CONTRACT-COMPANION §11) lands on its open card.
    return v1 ? el('div', { className: 'dc-card-wrap', 'data-nav': `decision:${str(p.decisionId)}` }, [card]) : card;
  }

  // --- reconfirmation queue and history (v1, from `decisions`) ---------------------------------

  function queueSection(data, ctx, c) {
    const items = arr(data.queue);
    if (!items.length) return null;
    return section('h-dc-queue', c.queueTitle, items.map(q => {
      const id = str(q.decisionId);
      const prev = q.previous || {};
      return el('article', { className: 'card dc-queue', 'data-queue-item': id, 'data-nav': `decision:${id}`,
        'aria-labelledby': `queue-${id}` }, [
        el('h3', { id: `queue-${id}`, text: str(q.title) }),
        el('p', { 'data-queue-reason': id, text: str(q.reason) }),
        el('p', { 'data-previous': id }, [c.previously, quote(prev.userWords),
          ` (${c.basisChannel(c.basis(str(prev.basis), null), str(prev.channel))})`]),
        q.openProposal
          ? el('button', { type: 'button', className: 'secondary', 'data-open-proposal': q.openProposal, text: c.openNew,
            onclick: () => ctx.navigate({ tab: 'decisions', kind: 'proposal', id: q.openProposal }) })
          : el('div', {}, [
            el('p', { className: 'muted', text: c.noNewProposal }),
            HT.askButton(ctx, { kind: 'decision', id }, str(q.title), { label: c.askShort, attrs: { 'data-ask-decision': id } }),
            DRAFT_DECISIONS.includes(id) ? ctx.gate('v2', el('button', { type: 'button', className: 'secondary',
              'data-choose': id, text: c.chooseInWhatIf, onclick: () => ctx.navigate({ tab: 'whatif', kind: 'decision', id }) })) : null,
          ]),
      ]);
    }));
  }

  /** WP-A7 (ADR 0005, R3): the corrections the junior recorded later, in their words. */
  function corrections(data, decisionId, c) {
    return arr(data.notes).filter(n => n.kind === 'correction' && n.decisionId === decisionId)
      .map(n => el('p', { className: 'dc-correction', 'data-correction': str(n.noteId) }, [c.correction, quote(n.userWords)]));
  }

  function historySection(entry, ctx, c) {
    const err = ctx.error('decisions');
    const children = [];
    if (err && !entry) {
      children.push(el('div', { className: 'card alert', role: 'alert', 'data-history-error': true }, [
        el('p', { className: 'title', text: c.historyError }),
        el('p', { text: str(err.message) }),
        err.detail ? el('details', {}, [el('summary', { text: ctx.copy.core.loadErrorDetail }), el('pre', { text: str(err.detail) })]) : null,
        el('button', { type: 'button', className: 'secondary', text: c.retry, onclick: () => retryLoad(ctx, 'decisions') }),
      ]));
      return section('h-dc-history', c.historyTitle, children);
    }
    if (!entry) {
      children.push(el('p', { className: 'muted', 'aria-busy': 'true', text: ctx.copy.core.reading }));
      return section('h-dc-history', c.historyTitle, children, { 'aria-busy': 'true' });
    }
    const stale = !ctx.fresh(entry);
    if (stale) children.push(el('p', { className: 'muted', 'data-updating': true, text: ctx.copy.core.updating }));
    const data = entry.model;
    const rows = arr(data.history);
    const navSeen = new Set();
    if (rows.length) {
      children.push(el('table', { className: 'dc-history', 'data-history': true }, [
        el('caption', { className: 'sr-only', text: c.historyCaption }),
        el('thead', {}, [el('tr', {}, c.columns.map(name => el('th', { scope: 'col', text: name })))]),
        el('tbody', {}, rows.map(h => {
          const nav = navSeen.has(h.decisionId) ? null : `decision:${h.decisionId}`;
          navSeen.add(h.decisionId);
          // R25: the revision and the time are internal: in the hover of the decision.
          const when = [Number.isInteger(h.revision) ? c.atRevision(h.revision) : null, h.time ? ctx.format.localTime(h.time) : null]
            .filter(Boolean).join(' · ');
          return el('tr', { className: h.current ? '' : 'muted dc-superseded', 'data-history-row': `${h.decisionId}:${h.revision}`,
            'data-current': h.current ? 'true' : 'false', 'data-nav': nav }, [
            el('td', { 'data-when': when || null, title: when || null }, [el('span', { className: 'dc-decision', text: str(h.title) }), ' ',
              h.groups ? el('span', { className: 'dc-history-value', title: groupsText(h.groups, c) },
                [readable(ctx, h.decisionId, Object.fromEntries(h.groups.flatMap(g => g.columns.map(col => [col, g.status]))))])
                : el('span', { className: 'dc-history-value' }, [readable(ctx, h.decisionId, h.value)])]),
            el('td', { 'data-words-cell': true }, [quote(h.userWords),
              h.reasonGiven === false ? el('span', { className: 'muted dc-no-reason', 'data-no-reason': h.decisionId, text: ` (${c.noReason})` }) : null,
              h.agentConcern ? el('p', { className: 'hold dc-concern', 'data-agent-concern': h.decisionId },
                [c.concern, quote(h.agentConcern)]) : null,
              ...(h.current ? corrections(data, h.decisionId, c) : [])]),
            el('td', { 'data-basis-cell': true }, [basisChip(c, h.basis, h.scope, str(h.channel)),
              h.current ? null : el('span', { className: 'muted dc-superseded-at', 'data-superseded': true,
                title: c.supersededAt(h.supersededAt), text: ` · ${c.superseded}` })]),
          ]);
        })),
      ]));
    } else {
      children.push(el('p', { className: 'muted', text: c.noHistory }));
    }
    children.push(el('p', { className: 'muted', 'data-not-authenticated': true, text: c.notAuthenticated }));
    const unconfirmed = arr(data.unconfirmedProposals);
    if (unconfirmed.length) {
      children.push(el('details', { 'data-unconfirmed': true }, [
        el('summary', { text: c.unconfirmedTitle }),
        el('ul', {}, unconfirmed.map(u => el('li', { 'data-unconfirmed-proposal': str(u.proposalId) }, [
          el('p', {}, [el('span', { className: 'dc-decision', text: str(u.title) }), ' ',
            el('span', { className: 'muted', title: str(u.proposalId), text: c.proposalStatus(str(u.status), u.closedReason) })]),
          el('blockquote', { text: str(u.restatement) }),
          el('p', {}, [c.proposedValue, u.groups ? el('code', { text: groupsText(u.groups, c) }) : readable(ctx, u.decisionId, u.value)]),
        ]))),
      ]));
    }
    return section('h-dc-history', c.historyTitle, children, stale ? { 'aria-busy': 'true' } : null);
  }

  HT.register('decisions', {
    tab: 'decisions',
    stage: 'v0',
    views: [],
    render(model, ctx) {
      const c = copyOf(ctx);
      const v1 = ctx.atLeast('v1');
      view.ctx = ctx;
      if (v1) ensureLoad(ctx, 'decisions');
      if (ctx.atLeast('v2')) ensureLoad(ctx, 'evidence');
      const proposals = arr(model.proposals);
      // v0.3 (WP-K): the trial budget and the shortlist, only while a variant proposal waits.
      if (ctx.atLeast('v2') && proposals.some(p => str(p.decisionId) === 'model_variant')) ensureLoad(ctx, 'trials');
      const cards = proposals.map(p => proposalCard(p, model, ctx, c));
      const articles = cards.map(n => (n.matches('[data-proposal-card]') ? n : n.querySelector('[data-proposal-card]')));
      const out = [
        section('h-proposals', c.waitingTitle, cards.length ? cards
          : [el('p', { className: 'muted', 'data-nothing-waiting': true, text: v1 ? c.nothingWaiting : c.nothingWaitingV0 })])];
      if (arr(model.holds).length) {
        out.push(section('h-holds', c.holdsTitle, [el('ul', {}, arr(model.holds).map(h =>
          el('li', { 'data-hold-item': str(h.noteId), title: str(h.noteId) }, [`${str(h.decisionTitle)}: `, quote(h.userWords)])))]));
      }
      if (v1) {
        // WP-A7: the mode follows the waiting cards, so what waits for the junior comes first.
        out.push(modeSection(model, ctx, c));
        const entry = ctx.data('decisions');
        if (entry && entry.model) out.push(queueSection(entry.model, ctx, c));
        out.push(historySection(entry && entry.model ? entry : null, ctx, c));
        observeCards(articles);
      }
      return out;
    },
    onMessage(m, ctx) {
      if (m.type === 'effects') {
        const epoch = view.effectsEpoch[m.proposalId];
        view.effects[m.proposalId] = { ...ctx.stamp(m, epoch === undefined ? ctx.epoch() : epoch), model: m.model };
        view.inflight.delete(m.proposalId);
        drainEffects();
        return true;
      }
      if (m.type === 'snapshot') {
        // Previews of proposals that are no longer open are dropped.
        const open = new Set(arr(m.model && m.model.proposals).map(p => p.proposalId));
        for (const pid of Object.keys(view.effects)) if (!open.has(pid)) delete view.effects[pid];
        for (const pid of [...view.inflight]) if (!open.has(pid)) view.inflight.delete(pid);
        view.waiting = view.waiting.filter(pid => open.has(pid));
      }
      return true;
    },
  });
})(globalThis.Hypotrail = globalThis.Hypotrail || {});
