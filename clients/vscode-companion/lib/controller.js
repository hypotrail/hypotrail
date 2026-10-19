'use strict';
// Panel controller: the router between the webview and the CLI, without the `vscode`
// module, so it is tested with a fake CLI (unit) and the real CLI (integration).
//
// Frozen by WP-0 (COMPANION-ADVANCED §7, §8, §11; docs/plans/COMPANION-ADVANCED-PLAN.md
// §2.2). The controller owns:
//   - validation of every message (lib/protocol.js) and the stage gate: a message whose
//     stage is above the active stage is ignored, like an invalid one (diagnostics.ignored);
//   - the reviewer refusal: every write message gets an `invalid` outcome, nothing runs;
//   - the summary read (snapshot), its coalescing, and the `load` dispatch to loaders;
//   - the per-key, per-revision read cache with coalescing, the read concurrency limits
//     (two reads, one `preview policy`), and the exclusive write lock (reads wait);
//   - the generic outcome mapping of a write (§7, "Outcome handling").
// Handlers live in lib/handlers/*.js. Each exports `{types?, loads?, onReady?}`:
//   types: {messageType: async (message, ctx) => void}
//   loads: {view: {key(message), argv(cli, agent, message), model(payload), stage?, when?(settings)}}
//     `key` names the CLI read, not the view: loaders that run the same command share a
//     key (`evidence` for EDA, Evidence, and What if?, COMPANION-ADVANCED §5, §8.1) and
//     one cached payload, which each projects with its own `model`. `when(settings)`
//     false makes the controller refuse the load like a stage gate (the learning layer
//     off: `explain` is never read, LE-3).
//   onReady: async ctx => void (after `ready`, once the first snapshot is posted)
//   commands: {name: async (args, ctx) => any} (extension commands, e.g. go_to_result)
// Handlers never call cli.run: they call ctx.read and ctx.write.

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const cli = require('./cli');
const protocol = require('./protocol');
const { createCache } = require('./cache');
const { toSummaryModel, ARTIFACT_PATHS } = require('./models/summary');
const refusals = require('./refusals');

const HANDLERS_DIR = path.join(__dirname, 'handlers');
const MAX_READS = 2;
const MAX_PREVIEWS = 1;
const DEFAULT_SETTINGS = Object.freeze({ stage: 'v0', reviewer: false, learningLayer: true, chatInsert: false });
const UNKNOWN_OUTCOME = 'The outcome is unknown: the refreshed panel shows whether anything was recorded.';
const REVIEWER_REFUSAL = 'Read-only reviewer mode.';
// Reviewer mode refuses every write of the study. The handoff export (W7) writes no study
// state, only files under the chosen folder, so a reviewer may run it (decision CA.9).
const REVIEWER_ALLOWED = Object.freeze(['W7']);
const BUSY_REFUSAL = 'Another request is in progress.';
const NOT_PROMOTED = 'The result was computed but not used: the study changed while it ran. Nothing in the study changed.';
const NOT_AVAILABLE = 'Not available in this stage.';

/** Handler modules of lib/handlers/, in file-name order; a type or view claimed twice throws. */
function loadHandlers(dir = HANDLERS_DIR) {
  let names = [];
  try { names = fs.readdirSync(dir).filter(f => f.endsWith('.js')).sort(); } catch (_) { names = []; }
  return names.map(f => ({ name: f.slice(0, -3), ...require(path.join(dir, f)) }));
}

function registry(modules) {
  const types = {};
  const loads = {};
  const ready = [];
  const commands = {};
  for (const m of modules) {
    for (const [name, fn] of Object.entries(m.commands || {})) {
      if (commands[name]) throw new Error(`command ${name} is handled twice (${m.name})`);
      commands[name] = fn;
    }
    for (const [type, fn] of Object.entries(m.types || {})) {
      if (types[type]) throw new Error(`message type ${type} is handled twice (${m.name})`);
      if (!protocol.TO_EXTENSION[type]) throw new Error(`handler ${m.name} names an unknown type ${type}`);
      if (['ready', 'refresh', 'load'].includes(type)) throw new Error(`${type} belongs to the controller`);
      types[type] = fn;
    }
    for (const [view, loader] of Object.entries(m.loads || {})) {
      if (loads[view]) throw new Error(`view ${view} is loaded twice (${m.name})`);
      if (!protocol.VIEWS.includes(view) || view === 'summary') throw new Error(`handler ${m.name} cannot load ${view}`);
      loads[view] = loader;
    }
    if (typeof m.onReady === 'function') ready.push(m.onReady);
  }
  return { types, loads, ready, commands };
}

