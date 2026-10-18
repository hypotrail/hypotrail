'use strict';
const vscode = require('vscode'), fs = require('fs'), path = require('path'), crypto = require('crypto');
const { createEngine } = require('./engine');
const { createAssistant } = require('./assistant');
const { createRouter, renderPage } = require('./router');
const { createCopilotProvider } = require('./lm');

const PROJECT_KEY = 'hypotrail.companion.project';
let panel, services, provider;
const diagnostics = { transport: 'message-passing', requests: 0, errors: [] };

function base(context) {
  const folder = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
  if (!folder) throw Error('Open the repository before starting the companion.');
  const candidates = [path.join(folder, 'experimental/companion/runtime'), path.resolve(folder, '../../experimental/companion/runtime')];
  const local = candidates.find(p => fs.existsSync(path.join(p, 'protocol.py')) && fs.existsSync(path.join(p, 'projects/registry.json')));
  const python = [...(local ? [path.join(local, '.venv/bin/python')] : []), path.join(folder, '.venv/bin/python')].find(p => fs.existsSync(p)) || 'python3';
  // One session per project: never share a database between datasets.
  const db = name => {
    if (local) return path.join(local, '.local', name + '.sqlite');
    const current = path.join(folder, '.hypotrail-tutorial', name + '.sqlite');
    // Compatibility: reuse an existing external-workspace session without resetting it.
    const legacy = path.join(folder, '.openspec-tutorial', name + '.sqlite');
    return !fs.existsSync(current) && fs.existsSync(legacy) ? legacy : current;
  };
  // Use the local engine when source data is available for hash verification; otherwise use the VSIX copy.
  return { folder, python, db, bridge: local ? path.join(local, 'bridge.py') : path.join(context.extensionPath, 'engine', 'bridge.py') };
}

function modelProvider(context) {
  if (provider) return provider;
  // Simulated provider: only in the'development test host, never in the installed VSIX.
  if (context.extensionMode === vscode.ExtensionMode.Development && process.env.OSML_FAKE_LM_MODULE) {
    provider = require(process.env.OSML_FAKE_LM_MODULE).createFakeProvider(JSON.parse(process.env.OSML_FAKE_LM_SCRIPT || '{}'));
  } else provider = createCopilotProvider({ vscode, memento: context.globalState });
  return provider;
}

async function listProjects(context) {
  const b = base(context);
  const engine = createEngine({ python: b.python, bridge: b.bridge, db: b.db('registry'), cwd: b.folder, isTrusted: () => vscode.workspace.isTrusted, diagnostics });
  return (await engine.run({ action: 'projects' })).projects;
}

function build(context, entry, list) {
  const b = base(context);
  const engine = createEngine({ python: b.python, bridge: b.bridge, db: b.db(entry.session_name), project: entry.id, cwd: b.folder, isTrusted: () => vscode.workspace.isTrusted, diagnostics });
  const mine = {};
  // A project already left cannot write to the panel.
  const post = message => { if (services === mine) panel?.webview.postMessage(message); };
  const assistant = createAssistant({ engine: engine.run, provider: modelProvider(context), post, projectId: entry.id,
    projects: async () => list.map(({ id, title, error }) => ({ id, title, error })), log: (where, e) => diagnostics.errors.push(where + ': ' + e.message) });
  const router = createRouter({
    engine: engine.run, assistant, post,
    copy: text => vscode.env.clipboard.writeText(text),
    saveExport: async data => {
      const target = await vscode.window.showSaveDialog({ defaultUri: vscode.Uri.file(path.join(b.folder, 'hypotrail-session-' + entry.session_name + '.json')), filters: { JSON: ['json'] } });
      if (target) await vscode.workspace.fs.writeFile(target, Buffer.from(JSON.stringify(data, null, 2)));
    },
    switchProject: id => switchProject(context, id)
  });
  Object.assign(mine, { entry, engine, assistant, router, post });
  services = mine;
  return mine;
}

async function getServices(context) {
  if (services) return services;
  const list = await listProjects(context);
  const wanted = context.workspaceState.get(PROJECT_KEY);
  const entry = list.find(p => p.id === wanted && !p.error) || list.find(p => p.default && !p.error) || list.find(p => !p.error);
  if (!entry) throw Error('No valid registry project: ' + list.map(p => p.error).join(' ; '));
  return build(context, entry, list);
}

async function switchProject(context, id) {
  const list = await listProjects(context);
  const entry = list.find(p => p.id === id);
  if (!entry || entry.error) { vscode.window.showWarningMessage('Project unavailable: ' + (entry?.error || id)); if (panel) setHtml(context, panel); return; }
  if (services?.entry.id === id) return;
  // Generations from the'previous project are cancelled; answers stay in that project session.
  services?.assistant.dispose('project_switch');
  await context.workspaceState.update(PROJECT_KEY, id);
  build(context, entry, list);
  if (panel) setHtml(context, panel);
}

