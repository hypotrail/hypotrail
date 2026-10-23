'use strict';
// Hypotrail study companion (ADR 0002, ADR 0003, ADR 0004). A VS Code webview that is one
// more client of the `hypotrail` CLI. It has no state, database, server, socket, or
// language-model integration of its own. Its writes are the whitelist W4-W7 of
// COMPANION-ADVANCED §7, each gated by `hypotrail.companion.stage` (default "v0": no
// write; W1-W3, confirm, withdraw and propose, were withdrawn by the v0.3 narrowing of
// ADR 0004: decisions are made in the chat only).
//
// Behind a feature flag, off by default. Activation only registers the commands and the
// URI handler; with the flag off each of them shows one message and does nothing else:
// no setting beyond the flag is read, no file is read, no process is started.
//
// Owned by the integrator (docs/plans/COMPANION-ADVANCED-PLAN.md §2.2, WP-I). Views and
// handlers never need to change it: a deep link goes through lib/uri.js, "go to a result"
// through the handler command `go_to_result`. The study switch and a link to another
// discovered study rebind the open panel to a new controller and watcher (§6.1.6, CI.10).

const vscode = require('vscode');
const fs = require('fs');
const path = require('path');
const flag = require('./lib/flag');
const study = require('./lib/study');
const uri = require('./lib/uri');
const launch = require('./lib/launch');
const { createController } = require('./lib/controller');
const { watchStudy } = require('./lib/watch');
const { renderHtml } = require('./lib/html');
const l10n = require('./lib/l10n');

const COMMAND = 'hypotrail.companion.open';
const REVIEWER_COMMAND = 'hypotrail.companion.openReviewer';
const GO_TO_RESULT_COMMAND = 'hypotrail.companion.goToResult';
const VIEW_TYPE = 'hypotrail.companion.study';
// v0.3 (WP-K, R21): the extension's words follow `hypotrail.companion.language`: `en`, `fr`,
// else the open study's language, else VS Code's display language (lib/l10n.js).
function lang() {
  const study = current && current.controller && typeof current.controller.language === 'function'
    ? current.controller.language() : null;
  return l10n.resolve(flag.language(vscode), study, vscode.env && vscode.env.language);
}
const say = (key, ...args) => l10n.say(lang(), key, ...args);
let current = null;   // {panel, controller, watcher, agent, reviewer}
// The Marimo terminals this extension opened, per notebook file: one terminal per file is
// reused while it is open (WP-A5, ADR 0004 "local launch").
const marimoTerminals = new Map();

/**
 * Open one of the three Marimo launches of lib/launch.js in a VS Code terminal, created with
 * an argument list (shellPath, shellArgs): no shell string, nothing typed in. The argv is
 * checked again here, so no other command can reach a terminal. Returns true when an open
 * terminal for the same file was shown again, false when a new one was created.
 */
function launchMarimo(agent, spec) {
  if (!spec || !launch.isMarimoLaunch(spec.argv, agent.studyDir, spec.name)) throw new Error('not a Marimo launch of this study');
  const open = marimoTerminals.get(spec.file);
  if (open && open.exitStatus === undefined && (vscode.window.terminals || [open]).includes(open)) {
    open.show();
    return true;
  }
  const terminal = vscode.window.createTerminal({ name: spec.terminalName, shellPath: spec.argv[0],
    shellArgs: spec.argv.slice(1), cwd: agent.studyDir });
  marimoTerminals.set(spec.file, terminal);
  terminal.show();
  return false;
}


/**
 * The study folder to open. `pick` (the study switch) always shows the quick pick. `want`
 * (a deep link's `study`) is opened directly only when it is a discovered study;
 * otherwise the quick pick asks (§12, "URI handler").
 */
async function chooseStudy(pick = false, want = null) {
  const folders = (vscode.workspace.workspaceFolders || []).map(f => f.uri.fsPath);
  const found = study.findStudies(folders);
  if (want) {
    const match = found.find(dir => path.resolve(dir) === path.resolve(want));
    if (match) return match;
    pick = true;
  }
  if (found.length === 1 && !pick) return found[0];
  if (found.length > 1 || (pick && found.length > 0)) {
    // One entry per study: its folder name, described by its path (§6.1.6).
    const items = found.map(dir => ({ label: path.basename(dir) || dir, description: dir, dir }));
    if (pick) items.push({ label: say('pickFolder'), dir: null });
    const picked = await vscode.window.showQuickPick(items,
      { title: say('chooseTitle'), placeHolder: say('choosePlaceholder') });
    if (!picked) return null;
    if (picked.dir) return picked.dir;
  }
  const uris = await vscode.window.showOpenDialog({ canSelectFolders: true, canSelectFiles: false,
    canSelectMany: false, openLabel: say('openLabel'), title: say('openTitle') });
  return uris && uris[0] ? uris[0].fsPath : null;
}

