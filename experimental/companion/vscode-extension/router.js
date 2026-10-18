'use strict';
// Single panel-message entry point: filter types, sizes, and actions here.
const fs = require('fs');
const path = require('path');

const PANEL_RPC = new Set(['status', 'project', 'submit', 'apply', 'export', 'confirm_fact']);
const MAX_MESSAGE = 16384;

function renderPage(assetsDir, { cspSource, assetUri, nonce, connectSrc = "'none'" }) {
  let source = fs.readFileSync(path.join(assetsDir, 'companion.html'), 'utf8');
  source = source.replace('href="design.css"', 'href="' + assetUri('design.css') + '"')
    .replace('src="markdown.js"', 'src="' + assetUri('markdown.js') + '"')
    .replace('src="companion.js"', 'src="' + assetUri('companion.js') + '"')
    .replace('src="bridge.js"', 'src="' + assetUri('bridge.js') + '"');
  // No network: only extension resources'are allowed.
  source = source.replace('<head>', '<head><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src ' + cspSource + ' data:; style-src ' + cspSource + ' \'unsafe-inline\'; script-src \'nonce-' + nonce + '\'; connect-src ' + connectSrc + '; base-uri \'none\'; form-action \'none\';">');
  return source.replace(/<script(?=[\s>])/g, '<script nonce="' + nonce + '"');
}

function createRouter({ engine, assistant, post, copy, saveExport, switchProject = async () => {} }) {
  const reply = (id, result) => post({ type: 'rpc-result', id, ...result });
  return async function onMessage(message) {
    if (!message || typeof message !== 'object' || Array.isArray(message)) return;
    let size;
    try { size = JSON.stringify(message).length; } catch (_) { return; }
    const id = typeof message.id === 'string' && message.id.length > 0 && message.id.length < 40 ? message.id : null;
    if (size > MAX_MESSAGE) return id && reply(id, { error: { code: 'size', message: 'Message too volumineux.' } });
    if (message.type === 'rpc' && id) {
      // The page cannot write an explanation as Copilot or execute a command.
      if (!PANEL_RPC.has(message.request?.action)) return reply(id, { error: { code: 'action', message: 'Action not allowed from the panel.' } });
      try { reply(id, { data: await engine(message.request) }); } catch (e) { reply(id, { error: { code: e.code || 'engine', message: e.message } }); }
    } else if (message.type === 'assistant' && id) {
      const op = Object.prototype.hasOwnProperty.call(assistant.ops, message.op) ? assistant.ops[message.op] : null;
      if (!op) return reply(id, { error: { code: 'action', message: 'Action not allowed from the panel.' } });
      try { reply(id, { data: await op(message.payload ?? {}) }); } catch (e) { reply(id, { error: { code: e.code || 'assistant', message: e.message } }); }
    } else if (message.type === 'copy' && typeof message.text === 'string' && message.text.length <= 6000) {
      await copy(message.text);
    } else if (message.type === 'export') {
      // Export state reread by the engine, never an object supplied by the browser.
      await saveExport(await engine({ action: 'export' }));
    } else if (message.type === 'switch-project' && typeof message.id === 'string' && message.id.length < 80) {
      // L'identifier is checked against the registry by the'extension; the panel supplies no path.
      await switchProject(message.id);
    }
  };
}

module.exports = { createRouter, renderPage, PANEL_RPC };
