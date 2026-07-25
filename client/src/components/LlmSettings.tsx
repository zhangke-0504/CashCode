import { useCallback, useEffect, useState } from 'react';
import {
  AlertCircle,
  CheckCircle2,
  Eye,
  EyeOff,
  KeyRound,
  LoaderCircle,
  RefreshCw,
  Save,
  Server,
  TestTube2,
  Trash2,
  Undo2,
} from 'lucide-react';
import { ApiError, fetchLlmSettings, saveLlmSettings, testLlmConnection } from '../lib/api';
import {
  buildLlmConnectionTestRequest,
  buildLlmSettingsUpdate,
  draftFromLlmSettings,
  validateLlmDraft,
  type LlmField,
  type LlmSettingsDraft,
  type LlmValidationErrors,
} from '../lib/llm-settings';
import type { LlmProvider, LlmSettings as LlmSettingsState } from '../types';

const EMPTY_SETTINGS: LlmSettingsState = {
  configured: false,
  openai_compatible: { base_url: '', ready: false, api_key_configured: false },
  ollama: { base_url: '', ready: false },
};

type Feedback = { tone: 'success' | 'error'; message: string } | null;

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.detail : error instanceof Error ? error.message : '请求失败';
}

const inputClass = (invalid: boolean) =>
  `h-10 w-full rounded-md border bg-zinc-950 px-3 text-sm text-zinc-100 outline-none transition-colors placeholder:text-zinc-700 focus:border-zinc-500 ${
    invalid ? 'border-red-800' : 'border-zinc-800'
  }`;

