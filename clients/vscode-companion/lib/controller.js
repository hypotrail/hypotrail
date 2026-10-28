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
//   - the per-key, per-version read cache with coalescing (a version is the summary's
//     `<revision>:<currency>`, decision CR.1; the explicit Refresh and every write empty
//     the non-preview entries), the read concurrency limits
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
const { studyKey } = require('./localstore');
const launch = require('./launch');
const l10n = require('./l10n');
const page = require('./models/page');
const flag = require('./flag');

const HANDLERS_DIR = path.join(__dirname, 'handlers');
const MAX_READS = 2;
const MAX_PREVIEWS = 1;
const DEFAULT_SETTINGS = Object.freeze({ stage: 'v0', reviewer: false, learningLayer: true, chatInsert: false, language: 'auto' });
// English values (tests and the contract); the text shown follows the language (lib/l10n.js).
const UNKNOWN_OUTCOME = l10n.EN.unknownOutcome;
const REVIEWER_REFUSAL = l10n.EN.reviewerRefusal;
// Reviewer mode refuses every write of the study. The handoff export (W7) writes no study
// state, only files under the chosen folder, so a reviewer may run it (decision CA.9).
const REVIEWER_ALLOWED = Object.freeze(['W7']);
const BUSY_REFUSAL = l10n.EN.busyRefusal;
const NOT_PROMOTED = l10n.EN.notPromoted;
const NOT_AVAILABLE = l10n.EN.notAvailable;

/** The cache version of a snapshot: its revision and currency (CR.1). */
function versionOf(snap) {
  return snap ? `${snap.revision}:${snap.currency || ''}` : '0:';
}

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

