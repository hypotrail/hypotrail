'use strict';
// Access GitHub Copilot models through the'stable vscode.lm API; no fixed model identifier.
const { AssistantError } = require('./assistant');

const MEMENTO_KEY = 'hypotrail.companion.model';
const JUSTIFICATION = 'Explain Bank Marketing tutorial choices in the Hypotrail panel at your request.';

function describe(model) {
  return { id: model.id, name: model.name, vendor: model.vendor, family: model.family, version: model.version };
}

function mapError(vscode, error) {
  if (error instanceof AssistantError) return error;
  if (error instanceof vscode.LanguageModelError) {
    const code = error.code;
    if (code === vscode.LanguageModelError.NoPermissions().code) return new AssistantError('access_denied', 'Model access denied. Authorize the extension when VS Code asks, then retry.');
    if (code === vscode.LanguageModelError.Blocked().code) return new AssistantError('quota', 'Model usage limit or quota reached. Your choice and results are retained; retry later.');
    if (code === vscode.LanguageModelError.NotFound().code) return new AssistantError('model_unavailable', 'The selected model is unavailable. Choose another model.');
    return new AssistantError('model_error', 'The model rejected the request: ' + String(error.message).slice(0, 300));
  }
  if (error instanceof vscode.CancellationError) return new AssistantError('cancelled', 'Cancelled.');
  const text = String(error?.message || error);
  if (/quota|rate.?limit|429/i.test(text)) return new AssistantError('quota', 'Usage limit reached. Your choice is retained; retry later.');
  return new AssistantError('network', 'The model service did not respond (' + text.slice(0, 200) + '). Your choice is retained; retry.');
}

function createCopilotProvider({ vscode, memento }) {
  const remembered = () => memento.get(MEMENTO_KEY) || null;

  async function choose() {
    const models = await vscode.lm.selectChatModels({ vendor: 'copilot' });
    if (!models.length) throw new AssistantError('no_model', 'No GitHub Copilot model available. Check that Copilot is installed and signed in, then retry.');
    let model = models[0];
    if (models.length > 1) {
      const items = models.map(m => ({ label: m.name, description: [m.family, m.version].filter(Boolean).join(' · '), detail: m.id === remembered()?.id ? 'Model current' : undefined, model: m }));
      const picked = await vscode.window.showQuickPick(items, { title: 'Hypotrail · explanation model', placeHolder: 'GitHub Copilot model for the tutorial panel (can be changed later)', ignoreFocusOut: true });
      if (!picked) throw new AssistantError('model_not_chosen', 'No model selected. Choose a model to receive an explanation.');
      model = picked.model;
    }
    await memento.update(MEMENTO_KEY, describe(model));
    return model;
  }

  async function resolve() {
    const saved = remembered();
    if (!saved) return choose();
    const [model] = await vscode.lm.selectChatModels({ id: saved.id });
    // Never silently switch model or provider.
    if (!model) throw new AssistantError('model_unavailable', `Model « ${saved.name} » is unavailable. Choose another model.`);
    return model;
  }

  function wrap(model) {
    return {
      info: describe(model),
      async *send(messages, signal) {
        const source = new vscode.CancellationTokenSource();
        const onAbort = () => source.cancel();
        signal.addEventListener('abort', onAbort, { once: true });
        try {
          const chat = messages.map(m => m.role === 'assistant' ? vscode.LanguageModelChatMessage.Assistant(m.content) : vscode.LanguageModelChatMessage.User(m.content));
          const response = await model.sendRequest(chat, { justification: JUSTIFICATION }, source.token);
          for await (const fragment of response.text) yield fragment;
        } catch (e) {
          if (signal.aborted) return;
          throw mapError(vscode, e);
        } finally {
          signal.removeEventListener('abort', onAbort);
          source.dispose();
        }
      }
    };
  }

  return {
    current: remembered,
    async ensureModel() {
      try { return wrap(await resolve()); } catch (e) { throw mapError(vscode, e); }
    },
    async chooseModel() {
      try { return describe(await choose()); } catch (e) { throw mapError(vscode, e); }
    }
  };
}

module.exports = { createCopilotProvider, mapError, MEMENTO_KEY };
