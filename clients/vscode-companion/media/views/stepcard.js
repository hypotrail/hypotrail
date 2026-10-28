// The step card (lot 2026-10-28, docs/plans/LOT-2026-10-28-SPEC.md §2, §5 and the binding §8
// and §9; approved mockup docs/plans/mockups/panel-all-steps-fr.html). A parts provider
// (HT.parts.stepcard) that media/views/page.js calls when the digest carries the engine's step
// cards (`texts.<lang>.step_cards`, schema `hypotrail.step_cards/1`):
//
//   now(ctx, page, h)        Now in four blocks (ST-1, PA-1): 1 the step in one picture, 2 what
//                            the step must establish with the chat's question, 3 to answer, look
//                            (one section per question: chart, three-part reading, folds),
//                            4 what it does not say and what comes next; block 0, the use-case
//                            brief, opens step 1 (R66)
//   questions(ctx, step)     block 2's questions as text, for Now at v0 and v1 (§5)
//   path(ctx, page, h)       the path with full step names (PA-5), a done step opening its
//                            review form (ST-7, PA-4): the decision, then the answers, each
//                            chart opening in place, then the limit
//   cardFor(ctx, step)       the step's card in the panel language, or null
//
// Every question, reading, caption, limit and next line is the engine's, shown as it came
// (ST-2, PA-2): the panel composes no reading and draws no conclusion of its own. A digest
// without step cards (an older engine) leaves Now and the path as they were (PA-2 fallback).
// Nothing here sends a message but the copy button of block 2, which page.js owns.
(function (HT) {
  'use strict';
  const el = (...a) => HT.el(...a);
  const C = () => HT.copy.stepcard;
  const arr = x => (Array.isArray(x) ? x : []);
  const ok = v => typeof v === 'number' && Number.isFinite(v);

  // --- the cards ----------------------------------------------------------------------------

  /** The step cards in the panel language, else in the other one (marked as foreign). */
  function cards(ctx) {
    const sc = ctx.snapshot && ctx.snapshot.stepCards;
    if (!sc) return null;
    const lang = ctx.language();
    const other = lang === 'fr' ? 'en' : 'fr';
    if (sc[lang] && sc[lang].steps.length) return { ...sc[lang], lang };
    if (sc[other] && sc[other].steps.length) return { ...sc[other], lang: other };
    return null;
  }
  function cardFor(ctx, step) {
    const c = cards(ctx);
    return c && step ? c.steps.find(s => s.step === step) || null : null;
  }

  /** An engine text in its language (marked when foreign), never retouched (NOW-1). */
  function et(ctx, text, tag = 'span', attrs = {}) {
    if (!text) return null;
    const c = cards(ctx);
    return HT.components.engineText(text, { tag, lang: c ? c.lang : null, attrs });
  }

  /**
   * A reading sentence with its cited numbers (ST-3): each `cites[].text` found in the
   * sentence becomes a hoverable value naming its result and path. The sentence is the
   * engine's; the panel only wraps the numbers it cites.
   */
  function cited(ctx, text, cites, attrs = {}) {
    if (!text) return null;
    const list = arr(cites).filter(c => c && c.text).sort((a, b) => b.text.length - a.text.length);
    const parts = [];
    let rest = String(text);
    while (rest) {
      let best = null;
      for (const c of list) {
        const i = rest.indexOf(c.text);
        if (i >= 0 && (best === null || i < best.i)) best = { i, c };
      }
      if (!best) { parts.push(rest); break; }
      if (best.i) parts.push(rest.slice(0, best.i));
      const c = best.c;
      parts.push(el('b', {}, [c.resultId || c.path ? ctx.components.cited(c.text, { resultId: c.resultId || '', path: c.path, value: c.value })
        : c.text]));
      rest = rest.slice(best.i + c.text.length);
    }
    const all = cards(ctx);
    const lang = all ? all.lang : null;
    const foreign = Boolean(lang) && lang !== ctx.language();
    return el('span', { ...attrs, lang: foreign ? lang : null, 'data-verbatim': '' }, [...parts,
      foreign ? el('span', { className: 'ht-en-marker', [`data-${lang}-marker`]: true, text: `(${lang})` }) : null]);
  }

  function blockHead(n, label) {
    return el('div', { className: 'sc-bk' }, [el('span', { className: 'sc-n', 'aria-hidden': 'true', text: String(n) }), el('span', { text: label })]);
  }

  function qBadge(q, multi) {
    return multi ? el('span', { className: 'sc-qn', 'data-q-badge': String(q.n), text: `Q${q.n}` }) : null;
  }

  function frameLine(ctx, q) {
    if (!q || !q.frame) return null;
    const label = C().frames[q.frame.evidence] || '';
    return el('p', { className: 'sc-frame', 'data-frame': q.frame.evidence }, [el('b', { text: label }), q.frame.rows ? [' · ', et(ctx, q.frame.rows)] : null]);
  }

  // --- block 3: one section per question --------------------------------------------------------

  function chip(v) {
    if (!v || !v.label) return null;
    return el('span', { className: `sc-chip ${v.met ? 'sc-chip-ok' : 'sc-chip-over'}`, 'data-verdict': v.met ? 'met' : 'not_met',
      title: ok(v.value) && ok(v.bound) ? `${v.value} · ${v.bound}` : null, text: v.label });
  }

  /** ST-3: the three labelled parts; while learning a stale result keeps only "What we see" (ST-11). */
  function reading(ctx, q, { review = false } = {}) {
    const r = q.reading;
    if (!r) return null;
    const c = C();
    const onlySee = q.status === 'stale' && !review;
    const illustrative = q.frame && q.frame.evidence === 'illustration';
    return el('div', { className: 'sc-readx', 'data-reading': q.id }, [
      r.see ? el('p', { className: 'sc-r1', 'data-part': 'see' }, [el('span', { className: 'sc-rl', text: c.see }), cited(ctx, r.see, q.cites), chip(q.verdict)]) : null,
      !onlySee && r.conclude ? el('p', { className: 'sc-r2', 'data-part': 'conclude' }, [el('span', { className: 'sc-rl', text: c.conclude }), cited(ctx, r.conclude, q.cites)]) : null,
      !onlySee && r.cannot ? el('p', { className: 'sc-r3', 'data-part': 'cannot' }, [el('span', { className: 'sc-rl', text: c.cannot }), cited(ctx, r.cannot, q.cites)]) : null,
      el('p', { className: 'sc-src', 'data-cited-revision': q.resultRevision === null ? '' : String(q.resultRevision),
        text: illustrative || q.resultRevision === null ? c.citedNone : c.cited(ctx.format.number(q.resultRevision, 'int')) }),
    ]);
  }

  function statusLine(ctx, q, page) {
    const c = C();
    if (q.status === 'pending') {
      const running = page && page.now && page.now.kind === 'run';
      return el('p', { className: 'sc-pending', 'data-status': 'pending', text: running ? c.pending : c.notComputed });
    }
    if (q.status === 'integrity_failed') return el('p', { className: 'sc-pending', 'data-status': 'integrity_failed', text: c.failed });
    return null;
  }

  function otherCharts(ctx, q, card, id) {
    const others = arr(q.otherCharts).filter(o => o.chart);
    if (!others.length) return null;
    return ctx.fold(`${id}-o`, { summary: C().others(ctx.format.number(others.length, 'int')), className: 'sc-f' }, () => el('div', {},
      others.map(o => el('div', { className: 'sc-other', 'data-other-chart': o.slot || o.chart }, [
        o.slot ? el('p', { className: 'sc-ct', text: HT.components.stepColName(ctx, String(o.slot).split(':')[1] || o.slot) }) : null,
        ...HT.components.stepChart(ctx, { ...q, chart: o.chart, resultId: o.resultId, source: { ...q.source, slot: o.slot } }, card, o.chart, o.slot),
      ]))));
  }

  /** One question's section: the chart open with its frame, the three parts, the folds (ST-1 block 3). */
  function section(ctx, card, q, multi, { idBase, page, review = false }) {
    const c = C();
    const id = `${idBase}-${q.id}`;
    const head = el('div', { className: 'sc-lab' }, [qBadge(q, multi), et(ctx, q.text, 'h4')]);
    const attrs = { className: 'card sc-ev', 'data-question-id': q.id, 'data-question-status': q.status };
    const pending = statusLine(ctx, q, page);
    if (pending) return el('div', attrs, [head, pending]);
    if (q.status === 'no_chart') return el('div', attrs, [head, el('p', { className: 'sc-nochart' }, [el('b', { text: c.noChart }), ' ', et(ctx, card.noChart)]), reading(ctx, q, { review })]);
    const stale = q.status === 'stale';
    const extra = q.chart === 'sample_table' ? HT.components.stepSampleFolds(ctx, (fid, summary, body) => ctx.fold(fid, { summary, className: 'sc-f' }, body), id) : [];
    return el('div', attrs, [
      head,
      stale ? el('p', { className: 'sc-stale-chip', 'data-stale': 'true', text: c.stale }) : null,
      el('div', { className: `sc-chart${stale ? ' sc-stale' : ''}`, 'data-chart': q.chart || 'none' }, HT.components.stepChart(ctx, q, card)),
      reading(ctx, q, { review }),
      ...extra,
      q.folds && q.folds.how ? ctx.fold(`${id}-h`, { summary: c.how, className: 'sc-f' }, () => et(ctx, q.folds.how, 'div')) : null,
      q.folds && q.folds.trap ? ctx.fold(`${id}-t`, { summary: c.trap, className: 'sc-f' }, () => et(ctx, q.folds.trap, 'div')) : null,
      otherCharts(ctx, q, card, id),
    ]);
  }

  // --- block 0: the use-case brief (R66) ------------------------------------------------------------

  function brief(ctx) {
    const snap = ctx.snapshot || {};
    const all = snap.caseBrief;
    if (!all) return null;
    const lang = ctx.language();
    const own = all[lang] ? lang : all[lang === 'fr' ? 'en' : 'fr'] ? (lang === 'fr' ? 'en' : 'fr') : null;
    if (!own) return null;
    const b = all[own];
    const c = C().brief;
    const txt = (t, tag = 'span') => (t ? HT.components.engineText(t, { tag, lang: own }) : null);
    const keys = ['problem', 'decision', 'objective', 'production'];
    // The PO's numbers as the brief writes them (4,5, not 4,50).
    const brief1 = v => (Number.isInteger(v) ? 'int' : 'f1');
    const unit = (n, fallback) => (n && n.unit) || fallback || '';
    const target = ctx.snapshot.criterionConfigurations ? ctx.snapshot.criterionConfigurations.unit : '';
    const numbers = [b.currentMethodError && ok(b.currentMethodError.value) ? c.currentError(ctx.format.number(b.currentMethodError.value, brief1(b.currentMethodError.value)), unit(b.currentMethodError, target)) : null,
      b.targetError && ok(b.targetError.value) ? c.targetError(ctx.format.number(b.targetError.value, brief1(b.targetError.value)), unit(b.targetError, target)) : null].filter(Boolean);
    const links = b.links && typeof b.links === 'object' ? Object.values(b.links).filter(Boolean) : b.links ? [b.links] : [];
    return el('section', { className: 'sc-blk', 'data-block': 'brief' }, [blockHead(0, C().blocks.brief),
      el('div', { className: 'sc-briefcard', 'data-case-brief': own }, [
        // The engine's source line names the brief itself; the panel's label only without it.
        el('p', { className: 'sc-bsrc' }, [b.source && b.source.text ? txt(b.source.text) : c.source,
          b.source && b.source.fictitious ? [' · ', el('b', { 'data-fictitious': true, text: c.fictitious })] : null]),
        el('dl', { className: 'sc-bkey' }, keys.filter(k => b[k]).flatMap(k => [el('dt', { text: c[k] }), txt(b[k], 'dd')])),
        numbers.length ? el('p', { className: 'sc-bnum', 'data-brief-numbers': true, text: numbers.join(' · ') }) : null,
        ...['data_provenance', 'users_and_cost_of_error', 'out_of_scope_and_risks'].filter(k => b[k]).map(k =>
          ctx.fold(`sc-brief-${k}`, { summary: c[k], className: 'sc-more' }, () => txt(b[k], 'div'))),
        links.length ? el('div', { className: 'sc-blink' }, [el('b', { text: c.links }), ...links.map(l => txt(l, 'p'))]) : null,
      ])]);
  }

  // --- Now ------------------------------------------------------------------------------------------

  function budget(ctx, card) {
    if (!['model_variant', 'model_choice'].includes(card.step)) return null;
    const l = ctx.snapshot.ledger;
    const v = l && l.variants;
    if (!v || !ok(v.max) || !ok(v.used)) return null;
    const n = x => ctx.format.number(x, 'int');
    return el('div', { className: 'sc-budget', 'data-budget-bar': `${v.used}/${v.max}` }, [
      el('span', { className: 'sc-bb', 'aria-hidden': 'true' }, Array.from({ length: v.max }, (_, i) => el('i', { className: i < v.used ? 'sc-u' : null }))),
      el('span', {}, [C().budgetTitle, ' ', el('b', { text: C().budget(n(v.used), n(v.max)) })]),
    ]);
  }

  function pause(ctx) {
    const next = ctx.snapshot && ctx.snapshot.nextAction;
    if (!next || next.kind !== 'read_exploration') return null;
    return el('p', { className: 'sc-pause', 'data-pause': 'read_exploration' }, [el('b', { text: C().pause.title }), ' ', C().pause.body]);
  }

  function questionList(ctx, card) {
    const qs = card.questions;
    if (!qs.length) return null;
    const multi = qs.length > 1;
    return el('ol', { className: `sc-qs${multi ? '' : ' sc-one'}`, 'data-step-questions': String(qs.length) },
      qs.map(q => el('li', { 'data-question': q.id }, [qBadge(q, multi), et(ctx, q.text)])));
  }

  function nowHeading(ctx, card) {
    const c = cards(ctx);
    const n = x => ctx.format.number(x, 'int');
    return el('h2', { id: 'ht-now-h', className: 'sc-nowh' }, [C().nowHeading(n(card.n), n(c.total || c.steps.length)),
      el('span', { className: 'sc-full', 'data-step-name': card.step, text: card.name })]);
  }

  /** Now in four blocks (ST-1); `h` are page.js's own helpers (the chat's question, the copy button). */
  function now(ctx, page, h) {
    const nowM = page.now;
    const card = cardFor(ctx, nowM.step) || cardFor(ctx, (cards(ctx) || {}).current);
    if (!card) return null;
    const c = C();
    const qs = card.questions;
    const multi = qs.length > 1;
    const first = qs.find(q => q.frame) || null;
    const idBase = `sc-now-${card.step}`;
    const pic = HT.components.stepPicture(ctx, card.picture);
    return [el('section', { className: 'ht-now sc-now', 'data-block': 'now', 'data-anchor': 'now', 'data-now': nowM.kind,
      'data-now-step': card.step, 'data-step-card': card.step, 'aria-labelledby': 'ht-now-h' }, [
      nowHeading(ctx, card),
      card.n === 1 ? brief(ctx) : null,
      el('section', { className: 'sc-blk', 'data-block': 'picture' }, [blockHead(1, c.blocks.picture),
        el('div', { className: `sc-idea${pic ? '' : ' sc-idea-nopic'}`, 'data-picture': card.picture ? card.picture.kind : '' }, [pic,
          el('div', {}, [card.picture ? et(ctx, card.picture.caption, 'p') : null,
            card.picture && card.picture.more ? ctx.fold(`${idBase}-more`, { summary: c.more, className: 'sc-more' }, () => et(ctx, card.picture.more, 'div')) : null])])]),
      el('section', { className: 'sc-blk', 'data-block': 'establish' }, [blockHead(2, c.blocks.establish),
        card.prepares ? et(ctx, card.prepares, 'p', { className: 'sc-feeds' }) : null,
        questionList(ctx, card),
        budget(ctx, card),
        pause(ctx),
        el('div', { className: 'sc-ask', 'data-chat-block': true }, h.questionParts()),
      ]),
      el('section', { className: 'sc-blk', 'data-block': 'answer' }, [blockHead(3, c.blocks.answer),
        frameLine(ctx, first),
        !qs.length || qs.every(q => q.status === 'no_chart') && card.noChart && !qs.some(q => q.reading)
          ? el('p', { className: 'sc-nochart', 'data-no-chart': true }, [el('b', { text: c.noChart }), ' ', et(ctx, card.noChart)])
          : null,
        ...qs.filter(q => !(q.status === 'no_chart' && !q.reading)).map(q => section(ctx, card, q, multi, { idBase, page })),
      ]),
      el('section', { className: 'sc-blk', 'data-block': 'limit' }, [blockHead(4, c.blocks.limit),
        card.limit ? et(ctx, card.limit, 'p', { className: 'sc-limit' }) : null,
        card.next ? et(ctx, card.next, 'p', { className: 'sc-next' }) : null]),
      ...arr(h.extras),
    ])];
  }

  /** §5: at v0 and v1, Now keeps today's content and lists block 2's questions as text. */
  function questions(ctx, step) {
    const card = cardFor(ctx, step);
    return card ? questionList(ctx, card) : null;
  }

  // --- review (ST-7) and the path (PA-4, PA-5) ---------------------------------------------------------

  function decisionLine(ctx, card) {
    const d = card.decision;
    const c = C();
    if (!d || !d.words) return null;
    return el('p', { className: 'sc-decided', 'data-decided': d.decisionId || card.step, 'data-decided-by': d.who || '' }, [
      el('b', { text: c.decided }), ' ', et(ctx, d.words), d.who ? el('span', { className: 'sc-who2', text: c.who[d.who] || '' }) : null]);
  }

  function review(ctx, card) {
    const c = C();
    const qs = card.questions;
    const multi = qs.length > 1;
    return el('div', { className: 'sc-review', 'data-review': card.step }, [
      decisionLine(ctx, card),
      qs.length ? el('ul', { className: 'sc-recap' }, qs.map(q => el('li', { 'data-question-id': q.id, 'data-question-status': q.status }, [
        el('div', { className: 'sc-rq' }, [qBadge(q, multi), et(ctx, q.text)]),
        q.status === 'no_chart' ? el('div', { className: 'sc-ra' }, [c.noChart, ' ', et(ctx, card.noChart)])
          : q.reading && q.reading.see ? el('div', { className: 'sc-ra', 'data-answer': q.id }, [cited(ctx, q.reading.see, q.cites), chip(q.verdict)])
            : statusLine(ctx, q, null),
        q.status !== 'no_chart' && q.status !== 'pending' ? ctx.fold(`sc-rv-${card.step}-${q.id}`, { summary: c.showChart, className: 'sc-show',
          attrs: { 'data-show-chart': q.id } }, () => {
          const s = section(ctx, card, q, false, { idBase: `sc-rv-${card.step}`, review: true });
          return el('div', { className: 'sc-inplace' }, [frameLine(ctx, q), s]);
        }) : null,
      ]))) : card.noChart ? el('p', { className: 'sc-ra' }, [et(ctx, card.noChart)]) : null,
      card.limit ? et(ctx, card.limit, 'p', { className: 'sc-limit sc-rvlimit' }) : null,
    ]);
  }

  /** PA-5: the path, every step by its full name; a done step opens its review form. */
  function path(ctx, page, h) {
    const c = C();
    const all = cards(ctx);
    if (!all) return null;
    const P = HT.copy.page;
    const items = [];
    for (const ph of page.path.phases) {
      items.push(el('li', { className: 'sc-phl', 'data-phase': ph.moment, text: ph.title }));
      for (const line of ph.steps) {
        const card = cardFor(ctx, line.id);
        const name = card ? `${ctx.format.number(card.n, 'int')} · ${card.name}` : line.title;
        const attrs = { 'data-step': line.id, 'data-step-state': line.state, 'data-anchor': `path:${line.id}`,
          'aria-current': line.state === 'current' ? 'step' : null, title: card ? card.short : null };
        if (line.state === 'current' || (card && card.state === 'current')) {
          items.push(el('li', { className: 'sc-st', ...attrs }, [el('div', { className: 'sc-row' }, [
            el('span', { className: 'sc-mk sc-mk-c', 'aria-hidden': 'true', text: '●' }), el('span', { className: 'sr-only', text: `${c.marks.current} ` }),
            el('span', { className: 'sc-tv' }, [el('span', { className: 'sc-t', text: name }), el('span', { className: 'sc-v', text: c.inProgress })]),
            el('span', { className: 'sc-b', text: c.waitsYou })])]));
        } else if (line.state === 'later' || !card || card.state === 'upcoming') {
          items.push(el('li', { className: 'sc-st sc-later', ...attrs }, [el('div', { className: 'sc-row' }, [
            el('span', { className: 'sc-mk sc-mk-l', 'aria-hidden': 'true', text: '○' }), el('span', { className: 'sr-only', text: `${c.marks.later} ` }),
            el('span', { className: 'sc-tv' }, [el('span', { className: 'sc-t', text: name })])])]));
        } else {
          const mark = { done: '✓', auto: '◇', computed: '◇', again: '↺', stale: '!', held: '‖', delegated: '◇' }[line.state] || '✓';
          items.push(el('li', { className: 'sc-st', ...attrs }, [ctx.fold(`st-${line.id}`, { summary: [
            el('span', { className: `sc-mk sc-mk-d ht-mk-${line.state}`, 'aria-hidden': 'true', text: mark }),
            el('span', { className: 'sr-only', text: `${c.marks.done} ` }),
            el('span', { className: 'sc-tv' }, [el('span', { className: 'sc-t', text: name }), el('span', { className: 'sc-v' }, [h.stepValue(line)])]),
            h.stepBadge(line), el('span', { className: 'sc-chev', 'aria-hidden': 'true', text: '›' })], className: 'sc-step' },
          () => el('div', { className: 'sc-rv' }, [review(ctx, card), ...arr(h.stepExtras(line))]))]));
        }
      }
    }
    return el('section', { className: 'ht-pathblock sc-pathblock', 'data-block': 'path', 'aria-labelledby': 'ht-path-h' }, [
      el('h2', { id: 'ht-path-h', text: P.path }), h.ledger(), el('ul', { className: 'sc-path', 'data-step-card-path': String(all.steps.length) }, items)]);
  }

  HT.parts = HT.parts || {};
  HT.parts.stepcard = { now, questions, path, cardFor, cards, review };
})(globalThis.Hypotrail = globalThis.Hypotrail || {});
