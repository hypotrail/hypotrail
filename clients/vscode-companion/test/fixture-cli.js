'use strict';
// Test helpers (WP-0): the fixtures of test/fixtures/ and a fake CLI that answers from
// them, for the controller's `runCli` option. No process is started. Every WP's unit
// tests use these; the real-CLI integration tests (integration*.test.js) do not.
//
//   fixture(name) -> {about, payload}        payload(name) -> the CLI payload
//   fakeCli(route?) -> runCli; runCli.calls holds every argv (after agent.argv)
//     route(tail) returns a fixture name, {name, exitCode?}, {payload, exitCode?},
//     {failure}, or undefined for the default route below.

const fs = require('fs');
const path = require('path');

const DIR = path.join(__dirname, 'fixtures');
const COMMANDS = ['data', 'status', 'decisions', 'evidence', 'explain', 'check', 'session-report', 'render', 'export', 'preview',
  'decide', 'run', 'init', 'plan'];

function fixture(name) {
  return JSON.parse(fs.readFileSync(path.join(DIR, `${name}.json`), 'utf8'));
}

function payload(name) {
  return fixture(name).payload;
}

function names() {
  return fs.readdirSync(DIR).filter(f => f.endsWith('.json') && f !== 'index.json' && f !== 'contract-keys.json')
    .map(f => f.slice(0, -5)).sort();
}

/** The fixture a command reads by default, by task. */
function defaultRoute(tail, task = 'binary') {
  const [command, verb] = tail;
  const b = task === 'binary';
  // WP-B5: `status --json` (no --summary) is the full view (the What if? scenario read).
  if (command === 'status' && !tail.includes('--summary')) return 'captured/status.shoppers';
  if (command === 'status') return tail.includes('--digest') ? (b ? 'summary.binary' : 'summary.regression') : (b ? 'summary.v0.binary' : 'summary.v0.regression');
  if (command === 'decisions') return b ? 'decisions.binary' : 'decisions.regression';
  if (command === 'data') return b ? 'data.binary' : 'data.regression';
  if (command === 'evidence') return tail.includes('--result') ? 'evidence.binary.detail' : (b ? 'evidence.binary' : 'evidence.regression');
  if (command === 'explain') return b ? 'explain.binary' : 'explain.regression';
  if (command === 'check') return 'check.binary';
  if (command === 'session-report') return 'session_report.binary';
  if (command === 'render') return 'render.binary';
  if (command === 'export') return 'export.binary';
  if (command === 'preview' && verb === 'policy') return 'preview.binary';
  if (command === 'preview' && verb === 'effects') return b ? 'preview_effects.binary' : 'preview_effects.regression';
  if (command === 'preview' && verb === 'proposal') return b ? 'proposal_draft.binary' : 'proposal_draft.regression';
  if (command === 'decide' && verb === 'confirm') return 'decide.confirm.binary';
  if (command === 'decide' && verb === 'withdraw') return 'decide.withdraw.binary';
  if (command === 'decide' && verb === 'propose') return 'decide.propose.webview.binary';
  if (command === 'run' && verb === '--acknowledge-interruption') return 'run.acknowledge.binary';
  if (command === 'run') return 'run.eda_distribution.binary';
  return null;
}

function fakeCli(route = () => undefined, { agentArgv = null, task = 'binary' } = {}) {
  const calls = [];
  const runCli = async (argv, options = {}) => {
    const skip = agentArgv ? agentArgv.length : argv.findIndex(a => COMMANDS.includes(a));
    const tail = argv.slice(Math.max(0, skip));
    calls.push({ argv, tail, options });
    let answer = route(tail, calls.length);
    if (answer === undefined || answer === null) answer = defaultRoute(tail, task);
    if (typeof answer === 'string') answer = { name: answer };
    if (!answer) return { exitCode: 2, payload: null, stderr: '', failure: `no fixture for ${tail.join(' ')}` };
    if (answer.failure) return { exitCode: null, payload: null, stderr: answer.stderr || '', failure: answer.failure };
    if (answer.name) {
      const f = fixture(answer.name);
      return { exitCode: answer.exitCode !== undefined ? answer.exitCode : f.about.exit_code, payload: f.payload, stderr: '', failure: null };
    }
    return { exitCode: answer.exitCode || 0, payload: answer.payload, stderr: '', failure: null };
  };
  runCli.calls = calls;
  return runCli;
}

module.exports = { fixture, payload, names, fakeCli, defaultRoute, DIR };
