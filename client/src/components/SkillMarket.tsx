import { useCallback, useEffect, useRef, useState } from 'react';
import {
  AlertCircle,
  ChevronLeft,
  ChevronRight,
  Eye,
  LoaderCircle,
  Pencil,
  RefreshCw,
  Search,
  Trash2,
  Upload,
  X,
  Zap,
} from 'lucide-react';
import {
  ApiError,
  deleteInvalidSkill,
  deleteSkill,
  fetchSkills,
  setSkillEnabled,
} from '../lib/api';
import {
  SKILL_SOURCE_LABELS,
  skillCanManage,
  skillDisplayName,
  skillInvalidCanDelete,
  skillInvalidDiagnostics,
  skillPageCount,
  skillSourceLabel,
  skillStatusLabel,
} from '../lib/skill-market';
import type { SkillInvalidDiagnostic, SkillListResponse, SkillSummary } from '../types';
import { SkillEditorModal } from './SkillEditorModal';
import { SkillUploadModal } from './SkillUploadModal';

const PAGE_SIZE = 20;

const EMPTY_RESULT: SkillListResponse = {
  items: [],
  total: 0,
  page: 1,
  page_size: PAGE_SIZE,
  invalid: {},
};

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.detail : error instanceof Error ? error.message : '请求失败';
}

function statusClass(skill: SkillSummary): string {
  if (!skill.enabled || skill.availability === 'disabled') return 'text-zinc-500';
  if (skill.availability === 'available') return 'text-emerald-400';
  if (skill.availability === 'missing_dependency') return 'text-amber-400';
  return 'text-red-400';
}

interface EditorTarget {
  skill: SkillSummary;
  editing: boolean;
}

