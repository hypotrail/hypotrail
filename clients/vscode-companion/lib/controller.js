'use strict';
// Panel controller: everything between the webview and the CLI, without the `vscode`
// module, so it is tested with the real CLI (test/integration.test.js).
//
// Reads: `status --summary`. Writes: `decide confirm` (typed words, channel webview,
// actor user, a fresh request id, the revision the panel showed) and `decide withdraw`.
// Nothing else mutates (ADR 0003, CW.5). The controller keeps no study state of its own:
// the last snapshot is only used to check that a request names a proposal the panel
// showed; the engine decides.

const path = require('path');
const crypto = require('crypto');
const cli = require('./cli');
const { toModel, ARTIFACT_PATHS, PROPOSAL_ID } = require('./model');
const refusals = require('./refusals');

const MAX_WORDS = 4000;
const INCOMING = {
  ready: [],
  refresh: [],
  confirm: ['proposalId', 'words', 'revision'],
  withdraw: ['proposalId', 'reason', 'revision'],
  open: ['artifact'],
};

/** null, or a validated copy of a message from the webview. */
function validateIncoming(message) {
  if (!message || typeof message !== 'object' || Array.isArray(message)) return null;
  const type = message.type;
  if (typeof type !== 'string' || !Object.prototype.hasOwnProperty.call(INCOMING, type)) return null;
  const allowed = new Set(['type', ...INCOMING[type]]);
  if (Object.keys(message).some(k => !allowed.has(k))) return null;
  if (type === 'confirm' || type === 'withdraw') {
    if (typeof message.proposalId !== 'string' || !PROPOSAL_ID.test(message.proposalId)) return null;
    if (!Number.isInteger(message.revision) || message.revision < 1) return null;
  }
  if (type === 'confirm') {
    if (typeof message.words !== 'string' || message.words.length > MAX_WORDS) return null;
  }
  if (type === 'withdraw') {
    if (message.reason !== undefined && message.reason !== null &&
        (typeof message.reason !== 'string' || message.reason.length > MAX_WORDS)) return null;
  }
  if (type === 'open') {
    if (typeof message.artifact !== 'string' || !Object.prototype.hasOwnProperty.call(ARTIFACT_PATHS, message.artifact)) return null;
  }
  return { ...message };
}

function artifactMessages(payload) {
  const items = (payload && payload.artifacts) || {};
  return Object.keys(items).map(name => ({ name, status: String(items[name] && items[name].status || ''),
    message: String(items[name] && items[name].message || '') }));
}

