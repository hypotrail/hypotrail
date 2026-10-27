// What if? view (COMPANION-ADVANCED §6.5, stage v2). WP-U3.
//
// Every state of the tab carries the banner "Experiment, not adopted." (role="note",
// data-experiment; WI-1). Binary: the policy sandbox. A segmented control (Threshold,
// Capacity), a slider and a number input bound to it; each move asks `preview_policy` (the
// controller debounces it and keeps the latest; this view drops an answer whose `seq` is
// not its latest), a release asks it again with paired intervals. The comparison, the
// intervals, and the "Ask the agent to propose this" area update in place, so the slider is
// never re-created under the pointer. Regression: the residual explorer (no slider, none of
// the decision-rule vocabulary). The panel proposes nothing (v0.3 narrowing, ADR 0004
// amendment, integrator decision I2): for a value the engine evaluated, it shows the
// engine's draft and copies a ready question for the chat; the agent proposes it there.
// Rules are named in words ("top 20%"), the recorded token in the hover (R26).
(function (HT) {
  'use strict';
  const RULE = /^(threshold:(0(\.[0-9]+)?|1(\.0+)?)|capacity:[1-9][0-9]{0,6}|share:(0\.[0-9]*[1-9][0-9]*|1(\.0+)?))$/;
  const S = {
    kind: null, value: null, rule: null, seq: 0, sent: {}, preview: null, pending: false,
    drafts: {}, asked: {}, draftRevision: null, draftVersion: null, fit: null, nodes: {}, started: null,
  };

  const C = () => HT.copy.whatif;
  const fmt = (ctx, x, f) => ctx.format.number(x, f);
  const signed = (text, x) => (x > 0 ? `+${text}` : text);
  const count = (ctx, x) => (x === null ? '' : fmt(ctx, x, Number.isInteger(x) ? 'int' : 'f1'));
  const levelText = (ctx, level) => (level === null ? '' : fmt(ctx, level, 'pct1').replace('.0%', '%'));

  // The intervalRows component sizes its label and text columns to their texts (WP-I).
  function intervals(ctx, container, options) {
    return ctx.components.intervalRows(container, options);
  }

  // --- rules ---------------------------------------------------------------------------------

  /** The canonical spelling of records.canonical_rule for the slider's position. */
  function canonical(kind, value) {
    if (kind === 'capacity') return `capacity:${Math.max(1, Math.round(value))}`;
    // WP-B5: a share of the scored rows, in hundredths, never zero.
    if (kind === 'share') return `share:${String(Number(Math.min(1, Math.max(0.01, Math.round(value * 100) / 100)).toFixed(2)))}`;
    const t = Math.min(1, Math.max(0, Math.round(value * 100) / 100));
    return `threshold:${String(Number(t.toFixed(2)))}`;
  }

  function parse(rule) {
    if (typeof rule !== 'string' || !RULE.test(rule)) return null;
    const [kind, number] = rule.split(':');
    return { kind, value: Number(number) };
  }

  function bounds(kind, n) {
    if (kind === 'share') return { min: 0.01, max: 1, step: 0.01 };
    return kind === 'capacity' ? { min: 1, max: Math.max(1, n || 1), step: 1 } : { min: 0, max: 1, step: 0.01 };
  }

  /** A rule token in words (`share:0.2` -> "top 20%"; WP-E1, R26). */
  const ruleWords = rule => HT.copy.junior.ruleShort(rule);

  /** A share (0 to 1) as the percentage of the junior's own parameter (no figure of results). */
  const percent = p => HT.copy.junior.sharePercent(p) || '';
  const rowsWord = model => C().binary.rows[model.evaluation] || null;

  function proposalRule(snapshot) {
    const p = snapshot && (snapshot.proposals || []).find(x => x.decisionId === 'policy' && RULE.test(x.value));
    return p ? p.value : null;
  }

  function adoptedRule(snapshot) {
    const d = snapshot && snapshot.decisions && snapshot.decisions.policy;
    return d && d.status === 'confirmed' && RULE.test(d.value) ? d.value : null;
  }

  // --- messages ------------------------------------------------------------------------------

  function askPreview(ctx, intervals) {
    S.seq += 1;
    S.sent = { [S.seq]: { rule: S.rule, intervals } };
    S.pending = true;
    ctx.send({ type: 'preview_policy', rules: [S.rule], intervals, seq: S.seq });
  }

  // Drafts are kept for the snapshot version they were asked at (revision, currency, and
  // Refresh epoch; CR.1); a new version drops them. The message carries the revision.
  function drafts(ctx) {
    const revision = ctx.snapshot ? ctx.snapshot.revision : 0;
    const version = ctx.version();
    if (S.draftVersion !== version) {
      S.draftVersion = version;
      S.draftRevision = revision;
      S.drafts = {};
      S.asked = {};
    }
    return S.drafts;
  }

  const draftKey = (decisionId, value) => `${decisionId}|${value}`;

  function askDraft(ctx, decisionId, value) {
    const key = draftKey(decisionId, value);
    if (drafts(ctx)[key] || S.asked[key]) return;
    S.asked[key] = true;
    ctx.send({ type: 'draft', decisionId, value, revision: Math.max(1, S.draftRevision) });
  }

  function currentDraft(ctx, decisionId, value) {
    return drafts(ctx)[draftKey(decisionId, value)] || null;
  }

  // --- shared pieces -------------------------------------------------------------------------

  function banner(ctx) {
    const c = C().common;
    return ctx.el('div', { className: 'ht-experiment ht-wi-banner', role: 'note', 'data-experiment': true }, [
      ctx.el('span', { className: 'ht-wi-icon', 'aria-hidden': 'true', text: '⚗' }),
      ctx.el('strong', { text: c.bannerStrong }), c.bannerRest,
    ]);
  }

  function deltaSentence(ctx, side) {
    const c = C().common;
    return ctx.el('p', { 'data-delta-sentence': side, text: side === 'one_side' ? c.oneSide : side === 'includes_zero' ? c.includesZero : C().binary.undefinedDelta });
  }

  /**
   * The engine's draft and "Ask the agent to propose this" (a ready question copied for the
   * chat, no write; WP-E1), or why the value cannot be proposed yet.
   */
  function proposeArea(ctx, decisionId, value, evaluated, t, families) {
    const common = C().common;
    const kids = [];
    const words = decisionId === 'policy' ? ruleWords(value) : fitLabel(t, value, families);
    if (!evaluated) {
      kids.push(ctx.el('p', { 'data-not-evaluated': value, text: t.notEvaluated }));
      if (decisionId === 'policy') {
        // The shared agent-bridge helper of media/terms.js (§6.8; WP-I).
        kids.push(HT.askButton(ctx, { kind: 'decision', id: 'policy' }, t.askAbout(words),
          { label: t.askEvaluate(words), attrs: { 'data-ask-agent': 'evaluate' }, question: t.askEvaluateQuestion(words, value) }));
      }
    } else {
      const draft = currentDraft(ctx, decisionId, value);
      if (!draft) {
        askDraft(ctx, decisionId, value);
        kids.push(ctx.el('p', { className: 'muted', 'aria-busy': 'true', text: common.readingDraft }));
      } else if (!draft.proposable) {
        kids.push(ctx.el('p', { 'data-not-evaluated': value, text: t.notEvaluated }));
      } else {
        kids.push(ctx.el('div', { className: 'card ht-wi-draft', 'data-draft': value }, [
          ctx.el('p', { className: 'title' }, [ctx.el('span', { className: 'ht-wi-label', text: common.draftOnly }), ' ', draft.note]),
          ctx.el('blockquote', { 'data-draft-restatement': true, text: draft.restatement }),
          ctx.el('p', { className: 'muted', text: draft.rationale }),
        ]));
        kids.push(ctx.el('div', { className: 'ht-wi-propose' }, [
          HT.askButton(ctx, { kind: 'decision', id: decisionId }, t.askAbout(words),
            { label: t.propose, attrs: { 'data-ask-propose': value, 'aria-describedby': 'ht-wi-propose-hint' },
              question: t.askProposeQuestion(words, value), direct: true }),
          ctx.el('span', { id: 'ht-wi-propose-hint', className: 'muted', text: common.proposeHint }),
        ]));
      }
    }
    return ctx.el('section', { className: 'ht-wi-propose-area', 'data-propose-area': value, 'aria-live': 'polite' }, kids);
  }

  // --- binary: policy sandbox ----------------------------------------------------------------

  function evaluatedRule(model, rule) {
    return model.evaluatedRules.some(r => r.rule === rule);
  }

  function startPosition(ctx, model) {
    const rule = proposalRule(ctx.snapshot) || adoptedRule(ctx.snapshot) || model.initialRule || 'threshold:0.5';
    const p = parse(rule) || { kind: 'threshold', value: 0.5 };
    S.kind = p.kind;
    S.value = p.kind === 'capacity' ? Math.min(p.value, Math.max(1, model.n || p.value)) : p.value;
    S.rule = canonical(S.kind, S.value);
  }

  function labelText(t, ctx) {
    if (S.kind === 'share') return t.shareLabel(percent(S.value));
    return S.kind === 'capacity' ? t.capacityLabel(fmt(ctx, S.value, 'int')) : t.thresholdLabel(String(Number(S.value.toFixed(2))));
  }

  function valueText(t, ctx) {
    if (S.kind === 'share') return t.valueText.share(percent(S.value));
    return S.kind === 'capacity' ? t.valueText.capacity(fmt(ctx, S.value, 'int')) : t.valueText.threshold(String(Number(S.value.toFixed(2))));
  }

  function shareLine(ctx, model, t) {
    if (S.kind === 'share') return ctx.el('p', { className: 'muted ht-wi-share', 'data-share': 'share', text: t.shareKind });
    if (S.kind !== 'capacity' || !model.n) return ctx.el('p', { className: 'muted ht-wi-share', 'data-share': true });
    const parts = t.share(fmt(ctx, S.value, 'int'), fmt(ctx, model.n, 'int'), null, rowsWord(model));
    // k / n is the only ratio the panel computes: a restatement of the junior's own parameter.
    return ctx.el('p', { className: 'muted ht-wi-share', 'data-share': true }, [parts[0],
      ctx.el('span', { 'data-literal': 'parameter', text: fmt(ctx, S.value / model.n, 'pct1') }), parts[2]]);
  }

  function setValue(ctx, model, value, { release }) {
    const b = bounds(S.kind, model.n);
    const v = Math.min(b.max, Math.max(b.min, Number(value)));
    if (!Number.isFinite(v)) return;
    S.value = S.kind === 'capacity' ? Math.round(v) : Math.max(b.min, Math.round(v * 100) / 100);
    S.rule = canonical(S.kind, S.value);
    // A repeated event for what was already asked (a blur after a change) changes nothing.
    const last = S.sent[S.seq];
    if (last && last.rule === S.rule && (last.intervals || !release)) return;
    const t = C().binary;
    const n = S.nodes;
    if (n.slider) { n.slider.value = String(S.value); n.slider.setAttribute('aria-valuetext', valueText(t, ctx)); }
    if (n.number) n.number.value = String(S.value);
    if (n.label) n.label.textContent = labelText(t, ctx);
    if (n.share) n.share.replaceWith(n.share = shareLine(ctx, model, t));
    askPreview(ctx, release);
    if (n.comparison) n.comparison.replaceWith(n.comparison = comparison(ctx, model));
    if (n.propose) n.propose.replaceWith(n.propose = release ? binaryPropose(ctx, model) : pendingPropose(ctx));
  }

  function pendingPropose(ctx) {
    return ctx.el('section', { className: 'ht-wi-propose-area', 'data-propose-area': S.rule }, [
      ctx.el('p', { className: 'muted', text: C().binary.intervalsPending })]);
  }

  function binaryPropose(ctx, model) {
    return proposeArea(ctx, 'policy', S.rule, evaluatedRule(model, S.rule), C().binary);
  }

  function controls(ctx, model) {
    const t = C().binary;
    const b = bounds(S.kind, model.n);
    const pick = kind => {
      if (kind === S.kind) return;
      S.kind = kind;
      const known = model.evaluatedRules.map(r => parse(r.rule)).find(p => p && p.kind === kind);
      S.value = known ? known.value : kind === 'capacity' ? Math.min(100, Math.max(1, model.n || 1)) : kind === 'share' ? 0.1 : 0.5;
      S.rule = canonical(S.kind, S.value);
      askPreview(ctx, true);
      ctx.rerender();
    };
    const label = ctx.el('label', { for: 'ht-wi-slider', id: 'ht-wi-slider-label', 'data-rule-label': true, text: labelText(t, ctx) });
    const slider = ctx.el('input', { type: 'range', id: 'ht-wi-slider', min: b.min, max: b.max, step: b.step, value: S.value,
      'aria-valuetext': valueText(t, ctx), 'data-slider': S.kind });
    slider.value = String(S.value);
    slider.addEventListener('input', () => setValue(ctx, model, slider.value, { release: false }));
    slider.addEventListener('change', () => setValue(ctx, model, slider.value, { release: true }));
    slider.addEventListener('keydown', e => {
      if (e.key !== 'PageUp' && e.key !== 'PageDown') return;
      e.preventDefault();
      const step = (b.max - b.min) / 10;
      setValue(ctx, model, S.value + (e.key === 'PageUp' ? step : -step), { release: true });
    });
    const number = ctx.el('input', { type: 'number', id: 'ht-wi-number', min: b.min, max: b.max, step: b.step, value: S.value,
      'aria-label': t.numberLabel, 'data-number': S.kind });
    number.value = String(S.value);
    number.addEventListener('change', () => setValue(ctx, model, number.value, { release: true }));
    const share = shareLine(ctx, model, t);
    Object.assign(S.nodes, { slider, number, label, share });
    return ctx.el('section', { className: 'card ht-wi-rule', 'aria-labelledby': 'ht-wi-rule-h' }, [
      ctx.el('div', { className: 'ht-wi-row' }, [
        ctx.el('h3', { id: 'ht-wi-rule-h', text: t.ruleTitle }),
        ctx.el('div', { role: 'group', 'aria-label': t.ruleType, className: 'ht-segmented' }, ['threshold', 'capacity', 'share'].map(kind =>
          ctx.el('button', { type: 'button', 'aria-pressed': kind === S.kind ? 'true' : 'false', 'data-rule-kind': kind,
            className: kind === S.kind ? '' : 'secondary', text: t.kinds[kind], onclick: () => pick(kind) }))),
      ]),
      label,
      ctx.el('div', { className: 'ht-wi-slider-row' }, [slider, number]),
      share,
    ]);
  }

  function fitName(t, fit) {
    return t.fits[fit] || fit;
  }

  // A regression fit slot in words (R9UX-5): the copy's name, a variant without one named
  // generically, and the model family the engine recorded for a variant, when it has one.
  function fitLabel(t, fit, families) {
    const slot = String(fit);
    const base = (t.fits && t.fits[slot]) || (slot.startsWith('fit.variant') && t.variantFit) || slot;
    const family = families && families[slot];
    const familyName = family && t.families && t.families[family];
    return familyName && t.familyFit ? t.familyFit(base, familyName) : base;
  }

  function comparison(ctx, model) {
    const t = C().binary;
    const common = C().common;
    const p = S.preview;
    const kids = [ctx.el('h3', { id: 'ht-wi-cmp-h', title: p ? p.rule : S.rule, text: t.comparisonTitle(ruleWords(p ? p.rule : S.rule)) })];
    if (!p) {
      kids.push(ctx.el('p', { className: 'muted', text: S.pending ? common.updating : t.noPreview }));
      return ctx.el('section', { className: 'card ht-wi-comparison', 'data-experiment': true, 'aria-labelledby': 'ht-wi-cmp-h' }, kids);
    }
    const stale = S.pending || p.rule !== S.rule;
    const entry = p.model.byRule[p.rule];
    const fits = p.model.fits;
    if (stale) kids.push(ctx.el('p', { className: 'muted', role: 'status', 'data-updating': true, text: common.updating }));
    const body = ctx.el('div', { className: stale ? 'ht-pending' : null, 'data-preview-rule': p.rule });
    for (const metric of ['precision', 'recall']) {
      ctx.components.bars(body, {
        title: t.metricAt(t.metrics[metric], ruleWords(p.rule), rowsWord(model)), max: 1, unit: t.metrics[metric], rule: null,
        items: fits.map(fit => {
          const v = entry.models[fit][metric];
          return { label: fitName(t, fit), value: v === null ? 0 : v, valueText: v === null ? t.notDefined : fmt(ctx, v, 'pct1'), small: false, cited: null,
            tone: fit === 'fit.baseline' || fit === p.model.reference ? 'baseline' : null };
        }),
      });
    }
    body.appendChild(ctx.el('ul', { className: 'ht-wi-counts' }, fits.map(fit => {
      const m = entry.models[fit];
      return ctx.el('li', { text: t.counts(fitName(t, fit), count(ctx, m.selected), count(ctx, m.truePositives)) });
    })));
    if (fits.some(fit => (entry.models[fit].tiedAtCut || 0) > 0)) body.appendChild(ctx.el('p', { 'data-tie': true, text: t.tie }));
    if (!p.model.modelsCurrent) body.appendChild(ctx.el('p', { className: 'hold', text: t.modelsNotCurrent }));
    for (const w of p.model.warnings) body.appendChild(ctx.el('div', { className: 'card ht-warn', role: 'note', 'data-preview-warning': true }, [ctx.el('p', { text: w })]));
    // Paired intervals (after a release).
    const iv = p.intervals && entry.intervals ? entry : null;
    if (iv) {
      const candidate = fits.find(f => f !== p.model.reference);
      const delta = candidate && entry.deltas && entry.deltas[candidate] ? entry.deltas[candidate].precision : null;
      const box = ctx.el('div', { className: 'ht-wi-intervals', 'data-intervals': p.rule });
      const interval = r => (r.low === null || r.high === null ? '' : `[${fmt(ctx, r.low, 'pct1')}, ${fmt(ctx, r.high, 'pct1')}]`);
      intervals(ctx, box, { title: t.metricAt(t.metrics.precision, ruleWords(p.rule), rowsWord(model)), zero: false,
        rows: fits.map(fit => {
          const point = entry.models[fit].precision;
          const r = entry.intervals[fit].precision;
          return { label: fitName(t, fit), point, low: r.low, high: r.high, tone: fit === p.model.reference || fit === 'fit.baseline' ? 'baseline' : null,
            pointText: point === null ? t.notDefined : fmt(ctx, point, 'pct1'), intervalText: interval(r) };
        }) });
      if (delta) {
        const f3 = x => signed(fmt(ctx, x, 'f3'), x);
        intervals(ctx, box, { title: t.intervalsTitle, zero: true,
          rows: [{ label: t.intervalRow(fitName(t, candidate), fitName(t, p.model.reference)), point: delta.point, low: delta.low, high: delta.high,
            pointText: delta.point === null ? t.notDefined : f3(delta.point),
            intervalText: delta.low === null || delta.high === null ? '' : `[${f3(delta.low)}, ${f3(delta.high)}]` }] });
        box.appendChild(deltaSentence(ctx, delta.side));
      }
      const b = entry.bootstrap;
      if (b && b.replicates !== null) box.appendChild(ctx.el('p', { className: 'muted', 'data-bootstrap': true,
        text: common.bootstrap(fmt(ctx, b.replicates, 'int'), levelText(ctx, b.level)) }));
      body.appendChild(box);
    } else {
      body.appendChild(ctx.el('p', { className: 'muted', text: t.intervalsPending }));
    }
    kids.push(body);
    return ctx.el('section', { className: 'card ht-wi-comparison', 'data-experiment': true, 'aria-labelledby': 'ht-wi-cmp-h' }, kids);
  }

  function smallData(ctx) {
    const top = (ctx.snapshot && ctx.snapshot.notYetDefensible && ctx.snapshot.notYetDefensible.top) || [];
    return top.filter(i => i.id === 'small_validation_partition' || i.id === 'capacity_exceeds_validation')
      .map(i => ctx.el('div', { className: 'card ht-warn', role: 'note', 'data-small-data': i.id }, [ctx.el('p', { text: i.text })]));
  }

  function evaluatedTable(ctx, model) {
    const t = C().binary;
    if (!model.evaluatedRules.length) {
      return ctx.el('section', { className: 'card ht-wi-evaluated', 'aria-labelledby': 'ht-wi-ev-h' }, [
        ctx.el('h3', { id: 'ht-wi-ev-h', text: t.evaluatedTitle }), ctx.el('p', { className: 'muted', 'data-no-evaluation': true, text: t.noEvaluation })]);
    }
    const adopted = adoptedRule(ctx.snapshot);
    const proposed = proposalRule(ctx.snapshot);
    const cite = (x, path, f) => (x === null ? t.notDefined : { text: f(x), cited: { resultId: model.resultId, path, value: x } });
    const table = ctx.components.valuesTable(null, {
      columns: [{ key: 'rule', label: t.columns.rule }, { key: 'selected', label: t.columns.selected },
        { key: 'tp', label: t.positives(model.targetLabel) }, { key: 'precision', label: t.columns.precision },
        { key: 'recall', label: t.columns.recall }, { key: 'status', label: t.columns.status }],
      rows: model.evaluatedRules.map(r => ({
        rule: ruleWords(r.rule),
        selected: cite(r.selected, r.paths.selected, x => count(ctx, x)),
        tp: cite(r.truePositives, r.paths.truePositives, x => count(ctx, x)),
        precision: cite(r.precision, r.paths.precision, x => fmt(ctx, x, 'pct1')),
        recall: cite(r.recall, r.paths.recall, x => fmt(ctx, x, 'pct1')),
        status: r.rule === adopted ? t.status.adopted : r.rule === proposed ? t.status.proposed : t.status.evaluated,
      })),
    });
    table.setAttribute('data-evaluated-rules', String(model.evaluatedRules.length));
    table.setAttribute('aria-labelledby', 'ht-wi-ev-h');
    for (const [i, tr] of [...table.querySelectorAll('tbody tr')].entries()) tr.setAttribute('data-evaluated-rule', model.evaluatedRules[i].rule);
    return ctx.el('section', { className: 'card ht-wi-evaluated', 'aria-labelledby': 'ht-wi-ev-h' }, [
      ctx.el('h3', { id: 'ht-wi-ev-h', text: t.evaluatedTitle }), table]);
  }

  /**
   * WP-B5: the gain curve of the registered points (the engine's gain points at 5, 10 and
   * 20 % and every evaluated rule with the share it acts on), with the junior's rule and the
   * case's scenario share as marks. "Try this share" moves the slider (a preview, read only);
   * proposing is asked of the agent in the chat (the area below).
   */
  function gainView(ctx, model) {
    const t = C().binary;
    const g = t.gain;
    const gain = model.gain;
    const kids = [ctx.el('h3', { id: 'ht-wi-gain-h', text: g.title })];
    if (!gain || (!gain.points.length && !gain.rules.length)) {
      kids.push(ctx.el('p', { className: 'muted', 'data-no-gain': true, text: g.noGain }));
      return ctx.el('section', { className: 'card ht-wi-gain', 'aria-labelledby': 'ht-wi-gain-h', 'data-gain': 'none' }, kids);
    }
    const pct0 = x => fmt(ctx, x, 'pct0');
    const pct1 = x => fmt(ctx, x, 'pct1');
    const byShare = new Map();
    for (const p of gain.points) byShare.set(p.share, { share: p.share, recall: p.recall, precision: p.precision, paths: p.paths,
      rule: p.rule, source: g.sourcePoint });
    for (const r of gain.rules) {
      const known = byShare.get(r.share);
      if (known && known.rule === r.rule) { known.source = g.sourceRule(ruleWords(r.rule)); known.evaluated = r.rule; continue; }
      byShare.set(`${r.share}|${r.rule}`, { share: r.share, recall: r.recall, precision: r.precision, paths: r.paths, rule: r.rule,
        source: g.sourceRule(ruleWords(r.rule)), evaluated: r.rule });
    }
    const rows = [...byShare.values()].sort((a, b) => a.share - b.share);
    const adopted = adoptedRule(ctx.snapshot) || proposalRule(ctx.snapshot);
    const scenario = ctx.data('scenario');
    const assumed = scenario && scenario.model && scenario.model.capacityShare ? scenario.model.capacityShare.value : null;
    const mine = adopted ? gain.rules.find(r => r.rule === adopted) : null;
    const marks = [mine ? { x: mine.share, label: g.yourRule, tone: 'accent' } : null,
      assumed !== null ? { x: assumed, label: g.scenarioMark, tone: 'experiment' } : null].filter(Boolean);
    const cite = (x, path, f) => (x === null ? '' : { text: f(x), cited: { resultId: gain.resultId, path, value: x } });
    // The axes are cut to the points' range (a quarter, a half, or all of the rows), so the
    // registered points are not crowded into a corner; the diagonal is drawn on that range.
    const top = v => [0.25, 0.5, 1].find(t => v <= t) || 1;
    const xMax = top(Math.max(...rows.map(r => r.share), ...marks.map(m => m.x)));
    const yMax = top(Math.max(...rows.map(r => r.recall)));
    const ticksOf = m => [0, m / 2, m].map(v => ({ value: v, text: `${Math.round(v * 1000) / 10}%` }));
    const box = ctx.el('div', { className: 'ht-wi-gain-chart', 'data-gain-chart': String(rows.length) });
    ctx.components.curve(box, { title: g.question, xDomain: [0, xMax], yDomain: [0, yMax], xTicks: ticksOf(xMax), yTicks: ticksOf(yMax),
      xLabel: g.x, yLabel: g.y,
      diagonal: { label: g.random, at: 0.6 }, marks,
      points: rows.map(r => ({ x: r.share, y: r.recall, label: `${pct0(r.share)}: ${pct0(r.recall)}` })),
      columns: [{ key: 'share', label: g.columns.share }, { key: 'recall', label: g.columns.recall },
        { key: 'precision', label: g.columns.precision }, { key: 'source', label: g.columns.source }],
      rows: rows.map(r => ({ share: cite(r.share, r.paths.share, pct1), recall: cite(r.recall, r.paths.recall, pct1),
        precision: cite(r.precision, r.paths.precision, pct1), source: r.source })) });
    kids.push(box);
    kids.push(ctx.el('p', { className: 'muted', text: g.caption(rowsWord(model) || t.rows.validation, fmt(ctx, gain.n, 'int')) }));
    kids.push(ctx.el('p', { 'data-gain-why': true, text: g.why }));
    if (assumed !== null) {
      kids.push(ctx.el('p', { className: 'ht-wi-scenario', 'data-scenario-share': String(assumed) }, [
        ctx.el('span', { className: 'ht-status ht-st-stale', 'data-literal': 'parameter', text: g.scenarioChip }), ' ',
        g.scenario(percent(assumed))]));
    }
    const status = r => (r.evaluated && r.evaluated === adoptedRule(ctx.snapshot) ? t.status.adopted
      : r.evaluated && r.evaluated === proposalRule(ctx.snapshot) ? t.status.proposed : r.evaluated ? t.status.evaluated : g.sourcePoint);
    const cell = c => (c && typeof c === 'object' ? ctx.components.cited(c.text, c.cited) : c || '');
    const head = ['share', 'recall', 'precision', 'status'].map(k => ctx.el('th', { scope: 'col', text: g.columns[k] }));
    const table = ctx.el('table', { className: 'ht-values ht-wi-gain-table', 'data-gain-table': String(rows.length) }, [
      ctx.el('caption', { className: 'sr-only', text: g.title }),
      ctx.el('thead', {}, [ctx.el('tr', {}, [...head, ctx.el('th', { scope: 'col', text: '' })])]),
      ctx.el('tbody', {}, rows.map(r => {
        const target = parse(r.rule);
        return ctx.el('tr', { 'data-gain-row': r.rule || '' }, [
          ctx.el('td', {}, [cell(cite(r.share, r.paths.share, pct1))]),
          ctx.el('td', {}, [cell(cite(r.recall, r.paths.recall, pct1))]),
          ctx.el('td', {}, [cell(cite(r.precision, r.paths.precision, pct1))]),
          ctx.el('td', { text: status(r), title: r.source }),
          ctx.el('td', {}, [target ? ctx.el('button', { type: 'button', className: 'secondary', 'data-try-rule': r.rule,
            text: g.tryShare, onclick: () => tryRule(ctx, r.rule) }) : null]),
        ]);
      })),
    ]);
    kids.push(table);
    return ctx.el('section', { className: 'card ht-wi-gain', 'aria-labelledby': 'ht-wi-gain-h', 'data-gain': String(rows.length),
      'data-experiment': true }, kids);
  }

  /** Move the slider to a rule of the gain table (a preview only, never a write). */
  function tryRule(ctx, rule) {
    const p = parse(rule);
    if (!p) return;
    S.kind = p.kind;
    S.value = p.value;
    S.rule = canonical(S.kind, S.value);
    askPreview(ctx, true);
    ctx.rerender();
  }

  function renderBinary(ctx, model) {
    const key = ctx.version();
    if (S.kind === null) startPosition(ctx, model);
    if (S.started !== key) {
      // First view of this revision: compute the current position with its intervals.
      S.started = key;
      S.preview = null;
      askPreview(ctx, true);
    }
    S.nodes = {};
    const cmp = comparison(ctx, model);
    const prop = binaryPropose(ctx, model);
    Object.assign(S.nodes, { comparison: cmp, propose: prop });
    return [controls(ctx, model), cmp, ...smallData(ctx), evaluatedTable(ctx, model), gainView(ctx, model), prop];
  }

  // --- regression: residual explorer ----------------------------------------------------------

  /** Bars of a signed value on an axis centred at 0 (geometry of engine values, INV-14). */
  let charts = 0;
  function centredBars(ctx, container, { title, items }) {
    charts += 1;
    const id = `ht-hatch-bias-${charts}`;
    const W = 420; const LABEL = 70; const VALUE = 96; const ROW = 24;
    const plot = W - LABEL - VALUE;
    const top = Math.max(1e-12, ...items.map(i => Math.abs(i.value || 0)));
    const mid = LABEL + plot / 2;
    const x = v => mid + (Math.max(-top, Math.min(top, v || 0)) / top) * (plot / 2);
    const height = items.length * ROW + 18;
    const chart = ctx.svg('svg', { viewBox: `0 0 ${W} ${height}`, width: '100%', class: 'ht-chart ht-centred' }, [
      ctx.svg('defs', {}, [ctx.svg('pattern', { id, width: 6, height: 6, patternUnits: 'userSpaceOnUse', patternTransform: 'rotate(45)' }, [
        ctx.svg('rect', { width: 6, height: 6, fill: 'surface' }),
        ctx.svg('line', { x1: 0, y1: 0, x2: 0, y2: 6, stroke: 'accent', 'stroke-width': 3 })])]),
      ...items.map((item, i) => {
        const y = i * ROW + 4;
        const x0 = Math.min(mid, x(item.value));
        return ctx.svg('g', { 'data-bar': item.label, 'data-small': item.small ? 'true' : null }, [
          ctx.svg('text', { x: LABEL - 6, y: y + 13, class: 'ht-label', 'text-anchor': 'end',
            text: item.small ? `${item.label} (${HT.copy.core.small})` : item.label }),
          ctx.svg('rect', { x: x0, y, height: ROW - 8, width: Math.max(1, Math.abs(x(item.value) - mid)),
            fill: item.small ? `url(#${id})` : 'accent', 'data-hatched': item.small ? 'true' : null }),
          ctx.svg('text', { x: W - VALUE + 6, y: y + 13, class: 'ht-value', text: item.valueText }),
        ]);
      }),
      ctx.svg('line', { x1: mid, x2: mid, y1: 0, y2: items.length * ROW + 4, stroke: 'fg', 'data-zero': true }),
      ctx.svg('text', { x: mid, y: items.length * ROW + 16, class: 'ht-muted-text', 'text-anchor': 'middle', 'aria-hidden': 'true',
        'data-literal': 'axis', text: '0' }),
    ]);
    // Lesson style (R30): the group predicted the most too low and the most too high.
    const R = HT.copy.lesson.concl;
    const known = items.filter(i => i.raw !== null && i.raw !== undefined);
    const read = known.some(i => !i.small) ? known.filter(i => !i.small) : known;
    const hi = read.length ? read.reduce((a, b) => (b.raw > a.raw ? b : a)) : null;
    const lo = read.length ? read.reduce((a, b) => (b.raw < a.raw ? b : a)) : null;
    return ctx.components.figure(container, {
      title, chart,
      reading: { kind: 'points', concl: !hi ? null : hi !== lo ? R.points(hi.label, HT.components.quote(hi.valueText), lo.label,
        HT.components.quote(lo.valueText)) : R.one(hi.label, HT.components.quote(hi.valueText)), steps: HT.copy.lesson.whatifBias },
      columns: [{ key: 'label', label: '' }, { key: 'value', label: '' }, { key: 'small', label: '' }],
      rows: items.map(i => ({ label: i.label, value: i.valueText, small: i.small ? HT.copy.core.small : '' })),
    });
  }

  function renderRegression(ctx, model) {
    const t = C().regression;
    const common = C().common;
    const out = [];
    if (!model.resultId) {
      out.push(ctx.el('p', { className: 'muted', 'data-no-evaluation': true, text: t.noEvaluation }));
    } else {
      if (!S.fit || !model.errors[S.fit]) S.fit = model.candidate || (model.models[0] && model.models[0].fit);
      const unit = model.unit ? ` ${model.unit}` : '';
      const f2 = x => fmt(ctx, x, 'f2');
      const name = fit => fitLabel(t, fit, model.families);
      // Model selector.
      out.push(ctx.el('fieldset', { className: 'card ht-wi-models', 'data-model-selector': true }, [
        ctx.el('legend', { text: t.modelTitle }),
        ...model.models.map(m => ctx.el('label', { className: 'ht-ev-radio' }, [
          ctx.el('input', { type: 'radio', name: 'ht-wi-fit', id: `ht-wi-fit-${m.fit.replace('.', '-')}`, value: m.fit, checked: m.fit === S.fit,
            onchange: () => { S.fit = m.fit; ctx.rerender(); } }),
          name(m.fit),
        ])),
      ]));
      // Error comparison.
      const v = model.validation;
      const description = v && v.method === 'ordinal_cutoff' && v.column && v.cutoff !== null
        ? t.ordinal(v.column, fmt(ctx, v.cutoff, Number.isInteger(v.cutoff) ? 'int' : 'auto')) : t.validationRows;
      const errors = ctx.el('section', { className: 'card ht-wi-errors', 'aria-labelledby': 'ht-wi-err-h', 'data-errors': true }, [
        ctx.el('h3', { id: 'ht-wi-err-h', text: t.errorTitle(description, model.n === null ? '' : fmt(ctx, model.n, 'int')) })]);
      const interval = (low, high, f) => (low === null || high === null ? '' : `[${f(low)}, ${f(high)}]`);
      intervals(ctx, errors, { title: t.maeTitle, zero: false,
        rows: model.models.map(m => {
          const e = model.errors[m.fit];
          return { label: name(m.fit), tone: m.fit === model.reference || m.fit === 'fit.baseline' ? 'baseline' : null,
            point: e.mae, low: e.maeLow, high: e.maeHigh, pointText: e.mae === null ? '' : `${f2(e.mae)}${unit}`,
            intervalText: interval(e.maeLow, e.maeHigh, f2) };
        }) });
      if (model.deltas) {
        const d = model.deltas.mae;
        const s = x => signed(f2(x), x);
        intervals(ctx, errors, { title: t.differenceTitle, zero: true,
          rows: [{ label: t.differenceRow(name(model.deltas.fit), name(model.reference)), point: d.point, low: d.low, high: d.high,
            pointText: d.point === null ? '' : `${s(d.point)}${unit}`, intervalText: interval(d.low, d.high, s) }] });
        errors.appendChild(deltaSentence(ctx, d.side));
      }
      if (model.bootstrap && model.bootstrap.replicates !== null) {
        errors.appendChild(ctx.el('p', { className: 'muted', 'data-bootstrap': true,
          text: common.bootstrap(fmt(ctx, model.bootstrap.replicates, 'int'), levelText(ctx, model.bootstrap.level)) }));
      }
      out.push(errors);
      // Residual summary.
      const q = model.residuals[S.fit];
      if (q && q.min !== null && q.max !== null) {
        const box = ctx.el('section', { className: 'card ht-wi-residuals', 'aria-labelledby': 'ht-wi-res-h', 'data-residuals': S.fit }, [
          ctx.el('h3', { id: 'ht-wi-res-h', text: t.residualSummary })]);
        ctx.components.boxplot(box, { title: t.residualTitle(name(S.fit)), min: q.min, q25: q.q25, median: q.median, q75: q.q75, max: q.max,
          texts: { min: f2(q.min), q25: f2(q.q25), median: f2(q.median), q75: f2(q.q75), max: f2(q.max) } });
        box.appendChild(ctx.el('p', { text: t.residualCaption }));
        out.push(box);
      }
      // Bias by group.
      const by = model.residualsBy;
      if (by && by.groups.length) {
        const items = by.groups.map(g => {
          const r = g.models[S.fit] ? g.models[S.fit].meanResidual : null;
          return { label: g.value, value: r === null ? 0 : r, valueText: r === null ? '' : `${signed(f2(r), r)}${unit}`, small: g.small, raw: r };
        });
        const box = ctx.el('section', { className: 'card ht-wi-bias', 'aria-labelledby': 'ht-wi-bias-h', 'data-bias': by.column }, [
          ctx.el('h3', { id: 'ht-wi-bias-h' }, [t.biasTitle(by.column), ctx.el('span', { className: 'muted', text: ` · ${t.biasNote}` })])]);
        centredBars(ctx, box, { title: t.biasChart(by.column, name(S.fit)), items });
        const values = items.map(i => i.raw).filter(x => x !== null);
        const positive = values.length === items.length && values.every(x => x > 0);
        const negative = values.length === items.length && values.every(x => x < 0);
        if (positive || negative) {
          box.appendChild(ctx.el('p', { 'data-bias-sign': positive ? 'positive' : 'negative', text: positive ? t.allPositive : t.allNegative }));
          if (model.splitOrdinal) {
            box.appendChild(ctx.el('p', { 'data-term-line': 'extrapolation' }, [
              ctx.el('strong', { 'data-term': 'extrapolation', text: t.extrapolationTerm }), t.extrapolationRest]));
          }
        }
        out.push(box);
      }
    }
    if (model.splitLimits) {
      const s = model.splitLimits;
      out.push(ctx.el('section', { className: 'card ht-warn', role: 'note', 'data-split-limits': true, 'aria-labelledby': 'ht-wi-lim-h' }, [
        ctx.el('h3', { id: 'ht-wi-lim-h', text: t.splitLimitsTitle }),
        ctx.el('p', { text: t.splitLimits(fmt(ctx, s.sharedGroups, 'int'), s.column, fmt(ctx, s.validationRowsInSharedGroups || 0, 'int')) }),
      ]));
    }
    if (model.resultId && S.fit) {
      out.push(proposeArea(ctx, 'model_choice', S.fit, model.models.some(m => m.fit === S.fit), t, model.families));
    }
    return out;
  }

  // --- the tab -------------------------------------------------------------------------------

  function render(summary, ctx) {
    const common = C().common;
    const root = ctx.el('div', { className: 'ht-whatif' }, [ctx.el('h2', { className: 'sr-only', text: ctx.copy.core.tabs.whatif }), banner(ctx)]);
    const d = ctx.data('whatif');
    const error = ctx.error('whatif');
    if (error) {
      root.appendChild(ctx.el('div', { className: 'card alert', role: 'alert', 'data-whatif-error': true }, [
        ctx.el('p', { className: 'title', text: common.loadError }), ctx.el('p', { text: error.message }),
        error.detail ? ctx.el('pre', { text: error.detail }) : null,
        ctx.el('button', { type: 'button', className: 'secondary', text: common.retry, onclick: () => { ctx.retry('whatif'); ctx.load('whatif'); } }),
      ]));
    }
    if (!d) {
      if (!error) root.appendChild(ctx.el('p', { className: 'muted', 'aria-busy': 'true', 'data-loading': 'whatif', text: common.reading }));
      return root;
    }
    if (summary && !ctx.fresh(d)) root.appendChild(ctx.el('p', { className: 'muted', role: 'status', 'data-updating': true, text: common.updating }));
    const model = d.model;
    // Lesson style (R30): every chart here is a sandbox on development evidence.
    const parts = HT.components.withGuide(guideOf(ctx, model),
      () => (model.task === 'regression' ? renderRegression(ctx, model) : renderBinary(ctx, model)));
    root.appendChild(ctx.el('div', { className: 'ht-wi-body', 'data-whatif': model.task }, parts));
    const notion = whatifNotion(ctx, model, summary);
    if (notion) root.appendChild(ctx.components.notions([notion], { 'data-whatif-notions': true }));
    return root;
  }

  /** The frame and the rows of the What if? charts ("Why this chart"). */
  function guideOf(ctx, model) {
    const L = HT.copy.lesson;
    return { frame: L.frames.sandbox, rows: model.n !== null && model.n !== undefined ? L.rowsOf(fmt(ctx, model.n, 'int')) : null };
  }

  /** The notion of this step: the residual (regression) or a rule on the scores (binary). */
  function whatifNotion(ctx, model, summary) {
    const N = HT.copy.lesson.notions;
    if (model.task === 'regression') {
      const q = S.fit && model.residuals ? model.residuals[S.fit] : null;
      const f2 = x => fmt(ctx, x, 'f2');
      const R = N.residual;
      return ctx.components.notion({ id: 'residual', term: R.term, tag: 'tool', definition: R.definition,
        here: q && q.median !== null && q.q25 !== null && q.q75 !== null ? R.here(f2(q.median), f2(q.q25), f2(q.q75)) : null,
        folds: [{ kind: 'why', body: R.why }, { kind: 'casse', body: R.casse }], keep: R.keep });
    }
    const R = N.rule;
    const rule = S.rule || (summary && summary.decisions && summary.decisions.policy && summary.decisions.policy.value) || null;
    const words = rule ? HT.copy.junior.value('policy', String(rule).split('@')[0], 'binary') : null;
    return ctx.components.notion({ id: 'rule', term: R.term, tag: 'rule', definition: R.definition,
      here: words ? R.here(words) : null, folds: [{ kind: 'why', body: R.why }, { kind: 'casse', body: R.casse }], keep: R.keep });
  }

  HT.register('whatif', {
    tab: 'whatif',
    stage: 'v2',
    // WP-B5: `scenario`, the case's teaching share (status --json), for the gain curve.
    views: ['scenario', 'whatif'],
    render,
    onMessage(m, ctx) {
      if (m.type === 'preview_policy_result') {
        const sent = S.sent[m.seq];
        if (m.seq !== S.seq || !sent) return false;   // not the latest request: dropped
        S.preview = { seq: m.seq, rule: sent.rule, intervals: sent.intervals, model: m.model, revision: m.revision };
        S.pending = false;
        const data = ctx.data('whatif');
        if (S.nodes.comparison && S.nodes.comparison.isConnected && data) {
          S.nodes.comparison.replaceWith(S.nodes.comparison = HT.components.withGuide(guideOf(ctx, data.model), () => comparison(ctx, data.model)));
        }
        return false;
      }
      if (m.type === 'draft_result') {
        drafts(ctx)[draftKey(m.decisionId, m.value)] = m.model;
        const data = ctx.data('whatif');
        const node = S.nodes.propose;
        if (data && data.model.task === 'binary' && node && node.isConnected && m.value === S.rule) {
          node.replaceWith(S.nodes.propose = binaryPropose(ctx, data.model));
          return false;
        }
        return undefined;
      }
      return undefined;
    },
  });
})(globalThis.Hypotrail = globalThis.Hypotrail || {});
