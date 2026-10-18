'use strict';
// Study discovery (ADR 0003, CW.3). A study is a folder holding `.hypotrail/agent.json`
// (`hypotrail.agent/1`, written by `hypotrail init`, CLI-CONTRACT §8.4). The CLI argv is
// taken from `agent.json.cli.argv`, never from its shell string.

const fs = require('fs');
const path = require('path');

const AGENT_SCHEMA = 'hypotrail.agent/1';
const AGENT_FILE = path.join('.hypotrail', 'agent.json');
const MAX_ARGV = 32;

class StudyError extends Error {
  constructor(code, message) {
    super(message);
    this.code = code;
  }
}

function isStudy(dir, fsImpl = fs) {
  try {
    return fsImpl.statSync(path.join(dir, AGENT_FILE)).isFile();
  } catch (_) {
    return false;
  }
}

/** Folders among `folders` (absolute paths) that hold a study, in the given order. */
function findStudies(folders, fsImpl = fs) {
  const seen = new Set();
  const out = [];
  for (const folder of folders || []) {
    if (typeof folder !== 'string' || !folder) continue;
    const dir = path.resolve(folder);
    if (seen.has(dir)) continue;
    seen.add(dir);
    if (isStudy(dir, fsImpl)) out.push(dir);
  }
  return out;
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
      throw new StudyError('no_study', `No study here: ${file} does not exist. Create one with "hypotrail init".`);
    }
    throw new StudyError('invalid_agent_file', `${file} is not valid JSON.`);
  }
  if (!record || typeof record !== 'object' || record.schema !== AGENT_SCHEMA) {
    throw new StudyError('invalid_agent_file', `${file} is not a ${AGENT_SCHEMA} record.`);
  }
  const argv = record.cli && record.cli.argv;
  if (!validArgv(argv)) {
    throw new StudyError('invalid_agent_file', `${file} has no valid cli.argv (a list of strings).`);
  }
  if (typeof record.study === 'string' && realpath(record.study, fsImpl) !== realpath(studyDir, fsImpl)) {
    throw new StudyError('study_moved',
      `This study was created at ${record.study} and is now at ${studyDir}. ` +
      'Its recorded paths are wrong after a move; create a new study with "hypotrail init".');
  }
  return { studyDir, argv: argv.slice(), how: (record.cli && record.cli.how) || null };
}

module.exports = { findStudies, readAgent, isStudy, StudyError, AGENT_FILE, AGENT_SCHEMA };
