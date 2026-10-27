'use strict';
// The only way this client reads or writes a study: the `hypotrail` CLI (ADR 0002,
// CLI-CONTRACT §1, CLI-CONTRACT-COMPANION). The argv comes from `.hypotrail/agent.json`;
// the process is started with child_process.execFile and an argument vector, never
// through a shell. Free text (a draft's texts, a column, a folder) is passed as
// `--option=value`, so a text that begins with "-" is never read as an option (CW.7).
//
// Frozen by WP-0 (COMPANION-ADVANCED §5 and §7). The three write builders W4, W5 and W7
// are the whole whitelist of writes: their names, signatures, and argv order do not change
// without the integrator. test/invariants.test.js enumerates WRITES. W1 (confirm), W2
// (withdraw) and W3 (propose) were withdrawn by the v0.3 narrowing (ADR 0004 amendment,
// owner decision R23, integrator decision I2): decisions are made in the chat only, and
// this module has no `decide` write at all (scripts/check_layout.py checks it). W6, the
// acknowledgement of an interrupted execution in typed words, was withdrawn by owner
// decision R31 (2026-10-27, ADR 0004 amendment): the panel takes no words of the junior,
// the acknowledgement is made in the chat, and this module has no acknowledgement builder
// (scripts/check_layout.py checks that too).

const childProcess = require('child_process');
const path = require('path');

const MAX_BUFFER = 16 * 1024 * 1024;
const READ_TIMEOUT_MS = 30000;
const WRITE_TIMEOUT_MS = 120000;
const EDA_TIMEOUT_MS = 300000;
const TIMEOUTS = Object.freeze({
  read: READ_TIMEOUT_MS, W4: EDA_TIMEOUT_MS, W5: WRITE_TIMEOUT_MS, W7: WRITE_TIMEOUT_MS,
});
const MAX_WORDS = 4000;
const PROPOSAL_ID = /^p_[0-9]+$/;
const RESULT_ID = /^[0-9a-f]{64}$/;
const RULE = /^(threshold:(0(\.[0-9]+)?|1(\.0+)?)|capacity:[1-9][0-9]{0,6}|share:(0\.[0-9]*[1-9][0-9]*|1(\.0+)?))$/;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const EDA_ACTIVITY = /^eda\.[a-z_]+$/;
const DRAFT_DECISIONS = ['policy', 'model_choice'];
const TOO_LARGE = 'The study\'s evidence is too large to show (more than 16 MB).';

class ArgvError extends Error {}

function text(value, name, { max = MAX_WORDS, blank = false } = {}) {
  if (typeof value !== 'string') throw new ArgvError(`${name} must be a string`);
  if (value.includes('\0')) throw new ArgvError(`${name} must not hold a NUL character`);
  if (!blank && !value.trim()) throw new ArgvError(`${name} must not be blank`);
  if (value.length > max) throw new ArgvError(`${name} is longer than ${max} characters`);
  return value;
}
function match(value, re, name) {
  if (typeof value !== 'string' || !re.test(value)) throw new ArgvError(`${name} has a wrong form`);
  return value;
}
function revision(value) {
  if (!Number.isInteger(value) || value < 1) throw new ArgvError('the revision must be a positive integer');
  return String(value);
}
function requestId(value) {
  return match(value, UUID, 'the request id');
}
function tail(agent) {
  return ['--json', '--study', agent.studyDir];
}
function mutation(id, rev) {
  return ['--request-id', requestId(id), '--expected-revision', revision(rev)];
}

// --- reads (COMPANION-ADVANCED §5) ----------------------------------------------------------

/** `status --summary [--digest [--since N]] --json --study S`. v0 reads without --digest. */
function statusArgv(agent, { digest = false, since = null } = {}) {
  const argv = [...agent.argv, 'status', '--summary'];
  if (digest) {
    argv.push('--digest');
    if (since !== null && since !== undefined) {
      if (!Number.isInteger(since) || since < 0) throw new ArgvError('since must be an integer >= 0');
      argv.push('--since', String(since));
    }
  }
  return [...argv, ...tail(agent)];
}

function decisionsArgv(agent) {
  return [...agent.argv, 'decisions', ...tail(agent)];
}

function previewEffectsArgv(agent, { proposalId }) {
  return [...agent.argv, 'preview', 'effects', match(proposalId, PROPOSAL_ID, 'the proposal id'), ...tail(agent)];
}

function evidenceArgv(agent, { resultId = null } = {}) {
  const argv = [...agent.argv, 'evidence'];
  if (resultId !== null && resultId !== undefined) argv.push('--result', match(resultId, RESULT_ID, 'the result id'));
  return [...argv, ...tail(agent)];
}

function previewPolicyArgv(agent, { rules, intervals = false }) {
  if (!Array.isArray(rules) || rules.length < 1 || rules.length > 4) throw new ArgvError('one to four rules');
  const argv = [...agent.argv, 'preview', 'policy'];
  for (const rule of rules) argv.push('--rule', match(rule, RULE, 'a rule'));
  if (intervals) argv.push('--intervals');
  return [...argv, ...tail(agent)];
}

function previewProposalArgv(agent, { decisionId, value }) {
  if (!DRAFT_DECISIONS.includes(decisionId)) throw new ArgvError('a draft is for policy or model_choice');
  return [...agent.argv, 'preview', 'proposal', decisionId, `--value=${text(value, 'the value', { max: 64 })}`, ...tail(agent)];
}

function checkArgv(agent) {
  return [...agent.argv, 'check', ...tail(agent)];
}

function explainArgv(agent) {
  return [...agent.argv, 'explain', ...tail(agent)];
}

