// Study panel script (runs inside the webview). It renders the model the extension
// sends and posts back a small set of requests. Every text is set with textContent:
// nothing from the study is parsed as HTML. The textarea starts empty and is never
// filled by the panel; only the junior's own typing goes into it.
(function () {
  'use strict';
  const vscode = acquireVsCodeApi();
  const saved = (function () {
    try { return vscode.getState() || {}; } catch (_) { return {}; }
  })();
  const drafts = (saved && typeof saved.drafts === 'object' && saved.drafts) || {};
  const OUTGOING = new Set(['ready', 'refresh', 'confirm', 'withdraw', 'open']);
  const INCOMING = new Set(['snapshot', 'load_error', 'busy', 'outcome']);
  const PROPOSAL_ID = /^p_[0-9]+$/;
  let model = null;
  let busy = false;
  let outcome = null;
  let loadError = null;
  let notice = '';
  const root = document.getElementById('root');

  function send(message) {
    if (OUTGOING.has(message.type)) vscode.postMessage(message);
  }
  function keep() {
    try { vscode.setState({ drafts }); } catch (_) { /* no state */ }
  }
  function el(tag, attrs, children) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v === null || v === undefined || v === false) continue;
      if (k === 'text') node.textContent = String(v);
      else if (k === 'className') node.className = v;
      else if (k.startsWith('on')) node.addEventListener(k.slice(2), v);
      else node.setAttribute(k, v === true ? '' : String(v));
    }
    for (const child of children || []) {
      if (child === null || child === undefined || child === false) continue;
      node.appendChild(typeof child === 'string' ? document.createTextNode(child) : child);
    }
    return node;
  }
  const str = x => (typeof x === 'string' ? x : '');
  const arr = x => (Array.isArray(x) ? x : []);

  function section(id, title, children) {
    return el('section', { 'aria-labelledby': id }, [el('h2', { id, text: title }), ...children]);
  }

  function renderOutcome(o) {
    if (!o) return null;
    if (o.kind === 'refused' && o.refusal) {
      const r = o.refusal;
      return el('div', { className: 'card alert', role: 'alert', 'data-outcome': 'refused', 'data-code': str(r.code), 'data-reason': str(r.reason) }, [
        el('p', { className: 'title', text: `The engine refused: ${str(r.code)}${r.reason ? ' (' + r.reason + ')' : ''}` }),
        el('p', { text: str(r.human), 'data-human': true }),
        el('p', { className: 'muted', text: 'Engine message, verbatim:' }),
        el('blockquote', { text: str(r.engineMessage), 'data-engine-message': true }),
        arr(r.details).length ? el('ul', {}, arr(r.details).map(line => el('li', { text: str(line) }))) : null,
      ]);
    }
    if (o.kind === 'confirmed' || o.kind === 'withdrawn') {
      const title = o.kind === 'confirmed'
        ? `Confirmed ${str(o.decisionId)} at revision ${o.revision}, channel ${str(o.channel)}.`
        : `Withdrew ${str(o.proposalId)} (${str(o.decisionId)}) at revision ${o.revision}.`;
      return el('div', { className: 'card success', role: 'status', 'data-outcome': o.kind }, [
        el('p', { className: 'title', text: title }),
        o.userWords !== null && o.userWords !== undefined ? el('p', {}, ['Recorded in your words: ', el('q', { text: str(o.userWords) })]) : null,
        arr(o.artifacts).length ? el('ul', {}, arr(o.artifacts).map(a => el('li', { text: str(a.message) }))) : null,
      ]);
    }
    return el('div', { className: 'card alert', role: 'alert', 'data-outcome': str(o.kind) }, [
      el('p', { className: 'title', text: o.kind === 'failed' ? 'The request failed.' : 'Not sent.' }),
      el('p', { text: str(o.message) }),
    ]);
  }

  function proposalCard(p) {
    const id = str(p.proposalId);
    const area = el('textarea', {
      id: `words-${id}`, name: `words-${id}`, 'aria-describedby': `hint-${id}`, spellcheck: 'true',
      'data-proposal': id, autocomplete: 'off',
    });
    area.value = str(drafts[id]);
    const confirm = el('button', { type: 'button', 'data-action': 'confirm', 'data-proposal': id, text: 'Confirm in my words' });
    const withdraw = el('button', { type: 'button', className: 'secondary', 'data-action': 'withdraw', 'data-proposal': id, text: 'Withdraw this proposal' });
    const sync = () => {
      confirm.disabled = busy || !area.value.trim();
      withdraw.disabled = busy;
    };
    area.addEventListener('input', () => {
      drafts[id] = area.value;
      if (!area.value) delete drafts[id];
      keep();
      sync();
    });
    confirm.addEventListener('click', () => {
      if (!area.value.trim() || busy || !model) return;
      send({ type: 'confirm', proposalId: id, words: area.value, revision: model.revision });
    });
    withdraw.addEventListener('click', () => {
      if (busy || !model) return;
      send({ type: 'withdraw', proposalId: id, reason: null, revision: model.revision });
    });
    sync();
    const holds = arr(p.holds);
    return el('article', { className: 'card', 'data-proposal-card': id, 'aria-labelledby': `title-${id}` }, [
      el('h3', { id: `title-${id}`, text: `${str(p.decisionTitle)} (${str(p.decisionId)})` }),
      el('p', { className: 'muted', text: `Proposal ${id}${Number.isInteger(p.revision) ? ', made at revision ' + p.revision : ''}` }),
      el('p', { text: 'The assistant restated it as:' }),
      el('blockquote', { text: str(p.restatement), 'data-restatement': id }),
      el('p', {}, ['Proposed value: ', el('code', { text: str(p.value) })]),
      ...holds.map(h => el('p', { className: 'hold', 'data-hold': str(h.noteId) },
        [`On hold in your words (${str(h.noteId)}): `, el('q', { text: str(h.userWords) }),
          '. The engine refuses a confirmation of this decision until you resolve the hold in the chat.'])),
      el('label', { for: `words-${id}`, text: 'Your answer, in your own words' }),
      area,
      el('p', { id: `hint-${id}`, className: 'muted', text:
        'What you type is recorded verbatim as your confirmation, with channel "webview". ' +
        'The engine checks it like an answer in the chat: an acknowledgement alone is not a decision. ' +
        'To hand the choice to the assistant, say so in the chat; this panel does not record delegations.' }),
      el('div', {}, [confirm, withdraw]),
    ]);
  }

  function render() {
    const active = document.activeElement;
    const focusId = active && active.id ? active.id : null;
    const selection = active && active.tagName === 'TEXTAREA' ? [active.selectionStart, active.selectionEnd] : null;
    root.textContent = '';
    root.appendChild(el('h1', { text: 'Hypotrail study' }));
    if (loadError) {
      root.appendChild(el('div', { className: 'card alert', role: 'alert', 'data-load-error': true }, [
        el('p', { className: 'title', text: 'The panel could not read the study.' }),
        el('p', { text: str(loadError.message) }),
        loadError.detail ? el('pre', { text: str(loadError.detail) }) : null,
        el('button', { type: 'button', className: 'secondary', text: 'Try again', onclick: () => send({ type: 'refresh' }) }),
      ]));
    }
    const live = el('div', { id: 'outcome', 'aria-live': 'polite' }, [
      notice ? el('p', { className: 'hold', role: 'status', 'data-notice': true, text: notice }) : null,
      renderOutcome(outcome),
    ]);
    root.appendChild(live);
    if (!model) {
      if (!loadError) root.appendChild(el('p', { className: 'muted', text: 'Reading the study…' }));
      return;
    }
    root.appendChild(el('p', { className: 'muted' }, [
      'Study ', el('code', { text: model.study }), ` at revision ${model.revision}. `,
      el('button', { type: 'button', className: 'secondary', text: 'Refresh', disabled: busy, onclick: () => send({ type: 'refresh' }) }),
    ]));

    root.appendChild(section('h-recap', 'Where the study stands', [
      el('ul', { 'data-recap': true }, arr(model.recap).map(line => el('li', { text: str(line) }))),
    ]));

    const step = model.currentStep;
    root.appendChild(section('h-plan', 'Plan', [
      el('p', { 'data-current-step': step ? step.id : '' , text: step
        ? `Step ${step.position} of ${step.total}: ${str(step.title)}.`
        : 'Every step is done.' }),
      model.nextAction && model.nextAction.message ? el('p', { className: 'muted', text: `Next: ${str(model.nextAction.message)}` }) : null,
      el('ol', {}, arr(model.plan).map(s => el('li', { 'aria-current': step && s.id === step.id ? 'step' : null },
        [`${str(s.title)} `, el('span', { className: 'muted', text: `(${str(s.status).replace(/_/g, ' ')})` })]))),
    ]));

    root.appendChild(section('h-proposals', 'Waiting for your words', arr(model.proposals).length
      ? arr(model.proposals).map(proposalCard)
      : [el('p', { className: 'muted', text: 'No open proposal. The assistant proposes decisions in the chat.' })]));

    if (arr(model.holds).length) {
      root.appendChild(section('h-holds', 'On hold', [el('ul', {}, arr(model.holds).map(h =>
        el('li', { 'data-hold-item': str(h.noteId) }, [`${str(h.decisionTitle)} (${str(h.noteId)}): `, el('q', { text: str(h.userWords) })])))]));
    }

    root.appendChild(section('h-artifacts', 'Deliverables', arr(model.artifacts).length
      ? arr(model.artifacts).map(a => el('div', { className: 'card', 'data-artifact': str(a.name) }, [
        el('p', {}, [el('span', { className: `status status-${str(a.status)}`, text: `${str(a.label)}: ${str(a.status)}` })]),
        el('p', { text: str(a.message) }),
        el('button', { type: 'button', className: 'secondary', disabled: busy,
          text: a.name === 'report' ? 'Open the report in the browser' : `Open ${str(a.label).toLowerCase()}`,
          onclick: () => send({ type: 'open', artifact: a.name }) }),
      ]))
      : [el('p', { className: 'muted', text: 'Nothing rendered yet.' })]));

    const nyd = model.notYetDefensible || {};
    root.appendChild(section('h-nyd', 'Not yet defensible', [
      el('ul', {}, arr(nyd.top).map(i => el('li', { 'data-nyd': str(i.id), text: str(i.text) }))),
      arr(nyd.more).length ? el('p', { className: 'muted', text: `Also listed: ${arr(nyd.more).join(', ')}.` }) : null,
    ]));

    if (focusId) {
      const again = document.getElementById(focusId);
      if (again) {
        again.focus();
        if (selection && again.tagName === 'TEXTAREA') again.setSelectionRange(selection[0], selection[1]);
      }
    }
  }

  function validIncoming(m) {
    if (!m || typeof m !== 'object' || !INCOMING.has(m.type)) return false;
    if (m.type === 'snapshot') return Boolean(m.model && typeof m.model === 'object' && Number.isInteger(m.model.revision));
    if (m.type === 'busy') return typeof m.busy === 'boolean';
    if (m.type === 'outcome') return typeof m.kind === 'string';
    if (m.type === 'load_error') return typeof m.message === 'string';
    return false;
  }

  window.addEventListener('message', event => {
    const m = event.data;
    if (!validIncoming(m)) return;
    if (m.type === 'snapshot') {
      const before = model ? model.revision : null;
      const open = new Set(arr(m.model.proposals).map(p => str(p.proposalId)).filter(id => PROPOSAL_ID.test(id)));
      const typing = Object.keys(drafts).some(id => open.has(id) && str(drafts[id]).trim());
      notice = before !== null && before !== m.model.revision && typing
        ? `The study changed while you were typing (revision ${before} to ${m.model.revision}). Read the proposal again before confirming.`
        : (before === m.model.revision ? notice : '');
      for (const id of Object.keys(drafts)) if (!open.has(id)) delete drafts[id];
      keep();
      model = m.model;
      loadError = null;
    } else if (m.type === 'load_error') {
      loadError = { message: m.message, detail: typeof m.detail === 'string' ? m.detail : '' };
    } else if (m.type === 'busy') {
      busy = m.busy;
    } else if (m.type === 'outcome') {
      outcome = m;
      if (m.kind === 'confirmed' || m.kind === 'withdrawn') {
        delete drafts[str(m.proposalId)];
        keep();
      }
      notice = '';
    }
    render();
  });

  render();
  send({ type: 'ready' });
})();
