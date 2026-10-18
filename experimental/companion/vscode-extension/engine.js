'use strict';
const { spawn } = require('child_process');

const ALLOWED = new Set(['status', 'project', 'projects', 'submit', 'apply', 'export', 'explain', 'confirm_fact', 'assistant_begin', 'assistant_update', 'assistant_recover', 'assistant_clear']);
const MAX_REQUEST = 131072;

function engineError(code, message) {
  return Object.assign(new Error(message), { code });
}

function createEngine({ python, bridge, db, project, cwd, isTrusted = () => true, timeoutMs = 12000, diagnostics = { requests: 0, errors: [] } }) {
  let queue = Promise.resolve();
  // Never pass test-only environment variables to the engine.
  const env = Object.fromEntries(Object.entries(process.env).filter(([key]) => !key.startsWith('OSML_')));
  function run(request) {
    // Queueing and SQLite also protect two clients using one session.
    const job = queue.then(() => new Promise((resolve, reject) => {
      if (!isTrusted()) return reject(engineError('untrusted', 'Untrusted workspace.'));
      const body = JSON.stringify(request ?? null);
      if (!request || !ALLOWED.has(request.action) || body.length > MAX_REQUEST) return reject(engineError('action', 'Unauthorized request.'));
      const args = [bridge, 'rpc', '--db', db].concat(project ? ['--project', project] : []);
      const child = spawn(python, args, { cwd, env, stdio: ['pipe', 'pipe', 'pipe'], shell: false });
      let output = '', errors = '', finished = false;
      const timer = setTimeout(() => { finished = true; child.kill(); reject(engineError('timeout', 'Engine timeout; reread status before retrying.')); }, timeoutMs);
      child.stdout.on('data', chunk => { output += chunk; if (output.length > 4e6) child.kill(); });
      child.stderr.on('data', chunk => { errors = (errors + chunk).slice(-3000); });
      child.on('error', e => { clearTimeout(timer); if (!finished) { finished = true; reject(e); } });
      child.on('close', code => {
        clearTimeout(timer); if (finished) return; finished = true; diagnostics.requests++;
        try {
          const data = JSON.parse(output);
          if (code !== 0 || data.error) throw engineError(data.error || 'engine', data.message || errors || 'Engine error');
          diagnostics.lastAction = request.action; diagnostics.lastRevision = data.revision; resolve(data);
        } catch (e) {
          if (!e.code) e.code = 'engine';
          diagnostics.errors.push(e.message); if (diagnostics.errors.length > 50) diagnostics.errors.shift(); reject(e);
        }
      });
      child.stdin.end(body);
    }));
    queue = job.catch(() => {});
    return job;
  }
  return { run, db, diagnostics };
}

module.exports = { createEngine, engineError, ALLOWED };
