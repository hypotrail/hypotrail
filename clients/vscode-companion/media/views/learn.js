// Learn & hand off view (COMPANION-ADVANCED §6.6; stage v3). Owned by WP-U5.
//
// - Learning layer (only when `learningLayer` is on): concept cards for the current step
//   and the steps awaiting confirmation, each counted as seen after 2 s fully visible (once
//   per panel session) and collapsed after its second sighting; "Predict before you look"
//   questions whose answers are kept on this computer only (globalState via learn_set,
//   never the study); glossary hovers through media/terms.js.
// - Hand off: "Export a handoff pack" (W7, `data-write="export"`, allowed in reviewer
//   mode by decision CA.9), its outcome with the files, and "Open folder".
// - Session report: a collapsed <details>; opening it reads `session-report`.
//
// No card, prediction, or answer is ever shown as a decision (INV-6). Study text is set
// as text nodes (INV-9). No textarea here: the bridge question uses Hypotrail.wordsArea.
(function (HT) {
  'use strict';
  const SEEN_AFTER_MS = 2000;
  const COLLAPSE_AFTER = 2;

  const local = {
    learn: { prefs: { hideCards: false }, seen: {}, predictions: {} },
    counted: new Set(),       // cards counted in this panel session
    expanded: new Set(),      // collapsed cards the junior opened again in this session
    requested: {},            // `${view}@${revision}` already asked for
    reportOpen: false,
    observer: null,
    timers: new Map(),
  };

  const L = () => HT.copy.learn;

  function loadOnce(ctx, view) {
    const snap = ctx.snapshot;
    if (!snap || ctx.fresh(ctx.data(view))) return;
    const key = `${view}@${ctx.version()}`;
    if (local.requested[key]) return;
    local.requested[key] = true;
    ctx.load(view);
  }

  /** Retry after a load error (CR.1): asked again now, and at the next version anyway. */
  function retryButton(ctx, view) {
    return ctx.el('button', { type: 'button', className: 'secondary', 'data-retry': view, text: L().retry, onclick: () => {
      for (const k of Object.keys(local.requested)) if (k.startsWith(`${view}@`)) delete local.requested[k];
      ctx.retry(view);
      loadOnce(ctx, view);
    } });
  }

  // --- concept cards ------------------------------------------------------------------------

  function cardSteps(snap) {
    const current = snap.currentStep ? snap.currentStep.id : null;
    return (snap.plan || []).filter(s => s.id === current || s.status === 'awaiting_confirmation');
  }

  function conceptTerm(model, stepId) {
    const id = (model.termOrder || Object.keys(model.terms)).find(t => (model.terms[t].steps || []).includes(stepId));
    return id ? { id, ...model.terms[id] } : null;
  }

  function watchSeen(node, cardId, ctx) {
    if (local.counted.has(cardId) || typeof IntersectionObserver !== 'function') return;
    if (!local.observer) {
      local.observer = new IntersectionObserver(entries => {
        for (const e of entries) {
          const id = e.target.getAttribute('data-concept-card');
          const fully = e.isIntersecting && e.intersectionRatio >= 0.99;
          if (fully && !local.timers.has(id) && !local.counted.has(id)) {
            // Test hook (§16): the card is being seen; its two seconds are running.
            e.target.setAttribute('data-seen-timing', 'true');
            local.timers.set(id, setTimeout(() => {
              local.timers.delete(id);
              e.target.removeAttribute('data-seen-timing');
              if (local.counted.has(id) || !e.target.isConnected) return;
              local.counted.add(id);
              HT.send({ type: 'learn_set', key: 'seen', id });
            }, SEEN_AFTER_MS));
          } else if (!fully && local.timers.has(id)) {
            e.target.removeAttribute('data-seen-timing');
            clearTimeout(local.timers.get(id));
            local.timers.delete(id);
          }
        }
      }, { threshold: [0, 0.99, 1] });
    }
    local.observer.observe(node);
  }

  function resetObserver() {
    if (local.observer) local.observer.disconnect();
    local.observer = null;
    for (const t of local.timers.values()) clearTimeout(t);
    local.timers.clear();
  }

  // L3 (R4, D4b): the Learn tab's texts come from `explain`, written in the study language;
  // in a panel of the other language each one is marked with its language, as an engine
  // text is ("(en)" / "(fr)", `lang`).
  function studyMark(node) {
    const study = HT.studyLanguage ? HT.studyLanguage() : 'en';
    const panel = HT.language ? HT.language() : 'en';
    if (!node || study === panel) return node;
    node.setAttribute('lang', study);
    node.appendChild(HT.el('span', study === 'fr'
      ? { className: 'ht-en-marker', 'data-fr-marker': true, text: '(fr)' }
      : { className: 'ht-en-marker', 'data-en-marker': true, text: '(en)' }));
    return node;
  }

  function stepText(ctx, segments) {
    return segments ? studyMark(ctx.components.segments(ctx.el('p'), segments)) : null;
  }

  function card(ctx, model, step, task) {
    const c = L();
    const { el } = ctx;
    const cardId = `${task}:${step.id}`;
    const texts = model.steps[step.id];
    if (!texts) return null;
    const term = conceptTerm(model, step.id);
    const title = term ? term.term : step.title;
    const count = local.learn.seen[cardId] || 0;
    if (count >= COLLAPSE_AFTER && !local.expanded.has(cardId)) {
      return el('p', { 'data-concept-card-link': cardId, 'data-nav': `step:${step.id}` }, [
        el('button', { type: 'button', className: 'ht-link', text: c.showConcept(title),
          onclick: () => { local.expanded.add(cardId); ctx.rerender(); } })]);
    }
    const body = [texts.concept, texts.context, texts.interpretation, texts.consequence];
    const node = el('article', { className: 'card ht-concept', 'data-concept-card': cardId, 'data-nav': `step:${step.id}`,
      'aria-label': `${c.cardLabel}: ${title}` }, [
      el('p', { className: 'ht-tag', text: c.cardLabel }),
      el('h3', {}, [term ? HT.terms.mark(term.term, term.id) : step.title]),
      term ? studyMark(el('p', { className: 'ht-concept-definition', text: term.definition })) : null,
      el('p', { className: 'muted', text: c.cardStep(step.title) }),
      ...body.map(s => stepText(ctx, s)),
      body.some(s => !s) || texts.textStatus === 'needs_results' ? el('p', { className: 'muted', text: c.cardMissing }) : null,
      el('div', { className: 'ht-row' }, [
        HT.askButton(ctx, { kind: 'step', id: step.id }, step.title),
        local.expanded.has(cardId) ? el('button', { type: 'button', className: 'ht-link', text: c.hideConcept,
          onclick: () => { local.expanded.delete(cardId); ctx.rerender(); } }) : null,
      ]),
    ]);
    watchSeen(node, cardId, ctx);
    return node;
  }

  function cards(ctx, model, snap) {
    const c = L();
    const { el } = ctx;
    const hidden = local.learn.prefs.hideCards === true;
    const toggle = el('button', { type: 'button', className: 'secondary', 'data-hide-cards': hidden ? 'false' : 'true',
      'aria-pressed': hidden ? 'true' : 'false', text: hidden ? c.showCards : c.hideCards,
      onclick: () => ctx.send({ type: 'learn_set', key: 'prefs', id: 'prefs', value: { hideCards: !hidden } }) });
    if (hidden) return [el('p', { className: 'muted', 'data-cards-hidden': true, text: c.cardsHidden }), toggle];
    const task = model.task || snap.task || 'binary';
    const list = cardSteps(snap).map(step => card(ctx, model, step, task)).filter(Boolean);
    return [...(list.length ? list : [el('p', { className: 'muted', text: c.noCards })]), toggle];
  }

  // --- predict before you look ----------------------------------------------------------------

  function predictions(ctx, model, snap) {
    const c = L();
    const { el } = ctx;
    const current = snap.currentStep ? snap.currentStep.id : null;
    const reached = new Set((snap.plan || []).filter(s => s.status === 'done' || s.id === current).map(s => s.id));
    const items = (model.predictions || []).filter(q => reached.has(q.step));
    const answers = local.learn.predictions || {};
    if (!items.length) return [el('p', { className: 'muted', text: c.noPredictions })];
    const boxes = items.map(q => {
      const answer = answers[q.id];
      const chosen = q.choices.find(x => x.id === answer);
      return el('section', { className: 'ht-predict', 'data-prediction': q.id, 'aria-label': c.predictTag }, [
        el('p', { className: 'ht-tag', text: c.predictTag }),
        studyMark(el('p', { className: 'ht-question', text: q.question })),
        answer ? el('p', { 'data-answer': answer, text: c.yourAnswer(chosen ? chosen.label : answer) })
          : el('div', { className: 'ht-row', role: 'group', 'aria-label': q.question }, q.choices.map(x => el('button', {
            type: 'button', className: 'secondary', 'data-choice': x.id, text: x.label,
            onclick: () => ctx.send({ type: 'learn_set', key: 'prediction', id: q.id, value: x.id }) }))),
        answer ? el('div', { className: 'ht-reveal', 'data-reveal': q.available ? 'shown' : 'later' }, [
          el('p', { className: 'ht-tag', text: c.revealTitle }),
          q.available ? studyMark(ctx.components.segments(el('p'), q.reveal)) : el('p', { text: c.revealLater }),
        ]) : null,
        el('p', { className: 'muted', 'data-kept-local': true, text: c.keptLocal }),
      ]);
    });
    const any = items.some(q => answers[q.id]);
    return [...boxes, any ? el('button', { type: 'button', className: 'secondary', 'data-reset-predictions': true,
      text: c.resetAnswers, onclick: () => ctx.send({ type: 'learn_set', key: 'reset_predictions', id: 'study' }) }) : null];
  }

  function layer(ctx, snap) {
    const c = L();
    const { el } = ctx;
    loadOnce(ctx, 'explain');
    const data = ctx.data('explain');
    const error = ctx.error('explain');
    const head = el('h3', { id: 'learn-layer-title', text: c.layerTitle });
    let inner;
    if (data && data.model) {
      inner = [
        el('p', { className: 'muted' }, [c.layerIntro, HT.terms.mark(c.layerIntroTerm, 'confirmed_decision'), c.layerIntroEnd]),
        ...cards(ctx, data.model, snap),
        el('h3', { id: 'learn-predict-title', text: c.predictionsTitle }),
        ...predictions(ctx, data.model, snap),
      ];
    } else if (error) {
      inner = [el('div', { className: 'card alert', role: 'alert', 'data-load-error': 'explain' }, [
        el('p', { className: 'title', text: c.layerError }), el('p', { text: error.message }), retryButton(ctx, 'explain')])];
    } else {
      // Until `explain` answers (WP-I replaced the WP-0 placeholder, U5 request R1).
      inner = [el('p', { className: 'muted', 'aria-busy': 'true', 'data-learn-loading': true, text: c.layerReading })];
    }
    return el('section', { className: 'ht-learn-layer', 'data-learning-layer': true, 'aria-labelledby': 'learn-layer-title' },
      [head, ...inner]);
  }

  // --- hand off -----------------------------------------------------------------------------

  function exportOutcome(ctx) {
    const c = L();
    const { el } = ctx;
    const o = ctx.outcome('handoff');
    if (!o) return null;
    const rec = o.recorded || {};
    const ok = o.kind === 'ok' || o.kind === 'ok_with_problems';
    return el('div', { 'data-export-outcome': o.kind }, [
      ctx.renderOutcome(o.kind === 'ok_with_problems' ? { ...o, artifacts: [] } : o),
      ok && o.exitCode === 3 ? el('p', { className: 'hold', 'data-export-stale-report': true, text: c.exportStaleReport }) : null,
      ok && (rec.files || []).length ? el('div', {}, [
        el('p', { text: c.exportFiles }),
        el('ul', { 'data-export-files': true }, rec.files.map(f => el('li', { className: 'ht-mono', text: c.exportFile(f.path, f.bytes) }))),
      ]) : null,
      ok && (rec.warnings || []).length ? el('p', { className: 'hold', 'data-export-warnings': true,
        text: c.exportIncomplete(rec.warnings.join('; ')) }) : null,
      ok && rec.out ? el('p', { className: 'ht-mono', 'data-export-out': true, text: c.exportOut(rec.out) }) : null,
      ok && rec.out ? el('button', { type: 'button', className: 'secondary', 'data-open-export': true, text: c.openFolder,
        onclick: () => ctx.send({ type: 'navigate_external', kind: 'reveal_export', path: rec.out }) }) : null,
    ]);
  }

  /**
   * L7 (owner session 2026-10-26, D15): at `done`, what comes after the study, read only:
   * the engine's junior text (`next_action.after_study.junior_text`) and, when the chosen
   * model is supported, that the Azure ML export plan is asked for in the chat. No control:
   * the only write here stays the handoff pack (W7).
   */
  function afterStudy(ctx, snap) {
    const c = L();
    const { el } = ctx;
    const next = (snap && snap.nextAction) || {};
    const after = next.kind === 'done' ? next.afterStudy : null;
    if (!after || !after.juniorText) return null;
    return el('div', { className: 'ht-after-study', 'data-after-study': after.exportPlanAvailable ? 'export_plan' : 'handoff' }, [
      el('h4', { text: c.afterStudyTitle }),
      el('p', { text: after.juniorText }),
      after.exportPlanAvailable ? el('p', { className: 'muted', 'data-after-study-export': true, text: c.exportPlanInChat }) : null,
    ]);
  }

  function handoff(ctx, snap) {
    const c = L();
    const { el } = ctx;
    const running = ctx.busy && ctx.busyOp === 'W7';
    return el('section', { className: 'ht-handoff', 'data-handoff': true, 'aria-labelledby': 'learn-handoff-title' }, [
      el('h3', { id: 'learn-handoff-title', text: c.handoffTitle }),
      el('p', { text: c.handoffIntro }),
      afterStudy(ctx, snap),
      el('button', { type: 'button', 'data-write': 'export', disabled: ctx.busy ? true : null, 'aria-busy': running ? 'true' : null,
        'aria-describedby': 'learn-export-hint', text: running ? HT.copy.core.working : c.exportButton,
        onclick: () => ctx.send({ type: 'export_handoff', revision: snap.revision }) }),
      el('p', { id: 'learn-export-hint', className: 'muted', text: c.exportFolder }),
      exportOutcome(ctx),
      el('p', { className: 'muted', 'data-reviewer-line': true, text: c.reviewerLine }),
    ]);
  }

  // --- session report -------------------------------------------------------------------------

  function report(ctx) {
    const c = L();
    const { el } = ctx;
    if (local.reportOpen) loadOnce(ctx, 'session_report');
    const data = ctx.data('session_report');
    const error = ctx.error('session_report');
    let inner;
    if (!local.reportOpen) inner = [];
    else if (data && data.model) {
      const m = data.model;
      const list = (items, fn, none) => (items.length ? el('ul', {}, items.map(x => el('li', { text: fn(x) })))
        : el('p', { className: 'muted', text: none }));
      inner = [
        el('p', { className: 'muted', text: c.reportPrivacy }),
        el('p', { className: 'status', 'data-session-log': m.log.enabled ? 'on' : 'off', text: m.log.enabled ? c.logOn : c.logOff }),
        m.log.note ? el('p', { 'data-session-log-note': true, text: m.log.note }) : null,
        m.log.enabled ? null : el('p', { 'data-session-log-instruction': true, text: c.sessionLogOff }),
        el('h4', { text: c.spanTitle }),
        el('p', { text: m.span.first ? c.span(m.span.first, m.span.last, m.span.seconds) : c.spanNone }),
        el('h4', { text: c.pausesTitle }),
        list(m.pauses, p => c.pause(p.pause, p.open ? null : p.seconds), c.noneYet),
        el('h4', { text: c.refusalsTitle }),
        list(m.refusals, r => c.refusal(r.code, r.reason, r.count), c.noRefusals),
        el('h4', { text: c.decisionsTitle }),
        list(m.decisions, d => c.decision(d.decisionId, d.proposalId, d.outcome, d.secondsOpen, d.refusedConfirmations), c.noneYet),
        el('h4', { text: c.gapsTitle }),
        list(m.gaps, g => c.gap(g.from, g.to, g.minutes), c.noGaps),
      ];
    } else if (error) {
      inner = [el('div', { className: 'card alert', role: 'alert', 'data-load-error': 'session_report' }, [
        el('p', { className: 'title', text: c.reportError }), el('p', { text: error.message }), retryButton(ctx, 'session_report')])];
    } else inner = [el('p', { className: 'muted', 'aria-busy': 'true', text: c.reportReading })];
    const details = el('details', { className: 'ht-report', 'data-session-report': true, open: local.reportOpen ? true : null }, [
      el('summary', { text: c.reportTitle }), ...inner]);
    details.addEventListener('toggle', () => {
      if (details.open === local.reportOpen) return;
      local.reportOpen = details.open;
      ctx.rerender();
    });
    return details;
  }

  HT.register('learn', {
    tab: 'learn',
    stage: 'v3',
    views: [],
    outcomes: ['W7'],
    render(model, ctx) {
      resetObserver();
      const { el } = ctx;
      return el('div', { className: 'ht-learn', 'data-view': 'learn' }, [
        el('h2', { text: L().title }),
        ctx.learningLayer ? layer(ctx, model) : null,
        handoff(ctx, model),
        report(ctx),
      ]);
    },
    onMessage(m, ctx) {
      if (m.type === 'init') HT.terms.configure(m);
      else if (m.type === 'snapshot') HT.terms.revision();
      else if (m.type === 'view_data' && m.view === 'explain') HT.terms.setExplain(m.model);
      else if (m.type === 'learn_state') {
        local.learn = { prefs: m.prefs || {}, seen: m.seen || {}, predictions: m.predictions || {} };
      }
      return undefined;
    },
  });
})(globalThis.Hypotrail = globalThis.Hypotrail || {});
