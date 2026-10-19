'use strict';
// Hypotrail study companion (ADR 0002, ADR 0003, ADR 0004). A VS Code webview that is one
// more client of the `hypotrail` CLI. It has no state, database, server, socket, or
// language-model integration of its own. Its writes are the whitelist W1-W7 of
// COMPANION-ADVANCED §7, each gated by `hypotrail.companion.stage` (default "v0": confirm
// and withdraw only).
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
const { createController } = require('./lib/controller');
const { watchStudy } = require('./lib/watch');
const { renderHtml } = require('./lib/html');

const COMMAND = 'hypotrail.companion.open';
const REVIEWER_COMMAND = 'hypotrail.companion.openReviewer';
const GO_TO_RESULT_COMMAND = 'hypotrail.companion.goToResult';
const VIEW_TYPE = 'hypotrail.companion.study';
const TRUST_MESSAGE = 'The Hypotrail companion runs the study CLI, so it needs a trusted workspace.';
const NOT_IN_STAGE = 'This is not available in the current stage of the companion (hypotrail.companion.stage).';
let current = null;   // {panel, controller, watcher, agent, reviewer}

const PICK_FOLDER = 'Pick another folder...';

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
    if (pick) items.push({ label: PICK_FOLDER, dir: null });
    const picked = await vscode.window.showQuickPick(items,
      { title: 'Hypotrail: choose a study', placeHolder: 'A folder holding .hypotrail/agent.json' });
    if (!picked) return null;
    if (picked.dir) return picked.dir;
  }
  const uris = await vscode.window.showOpenDialog({ canSelectFolders: true, canSelectFiles: false,
    canSelectMany: false, openLabel: 'Open this study', title: 'Hypotrail: pick a study folder (it holds .hypotrail/agent.json)' });
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
    vscode.window.showInformationMessage(flag.DISABLED_MESSAGE);
    return false;
  }
  if (!vscode.workspace.isTrusted) {
    vscode.window.showErrorMessage(TRUST_MESSAGE);
    return false;
  }
  return true;
}

function host(context) {
  return {
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
    confirmWithdraw: async proposal => {
      const answer = await vscode.window.showWarningMessage(
        `Withdraw proposal ${proposal.proposalId} (${proposal.decisionTitle})? Nothing is confirmed; the assistant can propose again in the chat.`,
        { modal: true }, 'Withdraw');
      return answer === 'Withdraw';
    },
    confirmModal: async (message, action) => (await vscode.window.showWarningMessage(message, { modal: true }, action)) === action,
    pickFolder: async defaultPath => {
      const uris = await vscode.window.showOpenDialog({ canSelectFolders: true, canSelectFiles: false, canSelectMany: false,
        defaultUri: defaultPath ? vscode.Uri.file(defaultPath) : undefined, openLabel: 'Export here' });
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
    vscode.window.showErrorMessage(e instanceof study.StudyError ? e.message : `Cannot open the study: ${e.message}`);
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
  const panel = vscode.window.createWebviewPanel(VIEW_TYPE, settings.reviewer ? 'Hypotrail study (reviewer)' : 'Hypotrail study',
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
    host: host(context),
    log: e => console.error('[hypotrail companion]', e),
  });
  mine.controller = controller;
  mine.agent = agent;
  mine.watcher = watchStudy(agent.studyDir, () => controller.refresh());
}

async function goToResult(context) {
  if (!allowed()) return null;
  if (!flag.stageAtLeast(flag.stage(vscode), 'v2')) {
    vscode.window.showInformationMessage(NOT_IN_STAGE);
    return null;
  }
  const text = await vscode.window.showInputBox({ title: 'Hypotrail: go to a result',
    prompt: 'The result id, or its first 8 or more characters, as the report shows it.' });
  if (text === undefined || text === null) return null;
  const prefix = uri.resultIdInput(text);
  if (!prefix) {
    vscode.window.showInformationMessage(uri.INVALID_LINK);
    return null;
  }
  const opened = current || await openPanel(context);
  if (!opened) return null;
  if (!opened.controller.hasCommand('go_to_result')) {
    vscode.window.showInformationMessage(NOT_IN_STAGE);
    return null;
  }
  return opened.controller.command('go_to_result', { prefix });
}

async function handleUri(context, link) {
  if (!allowed()) return null;
  const target = uri.parseDeepLink(link);
  if (!target) {
    vscode.window.showInformationMessage(uri.INVALID_LINK);
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
    vscode.window.showErrorMessage(`Hypotrail companion: ${e.message}`);
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
