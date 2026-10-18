'use strict';
// A fake `vscode` module for node:test (no VS Code is available offline). It records
// what the extension asks of the editor. `load()` installs it with a require hook and
// returns a fresh copy of the extension.

const Module = require('module');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');

function emitter() {
  const listeners = [];
  const event = cb => {
    listeners.push(cb);
    return { dispose() { const i = listeners.indexOf(cb); if (i >= 0) listeners.splice(i, 1); } };
  };
  event.fire = value => listeners.slice().forEach(cb => cb(value));
  return event;
}

function createFake({ folders = [], trusted = true, settings = {}, answers = {} } = {}) {
  const calls = { info: [], error: [], warning: [], quickPick: [], openDialog: [], panels: [],
    openExternal: [], showTextDocument: [], configuration: [] };
  const commands = new Map();
  const Uri = { file: p => ({ scheme: 'file', fsPath: p, toString: () => 'file://' + p }) };
  const fake = {
    calls, registered: commands,
    ViewColumn: { One: 1, Two: 2, Beside: -2 },
    Uri,
    commands: {
      registerCommand(id, fn) {
        commands.set(id, fn);
        return { dispose() { commands.delete(id); } };
      },
      executeCommand(id, ...args) { return commands.get(id)(...args); },
    },
    workspace: {
      isTrusted: trusted,
      workspaceFolders: folders.map((p, index) => ({ uri: Uri.file(p), name: path.basename(p), index })),
      getConfiguration(section) {
        calls.configuration.push(section);
        return { get: (key, def) => (Object.prototype.hasOwnProperty.call(settings, `${section}.${key}`) ? settings[`${section}.${key}`] : def) };
      },
    },
    window: {
      showInformationMessage: async (msg, ...rest) => { calls.info.push(msg); return answers.info; },
      showErrorMessage: async (msg, ...rest) => { calls.error.push(msg); return undefined; },
      showWarningMessage: async (msg, ...rest) => { calls.warning.push({ msg, rest }); return answers.warning; },
      showQuickPick: async (items, options) => { calls.quickPick.push({ items, options }); return answers.quickPick ? answers.quickPick(items) : undefined; },
      showOpenDialog: async options => { calls.openDialog.push(options); return answers.openDialog ? answers.openDialog.map(p => fake.Uri.file(p)) : undefined; },
      showTextDocument: async (uri, options) => { calls.showTextDocument.push(uri.fsPath); },
      createWebviewPanel(viewType, title, column, options) {
        const receive = emitter(), dispose = emitter(), view = emitter();
        const panel = {
          viewType, title, column, options, visible: true, disposed: false, revealed: 0,
          posted: [],
          webview: {
            html: '',
            cspSource: 'vscode-webview-test:',
            postMessage: async message => { panel.posted.push(JSON.parse(JSON.stringify(message))); return true; },
            onDidReceiveMessage: receive,
          },
          onDidDispose: dispose,
          onDidChangeViewState: view,
          reveal() { panel.revealed += 1; },
          dispose() { if (!panel.disposed) { panel.disposed = true; dispose.fire(); } },
          // Test helpers.
          receive: message => receive.fire(message),
          setVisible(v) { panel.visible = v; view.fire({ webviewPanel: panel }); },
        };
        calls.panels.push(panel);
        return panel;
      },
    },
    env: { openExternal: async uri => { calls.openExternal.push(uri.fsPath); return true; } },
  };
  return fake;
}

let installed = null;
const originalLoad = Module._load;

function install(fake) {
  installed = fake;
  if (Module._load.__hypotrailFake) return;
  const hooked = function (request, parent, isMain) {
    if (request === 'vscode') {
      if (!installed) throw new Error('fake vscode is not installed');
      return installed;
    }
    return originalLoad.apply(this, arguments);
  };
  hooked.__hypotrailFake = true;
  Module._load = hooked;
}

/** A fresh extension module bound to `fake`, and a fake extension context. */
function load(fake) {
  install(fake);
  for (const key of Object.keys(require.cache)) {
    if (key.startsWith(ROOT + path.sep) && !key.includes(`${path.sep}test${path.sep}`)) delete require.cache[key];
  }
  const extension = require(path.join(ROOT, 'extension.js'));
  const context = { subscriptions: [], extensionPath: ROOT };
  return { extension, context };
}

module.exports = { createFake, load, install };
