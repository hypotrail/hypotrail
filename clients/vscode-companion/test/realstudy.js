'use strict';
// Helpers of the real-CLI integration tests per stage (WP-I; integration-v1/v2/v3.test.js).
//
// A study is created from a committed case of use-cases/ (Bank Marketing, binary; Auto
// MPG, regression), which is only read, in a temporary folder outside the repository whose
// path holds spaces and quotes. The chat agent's part (propose, run, note) is played by
// direct CLI calls through the argv `init` recorded in .hypotrail/agent.json; the panel's
// part goes through the real controller (lib/controller.js) and the real CLI processes.
// No VS Code is involved. Every read command's wall time is recorded (§11, measured, not
// asserted) and printed as a test diagnostic.

const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFileSync, spawnSync } = require('child_process');
const cli = require('../lib/cli');
const { readAgent } = require('../lib/study');
const { createController } = require('../lib/controller');

const REPO = path.resolve(__dirname, '..', '..', '..');
const FRAMEWORK = path.join(REPO, 'framework');
const PYTHON = path.join(FRAMEWORK, '.venv', 'bin', 'python');
const CASES = { binary: path.join(REPO, 'use-cases', 'bank-marketing'), regression: path.join(REPO, 'use-cases', 'auto-mpg') };
const skip = fs.existsSync(PYTHON) ? false : 'framework/.venv is missing: run uv sync --project framework --group dev';
// INV-12: the words of a decision rule, absent from everything a regression study shows.
const FORBIDDEN = /\b(threshold|capacity|precision|recall|positive class|policy|calling rule|decision rule|selected)\b/i;
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

/** Every string of a value, recursively. */
function strings(value, out = []) {
  if (typeof value === 'string') out.push(value);
  else if (Array.isArray(value)) value.forEach(v => strings(v, out));
  else if (value && typeof value === 'object') Object.values(value).forEach(v => strings(v, out));
  return out;
}

/** The availability decision of the walkthroughs (a test choice, not a recommendation). */
function availability(task) {
  const code = [
    'import json, sys',
    `sys.path.insert(0, ${JSON.stringify(path.join(FRAMEWORK, 'tests', 'study'))})`,
    'import flowkit as fk',
    'over = json.loads(sys.argv[2])',
    'print(json.dumps(fk.availability(sys.argv[1], **over)))',
  ].join('\n');
  const over = task === 'binary'
    ? { duration: 'not_available', day: 'not_available', month: 'not_available', campaign: 'not_available', contact: 'uncertain_included' }
    : { acceleration: 'uncertain_excluded' };
  return JSON.parse(execFileSync(PYTHON, ['-c', code, CASES[task], JSON.stringify(over)], { encoding: 'utf8', cwd: os.tmpdir() }));
}

/** A copy of a committed case (case.yaml, case-*, data/) under `root`, so a test may edit its data. */
function copyCase(task, root) {
  const src = CASES[task];
  const dir = path.join(root, 'case');
  fs.mkdirSync(dir);
  for (const f of fs.readdirSync(src)) if (f === 'case.yaml' || f.startsWith('case-')) fs.copyFileSync(path.join(src, f), path.join(dir, f));
  fs.cpSync(path.join(src, 'data'), path.join(dir, 'data'), { recursive: true });
  return dir;
}