function createController({ agent, post, runCli = cli.run, settings = DEFAULT_SETTINGS, host = {}, surface = 'panel',
  openArtifact = host.openArtifact || (async () => {}),
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
  // A read runs with cli.READ_ENV (HYPOTRAIL_SESSION_LOG=0): the panel's reads, its polling
  // of `status` included, are not the junior's checks, so the opt-in session log never
  // records them (CLI-CONTRACT §8.6). A write inherits the environment and is logged.
  const runCommand = (argv, timeoutMs, { read = false } = {}) => {
    diagnostics.commands.push(argv.slice(agent.argv.length, agent.argv.length + 2).join(' '));
    const options = { timeoutMs, cwd: agent.studyDir };
    if (read) options.env = { ...process.env, ...cli.READ_ENV };
    return runCli(argv, options);
  };
  const stageAtLeast = wanted => protocol.stageAllows(active.stage, wanted);
  // v0.3 (WP-K, R21): the language of the extension's words: the setting, else (auto) the
  // study language of the last summary.
  const language = () => l10n.resolve(active.language, snapshot ? snapshot.language : null);
  const say = (key, ...args) => l10n.say(language(), key, ...args);

  function sendInit() {
    // `study` (CR.2): the study key, so the webview keeps draft words for this study only.
    send({ type: 'init', stage: active.stage, reviewer: active.reviewer === true, learningLayer: active.learningLayer !== false,
      chatInsert: active.chatInsert === true, task: snapshot ? snapshot.task : null, study: studyKey(agent.studyDir),
      panelContract: flag.PANEL_CONTRACT,
      // Lot P (R51, ADR 0004 decision 14): the read-only What if? tab draws only What if?.
      surface: surface === 'whatif' ? 'whatif' : 'panel',
      marimo: launch.display(agent),
      language: ['auto', 'en', 'fr'].includes(active.language) ? active.language : 'auto' });
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
      return await runCommand(argv, timeoutMs, { read: true });
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
   * ctx.read: a cached, coalesced read. Resolves {ok: true, model, revision, currency,
   * payload, cached?} or {ok: false, message, detail, refusal?}. The cache key is (key,
   * version of the last snapshot: `<revision>:<currency>`, CR.1) and holds the CLI
   * payload: each caller projects it with its own `modelFn`, so loaders of one command
   * share one process and one cache entry. `group: 'preview'` uses the single preview
   * slot. `cache: false` neither reads nor fills the cache (the deliverables read of Overview).
   */
  async function read(key, argv, modelFn, { group = key.startsWith('preview:') ? 'preview' : 'read', timeoutMs, cache: useCache = true } = {}) {
    const version = versionOf(snapshot);
    const currency = snapshot ? snapshot.currency || '' : '';
    const stamp = out => (out.ok ? { ...out, currency } : out);
    if (!useCache) return stamp(readResult(await readProcess(argv, { group, timeoutMs }), modelFn));
    const hit = cache.get(key, version);
    if (hit !== undefined) return { ...stamp(readResult({ payload: hit }, modelFn)), cached: true };
    const id = `${version}|${key}`;
    if (!inflight.has(id)) {
      inflight.set(id, (async () => {
        try {
          const res = await readProcess(argv, { group, timeoutMs });
          if (!res.failure && res.payload && res.payload.ok === true) cache.set(key, version, res.payload);
          return res;
        } finally {
          inflight.delete(id);
        }
      })());
    }
    return stamp(readResult(await inflight.get(id), modelFn));
  }

  async function loadSummary({ since = null } = {}) {
    // ADR 0004 d13 (§5): the one page needs the digest's P1 keys from stage v0.
    const digest = true;
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
    const before = versionOf(snapshot);
    snapshot = out.model;
    if (versionOf(snapshot) !== before) cache.prune(versionOf(snapshot));
    send({ type: 'snapshot', revision: snapshot.revision, currency: snapshot.currency, model: snapshot });
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
      return { op, kind: 'failed', exitCode: res.exitCode, message: `${res.failure || 'The hypotrail CLI failed.'} ${say('unknownOutcome')}` };
    }
    const p = res.payload;
    if (p.ok === true) {
      const out = { op, kind: res.exitCode === 3 ? 'ok_with_problems' : 'ok', exitCode: res.exitCode,
        revision: Number.isInteger(p.revision) ? p.revision : null, artifacts: artifactMessages(p) };
      if (p.status === 'late_not_promoted' || (p.result && p.result.status === 'late_not_promoted')) {
        out.kind = 'not_promoted';
        out.message = say('notPromoted');
      }
      if (p.replayed === true) out.message = say('replayed');
      const recorded = record ? record(p) : null;
      if (recorded) out.recorded = recorded;
      return out;
    }
    const out = { op, kind: 'refused', exitCode: res.exitCode, refusal: refusals.describe(p) };
    if (res.exitCode === 4) out.message = say('executionUnknown');
    return out;
  }

  function invalid(op, message, target = null) {
    send({ type: 'outcome', op, kind: 'invalid', target, message });
  }

  /**
   * ctx.write: one whitelisted write (W4, W5, W7, W8). `argv(requestId)` builds it with lib/cli.js;
   * `record(payload)` returns the `recorded` object of a success. Exclusive: reads wait;
   * a second write while one runs is `invalid`. Always refreshes after the outcome.
   */
  async function write(op, { target = null, argv, record = null, refresh: again_ = true } = {}) {
    if (!protocol.WRITE_OPS.includes(op)) throw new Error(`unknown write ${op}`);
    // Lot P (R51): the What if? tab writes nothing, whatever the stage.
    if (surface === 'whatif') { invalid(op, say('whatifReadOnly'), target); return null; }
    if (active.reviewer && !REVIEWER_ALLOWED.includes(op)) { invalid(op, say('reviewerRefusal'), target); return null; }
    if (busy) { invalid(op, say('busyRefusal'), target); return null; }
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
      // A write can change what a read answers without moving the summary (an export, a
      // render that changed nothing visible): the non-preview cache is emptied (CR.1).
      cache.clearData();
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
      return send({ type: 'view_data', view: 'summary', revision: out.model.revision, currency: out.model.currency, model: out.model });
    }
    const loader = routes.loads[message.view];
    if (!loader || (loader.stage && !stageAtLeast(loader.stage)) || (typeof loader.when === 'function' && !loader.when({ ...active }))) {
      return send({ type: 'load_error', view: message.view, message: say('notAvailable'), detail: '' });
    }
    let argv;
    try {
      // Lot P (R49): a loader may read the snapshot's revision (the Azure ML plan).
      argv = loader.argv(cli, agent, message, snapshot);
    } catch (e) {
      return send({ type: 'load_error', view: message.view, message: String((e && e.message) || e), detail: '' });
    }
    const out = await read(loader.key(message), argv, loader.model);
    if (!out.ok) return send({ type: 'load_error', view: message.view, message: out.message, detail: out.detail || '' });
    const reply = { type: 'view_data', view: message.view, revision: out.revision, currency: out.currency, model: out.model };
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
    exists,
    uuid,
    log,
    artifactPath: name => path.join(agent.studyDir, ARTIFACT_PATHS[name]),
    diagnostics,
    cli,
    refusals,
    language,
    say,
  };

  /** The anchor of a navigation target (§4.3), from the last summary; the path's head when unknown. */
  function anchorOf(target) {
    if (target && typeof target.anchor === 'string') return target.anchor;
    const kind = target && target.kind;
    const id = target && target.id;
    if (kind === 'result') return page.anchorOfResult(snapshot, id);
    const plan = snapshot ? snapshot.plan.map(s => s.id) : [];
    if (kind === 'decision' && plan.includes(id)) return `path:${id}`;
    if (kind === 'proposal') {
      const p = snapshot ? snapshot.proposals.find(x => x.proposalId === id) : null;
      return p ? 'now' : 'path';
    }
    return 'path';
  }

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
    if (spec.write && surface === 'whatif') {
      invalid(spec.write, say('whatifReadOnly'), null);
      return;
    }
    if (spec.write && active.reviewer && !REVIEWER_ALLOWED.includes(spec.write)) {
      invalid(spec.write, say('reviewerRefusal'), message.proposalId || message.executionId || null);
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
        // The explicit Refresh (and the load-error Retry) reads everything again (CR.1).
        cache.clearData();
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
    /** The number of cached payloads (tests: the cache stays bounded). */
    cacheSize: () => cache.size(),
    settings: () => ({ ...active }),
    /** The language of the extension's words (lib/l10n.js). */
    language,
    /**
     * Post a navigation request (a deep link, "go to a result"; §4.3): the target's anchor,
     * resolved from the last summary (a result to `path:<step>/<slot>`, a decision to its
     * step line, an open proposal to Now); false when invalid.
     */
    navigate(target) {
      return send({ type: 'navigate', anchor: anchorOf(target), kind: target.kind, id: target.id });
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
