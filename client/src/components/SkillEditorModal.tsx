import { useCallback, useEffect, useState } from 'react';
import { AlertCircle, LoaderCircle, Pencil, RefreshCw, Save, X } from 'lucide-react';
import { ApiError, fetchSkillContent, updateSkill } from '../lib/api';
import { skillDisplayName, skillEditorError, skillSourceLabel } from '../lib/skill-market';
import type { SkillContent, SkillSummary } from '../types';

interface SkillEditorModalProps {
  skill: SkillSummary;
  startEditing: boolean;
  onClose: () => void;
  onSaved: () => Promise<void> | void;
}

export function SkillEditorModal({ skill, startEditing, onClose, onSaved }: SkillEditorModalProps) {
  const [content, setContent] = useState<SkillContent | null>(null);
  const [draft, setDraft] = useState('');
  const [editing, setEditing] = useState(startEditing && skill.mutable);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [conflicted, setConflicted] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setConflicted(false);
    try {
      const next = await fetchSkillContent(skill.name);
      setContent(next);
      setDraft(next.content);
      if (!next.mutable) setEditing(false);
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.detail : reason instanceof Error ? reason.message : '加载 Skill 失败');
    } finally {
      setLoading(false);
    }
  }, [skill.name]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleSave = async () => {
    if (!content || !editing || saving || draft === content.content) return;
    setSaving(true);
    setError(null);
    setConflicted(false);
    try {
      await updateSkill(skill.name, { content: draft, expected_hash: content.hash });
      await onSaved();
      onClose();
    } catch (reason) {
      if (reason instanceof ApiError) {
        setConflicted(reason.status === 409);
        setError(skillEditorError(reason.status, reason.detail));
      } else {
        setError(reason instanceof Error ? reason.message : '保存 Skill 失败');
      }
    } finally {
      setSaving(false);
    }
  };

  const cancelEdit = () => {
    if (content) setDraft(content.content);
    setError(null);
    setConflicted(false);
    setEditing(false);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-3 sm:p-5">
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="skill-editor-title"
        className="flex max-h-[92vh] w-full max-w-4xl flex-col overflow-hidden rounded-lg border border-zinc-700 bg-[#111111] shadow-2xl"
      >
        <header className="flex items-start gap-3 border-b border-zinc-800 px-4 py-3 sm:px-5">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h2 id="skill-editor-title" className="truncate text-sm font-semibold text-zinc-100">{skillDisplayName(skill)}</h2>
              <span className="rounded border border-zinc-700 px-1.5 py-0.5 text-[10px] font-medium text-zinc-400">
                {skillSourceLabel(skill)}
              </span>
            </div>
            <p className="mt-1 truncate font-mono text-xs text-zinc-500">{skill.name} / SKILL.md</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={saving}
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-zinc-500 hover:bg-zinc-800 hover:text-zinc-100 disabled:opacity-40"
            title="关闭"
            aria-label="关闭 Skill 编辑器"
          >
            <X className="h-4 w-4" />
          </button>
        </header>

        <div className="flex min-h-0 flex-1 flex-col p-4 sm:p-5">
          {loading ? (
            <div className="flex h-[55vh] min-h-72 items-center justify-center text-zinc-500">
              <LoaderCircle className="h-5 w-5 animate-spin" />
            </div>
          ) : content ? (
            <textarea
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              readOnly={!editing}
              spellCheck={false}
              aria-label="Skill 配置内容"
              className={`h-[55vh] min-h-72 w-full resize-none rounded-md border bg-zinc-950 p-4 font-mono text-xs leading-6 text-zinc-200 outline-none ${
                editing ? 'border-zinc-600 focus:border-zinc-400' : 'border-zinc-800'
              }`}
            />
          ) : (
            <div className="flex h-[55vh] min-h-72 items-center justify-center text-sm text-zinc-500">无法读取 Skill</div>
          )}

          {error && (
            <div role="alert" className="mt-3 flex items-start gap-2 rounded-md border border-red-900/80 bg-red-950/30 px-3 py-2 text-xs text-red-300">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
              <span className="min-w-0 flex-1 break-words">{error}</span>
              {conflicted && (
                <button type="button" onClick={() => void load()} className="inline-flex shrink-0 items-center gap-1 rounded px-2 py-1 hover:bg-red-900/40">
                  <RefreshCw className="h-3.5 w-3.5" />
                  重新加载
                </button>
              )}
            </div>
          )}
        </div>

        <footer className="flex min-h-16 items-center justify-end gap-2 border-t border-zinc-800 px-4 py-3 sm:px-5">
          {editing ? (
            <>
              <button type="button" onClick={cancelEdit} disabled={saving} className="rounded-md px-3 py-2 text-sm text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100 disabled:opacity-40">
                取消
              </button>
              <button
                type="button"
                onClick={() => void handleSave()}
                disabled={saving || loading || !content || draft === content.content}
                className="inline-flex min-w-20 items-center justify-center gap-2 rounded-md bg-zinc-100 px-3 py-2 text-sm font-medium text-zinc-950 hover:bg-white disabled:opacity-40"
              >
                {saving ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                保存
              </button>
            </>
          ) : (
            <>
              <button type="button" onClick={onClose} className="rounded-md px-3 py-2 text-sm text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100">关闭</button>
              {content?.mutable && (
                <button type="button" onClick={() => setEditing(true)} className="inline-flex items-center gap-2 rounded-md bg-zinc-100 px-3 py-2 text-sm font-medium text-zinc-950 hover:bg-white">
                  <Pencil className="h-4 w-4" />
                  编辑
                </button>
              )}
            </>
          )}
        </footer>
      </section>
    </div>
  );
}