function sessionReportArgv(agent) {
  return [...agent.argv, 'session-report', ...tail(agent)];
}

/**
 * `status --json --study S`: the full view, read only when the junior opens a notebook in
 * Marimo, for `view.deliverables.launch` (CLI-CONTRACT §3, R7; WP-A5). Never cached.
 */
function viewArgv(agent) {
  return [...agent.argv, 'status', ...tail(agent)];
}

/**
 * `data --json --study S`: the data card of the development rows (CLI-CONTRACT §11.1; WP-A7,
 * the Data & EDA tab). Read-only: the engine records no exposure and logs no session line.
 */
function dataArgv(agent) {
  return [...agent.argv, 'data', ...tail(agent)];
}

const READS = Object.freeze({
  summary: statusArgv, decisions: decisionsArgv, effects: previewEffectsArgv, evidence: evidenceArgv,
  preview: previewPolicyArgv, draft: previewProposalArgv, check: checkArgv, explain: explainArgv,
  session_report: sessionReportArgv, view: viewArgv, data: dataArgv,
});

// --- writes W4, W5, W7 (COMPANION-ADVANCED §7; W6 withdrawn by R31) -------------------------

// v0.3 (WP-J, R35): every write says it comes from the panel, so the engine records it and
// the agent can tell the junior "you ran ... from the panel" (digest `channel_actions`).
const CHANNEL = '--channel=webview';

/** W4. `run <eda.activity> --column=<c> ...` (training rows; the activity from the catalog). */
function runEdaArgv(agent, { activity, column, requestId: id, expectedRevision }) {
  // v0.3 (WP-E2): a whole-study chart (`eda.correlation`) has no column.
  const columnArg = column === undefined ? [] : [`--column=${text(column, 'the column', { max: 200 })}`];
  return [...agent.argv, 'run', match(activity, EDA_ACTIVITY, 'the activity'),
    ...columnArg, CHANNEL, ...mutation(id, expectedRevision), ...tail(agent)];
}

/** W5. `render --json --study S` (no revision). */
function renderArgv(agent) {
  return [...agent.argv, 'render', CHANNEL, ...tail(agent)];
}

/**
 * W7. `export handoff --out=<parent>/revision-<R> --expected-revision R --json --study S`.
 * The engine refuses a stale R (decision CR.6), so the folder's name and its content name
 * the same revision. There is no form without the option: an engine that does not know it
 * refuses the export (`invalid_arguments`), and the panel says the engine is older.
 */
function exportArgv(agent, { parent, revision: rev }) {
  const folder = text(parent, 'the folder', { max: 4096 });
  if (!path.isAbsolute(folder)) throw new ArgvError('the folder must be absolute');
  const inside = path.resolve(agent.studyDir, '.hypotrail');
  const out = path.join(folder, `revision-${revision(rev)}`);
  if (out === inside || out.startsWith(inside + path.sep)) throw new ArgvError('the folder must not be inside .hypotrail');
  return [...agent.argv, 'export', 'handoff', `--out=${out}`, CHANNEL, '--expected-revision', String(revision(rev)),
    ...tail(agent)];
}

const WRITES = Object.freeze({
  W4: runEdaArgv, W5: renderArgv, W7: exportArgv,
});

/**
 * Run one CLI process. Resolves (never rejects) with
 * {exitCode, payload (parsed JSON or null), stderr, failure (null or a message)}.
 * stderr is kept for diagnostics only: `uv` may print warnings there.
 */
function run(argv, { execFile = childProcess.execFile, timeoutMs = READ_TIMEOUT_MS, cwd, env } = {}) {
  return new Promise(resolve => {
    const options = { shell: false, windowsHide: true, timeout: timeoutMs, maxBuffer: MAX_BUFFER,
      encoding: 'utf8', env: env || process.env };
    if (cwd) options.cwd = cwd;
    execFile(argv[0], argv.slice(1), options, (error, stdout, stderr) => {
      const exitCode = error ? (typeof error.code === 'number' ? error.code : null) : 0;
      const out = String(stdout || '').trim();
      let payload = null;
      if (out) {
        try { payload = JSON.parse(out); } catch (_) { payload = null; }
      }
      let failure = null;
      if (!payload || typeof payload !== 'object') {
        if (error && error.code === 'ERR_CHILD_PROCESS_STDIO_MAXBUFFER') failure = TOO_LARGE;
        else if (error && error.killed) failure = `The hypotrail CLI did not answer within ${Math.round(timeoutMs / 1000)} s.`;
        else if (error && typeof error.code === 'string') failure = `The hypotrail CLI could not be started (${error.code}: ${argv[0]}).`;
        else failure = 'The hypotrail CLI did not print one JSON document.';
        payload = null;
      }
      resolve({ exitCode, payload, stderr: String(stderr || '').slice(-2000), failure });
    });
  });
}

/**
 * The environment of every read (merged over the extension host's): the opt-in session
 * log never records the panel's reads (CLI-CONTRACT §8.6, CLI-CONTRACT-COMPANION R5).
 */
const READ_ENV = Object.freeze({ HYPOTRAIL_SESSION_LOG: '0' });

module.exports = {
  READ_ENV,
  run, READS, WRITES, TIMEOUTS, MAX_BUFFER, READ_TIMEOUT_MS, WRITE_TIMEOUT_MS, EDA_TIMEOUT_MS, MAX_WORDS,
  ArgvError, TOO_LARGE,
  statusArgv, decisionsArgv, previewEffectsArgv, evidenceArgv, previewPolicyArgv, previewProposalArgv,
  checkArgv, explainArgv, sessionReportArgv, viewArgv, dataArgv,
  runEdaArgv, renderArgv, exportArgv,
};
