import { useMemo, useState } from 'react';
import { Plus, Save, Trash2, X } from 'lucide-react';
import { ApiError, createMcpServer, updateMcpServer } from '../lib/api';
import type { McpServer, McpServerCreate, McpServerUpdate } from '../types';

const NAME_PATTERN = /^[a-z0-9][a-z0-9_-]{0,63}$/;
const HEADER_PATTERN = /^[!#$%&'*+.^_`|~0-9A-Za-z-]{1,128}$/;

interface HeaderRow {
  id: number;
  name: string;
  value: string;
}

interface McpServerFormProps {
  server: McpServer | null;
  onClose: () => void;
  onSaved: () => Promise<void> | void;
}

let nextHeaderRowId = 1;

function apiErrorMessage(error: unknown): string {
  return error instanceof ApiError ? error.detail : error instanceof Error ? error.message : '保存失败';
}

function isHttpUrl(value: string): boolean {
  try {
    const url = new URL(value);
    return (url.protocol === 'http:' || url.protocol === 'https:') && Boolean(url.host);
  } catch {
    return false;
  }
}

export function McpServerForm({ server, onClose, onSaved }: McpServerFormProps) {
  const editing = server !== null;
  const [name, setName] = useState(server?.name ?? '');
  const [displayName, setDisplayName] = useState(server?.display_name ?? '');
  const [description, setDescription] = useState(server?.description ?? '');
  const [url, setUrl] = useState(server?.url ?? '');
  const [headers, setHeaders] = useState<HeaderRow[]>(() =>
    Object.entries(server?.headers ?? {}).map(([headerName, value]) => ({
      id: nextHeaderRowId++,
      name: headerName,
      value,
    }))
  );
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const titleId = useMemo(() => `mcp-form-title-${editing ? server.name : 'new'}`, [editing, server]);

  const updateHeader = (id: number, field: 'name' | 'value', value: string) => {
    setHeaders((rows) => rows.map((row) => {
      if (row.id !== id) return row;
      if (field === 'name' && row.name !== value && row.value === '********') {
        return { ...row, name: value, value: '' };
      }
      return { ...row, [field]: value };
    }));
  };

  const validate = (): Record<string, string> => {
    const next: Record<string, string> = {};
    if (!editing && !NAME_PATTERN.test(name.trim())) {
      next.name = '使用小写字母、数字、下划线或连字符，最长 64 位';
    }
    if (!displayName.trim()) next.display_name = '请输入显示标题';
    else if (displayName.trim().length > 100) next.display_name = '显示标题不能超过 100 个字符';
    if (!isHttpUrl(url.trim())) next.url = '请输入完整的 HTTP(S) SSE 地址';
    if (description.trim().length > 1000) next.description = '描述不能超过 1000 个字符';

    const seen = new Set<string>();
    headers.forEach((header) => {
      const headerName = header.name.trim();
      if (!HEADER_PATTERN.test(headerName)) {
        next[`header-name-${header.id}`] = 'Header 名称无效';
      } else if (seen.has(headerName.toLocaleLowerCase())) {
        next[`header-name-${header.id}`] = 'Header 名称不能重复';
      }
      seen.add(headerName.toLocaleLowerCase());
      if (!header.value || header.value.length > 4096 || /[\r\n]/.test(header.value)) {
        next[`header-value-${header.id}`] = '值不能为空、包含换行或超过 4096 个字符';
      }
    });
    return next;
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    const nextErrors = validate();
    setErrors(nextErrors);
    setSubmitError(null);
    if (Object.keys(nextErrors).length > 0) return;

    const payload: McpServerUpdate = {
      type: 'sse',
      display_name: displayName.trim(),
      description: description.trim(),
      url: url.trim(),
      headers: Object.fromEntries(headers.map((header) => [header.name.trim(), header.value])),
    };
    setSaving(true);
    try {
      if (server) await updateMcpServer(server.name, payload);
      else await createMcpServer({ ...payload, name: name.trim() } satisfies McpServerCreate);
      await onSaved();
      onClose();
    } catch (error) {
      setSubmitError(apiErrorMessage(error));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" role="presentation">
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="w-full max-w-2xl max-h-[calc(100vh-2rem)] overflow-y-auto rounded-lg border border-zinc-700 bg-[#111111] shadow-2xl"
      >
        <header className="sticky top-0 z-10 flex items-center border-b border-zinc-800 bg-[#111111] px-5 py-4">
          <div>
            <h2 id={titleId} className="text-base font-semibold text-zinc-100">
              {editing ? '编辑 MCP' : '新建 MCP'}
            </h2>
            <p className="mt-0.5 text-xs text-zinc-500">连接方式固定为 SSE</p>
          </div>
          <button type="button" onClick={onClose} className="ml-auto p-2 rounded-md text-zinc-500 hover:bg-zinc-800 hover:text-zinc-200" aria-label="关闭表单">
            <X className="h-4 w-4" />
          </button>
        </header>

        <form onSubmit={handleSubmit} className="space-y-5 p-5" noValidate>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="block min-w-0 text-xs font-medium text-zinc-400">
              内部名称
              <input
                value={name}
                onChange={(event) => setName(event.target.value)}
                disabled={editing || saving}
                autoComplete="off"
                aria-invalid={Boolean(errors.name)}
                className="mt-1.5 w-full rounded-md border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-zinc-500 disabled:opacity-60"
                placeholder="weather-mcp"
              />
              {errors.name && <span className="mt-1 block text-xs text-red-400">{errors.name}</span>}
            </label>
            <label className="block min-w-0 text-xs font-medium text-zinc-400">
              显示标题
              <input
                value={displayName}
                onChange={(event) => setDisplayName(event.target.value)}
                disabled={saving}
                aria-invalid={Boolean(errors.display_name)}
                className="mt-1.5 w-full rounded-md border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-zinc-500"
                placeholder="天气服务"
              />
              {errors.display_name && <span className="mt-1 block text-xs text-red-400">{errors.display_name}</span>}
            </label>
          </div>

          <label className="block text-xs font-medium text-zinc-400">
            SSE 地址
            <input
              value={url}
              onChange={(event) => setUrl(event.target.value)}
              disabled={saving}
              aria-invalid={Boolean(errors.url)}
              className="mt-1.5 w-full rounded-md border border-zinc-700 bg-zinc-950 px-3 py-2 font-mono text-sm text-zinc-100 outline-none focus:border-zinc-500"
              placeholder="https://example.com/sse"
              inputMode="url"
            />
            {errors.url && <span className="mt-1 block text-xs text-red-400">{errors.url}</span>}
          </label>

          <label className="block text-xs font-medium text-zinc-400">
            描述
            <textarea
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              disabled={saving}
              aria-invalid={Boolean(errors.description)}
              className="mt-1.5 min-h-20 w-full resize-y rounded-md border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-zinc-500"
              placeholder="这个 MCP 提供的能力"
            />
            {errors.description && <span className="mt-1 block text-xs text-red-400">{errors.description}</span>}
          </label>

          <fieldset className="space-y-2">
            <div className="flex items-center justify-between gap-3">
              <legend className="text-xs font-medium text-zinc-400">Headers</legend>
              <button
                type="button"
                onClick={() => setHeaders((rows) => [...rows, { id: nextHeaderRowId++, name: '', value: '' }])}
                disabled={saving || headers.length >= 32}
                className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200 disabled:opacity-40"
              >
                <Plus className="h-3.5 w-3.5" />
                添加 Header
              </button>
            </div>
            {headers.length === 0 && <p className="border-t border-zinc-800 py-3 text-xs text-zinc-600">未配置请求 Header</p>}
            {headers.map((header) => (
              <div key={header.id} className="grid grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)_32px] gap-2">
                <div className="min-w-0">
                  <input
                    value={header.name}
                    onChange={(event) => updateHeader(header.id, 'name', event.target.value)}
                    disabled={saving}
                    aria-label="Header 名称"
                    aria-invalid={Boolean(errors[`header-name-${header.id}`])}
                    className="w-full rounded-md border border-zinc-700 bg-zinc-950 px-3 py-2 font-mono text-xs text-zinc-100 outline-none focus:border-zinc-500"
                    placeholder="Authorization"
                  />
                  {errors[`header-name-${header.id}`] && <span className="mt-1 block text-[11px] text-red-400">{errors[`header-name-${header.id}`]}</span>}
                </div>
                <div className="min-w-0">
                  <input
                    value={header.value}
                    onChange={(event) => updateHeader(header.id, 'value', event.target.value)}
                    disabled={saving}
                    aria-label="Header 值"
                    aria-invalid={Boolean(errors[`header-value-${header.id}`])}
                    autoComplete="new-password"
                    className="w-full rounded-md border border-zinc-700 bg-zinc-950 px-3 py-2 font-mono text-xs text-zinc-100 outline-none focus:border-zinc-500"
                    placeholder="Bearer ..."
                  />
                  {errors[`header-value-${header.id}`] && <span className="mt-1 block text-[11px] text-red-400">{errors[`header-value-${header.id}`]}</span>}
                </div>
                <button
                  type="button"
                  onClick={() => setHeaders((rows) => rows.filter((row) => row.id !== header.id))}
                  disabled={saving}
                  className="flex h-8 w-8 items-center justify-center rounded-md text-zinc-500 hover:bg-zinc-800 hover:text-red-400"
                  aria-label={`删除 Header ${header.name || '空行'}`}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            ))}
          </fieldset>

          {submitError && <div role="alert" className="rounded-md border border-red-900/80 bg-red-950/40 px-3 py-2 text-xs text-red-300">{submitError}</div>}

          <footer className="flex justify-end gap-2 border-t border-zinc-800 pt-4">
            <button type="button" onClick={onClose} disabled={saving} className="rounded-md px-3 py-2 text-sm text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100">取消</button>
            <button type="submit" disabled={saving} className="inline-flex min-w-20 items-center justify-center gap-2 rounded-md bg-zinc-100 px-3 py-2 text-sm font-medium text-zinc-950 hover:bg-white disabled:opacity-50">
              <Save className="h-4 w-4" />
              {saving ? '保存中' : '保存'}
            </button>
          </footer>
        </form>
      </section>
    </div>
  );
}