function createController({ agent, post, runCli = cli.run, openArtifact = async () => {},
  confirmWithdraw = async () => true, exists = () => true, uuid = () => crypto.randomUUID(),
  log = () => {} }) {
  let snapshot = null;
  let busy = false;
  let refreshing = null;
  let again = false;
  let disposed = false;
  const diagnostics = { ignored: 0, refreshes: 0, commands: [] };

  const send = message => { if (!disposed) post(message); };
  const runCommand = (argv, timeoutMs) => {
    diagnostics.commands.push(argv.slice(agent.argv.length, agent.argv.length + 2).join(' '));
    return runCli(argv, { timeoutMs, cwd: agent.studyDir });
  };

  async function load() {
    diagnostics.refreshes += 1;
    const res = await runCommand(cli.statusArgv(agent), cli.READ_TIMEOUT_MS);
    if (res.failure || !res.payload) {
      send({ type: 'load_error', message: res.failure || 'The hypotrail CLI failed.', detail: res.stderr || '' });
      return;
    }
    if (res.payload.ok !== true) {
      const d = refusals.describe(res.payload);
      send({ type: 'load_error', message: `${d.code}: ${d.engineMessage}`, detail: '' });
      return;
    }
    try {
      snapshot = toModel(res.payload);
    } catch (e) {
      send({ type: 'load_error', message: e.message, detail: '' });
      return;
    }
    send({ type: 'snapshot', model: snapshot });
  }

  /** Refresh from the CLI; concurrent calls are coalesced into one more read. */
  function refresh() {
    if (disposed) return Promise.resolve();
    if (refreshing) {
      again = true;
      return refreshing;
    }
    refreshing = (async () => {
      try {
        do {
          again = false;
          await load();
        } while (again && !disposed);
      } catch (e) {
        log(e);
        send({ type: 'load_error', message: String(e && e.message || e), detail: '' });
      } finally {
        refreshing = null;
      }
    })();
    return refreshing;
  }

  function shown(proposalId) {
    return Boolean(snapshot && snapshot.proposals.some(p => p.proposalId === proposalId));
  }

  async function mutate(kind, proposalId, argvFor) {
    if (busy) {
      send({ type: 'outcome', kind: 'invalid', proposalId, message: 'Another request is in progress.' });
      return;
    }
    if (!shown(proposalId)) {
      send({ type: 'outcome', kind: 'invalid', proposalId,
        message: 'This proposal is not open in the panel any more. Nothing was recorded.' });
      await refresh();
      return;
    }
    busy = true;
    send({ type: 'busy', busy: true, proposalId });
    try {
      const requestId = uuid();
      const res = await runCommand(argvFor(requestId), cli.WRITE_TIMEOUT_MS);
      if (res.failure || !res.payload) {
        send({ type: 'outcome', kind: 'failed', proposalId, exitCode: res.exitCode,
          message: `${res.failure || 'The hypotrail CLI failed.'} The outcome is unknown: the refreshed panel shows whether anything was recorded.` });
      } else if (res.payload.ok === true) {
        const result = res.payload.result || {};
        send({ type: 'outcome', kind, proposalId, exitCode: res.exitCode, revision: res.payload.revision,
          decisionId: String(result.decision_id || ''), userWords: typeof result.user_words === 'string' ? result.user_words : null,
          channel: typeof result.channel === 'string' ? result.channel : null,
          artifacts: artifactMessages(res.payload) });
      } else {
        send({ type: 'outcome', kind: 'refused', proposalId, exitCode: res.exitCode, refusal: refusals.describe(res.payload) });
      }
    } finally {
      busy = false;
      send({ type: 'busy', busy: false, proposalId });
    }
    await refresh();
  }

  async function handle(raw) {
    const message = validateIncoming(raw);
    if (!message) {
      diagnostics.ignored += 1;
      return;
    }
    switch (message.type) {
      case 'ready':
      case 'refresh':
        return refresh();
      case 'confirm': {
        if (!message.words.trim()) {
          send({ type: 'outcome', kind: 'invalid', proposalId: message.proposalId,
            message: 'Type your own answer first. Nothing was recorded.' });
          return;
        }
        return mutate('confirmed', message.proposalId, requestId => cli.confirmArgv(agent, {
          proposalId: message.proposalId, words: message.words, requestId, expectedRevision: message.revision }));
      }
      case 'withdraw': {
        const proposal = snapshot && snapshot.proposals.find(p => p.proposalId === message.proposalId);
        if (proposal && !(await confirmWithdraw(proposal))) return;
        return mutate('withdrawn', message.proposalId, requestId => cli.withdrawArgv(agent, {
          proposalId: message.proposalId, reason: message.reason, requestId, expectedRevision: message.revision }));
      }
      case 'open': {
        const target = path.join(agent.studyDir, ARTIFACT_PATHS[message.artifact]);
        if (!exists(target)) {
          send({ type: 'outcome', kind: 'invalid', proposalId: null,
            message: `${ARTIFACT_PATHS[message.artifact]} does not exist yet.` });
          return;
        }
        return openArtifact(message.artifact, target);
      }
      default:
        return undefined;
    }
  }

  return {
    handle, refresh,
    snapshot: () => snapshot,
    diagnostics: () => diagnostics,
    dispose() { disposed = true; },
  };
}

module.exports = { createController, validateIncoming, INCOMING, MAX_WORDS };
