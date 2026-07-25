import assert from 'node:assert/strict';
import test from 'node:test';

import type { LlmSettings } from '../src/types.ts';
import {
  buildLlmConnectionTestRequest,
  buildLlmSettingsUpdate,
  draftFromLlmSettings,
  validateLlmDraft,
} from '../src/lib/llm-settings.ts';

const configured: LlmSettings = {
  configured: true,
  openai_compatible: {
    base_url: 'https://provider.example/v1',
    ready: true,
    api_key_configured: true,
  },
  ollama: {
    base_url: 'http://127.0.0.1:11434',
    ready: true,
  },
};

test('creates a credential-only masked draft without fabricating the stored API key', () => {
  const draft = draftFromLlmSettings(configured);

  assert.equal(draft.apiKey, '');
  assert.equal(draft.apiKeyConfigured, true);
  assert.equal('apiModel' in draft, false);
  assert.equal('ollamaModel' in draft, false);
  assert.deepEqual(validateLlmDraft(draft), {});
});

test('omits blank retained keys and sends explicit clear semantics', () => {
  const retained = buildLlmSettingsUpdate(draftFromLlmSettings(configured));
  assert.equal('api_key' in retained.openai_compatible, false);
  assert.equal(retained.openai_compatible.clear_api_key, false);
  assert.equal('active_provider' in retained, false);
  assert.equal('model' in retained.openai_compatible, false);

  const cleared = buildLlmSettingsUpdate({
    ...draftFromLlmSettings(configured),
    section: 'ollama',
    clearApiKey: true,
  });
  assert.equal('api_key' in cleared.openai_compatible, false);
  assert.equal(cleared.openai_compatible.clear_api_key, true);
});

test('keeps both connection drafts while switching editing sections', () => {
  const draft = {
    ...draftFromLlmSettings(configured),
    section: 'ollama' as const,
    apiBaseUrl: 'https://edited.example/v1',
    ollamaBaseUrl: 'http://localhost:11434',
  };
  const payload = buildLlmConnectionTestRequest(draft);

  assert.equal(payload.provider, 'ollama');
  assert.equal(payload.openai_compatible.base_url, 'https://edited.example/v1');
  assert.equal(payload.ollama.base_url, 'http://localhost:11434');
});

test('validates only the displayed connection and requires an effective key', () => {
  const missingKey = draftFromLlmSettings({
    ...configured,
    configured: false,
    openai_compatible: { ...configured.openai_compatible, ready: false, api_key_configured: false },
  });
  assert.equal(validateLlmDraft(missingKey).apiKey, '请输入 API Key');

  const ollama = {
    ...missingKey,
    section: 'ollama' as const,
    ollamaBaseUrl: 'not-a-url',
  };
  const errors = validateLlmDraft(ollama);
  assert.equal(errors.apiKey, undefined);
  assert.match(errors.ollamaBaseUrl ?? '', /HTTP/);
});