function artifactMessages(payload) {
  const items = (payload && payload.artifacts) || {};
  return Object.keys(items).map(name => ({ name, status: String((items[name] && items[name].status) || ''),
    message: String((items[name] && items[name].message) || '') }));
}

/** A simple counting semaphore. */
function semaphore(limit) {
  let active = 0;
  const waiting = [];
  return {
    async acquire() {
      if (active < limit) { active += 1; return; }
      await new Promise(resolve => waiting.push(resolve));
      active += 1;
    },
    release() {
      active -= 1;
      const next = waiting.shift();
      if (next) next();
    },
  };
}

function createController({ agent, post, runCli = cli.run, settings = DEFAULT_SETTINGS, host = {},
  openArtifact = host.openArtifact || (async () => {}), confirmWithdraw = host.confirmWithdraw || (async () => true),
  exists = target => fs.existsSync(target), uuid = () => crypto.randomUUID(), log = () => {},
  handlers = loadHandlers() }) {
  let active = { ...DEFAULT_SETTINGS, ...settings };
  let snapshot = null;
  let busy = null;          // {op, target} while a write runs
  let refreshing = null;
  let again = false;
  let disposed = false;
  let writeGate = null;     // a promise while a write runs: reads wait for it
  const cache = createCache();
  const inflight = new Map();
  const reads = semaphore(MAX_READS);
  const previews = semaphore(MAX_PREVIEWS);
  const routes = registry(handlers);
  const diagnostics = { ignored: 0, refreshes: 0, dropped: 0, commands: [], invalid: [] };

  const send = message => {
    if (disposed) return false;
    const valid = protocol.validateOutgoing({ v: protocol.VERSION, ...message });
    if (!valid) {
      diagnostics.dropped += 1;
      diagnostics.invalid.push(protocol.explainOutgoing({ v: protocol.VERSION, ...message }));
      log(new Error(`dropped an invalid outgoing message: ${message && message.type}`));
      return false;
    }
    post(valid);
    return true;
  };
  const runCommand = (argv, timeoutMs) => {
    diagnostics.commands.push(argv.slice(agent.argv.length, agent.argv.length + 2).join(' '));
    return runCli(argv, { timeoutMs, cwd: agent.studyDir });
  };
  const stageAtLeast = wanted => protocol.stageAllows(active.stage, wanted);

  function sendInit() {
    send({ type: 'init', stage: active.stage, reviewer: active.reviewer === true, learningLayer: active.learningLayer !== false,
      chatInsert: active.chatInsert === true, task: snapshot ? snapshot.task : null });
  }

  async function waitForWrite() {
    while (writeGate) await writeGate;
  }

  /** One read process under the concurrency limits. */
  async function readProcess(argv, { group = 'read', timeoutMs = cli.TIMEOUTS.read } = {}) {
    await waitForWrite();
    const limit = group === 'preview' ? previews : reads;
    await limit.acquire();
    try {
      return await runCommand(argv, timeoutMs);
    } finally {
      limit.release();
    }
  }

  function readResult(res, modelFn) {
    if (res.failure || !res.payload) return { ok: false, message: res.failure || 'The hypotrail CLI failed.', detail: res.stderr || '' };
    if (res.payload.ok !== true) {
      const d = refusals.describe(res.payload);
      return { ok: false, refusal: d, message: `${d.code}: ${d.engineMessage}`, detail: '' };
    }
    try {
      const model = modelFn(res.payload);
      return { ok: true, model, payload: res.payload,
        revision: Number.isInteger(res.payload.revision) ? res.payload.revision : (snapshot ? snapshot.revision : 0) };
    } catch (e) {
      return { ok: false, message: String((e && e.message) || e), detail: '' };
    }
  }

  /**
   * ctx.read: a cached, coalesced read. Resolves {ok: true, model, revision, payload,
   * cached?} or {ok: false, message, detail, refusal?}. The cache key is (key, revision of
   * the last snapshot) and holds the CLI payload: each caller projects it with its own
   * `modelFn`, so loaders of one command share one process and one cache entry.
   * `group: 'preview'` uses the single preview slot.
   */
  async function read(key, argv, modelFn, { group = key.startsWith('preview:') ? 'preview' : 'read', timeoutMs } = {}) {
    const revision = snapshot ? snapshot.revision : 0;
    const hit = cache.get(key, revision);
    if (hit !== undefined) return { ...readResult({ payload: hit }, modelFn), cached: true };
    const id = `${revision}|${key}`;
    if (!inflight.has(id)) {
      inflight.set(id, (async () => {
        try {
          const res = await readProcess(argv, { group, timeoutMs });
          if (!res.failure && res.payload && res.payload.ok === true) cache.set(key, revision, res.payload);
          return res;
        } finally {
          inflight.delete(id);
        }
      })());
    }
    return readResult(await inflight.get(id), modelFn);
  }

  async function loadSummary({ since = null } = {}) {
    const digest = stageAtLeast('v1');
    let res = await readProcess(cli.statusArgv(agent, { digest, since }));
    // An engine without C1 (CLI-CONTRACT-COMPANION §13 stub): fall back to the v0 read.
    if (digest && res.payload && res.payload.ok === false && res.payload.error &&
        res.payload.error.code === 'unsupported_capability' && since === null) {
      res = await readProcess(cli.statusArgv(agent));
    }
    return readResult(res, toSummaryModel);
  }

  async function load() {
    diagnostics.refreshes += 1;
    const out = await loadSummary();
    if (!out.ok) {
      send({ type: 'load_error', view: null, message: out.message, detail: out.detail || '' });
      return;
    }
    const before = snapshot ? snapshot.revision : null;
    snapshot = out.model;
    if (before === null || snapshot.revision > before) cache.prune(snapshot.revision);
    send({ type: 'snapshot', revision: snapshot.revision, model: snapshot });
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
        send({ type: 'load_error', view: null, message: String((e && e.message) || e), detail: '' });
      } finally {
        refreshing = null;
      }
    })();
    return refreshing;
  }

  function outcomeOf(op, res, record) {
    if (res.failure || !res.payload) {
      return { op, kind: 'failed', exitCode: res.exitCode, message: `${res.failure || 'The hypotrail CLI failed.'} ${UNKNOWN_OUTCOME}` };
    }
    const p = res.payload;
    if (p.ok === true) {
      const out = { op, kind: res.exitCode === 3 ? 'ok_with_problems' : 'ok', exitCode: res.exitCode,
        revision: Number.isInteger(p.revision) ? p.revision : null, artifacts: artifactMessages(p) };
      if (p.status === 'late_not_promoted' || (p.result && p.result.status === 'late_not_promoted')) {
        out.kind = 'not_promoted';
        out.message = NOT_PROMOTED;
      }
      if (p.replayed === true) out.message = '(replayed, no effect)';
      const recorded = record ? record(p) : null;
      if (recorded) out.recorded = recorded;
      return out;
    }
    const out = { op, kind: 'refused', exitCode: res.exitCode, refusal: refusals.describe(p) };
    if (res.exitCode === 4) out.message = 'An execution has an unknown outcome.';
    return out;
  }

  function invalid(op, message, target = null) {
    send({ type: 'outcome', op, kind: 'invalid', target, message });
  }

  /**
   * ctx.write: one whitelisted write (W1-W7). `argv(requestId)` builds it with lib/cli.js;
   * `record(payload)` returns the `recorded` object of a success. Exclusive: reads wait;
   * a second write while one runs is `invalid`. Always refreshes after the outcome.
   */
  async function write(op, { target = null, argv, record = null, refresh: again_ = true } = {}) {
    if (!protocol.WRITE_OPS.includes(op)) throw new Error(`unknown write ${op}`);
    if (active.reviewer && !REVIEWER_ALLOWED.includes(op)) { invalid(op, REVIEWER_REFUSAL, target); return null; }
    if (busy) { invalid(op, BUSY_REFUSAL, target); return null; }
    let built;
    try {
      built = argv(uuid());
    } catch (e) {
      invalid(op, `${String((e && e.message) || e)}. Nothing was recorded.`, target);
      return null;
    }
    busy = { op, target };
    let release;
    writeGate = new Promise(resolve => { release = resolve; });
    send({ type: 'busy', busy: true, op, target });
    let outcome;
    try {
      const res = await runCommand(built, cli.TIMEOUTS[op]);
      outcome = { ...outcomeOf(op, res, record), target };
      send({ type: 'outcome', ...outcome });
    } finally {
      busy = null;
      writeGate = null;
      release();
      send({ type: 'busy', busy: false, op, target });
    }
    if (again_) await refresh();
    return outcome;
  }

  async function handleLoad(message) {
    if (message.view === 'summary') {
      const out = await loadSummary({ since: message.since === undefined ? null : message.since });
      if (!out.ok) return send({ type: 'load_error', view: 'summary', message: out.message, detail: out.detail || '' });
      return send({ type: 'view_data', view: 'summary', revision: out.model.revision, model: out.model });
    }
    const loader = routes.loads[message.view];
    if (!loader || (loader.stage && !stageAtLeast(loader.stage)) || (typeof loader.when === 'function' && !loader.when({ ...active }))) {
      return send({ type: 'load_error', view: message.view, message: NOT_AVAILABLE, detail: '' });
    }
    const out = await read(loader.key(message), loader.argv(cli, agent, message), loader.model);
    if (!out.ok) return send({ type: 'load_error', view: message.view, message: out.message, detail: out.detail || '' });
    const reply = { type: 'view_data', view: message.view, revision: out.revision, model: out.model };
    if (message.resultId !== undefined) reply.resultId = message.resultId;
    return send(reply);
  }

  const ctx = {
    get agent() { return agent; },
    get settings() { return { ...active }; },
    snapshot: () => snapshot,
    stageAtLeast,
    post: send,
    read,
    write,
    refresh,
    invalid,
    host,
    openArtifact,
    confirmWithdraw,
    exists,
    uuid,
    log,
    artifactPath: name => path.join(agent.studyDir, ARTIFACT_PATHS[name]),
    diagnostics,
    cli,
    refusals,
  };

  async function handle(raw) {
    const message = protocol.validateIncoming(raw);
    if (!message) {
      diagnostics.ignored += 1;
      return;
    }
    if (!protocol.stageAllows(active.stage, protocol.stageOf(message))) {
      diagnostics.ignored += 1;
      return;
    }
    const spec = protocol.TO_EXTENSION[message.type];
    if (spec.write && active.reviewer && !REVIEWER_ALLOWED.includes(spec.write)) {
      invalid(spec.write, REVIEWER_REFUSAL, message.proposalId || message.executionId || null);
      return;
    }
    switch (message.type) {
      case 'ready':
        sendInit();
        await refresh();
        if (snapshot) sendInit();
        for (const fn of routes.ready) await fn(ctx);
        return;
      case 'refresh':
        return refresh();
      case 'load':
        return handleLoad(message);
      default: {
        const fn = routes.types[message.type];
        if (!fn) {
          diagnostics.ignored += 1;
          return;
        }
        return fn(message, ctx);
      }
    }
  }

  return {
    handle, refresh,
    snapshot: () => snapshot,
    diagnostics: () => diagnostics,
    settings: () => ({ ...active }),
    /** Post a navigation request (a deep link, "go to a result"); false when invalid. */
    navigate(target) {
      return send({ type: 'navigate', tab: target.tab, kind: target.kind, id: target.id });
    },
    /** Run an extension command a handler registered; undefined when none did. */
    async command(name, args) {
      const fn = routes.commands[name];
      return fn ? fn(args || {}, ctx) : undefined;
    },
    hasCommand: name => Boolean(routes.commands[name]),
    /** New settings (a configuration change): posts `init` again. */
    updateSettings(next) {
      active = { ...active, ...next };
      sendInit();
    },
    context: ctx,
    dispose() { disposed = true; },
  };
}

module.exports = { createController, loadHandlers, registry, DEFAULT_SETTINGS, UNKNOWN_OUTCOME, REVIEWER_REFUSAL, REVIEWER_ALLOWED,
  BUSY_REFUSAL, NOT_PROMOTED, NOT_AVAILABLE, MAX_READS, MAX_PREVIEWS };
