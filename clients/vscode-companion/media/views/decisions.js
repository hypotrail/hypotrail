// Decision parts (COMPANION-ADVANCED §6.5, §A.2; formerly the Decisions tab, WP-U2). The one
// page (ADR 0004 d13) places them through media/views/page.js:
//
//   effects      Now's fold "What your answer will change" (NOW-9, v1): the engine's
//                `preview effects` of the open proposal, read when the fold opens
//   history      each step's detail in the path (PATH-5, PATH-8, v1): the confirmations
//                newest first, bases, concerns, corrections, proposals not confirmed
//   mode         Now's fold "What counts as your answer" (NOW-7, v1)
//   queueReason  why a decision came back (NOW-5, v1), from the reconfirmation queue
//
// v0.3 narrowing (WP-E1; ADR 0004 amendment, owner decision R23, integrator decision I2):
// the panel records no decision: no words field, no "Confirm", no "Withdraw", no delegation
// control (INV-4). Study text is always set as text (INV-9).
(function (HT) {
  'use strict';
  const el = HT.el;
  const str = x => (typeof x === 'string' ? x : '');
  const arr = x => (Array.isArray(x) ? x : []);
  const MAX_EFFECT_READS = 3;

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

  /**
   * L3 (owner session 2026-10-26, R4, D4b): a proposal's restatement, the chat's own words. In
   * the panel language when the chat gave it in that language; else as written, in its
   * language (`restatementLang`), with a marker that says whose wording it is.
   */
  // L3 (R4, D4b): the `decisions` read gives its step titles in the study language; the
  // summary's `texts` give them in both, so the titles follow the panel's language switch.
  function localTitles(model, snapshot) {
    const tables = snapshot && snapshot.texts;
    const T = tables && tables[snapshot.textsLanguage];
    if (!T || !T.plan) return model;
    const retitle = list => (Array.isArray(list) ? list.map(x => (x && typeof T.plan[x.decisionId] === 'string'
      ? { ...x, title: T.plan[x.decisionId] } : x)) : list);
    const out = { ...model };
    for (const [k, v] of Object.entries(model)) if (Array.isArray(v)) out[k] = retitle(v);
    return out;
  }

  /** A decision value in words (WP-A5); the recorded value in its hover, never lost. */
  function readable(ctx, decisionId, raw, attrs) {
    const words = J().value(decisionId, raw, taskOf(ctx));
    return el('span', { className: words ? 'ht-value-words' : 'ht-mono', 'data-value-raw': str(raw),
      title: words && str(raw) ? `${J().nextMove.engineLabel}: ${str(raw)}` : null, ...(attrs || {}), text: words || str(raw) });
  }

  /** Slot names of the engine in words (fit.logistic -> the logistic model), in the panel
   * language (third session of 2026-10-26: the copy's `slotWords`, never English in French). */
  function slotWords(ctx, slot) {
    const s = str(slot);
    if (s.startsWith('fit.')) return J().modelName(s, taskOf(ctx));
    const words = copyOf(ctx).slotWords || {};
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
      // L9 (R20): an automatic decision waits for the junior's review, like a delegation.
      el('span', { className: `ht-status dc-basis ${['delegated_default', 'automatic'].includes(b) ? 'ht-st-stale dc-delegated' : 'ht-st-ok'}`,
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

  // --- small parts ----------------------------------------------------------------------

  function groupsText(groups, c) {
    return groups.map(g => `${c.availability[g.status] || g.status}: ${g.columns.join(', ')}`).join('; ');
  }

  /** Recorded words in quotes, as text (the quotes are part of the text, not CSS). */
  function quote(text) {
    return el('span', { className: 'dc-quoted' }, ['“', el('span', { 'data-quoted': true, text: str(text) }), '”']);
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

  // --- R16: a choice the chat waits for, before any proposal (v1, read only) ----------------

  /** EV-13 (WP-K): the trial budget and the family shortlist, on a variant proposal (v2). */
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

  // --- reconfirmation queue and history (v1, from `decisions`) ---------------------------------

  /** WP-A7 (ADR 0005, R3): the corrections the junior recorded later, in their words. */
  function corrections(data, decisionId, c) {
    return arr(data.notes).filter(n => n.kind === 'correction' && n.decisionId === decisionId)
      .map(n => el('p', { className: 'dc-correction', 'data-correction': str(n.noteId) }, [c.correction, quote(n.userWords)]));
  }

  function historySection(entry, ctx, c, only = null) {
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
    const rows = arr(data.history).filter(h => !only || h.decisionId === only);
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
    const unconfirmed = arr(data.unconfirmedProposals).filter(u => !only || u.decisionId === only);
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
    if (only) return el('div', { className: 'dc-step-history', 'data-step-history': only, 'aria-busy': stale ? 'true' : null }, children);
    return section('h-dc-history', c.historyTitle, children, stale ? { 'aria-busy': 'true' } : null);
  }

  // --- lesson style (R30): the notions of this step ----------------------------------------

  // The one page (ADR 0004 d13): the Decisions tab is gone. Now holds the open proposal
  // (media/views/page.js) and its "What your answer will change" (`effects`, read when its fold
  // is opened, §5); each step's detail in the path holds its history (`history`, v1, PATH-5,
  // PATH-8); Now's fold "What counts as your answer" is the mode (`mode`, NOW-7).
  HT.register('decisions', {
    stage: 'v0',
    onMessage(m, ctx) {
      if (m.type === 'effects') {
        const epoch = view.effectsEpoch[m.proposalId];
        view.effects[m.proposalId] = { ...ctx.stamp(m, epoch === undefined ? ctx.epoch() : epoch), model: m.model };
        view.inflight.delete(m.proposalId);
        drainEffects();
        return true;
      }
      if (m.type === 'snapshot') {
        const open = new Set(arr(m.model && m.model.proposals).map(p => p.proposalId));
        for (const pid of Object.keys(view.effects)) if (!open.has(pid)) delete view.effects[pid];
        for (const pid of [...view.inflight]) if (!open.has(pid)) view.inflight.delete(pid);
        view.waiting = view.waiting.filter(pid => open.has(pid));
      }
      return true;
    },
  });
  HT.parts = HT.parts || {};
  HT.parts.decisions = {
    /** NOW-9: the engine's preview of what confirming the open proposal would invalidate. */
    effects(ctx, proposal) {
      view.ctx = ctx;
      if (!proposal) return null;
      wantEffects(proposal.proposalId);
      return effectsSection(proposal, ctx, copyOf(ctx));
    },
    /** PATH-5 (v1): the history of one decision, newest first, with bases, concerns, corrections. */
    history(ctx, decisionId) {
      view.ctx = ctx;
      ensureLoad(ctx, 'decisions');
      const read = ctx.data('decisions');
      const entry = read && read.model ? { ...read, model: localTitles(read.model, ctx.snapshot) } : read;
      return historySection(entry && entry.model ? entry : null, ctx, copyOf(ctx), decisionId);
    },
    /** WP-K: on Now's proposal of the variants to compare, the trial budget and the shortlist (v2). */
    trials(ctx) {
      if (!ctx.atLeast('v2')) return null;
      ctx.want('trials');
      return trialsNote(ctx, copyOf(ctx));
    },
    /** NOW-7: what counts as an answer in the study's mode (read only). */
    mode: ctx => modeSection(ctx.snapshot, ctx, copyOf(ctx)),
    /** NOW-5 (v1): why a decision came back, from the reconfirmation queue; null before the read. */
    queueReason(ctx, decisionId) {
      if (!ctx.atLeast('v1')) return null;
      view.ctx = ctx;
      ensureLoad(ctx, 'decisions');
      const read = ctx.data('decisions');
      const item = read && read.model ? arr(read.model.queue).find(q => q.decisionId === decisionId) : null;
      return item && str(item.reason) ? str(item.reason) : null;
    },
  };
})(globalThis.Hypotrail = globalThis.Hypotrail || {});
