import type {
  LlmConnectionTestRequest,
  LlmProvider,
  LlmSettings,
  LlmSettingsUpdate,
} from '../types';

export interface LlmSettingsDraft {
  section: LlmProvider;
  apiBaseUrl: string;
  apiKey: string;
  apiKeyConfigured: boolean;
  clearApiKey: boolean;
  ollamaBaseUrl: string;
}

export type LlmField = 'apiBaseUrl' | 'apiKey' | 'ollamaBaseUrl';
export type LlmValidationErrors = Partial<Record<LlmField, string>>;

export function draftFromLlmSettings(settings: LlmSettings): LlmSettingsDraft {
  return {
    section: 'openai_compatible',
    apiBaseUrl: settings.openai_compatible.base_url,
    apiKey: '',
    apiKeyConfigured: settings.openai_compatible.api_key_configured,
    clearApiKey: false,
    ollamaBaseUrl: settings.ollama.base_url,
  };
}

function validHttpUrl(value: string): boolean {
  try {
    const parsed = new URL(value);
    return (parsed.protocol === 'http:' || parsed.protocol === 'https:') && Boolean(parsed.hostname);
  } catch {
    return false;
  }
}

export function validateLlmDraft(draft: LlmSettingsDraft): LlmValidationErrors {
  const errors: LlmValidationErrors = {};
  if (draft.section === 'openai_compatible') {
    if (!draft.apiBaseUrl.trim()) errors.apiBaseUrl = '请输入 API Base URL';
    else if (!validHttpUrl(draft.apiBaseUrl.trim())) errors.apiBaseUrl = '请输入有效的 HTTP(S) 地址';
    const retainsStoredKey = draft.apiKeyConfigured && !draft.clearApiKey;
    if (!draft.apiKey.trim() && !retainsStoredKey) errors.apiKey = '请输入 API Key';
  } else {
    if (!draft.ollamaBaseUrl.trim()) errors.ollamaBaseUrl = '请输入 Ollama 地址';
    else if (!validHttpUrl(draft.ollamaBaseUrl.trim())) errors.ollamaBaseUrl = '请输入有效的 HTTP(S) 地址';
  }
  return errors;
}

export function buildLlmSettingsUpdate(draft: LlmSettingsDraft): LlmSettingsUpdate {
  const apiKey = draft.apiKey.trim();
  return {
    openai_compatible: {
      base_url: draft.apiBaseUrl.trim(),
      ...(apiKey ? { api_key: apiKey } : {}),
      clear_api_key: draft.clearApiKey,
    },
    ollama: { base_url: draft.ollamaBaseUrl.trim() },
  };
}

export function buildLlmConnectionTestRequest(draft: LlmSettingsDraft): LlmConnectionTestRequest {
  return {
    provider: draft.section,
    ...buildLlmSettingsUpdate(draft),
  };
}
