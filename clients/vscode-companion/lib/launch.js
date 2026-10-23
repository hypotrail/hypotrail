'use strict';
// The Marimo launches of the panel (WP-A5; ADR 0004 amendment "local launch";
// COMPANION-ADVANCED §6.1.4). The panel may open the study's three notebooks with Marimo's
// own local server, and nothing else:
//
//   notebook   notebooks/study_generated.py   `marimo run`   (read: it is regenerated)
//   editable   notebooks/study_editable.py    `marimo edit`  (synced until first edit)
//   workbench  notebooks/workbench.py         `marimo edit`  (the junior's own file)
//
// The argv is the engine's (`deliverables.launch.<name>.argv` of `status --json`, CLI-CONTRACT
// §3, R7) when it has exactly the expected form, else it is built from the study's recorded
// CLI argv (`.hypotrail/agent.json`): `uv run --project <engine>/framework marimo run|edit
// <file>`, or `<python> -m marimo run|edit <file>`. Anything else is refused (null). The
// extension starts it in a VS Code terminal created with an argument list (shellPath and
// shellArgs, no shell string), so the panel owns no process: `scripts/check_layout.py`
// allows `createTerminal` only for an argv that `isMarimoLaunch` accepts.

const path = require('path');

const NOTEBOOKS = Object.freeze({
  notebook: Object.freeze({ path: 'notebooks/study_generated.py', mode: 'run' }),
  editable: Object.freeze({ path: 'notebooks/study_editable.py', mode: 'edit' }),
  workbench: Object.freeze({ path: 'notebooks/workbench.py', mode: 'edit' }),
});
const MAX_ARG = 4096;

const okArg = a => typeof a === 'string' && a.length > 0 && a.length <= MAX_ARG && !a.includes('\0');

/** The absolute file a launch of `name` opens in study `studyDir`, or null. */
function fileOf(studyDir, name) {
  const nb = NOTEBOOKS[name];
  return nb && typeof studyDir === 'string' ? path.join(path.resolve(studyDir), nb.path) : null;
}

/**
 * True when `argv` opens notebook `name` of `studyDir` with Marimo and nothing else:
 * `uv run --project <dir> marimo <mode> <file>` or `<python> -m marimo <mode> <file>`,
 * with the mode of that notebook and its absolute path.
 */
function isMarimoLaunch(argv, studyDir, name) {
  const nb = NOTEBOOKS[name];
  const file = fileOf(studyDir, name);
  if (!nb || !file || !Array.isArray(argv) || !argv.every(okArg)) return false;
  const tail = argv.slice(-3);
  if (tail[0] !== 'marimo' || tail[1] !== nb.mode || path.resolve(tail[2]) !== file) return false;
  const head = argv.slice(0, -3);
  if (head.length === 4) {
    return head[0] === 'uv' && head[1] === 'run' && head[2] === '--project' && path.isAbsolute(head[3]);
  }
  if (head.length === 2) return path.isAbsolute(head[0]) && /python[0-9.]*(\.exe)?$/i.test(path.basename(head[0])) && head[1] === '-m';
  return false;
}

/** The Marimo prefix from the study's recorded CLI argv, or null when it is of no known form. */
function prefixFromAgent(agentArgv) {
  if (!Array.isArray(agentArgv) || !agentArgv.every(okArg)) return null;
  if (agentArgv[0] === 'uv' && agentArgv[1] === 'run' && agentArgv[2] === '--project' && agentArgv[3] && path.isAbsolute(agentArgv[3])) {
    return ['uv', 'run', '--project', agentArgv[3], 'marimo'];
  }
  if (agentArgv[1] === '-m' && path.isAbsolute(agentArgv[0]) && /python[0-9.]*(\.exe)?$/i.test(path.basename(agentArgv[0]))) {
    return [agentArgv[0], '-m', 'marimo'];
  }
  return null;
}

/**
 * The launch of notebook `name`: `{name, mode, file, argv, source: 'engine'|'agent',
 * terminalName}`, or null when no accepted argv exists. `engine` is the engine's
 * `deliverables.launch[name]` (or null).
 */
function launchFor(agent, name, engine = null) {
  const nb = NOTEBOOKS[name];
  if (!nb || !agent || typeof agent.studyDir !== 'string') return null;
  const file = fileOf(agent.studyDir, name);
  const terminalName = `Hypotrail · marimo ${nb.mode} ${path.basename(file)}`;
  const engineArgv = engine && Array.isArray(engine.argv) ? engine.argv : null;
  if (engineArgv && isMarimoLaunch(engineArgv, agent.studyDir, name)) {
    return { name, mode: nb.mode, file, argv: engineArgv.slice(), source: 'engine', terminalName };
  }
  const prefix = prefixFromAgent(agent.argv);
  if (!prefix) return null;
  const argv = [...prefix, nb.mode, file];
  return isMarimoLaunch(argv, agent.studyDir, name)
    ? { name, mode: nb.mode, file, argv, source: 'agent', terminalName } : null;
}

const quote = a => (/^[A-Za-z0-9_@%+=:,./-]+$/.test(a) ? a : `"${a.replace(/(["\\$`])/g, '\\$1')}"`);

/**
 * What the panel shows next to the buttons (display only, never run): the command of each
 * notebook with its study-relative file, and the engine environment, from agent.json.
 */
function display(agent) {
  const out = { kernel: null, notebook: null, editable: null, workbench: null };
  if (!agent) return out;
  const prefix = prefixFromAgent(agent.argv);
  if (prefix) out.kernel = prefix[0] === 'uv' ? path.join(prefix[3], '.venv') : prefix[0];
  for (const name of Object.keys(NOTEBOOKS)) {
    const l = launchFor(agent, name);
    if (l) out[name] = [...l.argv.slice(0, -1), NOTEBOOKS[name].path].map(quote).join(' ');
  }
  return out;
}

module.exports = { NOTEBOOKS, launchFor, isMarimoLaunch, prefixFromAgent, fileOf, display };
