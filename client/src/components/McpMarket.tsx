import { useCallback, useEffect, useState } from 'react';
import {
  AlertCircle,
  CheckCircle2,
  LoaderCircle,
  MoreHorizontal,
  Network,
  Pencil,
  Plus,
  RefreshCw,
  Trash2,
  Unplug,
  X,
} from 'lucide-react';
import {
  ApiError,
  connectMcpServer,
  deleteMcpServer,
  disconnectMcpServer,
  fetchMcpServers,
} from '../lib/api';
import type { McpLifecycleStatus, McpServer } from '../types';
import { McpServerForm } from './McpServerForm';

const STATUS_LABELS: Record<McpLifecycleStatus, string> = {
  disconnected: '未连接',
  connecting: '连接中',
  connected: '已连接',
  error: '连接失败',
};

const STATUS_CLASSES: Record<McpLifecycleStatus, string> = {
  disconnected: 'text-zinc-500',
  connecting: 'text-amber-400',
  connected: 'text-emerald-400',
  error: 'text-red-400',
};

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.detail : error instanceof Error ? error.message : '请求失败';
}

export function McpMarket() {
  const [servers, setServers] = useState<McpServer[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [working, setWorking] = useState<string | null>(null);
  const [rowErrors, setRowErrors] = useState<Record<string, string>>({});
  const [formServer, setFormServer] = useState<McpServer | null | undefined>(undefined);
  const [menuServer, setMenuServer] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<McpServer | null>(null);

  const loadServers = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      setServers(await fetchMcpServers());
    } catch (error) {
      setLoadError(errorMessage(error));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadServers();
  }, [loadServers]);

  useEffect(() => {
    const closeMenu = () => setMenuServer(null);
    document.addEventListener('click', closeMenu);
    return () => document.removeEventListener('click', closeMenu);
  }, []);

  const runLifecycle = async (server: McpServer) => {
    const action = server.connected ? 'disconnect' : 'connect';
    setWorking(`${action}:${server.name}`);
    setRowErrors((current) => ({ ...current, [server.name]: '' }));
    try {
      if (server.connected) await disconnectMcpServer(server.name);
      else await connectMcpServer(server.name);
    } catch (error) {
      setRowErrors((current) => ({ ...current, [server.name]: errorMessage(error) }));
    } finally {
      await loadServers();
      setWorking(null);
    }
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    const server = deleteTarget;
    setWorking(`delete:${server.name}`);
    setRowErrors((current) => ({ ...current, [server.name]: '' }));
    try {
      await deleteMcpServer(server.name);
      setDeleteTarget(null);
      await loadServers();
    } catch (error) {
      setRowErrors((current) => ({ ...current, [server.name]: errorMessage(error) }));
      setDeleteTarget(null);
    } finally {
      setWorking(null);
    }
  };

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="mx-auto w-full max-w-6xl px-4 py-5 sm:px-6 sm:py-7">
        <header className="flex flex-wrap items-center gap-3 border-b border-zinc-800 pb-5">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <Network className="h-5 w-5 text-zinc-400" />
              <h1 className="text-lg font-semibold text-zinc-100">MCP 市场</h1>
            </div>
            <p className="mt-1 text-sm text-zinc-500">管理本地配置并连接可用工具服务</p>
          </div>
          <div className="ml-auto flex items-center gap-2">
            <button
              type="button"
              onClick={() => void loadServers()}
              disabled={loading}
              className="flex h-9 w-9 items-center justify-center rounded-md border border-zinc-700 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100 disabled:opacity-50"
              title="刷新列表"
              aria-label="刷新 MCP 列表"
            >
              <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
            </button>
            <button
              type="button"
              onClick={() => setFormServer(null)}
              className="inline-flex h-9 items-center gap-2 rounded-md bg-zinc-100 px-3 text-sm font-medium text-zinc-950 hover:bg-white"
            >
              <Plus className="h-4 w-4" />
              新建 MCP
            </button>
          </div>
        </header>

        {loadError && (
          <div role="alert" className="mt-5 flex items-start gap-3 rounded-md border border-red-900/80 bg-red-950/30 p-4 text-sm text-red-300">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
            <span className="min-w-0 flex-1 break-words">{loadError}</span>
            <button type="button" onClick={() => void loadServers()} className="shrink-0 rounded-md px-2 py-1 text-xs hover:bg-red-900/40">重试</button>
          </div>
        )}

        <section aria-label="MCP 服务列表" className="mt-5 divide-y divide-zinc-800 border-y border-zinc-800">
          {loading && servers.length === 0 && Array.from({ length: 3 }, (_, index) => (
            <div key={index} className="h-32 animate-pulse py-5">
              <div className="h-4 w-40 rounded bg-zinc-800" />
              <div className="mt-3 h-3 w-2/3 rounded bg-zinc-900" />
              <div className="mt-6 h-3 w-52 rounded bg-zinc-900" />
            </div>
          ))}

          {!loading && !loadError && servers.length === 0 && (
            <div className="flex min-h-48 flex-col items-center justify-center text-center">
              <Network className="h-7 w-7 text-zinc-700" />
              <p className="mt-3 text-sm text-zinc-400">还没有 MCP 服务</p>
            </div>
          )}

          {servers.map((server) => {
            const lifecycleWorking = working === `connect:${server.name}` || working === `disconnect:${server.name}`;
            const visibleError = rowErrors[server.name] || server.status_error;
            return (
              <article key={server.name} className="grid gap-4 py-5 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="max-w-full break-words text-sm font-semibold text-zinc-100">{server.display_name || server.name}</h2>
                    {server.builtin && <span className="rounded border border-zinc-700 px-1.5 py-0.5 text-[10px] font-medium text-zinc-400">内置</span>}
                    <span className={`inline-flex items-center gap-1 text-xs ${STATUS_CLASSES[server.status]}`}>
                      {server.status === 'connected' ? <CheckCircle2 className="h-3.5 w-3.5" /> : server.status === 'connecting' ? <LoaderCircle className="h-3.5 w-3.5 animate-spin" /> : <span className="h-1.5 w-1.5 rounded-full bg-current" />}
                      {STATUS_LABELS[server.status]}
                    </span>
                  </div>
                  <p className="mt-1 break-words text-sm text-zinc-500">{server.description || '暂无描述'}</p>
                  <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-xs text-zinc-600">
                    <span>{server.name}</span>
                    <span>{server.type.toUpperCase()}</span>
                    <span>{server.tool_count} 个工具</span>
                  </div>
                  {visibleError && <p role="alert" className="mt-2 max-w-3xl break-words text-xs text-red-400">{visibleError}</p>}
                </div>

                <div className="flex items-center gap-2 sm:justify-end">
                  <button
                    type="button"
                    onClick={() => void runLifecycle(server)}
                    disabled={Boolean(working) || server.status === 'connecting'}
                    className={`inline-flex h-9 min-w-24 items-center justify-center gap-2 rounded-md border px-3 text-sm transition-colors disabled:opacity-50 ${
                      server.connected
                        ? 'border-zinc-700 text-zinc-300 hover:bg-zinc-800'
                        : 'border-emerald-800/80 text-emerald-400 hover:bg-emerald-950/40'
                    }`}
                  >
                    {lifecycleWorking ? <LoaderCircle className="h-4 w-4 animate-spin" /> : server.connected ? <Unplug className="h-4 w-4" /> : <Network className="h-4 w-4" />}
                    {lifecycleWorking ? '处理中' : server.connected ? '断开' : server.status === 'error' ? '重试连接' : '连接'}
                  </button>

                  {server.mutable && (
                    <div className="relative">
                      <button
                        type="button"
                        onClick={(event) => {
                          event.stopPropagation();
                          setMenuServer((current) => current === server.name ? null : server.name);
                        }}
                        className="flex h-9 w-9 items-center justify-center rounded-md border border-zinc-700 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100"
                        aria-label={`管理 ${server.display_name}`}
                        aria-expanded={menuServer === server.name}
                      >
                        <MoreHorizontal className="h-4 w-4" />
                      </button>
                      {menuServer === server.name && (
                        <div className="absolute bottom-full right-0 z-20 mb-1 w-32 rounded-md border border-zinc-700 bg-zinc-900 py-1 shadow-xl" onClick={(event) => event.stopPropagation()}>
                          <button type="button" onClick={() => { setFormServer(server); setMenuServer(null); }} className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-zinc-300 hover:bg-zinc-800">
                            <Pencil className="h-3.5 w-3.5" />编辑
                          </button>
                          <button type="button" onClick={() => { setDeleteTarget(server); setMenuServer(null); }} className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-red-400 hover:bg-zinc-800">
                            <Trash2 className="h-3.5 w-3.5" />删除
                          </button>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </article>
            );
          })}
        </section>
      </div>

      {formServer !== undefined && (
        <McpServerForm server={formServer} onClose={() => setFormServer(undefined)} onSaved={loadServers} />
      )}

      {deleteTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
          <section role="alertdialog" aria-modal="true" aria-labelledby="delete-mcp-title" className="w-full max-w-md rounded-lg border border-zinc-700 bg-[#111111] p-5 shadow-2xl">
            <div className="flex items-start gap-3">
              <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-red-400" />
              <div className="min-w-0">
                <h2 id="delete-mcp-title" className="text-sm font-semibold text-zinc-100">删除 {deleteTarget.display_name}？</h2>
                <p className="mt-1 text-sm text-zinc-500">该配置会从本地目录中移除，相关运行时工具也会被清理。</p>
              </div>
              <button type="button" onClick={() => setDeleteTarget(null)} className="ml-auto p-1 text-zinc-500 hover:text-zinc-200" aria-label="关闭删除确认"><X className="h-4 w-4" /></button>
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <button type="button" onClick={() => setDeleteTarget(null)} className="rounded-md px-3 py-2 text-sm text-zinc-400 hover:bg-zinc-800">取消</button>
              <button type="button" onClick={() => void confirmDelete()} disabled={working === `delete:${deleteTarget.name}`} className="inline-flex items-center gap-2 rounded-md bg-red-600 px-3 py-2 text-sm font-medium text-white hover:bg-red-500 disabled:opacity-50">
                {working === `delete:${deleteTarget.name}` && <LoaderCircle className="h-4 w-4 animate-spin" />}
                删除
              </button>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}

