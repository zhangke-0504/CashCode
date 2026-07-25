import type {
  SkillInvalidDiagnostic,
  SkillSelectionReceipt,
  SkillSummary,
} from '../types';

const MAX_INVALID_PACKAGES = 100;
const MAX_INVALID_ERRORS = 3;
const MAX_INVALID_DIRECTORY_CHARS = 80;
const MAX_INVALID_MESSAGE_CHARS = 240;

export const SKILL_SOURCE_LABELS: Record<SkillSummary['source'], string> = {
  builtin: '内置',
  user: '用户上传',
  agent: '聊天创建',
};

export const SKILL_AVAILABILITY_LABELS: Record<SkillSummary['availability'], string> = {
  available: '可用',
  missing_dependency: '缺少依赖',
  disabled: '已禁用',
  invalid: '无效',
};

export function skillSourceLabel(skill: SkillSummary): string {
  return SKILL_SOURCE_LABELS[skill.source];
}

export function skillDisplayName(skill: Pick<SkillSummary, 'name' | 'display_name'>): string {
  return skill.display_name?.trim() || skill.name;
}

export function skillSelectionReceipt(
  skill: Pick<SkillSummary, 'name' | 'display_name'>,
): SkillSelectionReceipt {
  return { name: skill.name, label: skillDisplayName(skill) };
}

function boundedDiagnosticText(value: unknown, limit: number, fallback: string): string {
  const normalized = typeof value === 'string'
    ? Array.from(value, (character) => {
      const code = character.charCodeAt(0);
      return code < 32 || code === 127 ? ' ' : character;
    }).join('').trim()
    : '';
  if (!normalized) return fallback;
  return normalized.length <= limit ? normalized : `${normalized.slice(0, limit - 3)}...`;
}

export function skillInvalidDiagnostics(
  invalid: Record<string, string[]>,
): SkillInvalidDiagnostic[] {
  return Object.entries(invalid).slice(0, MAX_INVALID_PACKAGES).map(([key, rawErrors], index) => {
    const separator = key.indexOf(':');
    const rawSource = separator >= 0 ? key.slice(0, separator) : '';
    const source = rawSource === 'builtin' || rawSource === 'agent' ? rawSource : 'user';
    const rawDirectory = separator >= 0 ? key.slice(separator + 1) : key;
    const directory = boundedDiagnosticText(
      rawDirectory,
      MAX_INVALID_DIRECTORY_CHARS,
      'unknown',
    );
    const errors = (Array.isArray(rawErrors) ? rawErrors : [])
      .slice(0, MAX_INVALID_ERRORS)
      .map((error) => boundedDiagnosticText(error, MAX_INVALID_MESSAGE_CHARS, '无效 Skill 包'));
    return {
      key: `${source}:${directory}:${index}`,
      source,
      directory,
      errors: errors.length > 0 ? errors : ['无效 Skill 包'],
      selectable: false,
      manageable: false,
    };
  });
}

export function skillStatusLabel(skill: SkillSummary): string {
  return skill.enabled ? SKILL_AVAILABILITY_LABELS[skill.availability] : '已禁用';
}

export function skillCanManage(skill: SkillSummary): boolean {
  return skill.mutable && skill.source !== 'builtin';
}

export function skillInvalidCanDelete(
  diagnostic: Pick<SkillInvalidDiagnostic, 'source'>,
): boolean {
  return diagnostic.source !== 'builtin';
}

export function skillPageCount(total: number, pageSize: number): number {
  return Math.max(1, Math.ceil(Math.max(0, total) / Math.max(1, pageSize)));
}

export function validateSkillZipName(name: string): string | null {
  const trimmed = name.trim();
  if (!trimmed || !trimmed.toLowerCase().endsWith('.zip')) {
    return '请选择 .zip 格式的 Skill 包';
  }
  return null;
}

export function skillEditorError(status: number, detail: string): string {
  if (status === 409) return 'Skill 已被其他操作更新，请重新加载后再保存。';
  return detail || '保存 Skill 失败';
}