function close() {
  if (!current) return;
  const { panel } = current;
  current = null;
  panel.dispose();
}

/** The flag and trust checks of every entry point (INV-10, INV-11); true when allowed. */
function allowed() {
  if (!flag.isEnabled(vscode)) {
    vscode.window.showInformationMessage(say('disabled'));
    return false;
  }
  if (!vscode.workspace.isTrusted) {
    vscode.window.showErrorMessage(say('trust'));
    return false;
  }
  return true;
}

function host(context, agent) {
  return {
    launchMarimo: async spec => launchMarimo(agent, spec),
    openArtifact: async (name, target, options = {}) => {
      let file = vscode.Uri.file(target);
      if (options.fragment && typeof file.with === 'function') file = file.with({ fragment: options.fragment });
      if (name === 'report') {
        await vscode.env.openExternal(file);
        return;
      }
      const shown = { preview: false };
      const line = options.line;
      if (Number.isInteger(line) && line > 0 && vscode.Range) shown.selection = new vscode.Range(line - 1, 0, line - 1, 0);
      await vscode.window.showTextDocument(file, shown);
    },
    pickFolder: async defaultPath => {
      const uris = await vscode.window.showOpenDialog({ canSelectFolders: true, canSelectFiles: false, canSelectMany: false,
        defaultUri: defaultPath ? vscode.Uri.file(defaultPath) : undefined, openLabel: say('exportHere') });
      return uris && uris[0] ? uris[0].fsPath : null;
    },
    openFile: async (target, { line = null } = {}) => {
      const options = { preview: false };
      if (Number.isInteger(line) && line > 0 && vscode.Range) options.selection = new vscode.Range(line - 1, 0, line - 1, 0);
      await vscode.window.showTextDocument(vscode.Uri.file(target), options);
    },
    revealInOS: async target => vscode.commands.executeCommand('revealFileInOS', vscode.Uri.file(target)),
    writeClipboard: async text => vscode.env.clipboard.writeText(text),
    executeCommand: (id, ...args) => vscode.commands.executeCommand(id, ...args),
    notify: text => vscode.window.showInformationMessage(text),
    globalState: context.globalState,
    switchStudy: async () => openPanel(context, { reviewer: current ? current.reviewer : false, pick: true }),
  };
}

async function openPanel(context, { reviewer = false, pick = false, want = null } = {}) {
  if (!allowed()) return null;
  const dir = await chooseStudy(pick, want);
  if (!dir) return null;
  let agent;
  try {
    agent = study.readAgent(dir);
  } catch (e) {
    vscode.window.showErrorMessage(e instanceof study.StudyError ? (lang() === 'fr' && e.messageFr) || e.message
      : say('cannotOpen', e.message));
    return null;
  }
  if (current && current.agent.studyDir === agent.studyDir && current.reviewer === reviewer) {
    current.panel.reveal(vscode.ViewColumn.Beside);
    await current.controller.refresh();
    return current;
  }
  // The study switch (§6.1.6, ST-1): the open panel stays; its controller and watcher are
  // disposed and a new pair reads the chosen study. The document is loaded again, so the
  // webview starts from `ready` with the new study's snapshot.
  if (current && (pick || want) && current.reviewer === reviewer) {
    attach(context, current, agent);
    current.panel.webview.html = renderHtml();
    current.panel.reveal(vscode.ViewColumn.Beside);
    return current;
  }
  close();

  const settings = flag.settings(vscode, process.env, { forceReviewer: reviewer });
  const panel = vscode.window.createWebviewPanel(VIEW_TYPE, settings.reviewer ? say('panelTitleReviewer') : say('panelTitle'),
    vscode.ViewColumn.Beside, {
      enableScripts: true, enableCommandUris: false, enableForms: false, retainContextWhenHidden: false,
      localResourceRoots: [],
    });
  const mine = { panel, controller: null, watcher: null, agent: null, reviewer };
  attach(context, mine, agent);
  current = mine;
  // Panel events go to the panel's controller of the moment (the study switch replaces it).
  const subscriptions = [
    panel.webview.onDidReceiveMessage(message => {
      mine.controller.handle(message).catch(e => console.error('[hypotrail companion]', e));
    }),
    panel.onDidChangeViewState(event => {
      if (event.webviewPanel.visible) mine.controller.refresh();
    }),
  ];
  if (typeof vscode.workspace.onDidChangeConfiguration === 'function') {
    subscriptions.push(vscode.workspace.onDidChangeConfiguration(event => {
      if (!event || typeof event.affectsConfiguration !== 'function' || event.affectsConfiguration(flag.SETTING_SECTION)) {
        // INV-10 (review finding M2): the master flag turned off closes the panel; its
        // controller and watcher are disposed with it, so nothing runs any more.
        if (!flag.isEnabled(vscode)) {
          panel.dispose();
          return;
        }
        if (mine.controller) mine.controller.updateSettings(flag.settings(vscode, process.env, { forceReviewer: reviewer }));
      }
    }));
  }
  const configuration = subscriptions.slice(2);
  subscriptions.push(panel.onDidDispose(() => {
    detach(mine);
    for (const s of configuration) if (s && typeof s.dispose === 'function') s.dispose();
    if (current === mine) current = null;
  }));
  context.subscriptions.push(...subscriptions);
  panel.webview.html = renderHtml();
  return mine;
}