function setHtml(context, target) {
  const nonce = crypto.randomBytes(24).toString('hex'), assets = path.join(context.extensionPath, 'assets');
  target.webview.html = renderPage(assets, { cspSource: target.webview.cspSource, nonce,
    assetUri: file => target.webview.asWebviewUri(vscode.Uri.file(path.join(assets, file))).toString() });
}

async function open(context) {
  if (panel) { panel.reveal(vscode.ViewColumn.Beside); return panel; }
  await getServices(context);
  panel = vscode.window.createWebviewPanel('hypotrailTutorial', 'Hypotrail · Companion', vscode.ViewColumn.Beside,
    { enableScripts: true, retainContextWhenHidden: true, localResourceRoots: [vscode.Uri.file(path.join(context.extensionPath, 'assets'))] });
  const local = panel;
  local.webview.onDidReceiveMessage(message => getServices(context).then(s => s.router(message)).catch(e => diagnostics.errors.push(e.message)), undefined, context.subscriptions);
  // Closing the panel does not stop an ongoing response; it is persisted and restored on reopening.
  local.onDidDispose(() => { if (panel === local) panel = undefined; });
  setHtml(context, local);
  return local;
}

function forTool(snapshot) {
  // Chat receives a summary; the full conversation remains in the panel and'export.
  const conversation = (snapshot.conversation || []).slice(-5).map(x => ({ exchange_id: x.exchange_id, kind: x.kind, status: x.status, subject: x.subject, activity: x.activity,
    choice: x.choice?.label, application_event_id: x.application_event_id, current: x.current, answer: String(x.answer || '').slice(0, 600) }));
  return { ...snapshot, conversation };
}

function activate(context) {
  const report = e => vscode.window.showErrorMessage(e.message);
  context.subscriptions.push(vscode.commands.registerCommand('hypotrail.openTutorial', () => open(context).catch(report)));
  context.subscriptions.push(vscode.commands.registerCommand('hypotrail.chooseModel', async () => {
    try { const { model } = await (await getServices(context)).assistant.ops['choose-model']({}); vscode.window.showInformationMessage('Explanation model: ' + model.name); }
    catch (e) { vscode.window.showWarningMessage(e.message); }
  }));
  context.subscriptions.push(vscode.commands.registerCommand('hypotrail.switchProject', async () => {
    try {
      const list = await listProjects(context);
      const picked = await vscode.window.showQuickPick(list.map(p => ({ label: p.title, description: p.error ? 'configuration invalid' : p.problem_type, detail: p.error, id: p.id })), { title: 'Hypotrail · companion project' });
      if (picked) await switchProject(context, picked.id);
    } catch (e) { report(e); }
  }));
  context.subscriptions.push(vscode.window.registerUriHandler({ handleUri: uri => { if (uri.path === '/open') return open(context); } }));
  const item = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 20);
  item.text = '$(book) Hypotrail'; item.tooltip = 'Open the Hypotrail companion'; item.command = 'hypotrail.openTutorial'; item.show(); context.subscriptions.push(item);
  if (vscode.lm?.registerTool) {
    const run = async request => (await getServices(context)).engine.run(request);
    const refresh = () => services?.post({ type: 'assistant-event', event: 'refresh', project_id: services.entry.id });
    const register = (name, invoke) => context.subscriptions.push(vscode.lm.registerTool(name, {
      invoke: async options => new vscode.LanguageModelToolResult([new vscode.LanguageModelTextPart(JSON.stringify(await invoke(options.input || {}), null, 2))])
    }));
    register('hypotrail_tutorial_status', async () => forTool(await run({ action: 'status' })));
    register('hypotrail_tutorial_apply', async p => { const r = forTool(await run({ action: 'apply', event_id: p.eventId, expected_revision: p.expectedRevision, context_hash: p.contextHash })); refresh(); return r; });
    register('hypotrail_tutorial_explain', async p => {
      const request = { action: 'explain', message: p.message, source: 'chat_tool' };
      if (p.applicationEventId !== undefined || p.contextHash !== undefined) Object.assign(request, { application_event_id: p.applicationEventId, context_hash: p.contextHash });
      const r = forTool(await run(request)); refresh(); return r;
    });
  }
  context.subscriptions.push({ dispose: () => services?.assistant.dispose() });
  // Only for the'automated test in the'isolated development host.
  if (context.extensionMode === vscode.ExtensionMode.Development && process.env.OSML_WEBVIEW_TEST === '1') open(context).catch(e => diagnostics.errors.push(e.message));
  return {
    open: () => open(context), request: async request => (await getServices(context)).engine.run(request), diagnostics: () => diagnostics,
    project: () => services?.entry.id, switchProject: id => switchProject(context, id)
  };
}
function deactivate() { services?.assistant.dispose(); }
module.exports = { activate, deactivate };
