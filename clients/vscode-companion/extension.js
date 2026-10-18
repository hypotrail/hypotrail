'use strict';
// Hypotrail study companion, v0 (ADR 0002, ADR 0003). A VS Code webview that is one
// more client of the `hypotrail` CLI: it reads `status --summary`, and its only writes
// are `decide confirm` with the junior's typed words and `decide withdraw`. It has no
// state, database, server, socket, or language-model integration of its own.
//
// Behind a feature flag, off by default. Activation only registers the command; with
// the flag off the command shows one message and does nothing else.

const vscode = require('vscode');
const fs = require('fs');
const flag = require('./lib/flag');
const study = require('./lib/study');
const { createController } = require('./lib/controller');
const { watchStudy } = require('./lib/watch');
const { renderHtml } = require('./lib/html');

const COMMAND = 'hypotrail.companion.open';
const VIEW_TYPE = 'hypotrail.companion.study';
let current = null;   // {panel, controller, watcher, agent}

async function chooseStudy() {
  const folders = (vscode.workspace.workspaceFolders || []).map(f => f.uri.fsPath);
  const found = study.findStudies(folders);
  if (found.length === 1) return found[0];
  if (found.length > 1) {
    const picked = await vscode.window.showQuickPick(found.map(dir => ({ label: dir, dir })),
      { title: 'Hypotrail: choose a study', placeHolder: 'A folder holding .hypotrail/agent.json' });
    return picked ? picked.dir : null;
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

async function openPanel(context) {
  if (!flag.isEnabled(vscode)) {
    vscode.window.showInformationMessage(flag.DISABLED_MESSAGE);
    return null;
  }
  if (!vscode.workspace.isTrusted) {
    vscode.window.showErrorMessage('The Hypotrail companion runs the study CLI, so it needs a trusted workspace.');
    return null;
  }
  const dir = await chooseStudy();
  if (!dir) return null;
  let agent;
  try {
    agent = study.readAgent(dir);
  } catch (e) {
    vscode.window.showErrorMessage(e instanceof study.StudyError ? e.message : `Cannot open the study: ${e.message}`);
    return null;
  }
  if (current && current.agent.studyDir === agent.studyDir) {
    current.panel.reveal(vscode.ViewColumn.Beside);
    await current.controller.refresh();
    return current;
  }
  close();

  const panel = vscode.window.createWebviewPanel(VIEW_TYPE, 'Hypotrail study', vscode.ViewColumn.Beside, {
    enableScripts: true, enableCommandUris: false, enableForms: false, retainContextWhenHidden: false,
    localResourceRoots: [],
  });
  const controller = createController({
    agent,
    post: message => { panel.webview.postMessage(message); },
    exists: target => fs.existsSync(target),
    openArtifact: async (name, target) => {
      const uri = vscode.Uri.file(target);
      if (name === 'report') await vscode.env.openExternal(uri);
      else await vscode.window.showTextDocument(uri, { preview: false });
    },
    confirmWithdraw: async proposal => {
      const answer = await vscode.window.showWarningMessage(
        `Withdraw proposal ${proposal.proposalId} (${proposal.decisionTitle})? Nothing is confirmed; the assistant can propose again in the chat.`,
        { modal: true }, 'Withdraw');
      return answer === 'Withdraw';
    },
    log: e => console.error('[hypotrail companion]', e),
  });
  const watcher = watchStudy(agent.studyDir, () => controller.refresh());
  const mine = { panel, controller, watcher, agent };
  current = mine;
  context.subscriptions.push(
    panel.webview.onDidReceiveMessage(message => {
      controller.handle(message).catch(e => console.error('[hypotrail companion]', e));
    }),
    panel.onDidChangeViewState(event => {
      if (event.webviewPanel.visible) controller.refresh();
    }),
    panel.onDidDispose(() => {
      watcher.dispose();
      controller.dispose();
      if (current === mine) current = null;
    }),
  );
  panel.webview.html = renderHtml();
  return mine;
}

function activate(context) {
  context.subscriptions.push(vscode.commands.registerCommand(COMMAND, () =>
    openPanel(context).catch(e => {
      vscode.window.showErrorMessage(`Hypotrail companion: ${e.message}`);
      return null;
    })));
  // For tests and diagnostics only: the panel currently open, if any.
  return { current: () => current };
}

function deactivate() {
  close();
}

module.exports = { activate, deactivate, COMMAND, VIEW_TYPE };
