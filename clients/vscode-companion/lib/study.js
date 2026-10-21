'use strict';
// Study discovery (ADR 0003, CW.3; COMPANION-ADVANCED §6.1.6, owned by WP-U1). A study is a folder holding `.hypotrail/agent.json`
// (`hypotrail.agent/1`, written by `hypotrail init`, CLI-CONTRACT §8.4). The CLI argv is
// taken from `agent.json.cli.argv`, never from its shell string.

const fs = require('fs');
const path = require('path');

const AGENT_SCHEMA = 'hypotrail.agent/1';
const AGENT_FILE = path.join('.hypotrail', 'agent.json');
const MAX_ARGV = 32;

class StudyError extends Error {
  // v0.3 (WP-K, R21): `messageFr`, the same message in French (the extension picks by language).
  constructor(code, message, messageFr = null) {
    super(message);
    this.code = code;
    this.messageFr = messageFr;
  }
}

function isStudy(dir, fsImpl = fs) {
  try {
    return fsImpl.statSync(path.join(dir, AGENT_FILE)).isFile();
  } catch (_) {
    return false;
  }
}

const MAX_DEPTH = 2;
const MAX_VISITED = 500;
const SKIPPED = new Set(['node_modules', '.git', '.venv']);

/**
 * Studies under the workspace folders `folders` (absolute paths), COMPANION-ADVANCED
 * §6.1.6: each folder, its direct subfolders, and their subfolders (depth <= 2). It skips
 * node_modules, .git, .venv, and every dot-folder, follows no symbolic link, and stops
 * after visiting MAX_VISITED folders. Returns the study folders, sorted. Only the
 * existence of `.hypotrail/agent.json` is tested here; readAgent validates the one chosen.
 */
function findStudies(folders, fsImpl = fs, { maxDepth = MAX_DEPTH, maxVisited = MAX_VISITED } = {}) {
  const seen = new Set();
  const found = new Set();
  let visited = 0;
  const queue = [];
  for (const folder of folders || []) {
    if (typeof folder !== 'string' || !folder) continue;
    queue.push({ dir: path.resolve(folder), depth: 0 });
  }
  // Breadth first, so the limit cuts the deepest folders first.
  while (queue.length && visited < maxVisited) {
    const { dir, depth } = queue.shift();
    if (seen.has(dir)) continue;
    seen.add(dir);
    visited += 1;
    if (isStudy(dir, fsImpl)) found.add(dir);
    if (depth >= maxDepth) continue;
    let entries = [];
    try {
      entries = fsImpl.readdirSync(dir, { withFileTypes: true });
    } catch (_) {
      entries = [];
    }
    for (const entry of entries.slice().sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0))) {
      if (!entry.isDirectory() || entry.name.startsWith('.') || SKIPPED.has(entry.name)) continue;
      queue.push({ dir: path.join(dir, entry.name), depth: depth + 1 });
    }
  }
  return [...found].sort();
}

function validArgv(argv) {
  return Array.isArray(argv) && argv.length > 0 && argv.length <= MAX_ARGV &&
    argv.every(a => typeof a === 'string' && a.length > 0 && !a.includes('\0'));
}

function realpath(p, fsImpl) {
  try { return fsImpl.realpathSync(p); } catch (_) { return path.resolve(p); }
}

/**
 * Read and validate `.hypotrail/agent.json` of `dir`.
 * Returns {studyDir, argv, how}. Throws StudyError(code) with a human message.
 */
function readAgent(dir, fsImpl = fs) {
  const studyDir = path.resolve(dir);
  const file = path.join(studyDir, AGENT_FILE);
  let record;
  try {
    record = JSON.parse(fsImpl.readFileSync(file, 'utf8'));
  } catch (e) {
    if (e && e.code === 'ENOENT') {
      throw new StudyError('no_study', `No study here: ${file} does not exist. Create one with "hypotrail init".`,
        `Aucune étude ici : ${file} n'existe pas. Créez-en une avec « hypotrail init ».`);
    }
    throw new StudyError('invalid_agent_file', `${file} is not valid JSON.`, `${file} n'est pas un JSON valide.`);
  }
  if (!record || typeof record !== 'object' || record.schema !== AGENT_SCHEMA) {
    throw new StudyError('invalid_agent_file', `${file} is not a ${AGENT_SCHEMA} record.`,
      `${file} n'est pas un enregistrement ${AGENT_SCHEMA}.`);
  }
  const argv = record.cli && record.cli.argv;
  if (!validArgv(argv)) {
    throw new StudyError('invalid_agent_file', `${file} has no valid cli.argv (a list of strings).`,
      `${file} n'a pas de cli.argv valide (une liste de chaînes).`);
  }
  if (typeof record.study === 'string' && realpath(record.study, fsImpl) !== realpath(studyDir, fsImpl)) {
    throw new StudyError('study_moved',
      `This study was created at ${record.study} and is now at ${studyDir}. ` +
      'Its recorded paths are wrong after a move; create a new study with "hypotrail init".',
      `Cette étude a été créée dans ${record.study} et se trouve maintenant dans ${studyDir}. ` +
      'Ses chemins enregistrés sont faux après un déplacement ; créez une nouvelle étude avec « hypotrail init ».');
  }
  return { studyDir, argv: argv.slice(), how: (record.cli && record.cli.how) || null };
}

module.exports = { findStudies, readAgent, isStudy, StudyError, AGENT_FILE, AGENT_SCHEMA, MAX_DEPTH, MAX_VISITED, SKIPPED };