/** Dispose the panel's controller and watcher (a study switch or the panel's close). */
function detach(mine) {
  if (mine.watcher) mine.watcher.dispose();
  if (mine.controller) mine.controller.dispose();
  mine.watcher = null;
  mine.controller = null;
}

/** Bind a panel to a study: a new controller and watcher, the old ones disposed. */
function attach(context, mine, agent) {
  detach(mine);
  const { panel, reviewer } = mine;
  const settings = flag.settings(vscode, process.env, { forceReviewer: reviewer });
  const controller = createController({
    agent,
    settings,
    post: message => { panel.webview.postMessage(message); },
    exists: target => fs.existsSync(target),
    host: host(context, agent),
    log: e => console.error('[hypotrail companion]', e),
  });
  mine.controller = controller;
  mine.agent = agent;
  mine.watcher = watchStudy(agent.studyDir, () => controller.refresh());
}

async function goToResult(context) {
  if (!allowed()) return null;
  if (!flag.stageAtLeast(flag.stage(vscode), 'v2')) {
    vscode.window.showInformationMessage(say('notInStage'));
    return null;
  }
  const text = await vscode.window.showInputBox({ title: say('goTitle'), prompt: say('goPrompt') });
  if (text === undefined || text === null) return null;
  const prefix = uri.resultIdInput(text);
  if (!prefix) {
    vscode.window.showInformationMessage(say('invalidLink'));
    return null;
  }
  const opened = current || await openPanel(context);
  if (!opened) return null;
  if (!opened.controller.hasCommand('go_to_result')) {
    vscode.window.showInformationMessage(say('notInStage'));
    return null;
  }
  return opened.controller.command('go_to_result', { prefix });
}

async function handleUri(context, link) {
  if (!allowed()) return null;
  const target = uri.parseDeepLink(link);
  if (!target) {
    vscode.window.showInformationMessage(say('invalidLink'));
    return null;
  }
  // A link naming another study opens it (a discovered one) or asks (the quick pick).
  const other = target.study && (!current || path.resolve(current.agent.studyDir) !== path.resolve(target.study));
  const opened = other ? await openPanel(context, { reviewer: current ? current.reviewer : false, want: target.study })
    : current || await openPanel(context);
  if (!opened) return null;
  opened.controller.navigate(target);
  return opened;
}

function activate(context) {
  const report = e => {
    vscode.window.showErrorMessage(say('failed', e.message));
    return null;
  };
  context.subscriptions.push(
    vscode.commands.registerCommand(COMMAND, () => openPanel(context).catch(report)),
    vscode.commands.registerCommand(REVIEWER_COMMAND, () => openPanel(context, { reviewer: true }).catch(report)),
    vscode.commands.registerCommand(GO_TO_RESULT_COMMAND, () => goToResult(context).catch(report)),
  );
  if (vscode.window && typeof vscode.window.registerUriHandler === 'function') {
    context.subscriptions.push(vscode.window.registerUriHandler({ handleUri: link => handleUri(context, link).catch(report) }));
  }
  // For tests and diagnostics only: the panel currently open, if any.
  return { current: () => current };
}

function deactivate() {
  close();
}

module.exports = { activate, deactivate, COMMAND, REVIEWER_COMMAND, GO_TO_RESULT_COMMAND, VIEW_TYPE };
