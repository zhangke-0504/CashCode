import { useRef, useState } from 'react';
import { AlertCircle, FileArchive, LoaderCircle, Upload, X } from 'lucide-react';
import { ApiError, importSkill } from '../lib/api';
import { validateSkillZipName } from '../lib/skill-market';

interface SkillUploadModalProps {
  onClose: () => void;
  onUploaded: () => Promise<void> | void;
}

export function SkillUploadModal({ onClose, onUploaded }: SkillUploadModalProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);

  const selectFile = (next: File | null) => {
    setFile(next);
    setError(next ? validateSkillZipName(next.name) : null);
  };

  const handleUpload = async () => {
    const validationError = file ? validateSkillZipName(file.name) : '请选择 Skill ZIP 包';
    setError(validationError);
    if (!file || validationError) return;
    setUploading(true);
    try {
      await importSkill(file);
      await onUploaded();
      onClose();
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.detail : reason instanceof Error ? reason.message : '上传 Skill 失败');
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4">
      <section role="dialog" aria-modal="true" aria-labelledby="skill-upload-title" className="w-full max-w-lg rounded-lg border border-zinc-700 bg-[#111111] shadow-2xl">
        <header className="flex items-center gap-3 border-b border-zinc-800 px-5 py-4">
          <FileArchive className="h-5 w-5 text-zinc-400" />
          <h2 id="skill-upload-title" className="text-sm font-semibold text-zinc-100">上传 Skill</h2>
          <button type="button" onClick={onClose} disabled={uploading} className="ml-auto flex h-8 w-8 items-center justify-center rounded-md text-zinc-500 hover:bg-zinc-800 hover:text-zinc-100 disabled:opacity-40" title="关闭" aria-label="关闭上传窗口">
            <X className="h-4 w-4" />
          </button>
        </header>

        <div className="p-5">
          <input
            ref={inputRef}
            type="file"
            accept=".zip,application/zip"
            className="hidden"
            onChange={(event) => selectFile(event.target.files?.[0] ?? null)}
          />
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            disabled={uploading}
            className="flex min-h-32 w-full flex-col items-center justify-center rounded-md border border-dashed border-zinc-700 bg-zinc-950/60 px-4 text-center hover:border-zinc-500 hover:bg-zinc-950 disabled:opacity-50"
          >
            <FileArchive className="h-7 w-7 text-zinc-500" />
            <span className="mt-3 max-w-full truncate text-sm text-zinc-300">{file?.name || '选择 ZIP 文件'}</span>
            {file && <span className="mt-1 text-xs text-zinc-600">{Math.max(1, Math.ceil(file.size / 1024))} KB</span>}
          </button>

          {error && (
            <div role="alert" className="mt-3 flex items-start gap-2 rounded-md border border-red-900/80 bg-red-950/30 px-3 py-2 text-xs text-red-300">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
              <span className="break-words">{error}</span>
            </div>
          )}
        </div>

        <footer className="flex justify-end gap-2 border-t border-zinc-800 px-5 py-4">
          <button type="button" onClick={onClose} disabled={uploading} className="rounded-md px-3 py-2 text-sm text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100 disabled:opacity-40">取消</button>
          <button type="button" onClick={() => void handleUpload()} disabled={uploading || !file} className="inline-flex min-w-20 items-center justify-center gap-2 rounded-md bg-zinc-100 px-3 py-2 text-sm font-medium text-zinc-950 hover:bg-white disabled:opacity-40">
            {uploading ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
            上传
          </button>
        </footer>
      </section>
    </div>
  );
}