export function LlmSettings() {
  const [settings, setSettings] = useState<LlmSettingsState | null>(null);
  const [draft, setDraft] = useState<LlmSettingsDraft>(() => draftFromLlmSettings(EMPTY_SETTINGS));
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [errors, setErrors] = useState<LlmValidationErrors>({});
  const [showKey, setShowKey] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [feedback, setFeedback] = useState<Feedback>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const value = await fetchLlmSettings();
      setSettings(value);
      setDraft(draftFromLlmSettings(value));
    } catch (error) {
      setLoadError(errorMessage(error));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const updateDraft = <K extends keyof LlmSettingsDraft>(key: K, value: LlmSettingsDraft[K]) => {
    setDraft((current) => ({ ...current, [key]: value }));
    const field = key as LlmField;
    if (field in errors) setErrors((current) => ({ ...current, [field]: undefined }));
    setFeedback(null);
  };

  const selectSection = (section: LlmProvider) => {
    updateDraft('section', section);
    setErrors({});
  };

  const validate = (): boolean => {
    const nextErrors = validateLlmDraft(draft);
    setErrors(nextErrors);
    return Object.keys(nextErrors).length === 0;
  };

  const handleTest = async () => {
    if (!validate()) return;
    setTesting(true);
    setFeedback(null);
    try {
      const result = await testLlmConnection(buildLlmConnectionTestRequest(draft));
      setFeedback({ tone: 'success', message: result.message });
    } catch (error) {
      setFeedback({ tone: 'error', message: errorMessage(error) });
    } finally {
      setTesting(false);
    }
  };

  const handleSave = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!validate()) return;
    setSaving(true);
    setFeedback(null);
    try {
      const activeSection = draft.section;
      const value = await saveLlmSettings(buildLlmSettingsUpdate(draft));
      setSettings(value);
      setDraft({ ...draftFromLlmSettings(value), section: activeSection });
      setShowKey(false);
      setFeedback({ tone: 'success', message: '连接设置已保存' });
    } catch (error) {
      setFeedback({ tone: 'error', message: errorMessage(error) });
    } finally {
      setSaving(false);
    }
  };

  const toggleClearKey = () => {
    if (!draft.clearApiKey && !window.confirm('清除已保存的 API Key？')) return;
    updateDraft('apiKey', '');
    updateDraft('clearApiKey', !draft.clearApiKey);
  };

  if (loading && !settings) {
    return (
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-4xl px-4 py-6 sm:px-6 sm:py-8">
          <div className="h-7 w-36 animate-pulse rounded bg-zinc-800" />
          <div className="mt-8 h-10 w-full max-w-sm animate-pulse rounded bg-zinc-900" />
          <div className="mt-8 h-56 animate-pulse border-y border-zinc-800 bg-zinc-950/30" />
        </div>
      </div>
    );
  }

  if (loadError && !settings) {
    return (
      <div className="flex flex-1 items-center justify-center p-5">
        <div role="alert" className="flex max-w-lg items-start gap-3 rounded-md border border-red-900/80 bg-red-950/30 p-4 text-sm text-red-300">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          <span className="min-w-0 flex-1 break-words">{loadError}</span>
          <button type="button" onClick={() => void load()} className="inline-flex h-8 items-center gap-1.5 rounded-md px-2 text-xs hover:bg-red-900/40">
            <RefreshCw className="h-3.5 w-3.5" />重试
          </button>
        </div>
      </div>
    );
  }

  const busy = saving || testing;
  const sectionReady = draft.section === 'openai_compatible'
    ? settings?.openai_compatible.ready
    : settings?.ollama.ready;

  return (
    <div className="flex-1 overflow-y-auto">
      <form onSubmit={handleSave} className="mx-auto w-full max-w-4xl px-4 py-6 sm:px-6 sm:py-8">
        <header className="flex flex-wrap items-center gap-3 border-b border-zinc-800 pb-5">
          <div>
            <h1 className="text-lg font-semibold text-zinc-100">LLM 设置</h1>
            <div className={`mt-1 inline-flex items-center gap-1.5 text-xs ${settings?.configured ? 'text-emerald-400' : 'text-amber-400'}`}>
              <span className="h-1.5 w-1.5 rounded-full bg-current" />
              {settings?.configured ? '已有可用连接' : '尚未配置连接'}
            </div>
          </div>
          <div className="ml-auto grid h-9 grid-cols-2 rounded-md border border-zinc-800 bg-zinc-950 p-0.5" role="tablist" aria-label="LLM 连接类型">
            <button type="button" role="tab" aria-selected={draft.section === 'openai_compatible'} onClick={() => selectSection('openai_compatible')} className={`min-w-24 rounded px-3 text-sm transition-colors ${draft.section === 'openai_compatible' ? 'bg-zinc-700 text-zinc-100' : 'text-zinc-500 hover:text-zinc-300'}`}>
              通用 API
            </button>
            <button type="button" role="tab" aria-selected={draft.section === 'ollama'} onClick={() => selectSection('ollama')} className={`min-w-24 rounded px-3 text-sm transition-colors ${draft.section === 'ollama' ? 'bg-zinc-700 text-zinc-100' : 'text-zinc-500 hover:text-zinc-300'}`}>
              Ollama
            </button>
          </div>
        </header>

        {draft.section === 'openai_compatible' ? (
          <section aria-labelledby="api-settings-title" className="border-b border-zinc-800 py-6">
            <div className="mb-5 flex items-center gap-2">
              <KeyRound className="h-4 w-4 text-zinc-500" />
              <h2 id="api-settings-title" className="text-sm font-semibold text-zinc-200">通用 API</h2>
              <span className={`ml-auto text-xs ${sectionReady ? 'text-emerald-400' : 'text-zinc-600'}`}>{sectionReady ? '已配置' : '未配置'}</span>
            </div>
            <div className="grid gap-5 sm:grid-cols-2">
              <label className="block sm:col-span-2">
                <span className="mb-2 block text-xs font-medium text-zinc-400">API Base URL</span>
                <input value={draft.apiBaseUrl} onChange={(event) => updateDraft('apiBaseUrl', event.target.value)} className={inputClass(Boolean(errors.apiBaseUrl))} placeholder="https://api.example.com/v1" spellCheck={false} />
                {errors.apiBaseUrl && <span className="mt-1.5 block text-xs text-red-400">{errors.apiBaseUrl}</span>}
              </label>
              <label className="block sm:col-span-2">
                <span className="mb-2 flex items-center gap-2 text-xs font-medium text-zinc-400">
                  API Key
                  {draft.apiKeyConfigured && !draft.clearApiKey && <span className="text-emerald-500">已保存</span>}
                  {draft.clearApiKey && <span className="text-amber-400">将清除</span>}
                </span>
                <span className="relative block">
                  <input type={showKey ? 'text' : 'password'} autoComplete="new-password" value={draft.apiKey} onChange={(event) => updateDraft('apiKey', event.target.value)} className={`${inputClass(Boolean(errors.apiKey))} pr-20`} placeholder={draft.apiKeyConfigured && !draft.clearApiKey ? '留空保持当前密钥' : '输入 API Key'} spellCheck={false} />
                  <span className="absolute inset-y-0 right-1 flex items-center gap-0.5">
                    <button type="button" onClick={() => setShowKey((value) => !value)} className="flex h-8 w-8 items-center justify-center rounded text-zinc-500 hover:bg-zinc-800 hover:text-zinc-200" title={showKey ? '隐藏密钥' : '显示密钥'} aria-label={showKey ? '隐藏密钥' : '显示密钥'}>
                      {showKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                    </button>
                    {draft.apiKeyConfigured && (
                      <button type="button" onClick={toggleClearKey} className={`flex h-8 w-8 items-center justify-center rounded hover:bg-zinc-800 ${draft.clearApiKey ? 'text-amber-400' : 'text-zinc-500 hover:text-red-400'}`} title={draft.clearApiKey ? '撤销清除' : '清除密钥'} aria-label={draft.clearApiKey ? '撤销清除密钥' : '清除密钥'}>
                        {draft.clearApiKey ? <Undo2 className="h-4 w-4" /> : <Trash2 className="h-4 w-4" />}
                      </button>
                    )}
                  </span>
                </span>
                {errors.apiKey && <span className="mt-1.5 block text-xs text-red-400">{errors.apiKey}</span>}
              </label>
            </div>
          </section>
        ) : (
          <section aria-labelledby="ollama-settings-title" className="border-b border-zinc-800 py-6">
            <div className="mb-5 flex items-center gap-2">
              <Server className="h-4 w-4 text-zinc-500" />
              <h2 id="ollama-settings-title" className="text-sm font-semibold text-zinc-200">Ollama</h2>
              <span className={`ml-auto text-xs ${sectionReady ? 'text-emerald-400' : 'text-zinc-600'}`}>{sectionReady ? '已配置' : '未配置'}</span>
            </div>
            <label className="block">
              <span className="mb-2 block text-xs font-medium text-zinc-400">服务地址</span>
              <input value={draft.ollamaBaseUrl} onChange={(event) => updateDraft('ollamaBaseUrl', event.target.value)} className={inputClass(Boolean(errors.ollamaBaseUrl))} placeholder="http://127.0.0.1:11434" spellCheck={false} />
              {errors.ollamaBaseUrl && <span className="mt-1.5 block text-xs text-red-400">{errors.ollamaBaseUrl}</span>}
            </label>
          </section>
        )}

        <div className="flex min-h-16 flex-wrap items-center gap-3 pt-5">
          {feedback && (
            <div role={feedback.tone === 'error' ? 'alert' : 'status'} className={`flex min-w-0 flex-1 items-center gap-2 text-sm ${feedback.tone === 'success' ? 'text-emerald-400' : 'text-red-400'}`}>
              {feedback.tone === 'success' ? <CheckCircle2 className="h-4 w-4 shrink-0" /> : <AlertCircle className="h-4 w-4 shrink-0" />}
              <span className="break-words">{feedback.message}</span>
            </div>
          )}
          <div className={`${feedback ? '' : 'ml-auto'} flex items-center gap-2 sm:ml-auto`}>
            <button type="button" onClick={() => void handleTest()} disabled={busy} className="inline-flex h-10 min-w-28 items-center justify-center gap-2 rounded-md border border-zinc-700 px-3 text-sm text-zinc-300 hover:bg-zinc-800 disabled:opacity-50">
              {testing ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <TestTube2 className="h-4 w-4" />}
              测试连接
            </button>
            <button type="submit" disabled={busy} className="inline-flex h-10 min-w-28 items-center justify-center gap-2 rounded-md bg-zinc-100 px-3 text-sm font-medium text-zinc-950 hover:bg-white disabled:opacity-50">
              {saving ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
              保存设置
            </button>
          </div>
        </div>
      </form>
    </div>
  );
}
