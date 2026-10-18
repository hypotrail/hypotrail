'use strict';
// Simulated host for'interface tests: real page, router, and engine; simulated model.
// Replace VS Code postMessage with POST /post and SSE /events. Tests only.
const http = require('http');
const fs = require('fs');
const os = require('os');
const path = require('path');
const crypto = require('crypto');
const { createEngine } = require('../engine');
const { createAssistant } = require('../assistant');
const { createRouter, renderPage } = require('../router');
const { createFakeProvider } = require('./fake-provider');

const SOURCE = path.resolve(__dirname, '../../runtime');
const PYTHON = [path.join(SOURCE, '.venv/bin/python')].find(fs.existsSync) || 'python3';
const dir = process.argv.includes('--dir') ? process.argv[process.argv.indexOf('--dir') + 1] : fs.mkdtempSync(path.join(os.tmpdir(), 'osml-harness-'));
const provider = createFakeProvider({ delay: 20 });
const clients = new Set();
const seen = { messageTypes: {}, posted: 0 };
let services = null, registry = null;

function emit(message) {
  seen.posted++;
  for (const res of clients) res.write('data: ' + JSON.stringify(message) + '\n\n');
}

async function projects() {
  const engine = createEngine({ python: PYTHON, bridge: path.join(SOURCE, 'bridge.py'), db: path.join(dir, 'registry.sqlite'), cwd: dir, timeoutMs: 60000 });
  return (registry = registry || (await engine.run({ action: 'projects' })).projects);
}

async function build(id) {
  const list = await projects();
  const entry = list.find(p => p.id === id) || list.find(p => p.default);
  const engine = createEngine({ python: PYTHON, bridge: path.join(SOURCE, 'bridge.py'), db: path.join(dir, entry.session_name + '.sqlite'), project: entry.id, cwd: dir, timeoutMs: 60000 });
  const mine = {};
  const post = m => { if (services === mine) emit(m); };
  const assistant = createAssistant({ engine: engine.run, provider, post, projectId: entry.id, projects: async () => list.map(({ id: pid, title, error }) => ({ id: pid, title, error })) });
  const router = createRouter({ engine: engine.run, assistant, post, copy: async () => {}, saveExport: async () => {},
    switchProject: async next => {
      if (next === services.entry.id || !list.some(p => p.id === next && !p.error)) return;
      services.assistant.dispose('project_switch');
      await build(next);
      emit({ type: 'harness-reload' });
    } });
  Object.assign(mine, { entry, engine, assistant, router });
  services = mine;
  return mine;
}

const SHIM = `(()=>{let state=null;try{state=JSON.parse(sessionStorage.getItem('vscode-state'))}catch(_){}
const cid=Math.random().toString(16).slice(2,8);
let open;const ready=new Promise(r=>open=r);const events=new EventSource('/events');events.onopen=()=>open();
events.onmessage=e=>{let data=JSON.parse(e.data);if(data.type==='harness-reload'){location.reload();return;}
if(data.type==='rpc-result'){if(!String(data.id).startsWith(cid+':'))return;data={...data,id:data.id.slice(cid.length+1)};}
window.dispatchEvent(new MessageEvent('message',{data}));};
let used=false;window.acquireVsCodeApi=()=>{if(used)throw Error('acquireVsCodeApi already called');used=true;return {postMessage:m=>ready.then(()=>fetch('/post',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(m.id&&(m.type==='rpc'||m.type==='assistant')?{...m,id:cid+':'+m.id}:m)})),getState:()=>state,setState:s=>{state=s;sessionStorage.setItem('vscode-state',JSON.stringify(s));}};};})();`;

function page() {
  const nonce = crypto.randomBytes(16).toString('hex');
  const html = renderPage(SOURCE, { cspSource: "'self'", nonce, connectSrc: "'self'", assetUri: file => '/assets/' + file });
  return html.replace('<head>', `<head><script nonce="${nonce}">${SHIM}</script>`);
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, 'http://127.0.0.1');
  try {
    if (req.method === 'GET' && url.pathname === '/') { res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' }); return res.end(page()); }
    if (req.method === 'GET' && url.pathname.startsWith('/assets/')) {
      const name = path.basename(url.pathname);
      if (!['companion.js', 'bridge.js', 'markdown.js', 'design.css'].includes(name)) { res.writeHead(404); return res.end(); }
      res.writeHead(200, { 'Content-Type': name.endsWith('.css') ? 'text/css' : 'text/javascript', 'Cache-Control': 'no-store' });
      return res.end(fs.readFileSync(path.join(SOURCE, name)));
    }
    if (url.pathname === '/events') {
      res.writeHead(200, { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-store', Connection: 'keep-alive' });
      res.write(': ok\n\n'); clients.add(res); req.on('close', () => clients.delete(res)); return;
    }
    if (req.method === 'POST' && url.pathname === '/post') {
      let body = ''; for await (const chunk of req) body += chunk;
      const message = JSON.parse(body);
      seen.messageTypes[message.type] = (seen.messageTypes[message.type] || 0) + 1;
      res.writeHead(204); res.end();
      return services.router(message);
    }
    if (url.pathname === '/control') {
      if (req.method === 'POST') { let body = ''; for await (const chunk of req) body += chunk; provider.configure(JSON.parse(body)); }
      res.writeHead(200, { 'Content-Type': 'application/json' });
      return res.end(JSON.stringify({ project: services.entry.id, calls: provider.state.calls.length, selections: provider.state.selections,
        aborted: provider.state.calls.filter(c => c.aborted).length, contexts: provider.state.calls.map(c => c.messages[1].content), seen }));
    }
    res.writeHead(404); res.end();
  } catch (e) { if (!res.headersSent) res.writeHead(500); res.end(String(e.message)); }
});

build(process.argv.includes('--project') ? process.argv[process.argv.indexOf('--project') + 1] : null).then(() => {
  server.listen(0, '127.0.0.1', () => console.log(JSON.stringify({ url: `http://127.0.0.1:${server.address().port}/`, dir })));
});
