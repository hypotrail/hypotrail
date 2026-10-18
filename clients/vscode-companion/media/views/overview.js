// Overview view. WP-0 skeleton: the v0 panel's read-only sections (recap, plan,
// deliverables, not yet defensible), moved from media/panel.js unchanged in behaviour.
// Owned by WP-U1, which builds the v1 Overview of COMPANION-ADVANCED §6.1 (map, digest,
// health, studies) on top of it. Text is always set as text (INV-9).
(function (HT) {
  'use strict';
  const el = HT.el;
  const str = x => (typeof x === 'string' ? x : '');
  const arr = x => (Array.isArray(x) ? x : []);

  function section(id, title, children) {
    return el('section', { 'aria-labelledby': id }, [el('h2', { id, text: title }), ...children]);
  }

  HT.register('overview', {
    tab: 'overview',
    stage: 'v0',
    views: [],
    render(model, ctx) {
      const out = [];
      out.push(section('h-recap', 'Where the study stands', [
        el('ul', { 'data-recap': true }, arr(model.recap).map(line => el('li', { text: str(line) }))),
      ]));
      const step = model.currentStep;
      out.push(section('h-plan', 'Plan', [
        el('p', { 'data-current-step': step ? step.id : '', text: step
          ? `Step ${step.position} of ${step.total}: ${str(step.title)}.`
          : 'Every step is done.' }),
        model.nextAction && model.nextAction.message ? el('p', { className: 'muted', text: `Next: ${str(model.nextAction.message)}` }) : null,
        el('ol', {}, arr(model.plan).map(s => el('li', { 'aria-current': step && s.id === step.id ? 'step' : null },
          [`${str(s.title)} `, el('span', { className: 'muted', text: `(${str(s.status).replace(/_/g, ' ')})` })]))),
      ]));
      out.push(section('h-artifacts', 'Deliverables', arr(model.artifacts).length
        ? arr(model.artifacts).map(a => el('div', { className: 'card', 'data-artifact': str(a.name) }, [
          el('p', {}, [el('span', { className: `status status-${str(a.status)}`, text: `${str(a.label)}: ${str(a.status)}` })]),
          el('p', { text: str(a.message) }),
          el('button', { type: 'button', className: 'secondary', disabled: ctx.busy,
            text: a.name === 'report' ? 'Open the report in the browser' : `Open ${str(a.label).toLowerCase()}`,
            onclick: () => ctx.send({ type: 'open_artifact', artifact: a.name }) }),
        ]))
        : [el('p', { className: 'muted', text: 'Nothing rendered yet.' })]));
      const nyd = model.notYetDefensible || {};
      out.push(section('h-nyd', 'Not yet defensible', [
        el('ul', {}, arr(nyd.top).map(i => el('li', { 'data-nyd': str(i.id), 'data-nav': `limit:${str(i.id)}`, text: str(i.text) }))),
        arr(nyd.more).length ? el('p', { className: 'muted', text: `Also listed: ${arr(nyd.more).join(', ')}.` }) : null,
      ]));
      return out;
    },
  });
})(globalThis.Hypotrail = globalThis.Hypotrail || {});
