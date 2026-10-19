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

/** A Memento like ExtensionContext.globalState; `updates` records every update. */
function memento() {
  const values = new Map();
  const updates = [];
  return {
    updates,
    get: (key, fallback) => (values.has(key) ? JSON.parse(JSON.stringify(values.get(key))) : fallback),
    update: async (key, value) => { updates.push({ key, value: JSON.parse(JSON.stringify(value === undefined ? null : value)) });
      if (value === undefined) values.delete(key); else values.set(key, JSON.parse(JSON.stringify(value))); },
    keys: () => [...values.keys()],
  };
}

function fileUri(p, fragment = '') {
  return { scheme: 'file', fsPath: p, path: p, fragment,
    with: change => fileUri(p, change && typeof change.fragment === 'string' ? change.fragment : fragment),
    toString: () => 'file://' + p + (fragment ? '#' + fragment : '') };
}

function createFake({ folders = [], trusted = true, settings = {}, answers = {}, builtinCommands = {} } = {}) {
  const calls = { info: [], error: [], warning: [], quickPick: [], openDialog: [], panels: [],
    openExternal: [], openExternalUris: [], showTextDocument: [], configuration: [], clipboard: [], inputBox: [],
    executed: [] };
  const commands = new Map();
  const configListeners = emitter();
  const uriHandlers = [];
  const Uri = {
    file: p => fileUri(p),
    parse: text => {
      const m = /^([a-z]+):\/\/([^/?#]*)([^?#]*)(\?[^#]*)?(#.*)?$/.exec(String(text));
      // As vscode.Uri.parse: the components are percent-decoded (`+` stays `+`).
      const decode = x => x.replace(/(%[0-9A-Fa-f]{2})+/g, s => { try { return decodeURIComponent(s); } catch (_) { return s; } });
      return m ? { scheme: m[1], authority: m[2], path: decode(m[3]), query: decode((m[4] || '').slice(1)),
        fragment: decode((m[5] || '').slice(1)), toString: () => String(text) } : null;
    },
  };
  const fake = {
    calls, registered: commands,
    ViewColumn: { One: 1, Two: 2, Beside: -2 },
    Uri,
    commands: {
      registerCommand(id, fn) {
        commands.set(id, fn);
        return { dispose() { commands.delete(id); } };
      },
      executeCommand(id, ...args) {
        calls.executed.push({ id, args });
        if (commands.has(id)) return commands.get(id)(...args);
        if (Object.prototype.hasOwnProperty.call(builtinCommands, id)) return builtinCommands[id](...args);
        return Promise.reject(new Error(`command '${id}' not found`));
      },
    },
    workspace: {
      isTrusted: trusted,
      workspaceFolders: folders.map((p, index) => ({ uri: Uri.file(p), name: path.basename(p), index })),
      getConfiguration(section) {
        calls.configuration.push(section);
        return { get: (key, def) => (Object.prototype.hasOwnProperty.call(settings, `${section}.${key}`) ? settings[`${section}.${key}`] : def) };
      },
      onDidChangeConfiguration: configListeners,
    },
    window: {
      showInformationMessage: async (msg, ...rest) => { calls.info.push(msg); return answers.info; },
      showErrorMessage: async (msg, ...rest) => { calls.error.push(msg); return undefined; },
      showWarningMessage: async (msg, ...rest) => { calls.warning.push({ msg, rest }); return answers.warning; },
      showQuickPick: async (items, options) => { calls.quickPick.push({ items, options }); return answers.quickPick ? answers.quickPick(items) : undefined; },
      showOpenDialog: async options => { calls.openDialog.push(options); return answers.openDialog ? answers.openDialog.map(p => fake.Uri.file(p)) : undefined; },
      showInputBox: async options => { calls.inputBox.push(options); return answers.inputBox; },
      registerUriHandler(handler) {
        uriHandlers.push(handler);
        return { dispose() { const i = uriHandlers.indexOf(handler); if (i >= 0) uriHandlers.splice(i, 1); } };
      },
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
    env: {
      openExternal: async uri => { calls.openExternal.push(uri.fsPath); calls.openExternalUris.push(uri.toString()); return true; },
      clipboard: { writeText: async text => { calls.clipboard.push(text); }, readText: async () => calls.clipboard.at(-1) || '' },
    },
    // Test helpers.
    uriHandlers,
    changeSettings(next) {
      Object.assign(settings, next);
      configListeners.fire({ affectsConfiguration: section => Object.keys(next).some(k => k.startsWith(section)) });
    },
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
  const context = { subscriptions: [], extensionPath: ROOT, globalState: memento() };
  return { extension, context };
}

module.exports = { createFake, load, install, memento };
