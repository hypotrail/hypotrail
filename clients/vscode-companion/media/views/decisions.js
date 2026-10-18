// Decisions view. WP-0 skeleton: the v0 pending decision cards (confirm in the junior's
// own words, withdraw) and the open holds, moved from media/panel.js unchanged in
// behaviour. Owned by WP-U2, which builds the v1 Decisions tab of COMPANION-ADVANCED §6.2
// (impact preview, queue, history) on top of it.
//
// The textarea starts empty and is never filled by the panel (INV-5): only the junior's
// own typing, kept as a draft for the same proposal in vscode.setState, goes into it.
(function (HT) {
  'use strict';
  const el = HT.el;
  const str = x => (typeof x === 'string' ? x : '');
  const arr = x => (Array.isArray(x) ? x : []);

  function section(id, title, children) {
    return el('section', { 'aria-labelledby': id }, [el('h2', { id, text: title }), ...children]);
  }

  function proposalCard(p, model, ctx) {
    const id = str(p.proposalId);
    const area = ctx.wordsArea({ kind: 'drafts', key: id, onInput: () => sync(), id: `words-${id}`, name: `words-${id}`,
      'aria-describedby': `hint-${id}`, 'data-proposal': id, 'data-write': 'confirm' });
    const confirm = el('button', { type: 'button', 'data-action': 'confirm', 'data-write': 'confirm', 'data-proposal': id,
      text: 'Confirm in my words' });
    const withdraw = el('button', { type: 'button', className: 'secondary', 'data-action': 'withdraw', 'data-write': 'withdraw',
      'data-proposal': id, text: 'Withdraw this proposal' });
    const sync = () => {
      confirm.disabled = ctx.busy || !area.value.trim();
      withdraw.disabled = ctx.busy;
      if (ctx.busy && ctx.busyTarget === id) confirm.setAttribute('aria-busy', 'true');
    };
    confirm.addEventListener('click', () => {
      if (!area.value.trim() || ctx.busy) return;
      ctx.send({ type: 'confirm', proposalId: id, words: area.value, revision: model.revision });
    });
    withdraw.addEventListener('click', () => {
      if (ctx.busy) return;
      ctx.send({ type: 'withdraw', proposalId: id, revision: model.revision });
    });
    sync();
    return el('article', { className: 'card', 'data-proposal-card': id, 'data-nav': `proposal:${id}`, 'aria-labelledby': `title-${id}` }, [
      el('h3', { id: `title-${id}`, text: `${str(p.decisionTitle)} (${str(p.decisionId)})` }),
      el('p', { className: 'muted', text: `Proposal ${id}${Number.isInteger(p.revision) ? ', made at revision ' + p.revision : ''}` }),
      el('p', { text: 'The assistant restated it as:' }),
      el('blockquote', { text: str(p.restatement), 'data-restatement': id }),
      el('p', {}, ['Proposed value: ', el('code', { text: str(p.value) })]),
      ...arr(p.holds).map(h => el('p', { className: 'hold', 'data-hold': str(h.noteId) },
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

  HT.register('decisions', {
    tab: 'decisions',
    stage: 'v0',
    views: [],
    render(model, ctx) {
      const out = [section('h-proposals', 'Waiting for your words', arr(model.proposals).length
        ? arr(model.proposals).map(p => proposalCard(p, model, ctx))
        : [el('p', { className: 'muted', text: 'No open proposal. The assistant proposes decisions in the chat.' })])];
      if (arr(model.holds).length) {
        out.push(section('h-holds', 'On hold', [el('ul', {}, arr(model.holds).map(h =>
          el('li', { 'data-hold-item': str(h.noteId) }, [`${str(h.decisionTitle)} (${str(h.noteId)}): `, el('q', { text: str(h.userWords) })])))]));
      }
      return out;
    },
  });
})(globalThis.Hypotrail = globalThis.Hypotrail || {});
