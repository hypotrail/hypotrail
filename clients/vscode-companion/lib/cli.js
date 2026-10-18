'use strict';
// The only way this client reads or writes a study: the `hypotrail` CLI
// (ADR 0002, CLI-CONTRACT §1). The argv comes from `.hypotrail/agent.json`; the
// process is started with child_process.execFile and an argument vector, never through
// a shell. Free text (the junior's words, a reason) is passed as `--option=value`, so a
// text that begins with "-" is never read as an option.

const childProcess = require('child_process');

const MAX_BUFFER = 8 * 1024 * 1024;
const READ_TIMEOUT_MS = 30000;
const WRITE_TIMEOUT_MS = 120000;

function statusArgv(agent) {
  return [...agent.argv, 'status', '--summary', '--json', '--study', agent.studyDir];
}

function confirmArgv(agent, { proposalId, words, requestId, expectedRevision }) {
  return [...agent.argv, 'decide', 'confirm', proposalId,
    `--user-words=${words}`, '--channel', 'webview', '--actor', 'user',
    '--request-id', requestId, '--expected-revision', String(expectedRevision),
    '--json', '--study', agent.studyDir];
}

function withdrawArgv(agent, { proposalId, reason, requestId, expectedRevision }) {
  const argv = [...agent.argv, 'decide', 'withdraw', proposalId];
  if (typeof reason === 'string' && reason.trim()) argv.push(`--reason=${reason}`);
  argv.push('--request-id', requestId, '--expected-revision', String(expectedRevision),
    '--json', '--study', agent.studyDir);
  return argv;
}

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
      const text = String(stdout || '').trim();
      let payload = null;
      if (text) {
        try { payload = JSON.parse(text); } catch (_) { payload = null; }
      }
      let failure = null;
      if (!payload || typeof payload !== 'object') {
        if (error && error.killed) failure = `The hypotrail CLI did not answer within ${Math.round(timeoutMs / 1000)} s.`;
        else if (error && typeof error.code === 'string') failure = `The hypotrail CLI could not be started (${error.code}: ${argv[0]}).`;
        else failure = 'The hypotrail CLI did not print one JSON document.';
        payload = null;
      }
      resolve({ exitCode, payload, stderr: String(stderr || '').slice(-2000), failure });
    });
  });
}

module.exports = { run, statusArgv, confirmArgv, withdrawArgv, READ_TIMEOUT_MS, WRITE_TIMEOUT_MS };
