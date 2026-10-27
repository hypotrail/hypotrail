// The one page (ADR 0004 decision 13; COMPANION-ADVANCED §4, §6; approved mockup
// docs/plans/mockups/panel-synthesis-fr.html). It draws, in this fixed order (OP-1, PG-1):
//
//   the sticky region   header (study, theme, more; the pills) and the progress (§6.1, §6.2)
//   To handle           only what lies outside the current step (§6.3)
//   Since your last visit  a fold, from v1 (§6.4)
//   Now                 what the chat waits for, and from v2 the figure that helps answer (§6.5)
//   Waiting             a step the reopened one keeps waiting, its figures marked stale (§6.5.3)
//   The path            the ledger line, then the steps grouped by moment, folded (§6.6)
//   Tools               the drawers: the data, What if?, my notions, deliverables (§6.7)
//   the footer
//
// The placement is the page model's (lib/models/page.js, `ctx.page`); the figures, cards and
// drawers' contents are the other views' parts (`Hypotrail.parts.<view>`). Nothing here
// decides anything about the study (OP-2): every fact is the engine's, every word is the
// panel's copy (media/copy*/page.js) or an engine text in the panel language. The engine's
// options are plain text, never buttons; the only control next to a question copies a ready
// question whose label shows it (OP-3, HON-10). Study text is set as text (INV-9).
(function (HT) {
  'use strict';
  const el = (...a) => HT.el(...a);
  const C = () => HT.copy.page;
  const J = () => HT.copy.junior;
  const str = x => (typeof x === 'string' ? x : '');
  const arr = x => (Array.isArray(x) ? x : []);
  const parts = x => (HT.components.parts ? HT.components.parts(x) : x);
  const PARTS = name => (HT.parts && HT.parts[name]) || {};

  function folderName(study) {
    const p = String(study || '').split(/[\\/]/).filter(Boolean);
    return p[p.length - 1] || '';
  }
  const shortName = (id, title) => ((HT.copy.overview && HT.copy.overview.journeyLabels) || {})[id] || title || id;
  const num = (ctx, n) => (n === null || n === undefined ? '' : ctx.format.number(n, 'int'));

  /** An engine text {text, lang} of the page model, marked "(en)"/"(fr)" in the other language. */
  function engine(t, tag = 'span', attrs = {}) {
    if (!t || !t.text) return null;
    return HT.components.engineText(t.text, { tag, lang: t.lang, attrs });
  }

  // --- the copy button (NOW-3, HON-10) ----------------------------------------------------------

  /** "Copy "<question>"": one press copies the ready question for the chat; nothing is recorded. */
  function copyButton(ctx, about, question, attrs = {}) {
    const c = C();
    const id = `${about.kind}:${about.id}`;
    const done = ctx.copied() === id;
    return el('span', { className: 'ht-copywrap' }, [
      el('button', { type: 'button', className: 'ht-copy', 'data-copy-question': about.id, 'data-focus-id': `copy:${id}`,
        title: c.copyTitle(question), ...attrs, text: c.copy(question),
        onclick: () => {
          ctx.send({ type: 'ask_agent', about: { kind: about.kind, id: String(about.id).slice(0, 100) },
            question: String(question).slice(0, 2000), mode: 'copy' });
          ctx.markCopied(id);
          ctx.rerender();
        } }),
      done ? el('span', { className: 'ht-copied', role: 'status', 'data-copied': true, text: c.copied }) : null,
    ]);
  }

  function askQuestion(step, kind, title, task) {
    const q = C().askQuestions;
    if (kind === 'review') return q.review(J().decisionName ? J().decisionName(step, task) : title || '');
    if (kind === 'done') return q.done;
    return q[step] || q.fallback(title || step || '');
  }

  // --- the sticky region --------------------------------------------------------------------------

  function themeIcon(t) {
    const s = (tag, attrs) => HT.svg(tag, attrs);
    const icon = HT.svg('svg', { width: '14', height: '14', viewBox: '0 0 14 14', 'aria-hidden': 'true', focusable: 'false' });
    if (t === 'dark') icon.appendChild(s('circle', { cx: '7', cy: '7', r: '5.5', fill: 'fg' }));
    else {
      icon.appendChild(s('circle', { cx: '7', cy: '7', r: '5.5', fill: 'none', stroke: 'fg', 'stroke-width': '1.4' }));
      if (t === 'auto') icon.appendChild(s('path', { d: 'M7 1.5a5.5 5.5 0 0 1 0 11z', fill: 'fg' }));
    }
    return icon;
  }

  function sealPill(ctx, seal) {
    const c = C().seal;
    if (!seal) return null;
    const when = seal.openingTime ? ctx.format.localTime(seal.openingTime) : '';
    const changed = seal.changedAfter.map(x => (J().changedName ? J().changedName(x, ctx.snapshot.task) : x)).join(', ');
    const text = { sealed: `🔒 ${c.sealed}`, opened: c.opened, changed: c.changed, absent: c.absent }[seal.kind];
    const hover = { sealed: c.sealedHover(num(ctx, seal.rows)), opened: c.openedHover(when), changed: c.changedHover(changed),
      absent: c.absentHover }[seal.kind];
    return el('span', { className: `ht-pill ht-pill-seal ht-pill-${seal.kind}`, 'data-pill': 'seal', 'data-seal': seal.kind,
      title: hover, text: `${text}${seal.demo ? c.demo : ''}` });
  }

  function defensiblePill(ctx, d) {
    const c = C().defensible;
    const open = ctx.popover() === 'def';
    return el('button', { type: 'button', className: `ht-pill ht-pill-def ht-pill-def-${d.kind}`, 'data-pill': 'defensible',
      'data-defensibility': d.kind, 'data-popover-opener': 'def', 'data-focus-id': 'pill:defensible',
      'aria-haspopup': 'dialog', 'aria-expanded': open ? 'true' : 'false', 'aria-controls': 'ht-pop-def',
      text: c[d.kind](num(ctx, d.count)), onclick: () => ctx.togglePopover('def') });
  }

  function automationPill(a) {
    if (!a) return null;
    const c = C().automation;
    return el('span', { className: 'ht-pill ht-pill-auto', 'data-pill': 'automation', 'data-automation': a.state,
      title: c.hover[a.variant] || '', text: c[a.state] });
  }

  /** The text of a limit item: the engine's junior text in the panel language, else the panel's words. */
  function limitWords(ctx, id) {
    const snap = ctx.snapshot || {};
    const lang = ctx.language();
    const texts = snap.texts || {};
    const own = texts[lang] && texts[lang].limits && texts[lang].limits[id];
    if (own) return { text: own, lang };
    const other = ['en', 'fr'].find(l => l !== lang && texts[l] && texts[l].limits && texts[l].limits[id]);
    if (other) return { text: texts[other].limits[id], lang: other };
    const top = arr((snap.notYetDefensible || {}).top).find(i => i.id === id);
    if (top && top.juniorText) return { text: top.juniorText, lang: snap.language || 'en' };
    return { text: (J().limitText && J().limitText[id]) || J().limitFallback(id), lang };
  }

  function defensibilityPopover(ctx, d) {
    const c = C().defensible;
    return el('div', { className: 'ht-pop', id: 'ht-pop-def', role: 'dialog', tabindex: '-1', 'data-popover': 'def',
      'aria-labelledby': 'ht-pop-def-h' }, [
      el('h3', { id: 'ht-pop-def-h', text: c.headings[d.kind] }),
      el('ol', { 'data-defensibility-items': String(d.items.length) }, d.items.map(i => el('li', { 'data-item': i.id }, [
        engine(limitWords(ctx, i.id)),
        i.severity ? [' ', el('span', { className: `ht-tag ht-sev-${i.severity}`, 'data-severity': i.severity, text: c.severity[i.severity] })] : null,
      ]))),
    ]);
  }

  function radioGroup(label, name, values, current, onPick, attrs = {}) {
    return el('span', { className: 'ht-rg', role: 'radiogroup', 'aria-label': label, ...attrs }, values.map(([v, text]) =>
      el('button', { type: 'button', role: 'radio', 'aria-checked': v === current ? 'true' : 'false', [`data-${name}`]: v,
        'data-focus-id': `${name}:${v}`, lang: name === 'language' ? v : null, text, onclick: () => onPick(v) })));
  }

  function morePopover(ctx, page) {
    const c = C();
    const snap = ctx.snapshot;
    const lang = ctx.language();
    const t = ctx.theme();
    const skew = ctx.init.panelContract !== null && (page ? page.header.skew !== ctx.init.panelContract : false);
    return el('div', { className: 'ht-pop ht-pop-more', id: 'ht-pop-more', role: 'dialog', tabindex: '-1', 'data-popover': 'more',
      'data-more-menu': true, 'aria-label': c.more }, [
      el('div', { className: 'ht-grp' }, [el('span', { id: 'ht-lang-l', text: c.language }),
        radioGroup(c.language, 'language', [['en', c.languageNames.en], ['fr', c.languageNames.fr]], lang, l => ctx.setLanguage(l),
          { 'data-language-toggle': lang, 'aria-labelledby': 'ht-lang-l' })]),
      el('div', { className: 'ht-grp' }, [el('span', { id: 'ht-theme-l', text: c.theme.group }),
        radioGroup(c.theme.group, 'theme', [['auto', c.theme.options.auto], ['dark', c.theme.options.dark], ['light', c.theme.options.light]],
          t, v => ctx.setTheme(v), { 'aria-labelledby': 'ht-theme-l' })]),
      el('button', { type: 'button', className: 'ht-plain', 'data-refresh': true, 'data-focus-id': 'more:refresh', disabled: ctx.busy ? true : null,
        onclick: () => ctx.refreshAll() }, refreshText(ctx)),
      snap && ctx.atLeast('v1') ? el('button', { type: 'button', className: 'ht-plain', 'data-switch-study': true, 'data-stage': 'v1',
        'data-focus-id': 'more:switch', text: c.switchStudy(folderName(snap.study)), onclick: () => ctx.send({ type: 'switch_study' }) }) : null,
      el('button', { type: 'button', className: 'ht-plain', 'data-how': true, 'data-focus-id': 'more:how', text: c.howItWorks,
        onclick: () => ctx.navigate({ anchor: 'tools:how' }) }),
      el('p', { className: 'ht-faint ht-stageline', 'data-stage-line': ctx.stage,
        text: c.stageLine(snap && snap.task ? c.tasks[snap.task] : null, ctx.stage) }),
      skew ? el('p', { className: 'ht-faint', 'data-skew': true, text: c.skew }) : null,
    ]);
  }

  /** "Refresh · read <age> ago, revision N": the age is the view's clock (data-literal="age"). */
  function refreshText(ctx) {
    const c = C();
    const snap = ctx.snapshot;
    if (!snap) return c.reading;
    const line = c.refreshLine('\u0000', snap.revision).split('\u0000');
    return [line[0], el('span', { 'data-literal': 'age', text: ctx.ageText() }), line[1]];
  }

  function progress(ctx, page) {
    const c = C().progress;
    const p = page.progress;
    const bar = el('div', { className: 'ht-bar', 'aria-hidden': 'true' }, p.groups.map(g => {
      const ph = el('span', { className: 'ht-ph', 'data-moment-bar': g.moment, css: { '--n': String(Math.max(1, g.segments.length)) } },
        g.segments.map(s => el('i', { className: `ht-seg-${s.state}`, 'data-seg': s.step || s.state })));
      return ph;
    }));
    let label;
    let sr;
    if (p.mode === 'review') {
      const [a, b] = c.review(num(ctx, p.k), num(ctx, p.n));
      label = [el('b', { text: a }), b];
      sr = c.reviewSr(num(ctx, p.k), num(ctx, p.n));
    } else if (p.mode === 'done') {
      label = [el('b', { text: c.done })];
      sr = c.done;
    } else {
      const [a, b] = c.step(num(ctx, p.index), num(ctx, p.total), p.momentTitle);
      label = [el('b', { text: a }), b];
      sr = c.stepSr(num(ctx, p.index), num(ctx, p.total), p.momentTitle);
    }
    return el('div', { className: 'ht-prog', 'data-block': 'progress', 'data-progress': p.mode }, [
      bar, el('span', { className: 'ht-plbl', 'aria-hidden': 'true' }, label), el('span', { className: 'sr-only', text: sr })]);
  }

  function header(ctx, page) {
    const c = C();
    const snap = ctx.snapshot;
    const t = ctx.theme();
    const hc = ctx.highContrast();
    const name = snap ? folderName(snap.study) : '';
    const themeLabel = `${c.theme.label(c.theme.states[t])}${hc ? ` · ${c.theme.highContrast}` : ''}`;
    const next = { auto: 'dark', dark: 'light', light: 'auto' }[t];
    const pop = ctx.popover();
    const h = page ? page.header : null;
    return el('header', { className: 'ht-top', 'data-block': 'header' }, [
      el('h1', { className: 'sr-only', text: c.title }),
      el('div', { className: 'ht-headrow' }, [
        el('span', { className: 'ht-studyname', title: snap ? snap.study : null, 'data-study-name': true,
          'aria-busy': snap ? null : 'true', text: name || c.reading }),
        el('span', { className: 'ht-btns' }, [
          el('button', { type: 'button', className: 'ht-ib', 'data-theme-control': t, 'data-focus-id': 'theme', 'aria-label': themeLabel,
            title: c.theme.hover, onclick: () => ctx.setTheme(next) }, [themeIcon(t)]),
          el('button', { type: 'button', className: 'ht-ib', 'data-more': true, 'data-popover-opener': 'more', 'data-focus-id': 'more',
            'aria-haspopup': 'dialog', 'aria-expanded': pop === 'more' ? 'true' : 'false', 'aria-controls': 'ht-pop-more',
            'aria-label': c.more, text: '⋯', onclick: () => ctx.togglePopover('more') }),
        ]),
        h && !ctx.loadError() ? el('div', { className: 'ht-pills' }, [
          sealPill(ctx, h.seal), defensiblePill(ctx, h.defensibility), automationPill(h.automation),
          ctx.reviewer ? el('span', { className: 'ht-pill ht-pill-reviewer', 'data-pill': 'reviewer', text: c.reviewer }) : null,
        ]) : null,
      ]),
      page && !ctx.loadError() ? progress(ctx, page) : null,
      pop === 'more' ? morePopover(ctx, page) : null,
      pop === 'def' && h ? defensibilityPopover(ctx, h.defensibility) : null,
    ]);
  }

  // --- To handle (§6.3) ---------------------------------------------------------------------------

  /** An activity in words (the panel's copy), never its token. */
  function activityWords(ctx, activity) {
    const a = C().activities;
    const id = String(activity || '');
    return a[id] || (id.startsWith('eda.') ? a.eda : id.startsWith('diag.') ? a.diag : a.other);
  }

  function todoBlock(ctx, page) {
    const c = C();
    const items = [...page.todo];
    const checks = ctx.atLeast('v1') ? ctx.data('check') : null;
    const findings = checks && checks.model && !checks.model.clean ? arr(checks.model.findings).filter(f => f.severity === 'error') : [];
    if (findings.length) items.push({ kind: 'checks', anchor: 'todo:checks', findings });
    if (!items.length) return null;
    const planIds = arr(ctx.snapshot.plan);
    const stepTitle = activity => {
      const step = HT.pageModel.stepOf(activity, planIds.map(p => p.id));
      const row = planIds.find(p => p.id === step);
      return row ? shortName(row.id, row.title) : activityWords(ctx, activity);
    };
    const lis = [];
    for (const item of items) {
      if (item.kind === 'execution') {
        for (const run of item.runs) {
          const what = activityWords(ctx, run.activity);
          lis.push(el('li', { 'data-anchor': item.anchor, 'data-todo': 'execution', 'data-execution-card': run.executionId }, run.state === 'late'
            ? [el('b', { text: c.run.late(stepTitle(run.activity)) }), el('br'), c.run.lateBody(what)]
            : [el('b', { text: c.run.interrupted(stepTitle(run.activity)) }), el('br'), c.run.body(what),
              el('div', { className: 'ht-acts' }, [copyButton(ctx, { kind: 'execution', id: run.executionId }, c.run.question(what),
                { 'data-ask-execution': run.executionId })])]));
        }
      } else if (item.kind === 'deliverables') {
        const snap = ctx.snapshot;
        const revs = arr(item.artifacts).map(a => a.revision).filter(Number.isInteger);
        const from = revs.length ? Math.min(...revs) : null;
        const label = item.notRendered ? c.notRendered : item.artifacts.length === 1 ? c.deliverablesOne[item.artifacts[0].name] : c.deliverablesItem;
        const o = ctx.outcome('render');
        const working = ctx.busy && ctx.busyTarget === 'render';
        lis.push(el('li', { 'data-anchor': item.anchor, 'data-todo': 'deliverables',
          title: arr(item.artifacts).map(a => str(a.juniorMessage)).filter(Boolean).join(' ') || null }, [
          el('b', { text: label }), el('br'),
          from !== null && from < snap.revision ? c.deliverablesBody(num(ctx, from), num(ctx, snap.revision)) : c.deliverablesBodyUnknown,
          el('div', { className: 'ht-acts' }, [item.regenerate && !ctx.reviewer
            ? el('button', { type: 'button', className: 'ht-act', 'data-write': 'render', 'data-stage': 'v1', disabled: ctx.busy ? true : null,
              'aria-busy': working ? 'true' : null, text: working ? HT.copy.core.working : c.regenerate,
              onclick: () => { if (!ctx.busy) ctx.send({ type: 'render' }); } })
            : el('span', { className: 'ht-off', text: c.askInChat })]),
          o ? (PARTS('overview').renderOutcomeW5 ? PARTS('overview').renderOutcomeW5(o, ctx) : ctx.renderOutcome(o)) : null,
        ]));
      } else if (item.kind === 'sources' || item.kind === 'integrity') {
        const words = limitWords(ctx, item.limit.id);
        lis.push(el('li', { 'data-anchor': item.anchor, 'data-todo': item.kind }, [
          el('b', { text: c[item.kind] }), el('br'), engine(words),
          item.limit.text && item.limit.text !== words.text ? el('details', { className: 'ht-details' }, [
            el('summary', { text: c.details }), el('p', { className: 'muted', text: item.limit.text })]) : null]));
      } else if (item.kind === 'checks') {
        lis.push(el('li', { 'data-anchor': item.anchor, 'data-todo': 'checks' }, [
          el('b', { text: c.checks }), PARTS('overview').findings ? PARTS('overview').findings(ctx, item.findings) : null]));
      }
    }
    return el('section', { className: 'ht-todo', 'data-block': 'todo', 'aria-labelledby': 'ht-todo-h' }, [
      el('h2', { id: 'ht-todo-h', text: c.todo(num(ctx, lis.length)) }), el('ul', {}, lis)]);
  }

  // --- Since your last visit (§6.4, v1) --------------------------------------------------------------

  function sinceBlock(ctx, page) {
    if (!page.since) return null;
    const c = C();
    const n = arr(ctx.snapshot.digest && ctx.snapshot.digest.items).length;
    return ctx.fold('since', { summary: [c.since, el('span', { className: 'ht-count', text: c.sinceCount(n, num(ctx, n)) })],
      className: 'ht-since ht-p', attrs: { 'data-block': 'since', 'data-stage': 'v1' } },
    () => (PARTS('overview').since ? PARTS('overview').since(ctx) : null));
  }

  // --- Now (§6.5) -----------------------------------------------------------------------------------

  function heading(now, c) {
    if (now.kind === 'done') return c.claim;
    if (now.kind === 'review') return c.nowReview;
    const title = now.title || '';
    return now.first ? c.nowFirst(title) : c.now(title);
  }

  /** The question, the engine's options as plain text, their note, the copy button (parts 2-5). */
  function questionParts(ctx, now) {
    const c = C();
    const about = { kind: now.kind === 'review' || now.kind === 'reopened' ? 'decision' : 'step', id: now.step || 'done' };
    const copy = el('div', { className: 'ht-acts' }, [copyButton(ctx, about, askQuestion(now.step, now.kind, now.title, ctx.snapshot.task))]);
    // HON-9: an engine without the question (P1 §17.2.3) still gets "Copy the question", with
    // the panel's own question for the step.
    if (!now.question && !now.options.length) return now.step || now.kind === 'done' ? [copy] : [];
    return [
      now.question ? el('p', { className: 'ht-who', text: c.waitsFor }) : null,
      now.question ? el('h3', { className: 'ht-question', 'data-question': true }, [engine(now.question)]) : null,
      now.options.length ? el('ul', { className: 'ht-opts', 'data-options': true, 'aria-label': c.optionsLead,
        lang: now.optionsLang !== ctx.language() ? now.optionsLang : null }, [
        el('li', { className: 'ht-opts-lead', 'aria-hidden': 'true', text: c.optionsLead }),
        ...now.options.map(o => el('li', { 'data-option': o.id, text: o.label }))]) : null,
      now.optionsNote ? el('p', { className: 'ht-opts-note', 'data-options-note': true }, [engine(now.optionsNote)]) : null,
      copy,
    ];
  }

  function paperCard(kind, title, children, attrs = {}) {
    return el('div', { className: 'card ht-ctx', 'data-context': kind, ...attrs }, [
      el('p', { className: 'ht-k' }, kind === 'proposal' ? [HT.terms.mark(title.eyebrow, 'proposal')] : [title.eyebrow]),
      title.h3 ? el('h3', {}, Array.isArray(title.h3) ? title.h3 : [title.h3]) : null, ...children]);
  }

  function frameLine(kind, text) {
    return el('p', { className: 'ht-frame', 'data-frame': kind }, [el('b', { text }), '']);
  }

  /** NOW-8: the criterion line, from `criterion_configurations` (P1.6), or OV-9's one model. */
  function criterionLine(ctx, now) {
    const c = C().criterion;
    const snap = ctx.snapshot;
    const decision = (snap.decisions || {}).success_criterion;
    // The criterion as decided, else as the summary's criterion states it (an engine before WP-A4).
    const value = decision && decision.value ? decision.value : snap.criterion && snap.criterion.value ? snap.criterion.value : null;
    const raw = value ? (J().value('success_criterion', value, snap.task) || str(value)) : '';
    const words = raw ? raw.charAt(0).toLowerCase() + raw.slice(1) : '';
    const cc = snap.criterionConfigurations;
    if (now.criterion === 'configurations' && cc && cc.bound && cc.bound.value !== null) {
      const regression = snap.task === 'regression' || cc.metric === 'mae_reduction';
      const fmt = x => (regression ? `${ctx.format.number(x, 'f2')}${cc.unit ? ` ${cc.unit}` : ''}` : ctx.format.number(x, 'pct1'));
      const bound = ctx.components.cited(fmt(cc.bound.value), { resultId: cc.bound.resultId, path: cc.bound.path, value: cc.bound.value });
      const configs = cc.configurations.filter(x => x.slot !== 'fit.baseline');
      const final = configs.find(x => x.judgedOn === 'final_test');
      let verdict;
      if (now.kind === 'done' && final) {
        verdict = el('b', { text: c.status[final.status] || final.status });
        return el('p', { className: 'ht-crit', 'data-criterion': 'final' }, parts(c.lineFinal(words, bound, verdict)));
      }
      const meets = configs.filter(x => (x.status === 'not_assessed' ? x.pointMeetsBound : x.status === 'met'));
      const text = meets.length === configs.length ? c.allMet(num(ctx, configs.length))
        : meets.length ? c.someMet(num(ctx, meets.length), num(ctx, configs.length)) : c.noneMet;
      verdict = el('b', { text });
      const detail = el('ul', { className: 'ht-crit-list', 'data-criterion-configurations': String(configs.length) }, configs.map(x => el('li', {
        'data-config': x.slot, 'data-config-status': x.status }, [J().modelName(x.slot, snap.task), ': ',
        x.value !== null ? ctx.components.cited(fmt(x.value), { resultId: x.resultId, path: x.path, value: x.value }) : '', ' · ',
        x.status === 'not_assessed' ? (x.pointMeetsBound ? c.pointOnly : c.pointNot) : c.status[x.status]])));
      return el('div', { className: 'ht-crit', 'data-criterion': 'configurations' }, [el('p', {}, parts(c.line(words, bound, verdict))), detail]);
    }
    if (now.criterion === 'single' && snap.criterion) {
      // OV-9: the one model the summary names, its gain and interval cited (CLI-CONTRACT §11.4).
      const k = snap.criterion;
      const O = HT.copy.overview.criterion;
      const share = k.unit === 'share';
      const has = x => typeof x === 'number' && Number.isFinite(x);
      const signed = x => `${x > 0 ? '+' : ''}${ctx.format.number(x, share ? 'pct1' : 'f1')}`;
      const cite = (x, path) => (k.resultId ? ctx.components.cited(signed(x), { resultId: k.resultId, path, value: x }) : signed(x));
      const rule = k.rule ? J().value('policy', k.rule, snap.task) : null;
      const gain = has(k.gain) ? el('span', { 'data-criterion-gain': true }, [' ',
        share ? O.reduction : O.gain(rule ? rule.charAt(0).toLowerCase() + rule.slice(1) : null),
        cite(k.gain, 'criterion.gain'), share ? '' : O.points,
        has(k.low) && has(k.high) ? [O.interval, cite(k.low, 'criterion.low'), O.to, cite(k.high, 'criterion.high'), O.close] : null,
        '.']) : null;
      return el('p', { className: 'ht-crit', 'data-criterion': 'single', 'data-criterion-status': k.status }, [
        c.single(words, c.status[k.status] || ''), gain]);
    }
    return null;
  }

  function dataCardContext(ctx, now) {
    const c = C();
    if (now.dataCard === 'stage_line') return [el('p', { className: 'ht-next ht-stage-line', 'data-stage-line': 'v2', text: c.dataCardStage('v2') })];
    return [PARTS('eda').nowCard ? PARTS('eda').nowCard(ctx) : null];
  }

  function proposalContext(ctx, now) {
    const c = C();
    const p = now.proposal;
    if (!p) return [];
    const lang = ctx.language();
    const foreign = p.restatementLang && p.restatementLang !== lang;
    const words = J().value(p.decisionId, p.value, ctx.snapshot.task);
    return [paperCard('proposal', { eyebrow: c.proposed, h3: now.title }, [
      el('blockquote', { 'data-restatement': p.proposalId, lang: foreign ? p.restatementLang : null }, [str(p.restatement),
        foreign ? el('span', { className: 'ht-en-marker', 'data-chat-wording': p.restatementLang, text: ` ${c.chatWording(p.restatementLang)}` }) : null]),
      words ? el('p', { className: 'ht-plainsay' }, [el('b', { text: c.inShort }), el('span', { title: str(p.value), 'data-value-raw': str(p.value), text: words })]) : null,
      el('p', { 'data-answer-in-chat': ctx.snapshot.mode || true, text: now.finalTest ? c.finalTestInChat
        : ctx.snapshot.mode === 'training' ? c.answerInChatTraining : c.answerInChat }),
      p.decisionId === 'model_variant' && PARTS('decisions').trials ? PARTS('decisions').trials(ctx) : null,
      now.contingent ? el('p', { className: 'ht-warnline', role: 'note', 'data-contingent': p.proposalId }, [
        el('b', { text: `${c.contingentNote}: ` }), engine(now.contingent)]) : null,
    ], { 'data-proposal-card': p.proposalId })];
  }

  function choiceContext(ctx, now) {
    const c = C();
    if (!ctx.atLeast('v2')) return [el('p', { className: 'ht-next ht-stage-line', 'data-stage-line': 'v2', text: c.comparisonStage('v2') })];
    const ev = PARTS('evidence');
    const question = c.figureQuestion[now.step] || c.figureQuestion.default;
    return [paperCard('choice', { eyebrow: c.toAnswer, h3: question }, [
      frameLine('development', c.frame.development),
      ev.comparison ? ev.comparison(ctx, now.step) : null,
      criterionLine(ctx, now),
    ])];
  }

  function reviewContext(ctx, now) {
    const c = C();
    const d = now.decision || {};
    const raw = now.reviewItem ? now.reviewItem.value : d.value;
    const words = J().value(now.step, raw, ctx.snapshot.task) || str(raw);
    return [paperCard('review', { eyebrow: c.reviewCard, h3: now.title }, [
      el('p', { className: 'ht-frame', 'data-frame': 'automatic' }, [el('b', { text: c.notByYou })]),
      el('p', { className: 'ht-head-line' }, [c.valueLine, el('span', { title: str(raw), 'data-value-raw': str(raw), text: words })]),
      now.digest ? el('p', { className: 'ht-plainsay' }, [el('b', { text: c.toJudge }), engine(now.digest)]) : null,
    ])];
  }

  function reopenedContext(ctx, now) {
    const c = C();
    const reason = PARTS('decisions').queueReason ? PARTS('decisions').queueReason(ctx, now.step) : null;
    return [paperCard('reopened', { eyebrow: c.reopenedCard, h3: c.setAside }, [
      reason ? el('p', { className: 'ht-head-line', 'data-reopened-reason': true, text: reason })
        : now.nextMessage ? el('p', { className: 'ht-head-line', 'data-reopened-reason': true }, [engine(now.nextMessage)]) : null,
    ])];
  }

  function nowContext(ctx, now) {
    const c = C();
    switch (now.kind) {
      case 'data_card': return dataCardContext(ctx, now);
      case 'proposal': return proposalContext(ctx, now).concat(now.figure && ctx.atLeast('v2') ? choiceContext(ctx, now) : []);
      case 'choice': return choiceContext(ctx, now);
      case 'review': return reviewContext(ctx, now);
      case 'reopened': return reopenedContext(ctx, now);
      case 'hold': return [paperCard('hold', { eyebrow: c.holdCard, h3: now.title }, [
        ...now.hold.map(h => el('blockquote', { 'data-hold': h.noteId, text: h.userWords })), el('p', { text: c.holdNote })])];
      case 'run': return [paperCard('run', { eyebrow: c.runCard, h3: now.title }, [el('p', { text: c.runBody(activityWords(ctx, now.activity || now.step)) })])];
      case 'blocked': return [paperCard('blocked', { eyebrow: c.blockedCard, h3: now.requires ? now.requires.title : now.title }, [
        now.nextMessage ? el('p', {}, [engine(now.nextMessage)]) : null])];
      case 'execution': return [paperCard('execution', { eyebrow: c.executionCard, h3: now.title }, [el('p', { text: c.executionBody })])];
      default: return now.nextMessage ? [el('p', { className: 'ht-next' }, [engine(now.nextMessage)])] : [];
    }
  }

  function effectsFold(ctx, now) {
    const c = C();
    if (!now.effects) return null;
    return ctx.fold('effects', { summary: c.effects, className: 'ht-p', attrs: { 'data-stage': 'v1' } }, () => {
      if (now.effects.proposalId && now.kind !== 'review' && PARTS('decisions').effects) return PARTS('decisions').effects(ctx, now.proposal);
      return el('p', { 'data-effects-fixed': now.kind, text: now.kind === 'review' ? c.effectsReview : c.effectsReopened });
    });
  }

  function limitLine(ctx, now) {
    const c = C();
    if (!now.limit) return null;
    const text = now.limit.kind === 'step1' ? c.limitStep1 : now.limit.kind === 'review' ? c.limitReview : null;
    return el('p', { className: 'ht-limit', 'data-limit': now.limit.kind }, [text || engine({ text: now.limit.text, lang: now.limit.lang })]);
  }

  function nextLine(now) {
    const c = C();
    if (!now.next) return null;
    const why = c.whyNext[now.next.id] || '';
    const [a, b] = c.next(now.next.title, why);
    return el('p', { className: 'ht-next', 'data-next': now.next.id }, [el('b', { text: a }), b]);
  }

  /** "What the study can claim" (§6.5.2 `done`), then "And after" (HO-3) and "Your path". */
  function doneBlock(ctx, page) {
    const c = C();
    const now = page.now;
    const snap = ctx.snapshot;
    const conclusion = (snap.decisions || {}).conclusion || null;
    let text = '';
    let basis = conclusion ? conclusion.basis : null;
    if (conclusion && conclusion.value) {
      try {
        const v = JSON.parse(conclusion.value);
        text = str(v.text) || (J().value('conclusion', conclusion.value, snap.task) || str(v.verdict));
      } catch (_) { text = str(conclusion.value); }
    }
    const caveats = arr(page.header.defensibility.items).filter(i => i.severity === 'caveat');
    const card = el('div', { className: 'card ht-ctx', 'data-context': 'done' }, [
      el('p', { className: 'ht-k', text: c.conclusion(c.basis[basis] || '') }),
      el('h3', { 'data-conclusion': true }, [engine({ text, lang: snap.language || 'en' })]),
      ctx.atLeast('v2') && PARTS('evidence').devFinalTable ? PARTS('evidence').devFinalTable(ctx) : null,
      ctx.atLeast('v2') ? criterionLine(ctx, now) : null,
      caveats.length ? ctx.fold('not-say', { summary: c.notSay, className: 'ht-f' },
        () => el('ul', { 'data-not-say': String(caveats.length) }, caveats.map(i => el('li', { 'data-item': i.id }, [engine(limitWords(ctx, i.id))])))) : null,
    ]);
    const j = page.journey;
    const after = now.afterStudy;
    return [
      el('section', { className: 'ht-now', 'data-block': 'now', 'data-anchor': 'now', 'data-now': 'done', 'aria-labelledby': 'ht-now-h' }, [
        el('h2', { id: 'ht-now-h', text: c.claim }), card,
      ]),
      el('section', { className: 'ht-after', 'data-block': 'after', 'aria-labelledby': 'ht-after-h' }, [
        el('h2', { id: 'ht-after-h', text: c.after }),
        ...questionParts(ctx, now),
        after ? el('p', { className: 'ht-next', 'data-after-study': after.exportPlanAvailable ? 'export_plan' : 'handoff' }, [engine({ text: after.juniorText, lang: ctx.snapshot.language || 'en' })]) : null,
        after && after.exportPlanAvailable ? el('p', { className: 'ht-faint', 'data-after-study-export': true, text: c.exportPlanInChat }) : null,
        el('p', { className: 'ht-next', 'data-journey': true, text: c.journey(num(ctx, j.steps), num(ctx, j.ownWords),
          j.looks === null ? null : num(ctx, j.looks), j.openings) }),
      ]),
    ];
  }

  function nowBlock(ctx, page) {
    const c = C();
    const now = page.now;
    if (now.kind === 'done') return doneBlock(ctx, page);
    const learn = PARTS('learn');
    return [el('section', { className: 'ht-now', 'data-block': 'now', 'data-anchor': 'now', 'data-now': now.kind,
      'data-now-step': now.step || '', 'aria-labelledby': 'ht-now-h' }, [
      el('h2', { id: 'ht-now-h', text: heading(now, c) }),
      ...questionParts(ctx, now),
      ...nowContext(ctx, now),
      // NOW-7, EV-7: at the opening of the final test, its card (sealed rows, what must be
      // confirmed first, "a chat act"), from v2; it holds no control.
      now.step === 'final_test' && ctx.atLeast('v2') && PARTS('evidence').finalTest ? PARTS('evidence').finalTest(ctx) : null,
      ctx.atLeast('v3') && ctx.learningLayer && learn.prediction ? learn.prediction(ctx, now.step) : null,
      effectsFold(ctx, now),
      ctx.atLeast('v1') && ctx.snapshot.mode && PARTS('decisions').mode && ['proposal', 'choice', 'review', 'reopened'].includes(now.kind)
        ? ctx.fold('answer-rules', { summary: c.answerRules, className: 'ht-p', attrs: { 'data-stage': 'v1' } }, () => PARTS('decisions').mode(ctx))
        : null,
      limitLine(ctx, now),
      nextLine(now),
    ])];
  }

  // --- Waiting (§6.5.3) ------------------------------------------------------------------------------

  function waitingBlocks(ctx, page) {
    const c = C();
    return page.waiting.map(w => {
      const id = `ht-wait-${w.step}`;
      const reasons = [];
      if (w.reasons.length) reasons.push(el('p', { className: 'ht-warnline', text: c.staleBecause(w.reasons.join('; ')) }));
      for (const a of w.unknown) reasons.push(el('p', { className: 'ht-warnline', text: c.unknownRun(activityWords(ctx, a)) }));
      return el('section', { className: 'ht-waiting', 'data-block': 'waiting', 'data-waiting': w.step, 'aria-labelledby': id }, [
        el('h2', { id, text: c.waiting(w.title) }),
        el('div', { className: `card ht-ctx${w.stale ? ' pg-stale' : ''}`, 'data-stale': w.stale ? 'true' : null }, [
          w.stale ? el('span', { className: 'ht-badge-stale' }, [HT.terms.mark(c.staleBadge, 'stale_result')]) : null,
          el('h3', {}, [el('button', { type: 'button', className: 'ht-link', 'data-goto': `path:${w.step}`,
            text: c.figureQuestion[w.step] || c.figureQuestion.default, onclick: () => ctx.navigate({ anchor: `path:${w.step}` }) })]),
          ...reasons,
        ]),
      ]);
    });
  }

  // --- the path (§6.6) -------------------------------------------------------------------------------

  function ledgerLine(ctx, page) {
    const c = C().ledger;
    const l = page.path.ledger;
    if (!l) return [c.absent];
    const looks = l.targetLooks.total;
    return [el('b', { text: c.label }),
      l.finalTest ? c.finalTest(num(ctx, l.finalTest.openings), num(ctx, l.finalTest.max)) : c.noFinalTest, ' · ',
      c.looks(looks, num(ctx, looks)), l.targetLooks.sample > 0 && looks > 0 ? c.preview : '',
      l.configurations.tried > 0 ? c.tried(num(ctx, l.configurations.tried)) : '',
      l.configurations.tried > 0 && l.configurations.reference ? c.reference : ''];
  }

  function ledgerBlock(ctx, page) {
    const c = C();
    const line = ledgerLine(ctx, page);
    if (!ctx.atLeast('v2')) {
      return el('p', { className: 'ht-ledger', 'data-ledger': true, 'data-anchor': 'path' }, line);
    }
    return ctx.fold('ledger', { summary: line, className: 'ht-ledger ht-p', attrs: { 'data-anchor': 'path', 'data-ledger': true },
      summaryAttrs: { 'data-ledger-line': true } }, () => el('div', { className: 'ht-ledger-body' }, [
      PARTS('evidence').ledgerTable ? PARTS('evidence').ledgerTable(ctx) : null,
      page.path.sampleNote ? el('p', { 'data-sample-note': true }, [engine(page.path.sampleNote)]) : null,
      el('p', { className: 'ht-faint', text: c.ledger.split }),
    ]));
  }

  const MARKS = { done: '✓', current: '●', auto: '◇', computed: '◇', again: '↺', stale: '!', held: '‖', delegated: '◇', later: '○' };

  function stepValue(ctx, line) {
    const c = C();
    if (line.state === 'current') return c.inProgress;
    if (line.headline && line.headline.text) return engine(line.headline.text);
    if (line.decision && line.decision.value) {
      return J().value(line.id, line.decision.value, ctx.snapshot.task) || '';
    }
    return '';
  }

  function stepBadge(line) {
    const c = C().badges;
    const kind = line.state === 'current' ? 'current' : ['auto', 'computed', 'again', 'stale', 'held', 'delegated'].includes(line.state) ? line.state : null;
    return kind ? el('span', { className: `ht-b ht-b-${kind}`, 'data-badge': kind, text: c[kind] }) : null;
  }

  /** A result's name in words (NOW-12: no raw slot in the prose; the slot is in the hover). */
  function slotTitle(ctx, slot) {
    const s = String(slot || '');
    if (s.startsWith('fit.') && J().modelName) {
      const name = J().modelName(s, ctx.snapshot.task);
      return name ? name.charAt(0).toUpperCase() + name.slice(1) : s;
    }
    return activityWords(ctx, s.split(':')[0]);
  }

  function resultFold(ctx, line, r) {
    const c = C();
    const anchor = `path:${line.id}/${r.slot}`;
    if (!r.current) {
      return el('li', { className: 'ht-res', 'data-anchor': anchor, 'data-stale': 'true', 'data-result-slot': r.slot },
        [el('span', { className: 'ht-badge-stale', text: c.staleBadge }), ' ', c.staleResult(r.slot, r.staleReason)]);
    }
    const ev = PARTS('evidence');
    const eda = PARTS('eda');
    const isEda = /^eda\./.test(r.slot);
    const notes = [r.channel === 'webview' ? el('p', { className: 'ht-faint', 'data-from-panel': true, text: c.fromPanelLine }) : null,
      r.channel === 'cli' ? el('p', { className: 'ht-faint', 'data-computed': true, text: c.computedLine }) : null];
    return el('li', { className: 'ht-res', 'data-result-slot': r.slot }, [ctx.fold(`fig-${r.slot}`, {
      summary: [c.seeFigure, el('span', { className: 'ht-faint ht-slot', title: r.slot }, [' · ', isEda && eda.titleNode ? eda.titleNode(ctx, r.slot) : slotTitle(ctx, r.slot)])],
      className: 'ht-fig', attrs: { 'data-anchor': anchor, 'data-stage': 'v2' } }, () => el('div', { className: 'ht-fig-body' }, [
      ...notes,
      isEda && eda.cardFor ? eda.cardFor(ctx, r.slot) : ev.slotFigure ? ev.slotFigure(ctx, line.id, r.slot) : null,
      ctx.fold(`src-${r.slot}`, { summary: c.whereFrom, className: 'ht-f' }, () => (ev.detail ? ev.detail(ctx, r.resultId) : null)),
    ]))]);
  }

  function stepDetail(ctx, line) {
    const c = C();
    const d = line.decision;
    const kids = [];
    // EV-7: the final test's card comes first in its step's detail (figures from v2).
    if (line.id === 'final_test' && ctx.atLeast('v2') && PARTS('evidence').finalTest) kids.push(PARTS('evidence').finalTest(ctx));
    if (d && d.status !== 'open' && d.value) {
      kids.push(el('p', {}, [el('span', { 'data-value-raw': str(d.value), title: str(d.value),
        text: J().value(line.id, d.value, ctx.snapshot.task) || str(d.value) }),
      d.basis ? [' · ', el('span', { className: `ht-basis ht-basis-${d.basis}`, 'data-basis': d.basis,
        text: `${c.basis[d.basis] || d.basis}${d.basis === 'delegated_default' && d.delegationScope ? c.delegatedScope(d.delegationScope) : ''}` })] : null]));
      if (d.userWords && d.basis !== 'automatic') kids.push(el('p', {}, [c.yourWords, el('q', { 'data-user-words': line.id, text: d.userWords })]));
      if (d.basis !== 'automatic' && d.status === 'confirmed') kids.push(el('p', { className: 'ht-faint', text: d.reason ? `${c.reasonGiven}${d.reason}` : c.noReason }));
    }
    if (line.headline && line.headline.results.length) {
      kids.push(el('p', { className: 'ht-src', title: line.headline.results.join(', ') }, [c.source, c.sourceResults(line.headline.results.length, num(ctx, line.headline.results.length))]));
    }
    if (ctx.atLeast('v1') && d && PARTS('decisions').history) kids.push(PARTS('decisions').history(ctx, line.id));
    const stale = line.results.filter(r => !r.current);
    if (ctx.atLeast('v1') && !ctx.atLeast('v2')) {
      for (const r of stale) kids.push(el('p', { className: 'ht-warnline', 'data-stale': 'true', text: c.staleResult(r.slot, r.staleReason) }));
    }
    if (ctx.atLeast('v2') && line.results.length) kids.push(el('ul', { className: 'ht-results' }, line.results.map(r => resultFold(ctx, line, r))));
    if (ctx.atLeast('v1')) {
      kids.push(HT.askButton(ctx, { kind: 'step', id: line.id }, line.title, { label: c.askStep, stage: 'v1', attrs: { 'data-ask-step': line.id } }));
    }
    return el('div', { className: 'pg-detail' }, kids);
  }

  function stepItem(ctx, line) {
    const c = C();
    const mark = MARKS[line.state] || '○';
    const markWord = line.state === 'current' ? c.marks.current : line.state === 'done' ? c.marks.done
      : line.state === 'later' ? c.marks.later : c.marks.flagged;
    const head = [el('span', { className: `ht-mk ht-mk-${line.state}`, 'aria-hidden': 'true', text: mark }),
      el('span', { className: 'sr-only', text: `${markWord} ` }),
      el('span', { className: 'ht-t', title: line.title, text: shortName(line.id, line.title) }),
      el('span', { className: 'ht-v' }, [stepValue(ctx, line)]), stepBadge(line)];
    const attrs = { 'data-step': line.id, 'data-step-state': line.state, 'data-anchor': `path:${line.id}`,
      'aria-current': line.state === 'current' ? 'step' : null };
    if (!line.detail) return el('li', { className: line.state === 'later' ? 'ht-later' : null, ...attrs }, [el('div', { className: 'pg-row' }, head)]);
    return el('li', attrs, [ctx.fold(`st-${line.id}`, { summary: head, className: 'pg-step' }, () => stepDetail(ctx, line))]);
  }

  function phaseItem(ctx, ph) {
    const c = C();
    const steps = () => el('ul', { className: 'pg-steps' }, ph.steps.map(line => stepItem(ctx, line)));
    if (ph.kind === 'later') {
      // A moment not started is one line; each step name keeps its anchor and state (PATH-2, PG-13).
      return el('li', { className: 'ht-later', 'data-phase': ph.moment, 'data-phase-kind': 'later' }, [el('div', { className: 'pg-row' }, [
        el('span', { className: 'ht-mk ht-mk-later', 'aria-hidden': 'true', text: '○' }), el('span', { className: 'sr-only', text: `${c.marks.later} ` }),
        el('span', { className: 'ht-t ht-phase-t', text: ph.title }),
        el('span', { className: 'ht-v' }, ph.steps.map((line, i) => [i ? ' · ' : '', el('span', { 'data-step': line.id,
          'data-step-state': line.state, 'data-anchor': `path:${line.id}`, title: line.title, text: shortName(line.id, line.title) })])),
      ])]);
    }
    if (ph.kind === 'done') {
      return el('li', { 'data-phase': ph.moment, 'data-phase-kind': 'done' }, [ctx.fold(`ph-${ph.moment}`, { summary: [
        el('span', { className: 'ht-mk ht-mk-done', 'aria-hidden': 'true', text: '✓' }), el('span', { className: 'sr-only', text: `${c.marks.done} ` }),
        el('span', { className: 'ht-t ht-phase-t', text: ph.title }), el('span', { className: 'ht-v', text: c.phaseDone(num(ctx, ph.steps.length)) })],
      className: 'ht-phase' }, steps)]);
    }
    const flagWords = Object.entries(ph.counts).map(([f, n]) => (c.flags[f] ? c.flags[f](num(ctx, n)) : null)).filter(Boolean).join(' · ');
    const flagged = Object.keys(ph.counts).length > 0;
    return el('li', { 'data-phase': ph.moment, 'data-phase-kind': 'open' }, [ctx.fold(`ph-${ph.moment}`, { open: true, summary: [
      el('span', { className: `ht-mk ${flagged ? 'ht-mk-again' : ph.current ? 'ht-mk-current' : 'ht-mk-done'}`, 'aria-hidden': 'true',
        text: flagged ? '↺' : ph.current ? '●' : '✓' }),
      el('span', { className: 'sr-only', text: `${flagged ? c.marks.flagged : ph.current ? c.marks.current : c.marks.done} ` }),
      el('span', { className: 'ht-t ht-phase-t', text: ph.title }), el('span', { className: 'ht-v', text: flagWords })],
    className: 'ht-phase' }, steps)]);
  }

  function pathBlock(ctx, page) {
    const c = C();
    return el('section', { className: 'ht-pathblock', 'data-block': 'path', 'aria-labelledby': 'ht-path-h' }, [
      el('h2', { id: 'ht-path-h', text: c.path }),
      ledgerBlock(ctx, page),
      el('ul', { className: 'ht-path' }, page.path.phases.map(ph => phaseItem(ctx, ph))),
    ]);
  }

  // --- tools (§6.7) -----------------------------------------------------------------------------------

  function drawer(ctx, id, summary, content, stage) {
    return ctx.fold(`t-${id}`, { summary, className: 'ht-drawer ht-p',
      attrs: { 'data-drawer': id, 'data-anchor': `tools:${id}`, 'data-stage': stage === 'v0' ? null : stage } }, content);
  }

  function toolsBlock(ctx, page) {
    const c = C();
    const drawers = page.tools.map(t => {
      if (t.id === 'data') return drawer(ctx, 'data', c.drawers.data, () => (PARTS('eda').drawer ? PARTS('eda').drawer(ctx, page) : null), 'v2');
      if (t.id === 'whatif') {
        return drawer(ctx, 'whatif', c.drawers.whatif, () => el('div', { className: 'ht-drawer-body' }, [
          el('p', { className: 'ht-warnline', 'data-whatif-warning': true, text: c.whatifWarning }),
          PARTS('whatif').body ? PARTS('whatif').body(ctx) : null]), 'v2');
      }
      if (t.id === 'notions') return drawer(ctx, 'notions', c.drawers.notions, () => (PARTS('learn').notions ? PARTS('learn').notions(ctx, page) : null), 'v3');
      return drawer(ctx, 'deliverables', c.drawers.deliverables, () => el('div', { className: 'ht-drawer-body' }, [
        PARTS('overview').deliverables ? PARTS('overview').deliverables(ctx) : null,
        ctx.atLeast('v3') && PARTS('learn').handoff ? PARTS('learn').handoff(ctx) : null,
        ctx.atLeast('v3') && PARTS('learn').report ? PARTS('learn').report(ctx) : null,
      ]), 'v0');
    });
    const how = ctx.fold('t-how', { summary: c.howItWorks, className: 'ht-drawer ht-p', attrs: { 'data-anchor': 'tools:how', 'data-how-panel': true } },
      () => el('div', { className: 'ht-drawer-body' }, c.howIntro('v1', 'v2', 'v3').map(t => el('p', { text: t }))));
    return el('section', { className: 'ht-tools', 'data-block': 'tools', 'aria-labelledby': 'ht-tools-h' }, [
      el('h2', { id: 'ht-tools-h', text: c.tools }), ...drawers, how]);
  }

  // --- the page ----------------------------------------------------------------------------------------

  function loadingMain() {
    const c = C();
    return el('main', { id: 'main', 'aria-busy': 'true' }, ['now', 'path', 'tools'].map(b =>
      el('section', { className: 'ht-skeleton', 'data-block': b, 'aria-busy': 'true' }, [el('p', { className: 'muted', text: c.reading })])));
  }

  function errorMain(ctx) {
    const core = HT.copy.core;
    const e = ctx.loadError();
    return el('main', { id: 'main' }, [el('div', { className: 'card alert ht-error-state', role: 'alert', 'data-load-error': true }, [
      el('p', { className: 'title', text: core.loadErrorTitle }),
      el('p', { 'data-next-step': true, text: core.loadErrorNext }),
      ctx.snapshot ? el('p', { className: 'muted', 'data-last-read': true, text: core.lastRead(ctx.snapshot.revision) }) : null,
      el('button', { type: 'button', 'data-retry': true, text: core.retry, onclick: () => ctx.refreshAll() }),
      el('details', { className: 'ht-details' }, [el('summary', { text: core.loadErrorDetail }),
        el('p', { 'data-error-message': true, text: e.message }), e.detail ? el('pre', { text: e.detail }) : null]),
    ])]);
  }

  function footer(ctx, page) {
    const c = C();
    const skew = page && ctx.init.panelContract !== null && page.header.skew !== ctx.init.panelContract;
    return el('footer', { className: 'ht-footer' }, [el('p', { text: c.footer }),
      skew ? el('p', { className: 'ht-faint', 'data-skew': true, text: c.skew }) : null]);
  }

  function render(snapshot, ctx) {
    const page = ctx.page;
    if (ctx.loadError()) return [header(ctx, page), errorMain(ctx), footer(ctx, null)];
    if (!snapshot || !page) return [header(ctx, null), loadingMain(), footer(ctx, null)];
    const main = el('main', { id: 'main' }, [
      todoBlock(ctx, page),
      sinceBlock(ctx, page),
      ...nowBlock(ctx, page),
      ...waitingBlocks(ctx, page),
      pathBlock(ctx, page),
      toolsBlock(ctx, page),
    ]);
    return [header(ctx, page), main, footer(ctx, page)];
  }

  HT.register('page', { stage: 'v0', render });
})(globalThis.Hypotrail = globalThis.Hypotrail || {});