class Study {
  /** `copy: true` initialises the study on a copy of the case (`this.caseDir`), never on use-cases/. */
  constructor(task, name, { copy = false } = {}) {
    this.task = task;
    this.root = fs.mkdtempSync(path.join(os.tmpdir(), `hypotrail ${name} 'it' "q" `));
    this.studyDir = path.join(this.root, `${name} "study" here`);
    this.caseDir = copy ? copyCase(task, this.root) : CASES[task];
    const init = JSON.parse(execFileSync(PYTHON, ['-m', 'mlkit.study.cli', 'init', '--case', path.join(this.caseDir, 'case.yaml'),
      '--study', this.studyDir], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'], cwd: os.tmpdir() }));
    assert.equal(init.ok, true, JSON.stringify(init));
    this.agent = readAgent(this.studyDir);
    this.n = 0;
  }

  /** One CLI call of the chat agent, through the recorded argv. */
  hyp(args, env = {}) {
    const res = spawnSync(this.agent.argv[0], [...this.agent.argv.slice(1), ...args.map(String), '--study', this.studyDir],
      { encoding: 'utf8', cwd: os.tmpdir(), env: { ...process.env, ...env } });
    const out = String(res.stdout || '').trim();
    return out ? JSON.parse(out) : { ok: null, exitCode: res.status, stderr: res.stderr };
  }

  rid() { this.n += 1; return `chat-${this.task}-${this.n}`; }
  rev() { return this.hyp(['status', '--json']).revision; }
  view() { return this.hyp(['status', '--json']).view; }

  propose(decision, value, { json = true, restatement, rationale = 'It fits the scenario.' } = {}) {
    const out = this.hyp(['decide', 'propose', decision, json ? '--value-json' : '--value', json ? JSON.stringify(value) : value,
      '--restatement', restatement || `You decide the ${decision} as stated.`, '--rationale', rationale,
      '--request-id', this.rid(), '--expected-revision', this.rev()]);
    assert.equal(out.ok, true, JSON.stringify(out));
    return out.result.proposal_id;
  }

  decide(decision, value, opts = {}) {
    const pid = this.propose(decision, value, opts);
    const out = this.hyp(['decide', 'confirm', pid, '--user-words', opts.words || `Yes, I want the ${decision} exactly as you stated it`,
      '--request-id', this.rid(), '--expected-revision', this.rev()]);
    assert.equal(out.ok, true, JSON.stringify(out));
    return pid;
  }

  run(activity, ...options) {
    const out = this.hyp(['run', activity, ...options, '--request-id', this.rid(), '--expected-revision', this.rev()]);
    assert.equal(out.ok, true, JSON.stringify(out).slice(0, 2000));
    return out;
  }

  /** The three pauses of the walkthrough, confirmed in the chat. */
  pauses() {
    if (this.task === 'binary') {
      this.decide('prediction_time', 'before the first contact of the campaign, from the client file');
      this.decide('feature_availability', availability('binary'));
      this.decide('split', { method: 'stratified_random', validation_fraction: 0.3, seed: 20261017 });
    } else {
      this.decide('prediction_time', 'when the technical characteristics of a new model are fixed, before its fuel efficiency is measured');
      this.decide('feature_availability', availability('regression'));
      this.decide('split', { method: 'ordinal_cutoff', column: 'model_year', cutoff: 79 });
    }
    this.modelDecisions();
  }

  /** WP-A4: the success criterion and the engine's default preprocessing, needed before any fit. */
  modelDecisions() {
    const decisions = this.view().decisions;
    if (!decisions.success_criterion) return;   // a study created before WP-A4
    this.decide('success_criterion', this.task === 'binary'
      ? { metric: 'precision_gain', min_points: 5 } : { metric: 'mae_reduction', min_share: 0.1 });
    this.decide('preprocessing', { missing: 'none', rare_category_min_rows: 0, caps: {}, log_transform: [] });
  }

  /** WP-B1: the variant the choice compares, named in the chat and fitted like the candidate. */
  variant() {
    if (!this.view().decisions.model_variant) return;   // a study created before WP-B1
    this.decide('model_variant', { kind: 'regularisation', strength: 'strong' });
    this.run('fit.variant');
  }

  /** The agent's walkthrough up to the fits (binary: and two policy evaluations). */
  walk() {
    this.pauses();
    if (this.task === 'binary') {
      for (const a of ['split', 'eda.target_rate', 'eda.special_values']) this.run(a);
      this.run('eda.rate_by', '--column=job');
      this.run('fit.baseline');
      this.run('fit.logistic');
      this.variant();
      this.run('policy.evaluate', '--rule', 'capacity:100');
    } else {
      for (const a of ['split', 'eda.target_summary', 'eda.special_values']) this.run(a);
      this.run('eda.mean_by', '--column=model_year');
      this.run('fit.baseline');
      this.run('fit.linear');
      this.variant();
      this.run('evaluate.regression');
    }
  }

  /** A clone of this study at its current state (shutil-like copy), for an isolated test. */
  clone(name) {
    const copy = Object.create(Study.prototype);
    Object.assign(copy, { task: this.task, n: this.n + 1000 });
    copy.root = fs.mkdtempSync(path.join(os.tmpdir(), `hypotrail ${name} 'it' "q" `));
    copy.studyDir = path.join(copy.root, `${name} "study" here`);
    fs.cpSync(this.studyDir, copy.studyDir, { recursive: true });
    copy.agent = { ...this.agent, studyDir: copy.studyDir };
    return copy;
  }

  dispose() { fs.rmSync(this.root, { recursive: true, force: true }); }
}

/**
 * The real controller on a study. `times` collects [command, ms] of every CLI process the
 * panel ran; `last(type)` is the last posted message of a type.
 */
function panel(study, settings = {}, host = {}) {
  const posted = [];
  const times = [];
  const runCli = async (argv, options) => {
    const start = Date.now();
    const res = await cli.run(argv, options);
    times.push([argv.slice(study.agent.argv.length, study.agent.argv.length + 2).join(' '), Date.now() - start]);
    return res;
  };
  const c = createController({ agent: study.agent, post: m => posted.push(m), runCli, settings,
    host: { confirmWithdraw: async () => true, confirmModal: async () => true, ...host },
    confirmWithdraw: async () => true });
  return {
    c, posted, times,
    last: type => posted.filter(m => m.type === type).at(-1),
    all: type => posted.filter(m => m.type === type),
    snapshot: () => posted.filter(m => m.type === 'snapshot').at(-1).model,
    commands: () => c.diagnostics().commands,
    send: m => c.handle({ v: 2, ...m }),
  };
}

/** Print the read wall times of a panel (§11: measured, written to the test output). */
function report(t, p, label) {
  const reads = p.times.filter(([cmd]) => !/^(decide|render|export|run)\b/.test(cmd));
  t.diagnostic(`${label}: ${reads.map(([cmd, ms]) => `${cmd} ${ms} ms`).join('; ')}`);
}

module.exports = { Study, panel, report, strings, availability, skip, FORBIDDEN, UUID_RE, PYTHON, REPO, CASES };