export function SkillMarket() {
  const requestId = useRef(0);
  const [result, setResult] = useState<SkillListResponse>(EMPTY_RESULT);
  const [query, setQuery] = useState('');
  const [debouncedQuery, setDebouncedQuery] = useState('');
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [working, setWorking] = useState<string | null>(null);
  const [rowErrors, setRowErrors] = useState<Record<string, string>>({});
  const [editorTarget, setEditorTarget] = useState<EditorTarget | null>(null);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<SkillSummary | null>(null);
  const [invalidDeleteTarget, setInvalidDeleteTarget] = useState<SkillInvalidDiagnostic | null>(null);
  const [invalidErrors, setInvalidErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setPage(1);
      setDebouncedQuery(query.trim());
    }, 250);
    return () => window.clearTimeout(timer);
  }, [query]);

  const loadSkills = useCallback(async () => {
    const id = ++requestId.current;
    setLoading(true);
    setLoadError(null);
    try {
      const next = await fetchSkills({ query: debouncedQuery || undefined, page, page_size: PAGE_SIZE });
      if (id !== requestId.current) return;
      const pages = skillPageCount(next.total, next.page_size);
      if (page > pages) {
        setPage(pages);
        return;
      }
      setResult(next);
    } catch (error) {
      if (id === requestId.current) setLoadError(errorMessage(error));
    } finally {
      if (id === requestId.current) setLoading(false);
    }
  }, [debouncedQuery, page]);

  useEffect(() => {
    void loadSkills();
  }, [loadSkills]);

  const refresh = useCallback(async () => {
    await loadSkills();
  }, [loadSkills]);

  const toggleEnabled = async (skill: SkillSummary) => {
    const key = `enabled:${skill.name}`;
    setWorking(key);
    setRowErrors((current) => ({ ...current, [skill.name]: '' }));
    try {
      await setSkillEnabled(skill.name, !skill.enabled);
      await refresh();
    } catch (error) {
      setRowErrors((current) => ({ ...current, [skill.name]: errorMessage(error) }));
    } finally {
      setWorking(null);
    }
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    const skill = deleteTarget;
    const key = `delete:${skill.name}`;
    setWorking(key);
    setRowErrors((current) => ({ ...current, [skill.name]: '' }));
    try {
      await deleteSkill(skill.name);
      setDeleteTarget(null);
      await refresh();
    } catch (error) {
      setRowErrors((current) => ({ ...current, [skill.name]: errorMessage(error) }));
      setDeleteTarget(null);
    } finally {
      setWorking(null);
    }
  };

  const confirmInvalidDelete = async () => {
    if (!invalidDeleteTarget) return;
    const diagnostic = invalidDeleteTarget;
    const key = `invalid:${diagnostic.key}`;
    setWorking(key);
    setInvalidErrors((current) => ({ ...current, [diagnostic.key]: '' }));
    try {
      await deleteInvalidSkill(diagnostic.source, diagnostic.directory);
      setInvalidDeleteTarget(null);
      await refresh();
    } catch (error) {
      setInvalidErrors((current) => ({
        ...current,
        [diagnostic.key]: errorMessage(error),
      }));
      setInvalidDeleteTarget(null);
    } finally {
      setWorking(null);
    }
  };

  const pages = skillPageCount(result.total, result.page_size);
  const invalidDiagnostics = skillInvalidDiagnostics(result.invalid);

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="mx-auto w-full max-w-6xl px-4 py-5 sm:px-6 sm:py-7">
        <header className="flex flex-wrap items-center gap-3 border-b border-zinc-800 pb-5">
          <div className="flex min-w-0 items-center gap-2">
            <Zap className="h-5 w-5 text-zinc-400" />
            <h1 className="text-lg font-semibold text-zinc-100">Skill 市场</h1>
          </div>
          <div className="ml-auto flex w-full items-center gap-2 sm:w-auto">
            <label className="relative min-w-0 flex-1 sm:w-72 sm:flex-none">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-600" />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                className="h-9 w-full rounded-md border border-zinc-700 bg-zinc-950 pl-9 pr-3 text-sm text-zinc-100 outline-none placeholder:text-zinc-600 focus:border-zinc-500"
                placeholder="搜索 Skill"
                aria-label="搜索 Skill"
              />
            </label>
            <button type="button" onClick={() => void refresh()} disabled={loading} className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-zinc-700 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100 disabled:opacity-50" title="刷新列表" aria-label="刷新 Skill 列表">
              <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
            </button>
            <button type="button" onClick={() => setUploadOpen(true)} className="inline-flex h-9 shrink-0 items-center gap-2 rounded-md bg-zinc-100 px-3 text-sm font-medium text-zinc-950 hover:bg-white">
              <Upload className="h-4 w-4" />
              上传
            </button>
          </div>
        </header>

        {loadError && (
          <div role="alert" className="mt-5 flex items-start gap-3 rounded-md border border-red-900/80 bg-red-950/30 p-4 text-sm text-red-300">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
            <span className="min-w-0 flex-1 break-words">{loadError}</span>
            <button type="button" onClick={() => void refresh()} className="shrink-0 rounded-md px-2 py-1 text-xs hover:bg-red-900/40">重试</button>
          </div>
        )}

        <section aria-label="Skill 列表" aria-busy={loading} className="mt-5 divide-y divide-zinc-800 border-y border-zinc-800">
          {loading && result.items.length === 0 && Array.from({ length: 4 }, (_, index) => (
            <div key={index} className="h-28 animate-pulse py-5">
              <div className="h-4 w-40 rounded bg-zinc-800" />
              <div className="mt-3 h-3 w-2/3 rounded bg-zinc-900" />
              <div className="mt-5 h-3 w-52 rounded bg-zinc-900" />
            </div>
          ))}

          {!loading && !loadError && result.items.length === 0 && (
            <div className="flex min-h-48 flex-col items-center justify-center text-center">
              <Zap className="h-7 w-7 text-zinc-700" />
              <p className="mt-3 text-sm text-zinc-400">暂无 Skill</p>
            </div>
          )}

          {result.items.map((skill) => {
            const manageable = skillCanManage(skill);
            const visibleError = rowErrors[skill.name];
            const rowWorking = working?.endsWith(`:${skill.name}`) ?? false;
            return (
              <article key={skill.name} className="grid min-h-28 gap-4 py-5 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="max-w-full break-words text-sm font-semibold text-zinc-100">{skillDisplayName(skill)}</h2>
                    <span className="rounded border border-zinc-700 px-1.5 py-0.5 text-[10px] font-medium text-zinc-400">{skillSourceLabel(skill)}</span>
                    <span className={`inline-flex items-center gap-1 text-xs ${statusClass(skill)}`}>
                      <span className="h-1.5 w-1.5 rounded-full bg-current" />
                      {skillStatusLabel(skill)}
                    </span>
                  </div>
                  <p className="mt-1 break-words text-sm text-zinc-500">{skill.description || '暂无描述'}</p>
                  <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-xs text-zinc-600">
                    {skillDisplayName(skill) !== skill.name && <span>{skill.name}</span>}
                    <span>v{skill.version}</span>
                    {skill.tags.slice(0, 4).map((tag) => <span key={tag}>#{tag}</span>)}
                    {skill.always && <span>always</span>}
                  </div>
                  {skill.missing.length > 0 && <p className="mt-2 break-words text-xs text-amber-500">{skill.missing.slice(0, 6).join(' · ')}</p>}
                  {visibleError && <p role="alert" className="mt-2 break-words text-xs text-red-400">{visibleError}</p>}
                </div>

                <div className="flex min-h-9 items-center gap-1 sm:justify-end">
                  <button type="button" onClick={() => setEditorTarget({ skill, editing: false })} className="flex h-9 w-9 items-center justify-center rounded-md text-zinc-500 hover:bg-zinc-800 hover:text-zinc-100" title="查看" aria-label={`查看 ${skill.name}`}>
                    <Eye className="h-4 w-4" />
                  </button>
                  {manageable && (
                    <>
                      <button type="button" onClick={() => setEditorTarget({ skill, editing: true })} className="flex h-9 w-9 items-center justify-center rounded-md text-zinc-500 hover:bg-zinc-800 hover:text-zinc-100" title="编辑" aria-label={`编辑 ${skill.name}`}>
                        <Pencil className="h-4 w-4" />
                      </button>
                      <button
                        type="button"
                        role="switch"
                        aria-checked={skill.enabled}
                        onClick={() => void toggleEnabled(skill)}
                        disabled={Boolean(working)}
                        className={`relative h-5 w-9 rounded-full transition-colors disabled:opacity-40 ${skill.enabled ? 'bg-emerald-700' : 'bg-zinc-700'}`}
                        title={skill.enabled ? '禁用' : '启用'}
                        aria-label={`${skill.enabled ? '禁用' : '启用'} ${skill.name}`}
                      >
                        <span className={`absolute top-0.5 h-4 w-4 rounded-full bg-white transition-transform ${skill.enabled ? 'translate-x-4' : 'translate-x-0.5'}`} />
                      </button>
                      <button type="button" onClick={() => setDeleteTarget(skill)} disabled={Boolean(working)} className="flex h-9 w-9 items-center justify-center rounded-md text-zinc-500 hover:bg-zinc-800 hover:text-red-400 disabled:opacity-40" title="删除" aria-label={`删除 ${skill.name}`}>
                        {rowWorking ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
                      </button>
                    </>
                  )}
                </div>
              </article>
            );
          })}
        </section>

        {invalidDiagnostics.length > 0 && (
          <section aria-label="无效 Skill 包" className="mt-7 border-t border-red-950/80">
            <header className="flex min-h-12 items-center gap-2 border-b border-zinc-800 text-sm text-zinc-300">
              <AlertCircle className="h-4 w-4 text-red-400" />
              <h2 className="font-medium">无效 Skill 包</h2>
              <span className="text-xs text-zinc-600">{invalidDiagnostics.length}</span>
            </header>
            <div className="divide-y divide-zinc-800">
              {invalidDiagnostics.map((diagnostic) => (
                <article key={diagnostic.key} className="grid min-h-24 gap-3 py-4 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-start">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="break-words font-mono text-sm font-medium text-zinc-300">{diagnostic.directory}</h3>
                      <span className="rounded border border-red-900/70 px-1.5 py-0.5 text-[10px] font-medium text-red-400">无效</span>
                    </div>
                    {diagnostic.errors.map((error, index) => (
                      <p key={`${diagnostic.key}:${index}`} className="mt-2 break-words text-xs text-red-300/80">{error}</p>
                    ))}
                    {invalidErrors[diagnostic.key] && (
                      <p role="alert" className="mt-2 break-words text-xs text-red-400">{invalidErrors[diagnostic.key]}</p>
                    )}
                  </div>
                  <div className="flex min-h-9 items-center gap-2 sm:justify-end">
                    <span className="text-xs text-zinc-600">{SKILL_SOURCE_LABELS[diagnostic.source]}</span>
                    {skillInvalidCanDelete(diagnostic) && (
                      <button
                        type="button"
                        onClick={() => setInvalidDeleteTarget(diagnostic)}
                        disabled={Boolean(working)}
                        className="flex h-9 w-9 items-center justify-center rounded-md text-zinc-500 hover:bg-zinc-800 hover:text-red-400 disabled:opacity-40"
                        title="删除无效包"
                        aria-label={`删除无效 Skill 包 ${diagnostic.directory}`}
                      >
                        {working === `invalid:${diagnostic.key}` ? (
                          <LoaderCircle className="h-4 w-4 animate-spin" />
                        ) : (
                          <Trash2 className="h-4 w-4" />
                        )}
                      </button>
                    )}
                  </div>
                </article>
              ))}
            </div>
          </section>
        )}

        <footer className="flex min-h-14 items-center justify-between gap-3 py-3 text-xs text-zinc-500">
          <span>共 {result.total} 个</span>
          <div className="flex items-center gap-2">
            <button type="button" onClick={() => setPage((value) => Math.max(1, value - 1))} disabled={loading || page <= 1} className="flex h-8 w-8 items-center justify-center rounded-md border border-zinc-800 hover:bg-zinc-800 hover:text-zinc-200 disabled:opacity-30" title="上一页" aria-label="上一页">
              <ChevronLeft className="h-4 w-4" />
            </button>
            <span className="w-20 text-center">{page} / {pages}</span>
            <button type="button" onClick={() => setPage((value) => Math.min(pages, value + 1))} disabled={loading || page >= pages} className="flex h-8 w-8 items-center justify-center rounded-md border border-zinc-800 hover:bg-zinc-800 hover:text-zinc-200 disabled:opacity-30" title="下一页" aria-label="下一页">
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
        </footer>
      </div>

      {editorTarget && (
        <SkillEditorModal
          key={`${editorTarget.skill.name}:${editorTarget.editing}`}
          skill={editorTarget.skill}
          startEditing={editorTarget.editing}
          onClose={() => setEditorTarget(null)}
          onSaved={refresh}
        />
      )}
      {uploadOpen && <SkillUploadModal onClose={() => setUploadOpen(false)} onUploaded={refresh} />}

      {deleteTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4">
          <section role="alertdialog" aria-modal="true" aria-labelledby="delete-skill-title" className="w-full max-w-md rounded-lg border border-zinc-700 bg-[#111111] p-5 shadow-2xl">
            <div className="flex items-start gap-3">
              <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-red-400" />
              <div className="min-w-0 flex-1">
                <h2 id="delete-skill-title" className="break-words text-sm font-semibold text-zinc-100">删除 {skillDisplayName(deleteTarget)}？</h2>
                <p className="mt-2 text-sm text-zinc-500">当前版本会保留在本地快照中。</p>
              </div>
              <button type="button" onClick={() => setDeleteTarget(null)} disabled={working === `delete:${deleteTarget.name}`} className="flex h-8 w-8 items-center justify-center rounded-md text-zinc-500 hover:bg-zinc-800 hover:text-zinc-100 disabled:opacity-40" title="关闭" aria-label="关闭删除确认">
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <button type="button" onClick={() => setDeleteTarget(null)} disabled={working === `delete:${deleteTarget.name}`} className="rounded-md px-3 py-2 text-sm text-zinc-400 hover:bg-zinc-800 disabled:opacity-40">取消</button>
              <button type="button" onClick={() => void confirmDelete()} disabled={working === `delete:${deleteTarget.name}`} className="inline-flex min-w-20 items-center justify-center gap-2 rounded-md bg-red-600 px-3 py-2 text-sm font-medium text-white hover:bg-red-500 disabled:opacity-50">
                {working === `delete:${deleteTarget.name}` && <LoaderCircle className="h-4 w-4 animate-spin" />}
                删除
              </button>
            </div>
          </section>
        </div>
      )}

      {invalidDeleteTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4">
          <section role="alertdialog" aria-modal="true" aria-labelledby="delete-invalid-skill-title" className="w-full max-w-md rounded-lg border border-zinc-700 bg-[#111111] p-5 shadow-2xl">
            <div className="flex items-start gap-3">
              <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-red-400" />
              <div className="min-w-0 flex-1">
                <h2 id="delete-invalid-skill-title" className="break-words text-sm font-semibold text-zinc-100">删除无效包 {invalidDeleteTarget.directory}？</h2>
                <p className="mt-2 text-sm text-zinc-500">目录会移出 Skill 市场，并保留在本地恢复快照中。</p>
              </div>
              <button type="button" onClick={() => setInvalidDeleteTarget(null)} disabled={Boolean(working)} className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-zinc-500 hover:bg-zinc-800 hover:text-zinc-100 disabled:opacity-40" title="关闭" aria-label="关闭无效包删除确认">
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <button type="button" onClick={() => setInvalidDeleteTarget(null)} disabled={Boolean(working)} className="rounded-md px-3 py-2 text-sm text-zinc-400 hover:bg-zinc-800 disabled:opacity-40">取消</button>
              <button type="button" onClick={() => void confirmInvalidDelete()} disabled={Boolean(working)} className="inline-flex min-w-20 items-center justify-center gap-2 rounded-md bg-red-600 px-3 py-2 text-sm font-medium text-white hover:bg-red-500 disabled:opacity-50">
                {working === `invalid:${invalidDeleteTarget.key}` && <LoaderCircle className="h-4 w-4 animate-spin" />}
                删除
              </button>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
