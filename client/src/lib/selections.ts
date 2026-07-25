import type {
  CapabilitySelections,
  Message,
  McpSelectionReceipt,
  OutboundWsFrame,
  PersistedMessage,
  SkillSelectionReceipt,
} from '../types';

export const MAX_CAPABILITY_SELECTIONS = 8;
export const MAX_SELECTION_LABEL = 100;

const SKILL_NAME_PATTERN = /^[a-z0-9][a-z0-9._-]{0,63}$/;
const MCP_NAME_PATTERN = /^[a-z0-9][a-z0-9_-]{0,63}$/;

export type CapabilityKind = 'skill' | 'mcp';
export type PickerLevel = 'category' | CapabilityKind;

export interface SelectionDraft {
  skills: SkillSelectionReceipt[];
  mcps: McpSelectionReceipt[];
}

export interface CapabilityTrigger {
  start: number;
  end: number;
  query: string;
}

export class SelectionError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'SelectionError';
  }
}

function cleanLabel(value: unknown): string | undefined {
  if (value === undefined || value === null) return undefined;
  if (typeof value !== 'string') throw new SelectionError('显示名称必须是文本');
  const label = value.replaceAll('\0', '').trim();
  if (!label) return undefined;
  if (label.length > MAX_SELECTION_LABEL) {
    throw new SelectionError(`显示名称不能超过 ${MAX_SELECTION_LABEL} 个字符`);
  }
  return label;
}

function cleanSkill(value: SkillSelectionReceipt): SkillSelectionReceipt {
  const name = value.name?.trim();
  if (!SKILL_NAME_PATTERN.test(name)) throw new SelectionError('Skill 标识无效');
  const label = cleanLabel(value.label);
  return label ? { name, label } : { name };
}

function cleanMcp(value: McpSelectionReceipt): McpSelectionReceipt {
  const server = value.server?.trim();
  if (!MCP_NAME_PATTERN.test(server)) throw new SelectionError('MCP 标识无效');
  const label = cleanLabel(value.label);
  return label ? { server, label } : { server };
}

function dedupeBy<T>(items: T[], identity: (item: T) => string): T[] {
  const seen = new Set<string>();
  return items.filter((item) => {
    const key = identity(item);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

export function normalizeSelectionDraft(draft: SelectionDraft): SelectionDraft {
  const skills = dedupeBy(draft.skills.map(cleanSkill), (item) => item.name);
  const mcps = dedupeBy(draft.mcps.map(cleanMcp), (item) => item.server);
  if (skills.length + mcps.length > MAX_CAPABILITY_SELECTIONS) {
    throw new SelectionError(`最多选择 ${MAX_CAPABILITY_SELECTIONS} 个 Skill 或 MCP`);
  }
  return { skills, mcps };
}

export function addSkillSelection(
  draft: SelectionDraft,
  selection: SkillSelectionReceipt,
): SelectionDraft {
  return normalizeSelectionDraft({ ...draft, skills: [...draft.skills, selection] });
}

export function addMcpSelection(
  draft: SelectionDraft,
  selection: McpSelectionReceipt,
): SelectionDraft {
  return normalizeSelectionDraft({ ...draft, mcps: [...draft.mcps, selection] });
}

export function removeCapabilitySelection(
  draft: SelectionDraft,
  kind: CapabilityKind,
  identity: string,
): SelectionDraft {
  return kind === 'skill'
    ? { ...draft, skills: draft.skills.filter((item) => item.name !== identity) }
    : { ...draft, mcps: draft.mcps.filter((item) => item.server !== identity) };
}

export function parseCapabilityTrigger(text: string, caret: number): CapabilityTrigger | null {
  if (!Number.isInteger(caret) || caret < 0 || caret > text.length) return null;
  const beforeCaret = text.slice(0, caret);
  const match = /(?:^|\s)@([^\s@]*)$/.exec(beforeCaret);
  if (!match) return null;
  const start = beforeCaret.lastIndexOf('@');
  return { start, end: caret, query: match[1] ?? '' };
}

export function replaceCapabilityTrigger(
  text: string,
  trigger: CapabilityTrigger,
): { text: string; caret: number } {
  if (trigger.start < 0 || trigger.end < trigger.start || trigger.end > text.length) {
    throw new SelectionError('选择器触发区间无效');
  }
  return {
    text: text.slice(0, trigger.start) + text.slice(trigger.end),
    caret: trigger.start,
  };
}

export function filterCapabilities<T>(
  items: T[],
  query: string,
  searchableText: (item: T) => Array<string | undefined>,
): T[] {
  const normalizedQuery = query.trim().toLocaleLowerCase();
  if (!normalizedQuery) return items;
  return items.filter((item) =>
    searchableText(item).some((value) => value?.toLocaleLowerCase().includes(normalizedQuery))
  );
}

export function selectionMetadata(draft: SelectionDraft): CapabilitySelections | undefined {
  const normalized = normalizeSelectionDraft(draft);
  const metadata: CapabilitySelections = {};
  if (normalized.skills.length > 0) metadata.mentioned_skills = normalized.skills;
  if (normalized.mcps.length > 0) metadata.selected_mcp_connectors = normalized.mcps;
  return Object.keys(metadata).length > 0 ? metadata : undefined;
}

export function buildMessageFrame(
  chatId: string,
  content: string,
  draft: SelectionDraft,
): Extract<OutboundWsFrame, { type: 'message' }> {
  const trimmed = content.trim();
  if (!trimmed) throw new SelectionError('请输入消息内容');
  const metadata = selectionMetadata(draft);
  return metadata
    ? { type: 'message', chat_id: chatId, content: trimmed, metadata }
    : { type: 'message', chat_id: chatId, content: trimmed };
}

export function movePickerIndex(
  current: number,
  direction: 'next' | 'previous',
  itemCount: number,
): number {
  if (itemCount <= 0) return 0;
  return direction === 'next'
    ? (current + 1) % itemCount
    : (current - 1 + itemCount) % itemCount;
}

export function pickerBackLevel(level: PickerLevel): PickerLevel | null {
  return level === 'category' ? null : 'category';
}

function persistedSkillReceipts(value: unknown): SkillSelectionReceipt[] {
  if (!Array.isArray(value)) return [];
  const rows: SkillSelectionReceipt[] = [];
  for (const raw of value) {
    if (!raw || typeof raw !== 'object' || !('name' in raw) || typeof raw.name !== 'string') continue;
    const name = raw.name.trim();
    if (!SKILL_NAME_PATTERN.test(name)) continue;
    let label: string | undefined;
    try {
      label = cleanLabel('label' in raw ? raw.label : undefined);
    } catch {
      label = undefined;
    }
    rows.push(label ? { name, label } : { name });
  }
  return dedupeBy(rows, (item) => item.name).slice(0, MAX_CAPABILITY_SELECTIONS);
}

function persistedMcpReceipts(value: unknown): McpSelectionReceipt[] {
  if (!Array.isArray(value)) return [];
  const rows: McpSelectionReceipt[] = [];
  for (const raw of value) {
    if (!raw || typeof raw !== 'object' || !('server' in raw) || typeof raw.server !== 'string') continue;
    const server = raw.server.trim();
    if (!MCP_NAME_PATTERN.test(server)) continue;
    let label: string | undefined;
    try {
      label = cleanLabel('label' in raw ? raw.label : undefined);
    } catch {
      label = undefined;
    }
    rows.push(label ? { server, label } : { server });
  }
  return dedupeBy(rows, (item) => item.server).slice(0, MAX_CAPABILITY_SELECTIONS);
}

export function normalizePersistedMessage(message: PersistedMessage): PersistedMessage {
  const skills = persistedSkillReceipts(message.mentioned_skills);
  const mcps = persistedMcpReceipts(message.selected_mcp_connectors)
    .slice(0, MAX_CAPABILITY_SELECTIONS - skills.length);
  return {
    role: message.role,
    content: message.content,
    ...(skills.length > 0 ? { mentioned_skills: skills } : {}),
    ...(mcps.length > 0 ? { selected_mcp_connectors: mcps } : {}),
  };
}

export function optimisticMessageFromFrame(
  frame: Extract<OutboundWsFrame, { type: 'message' }>,
  id: string,
): Message {
  return {
    id,
    role: 'user',
    content: frame.content,
    ...(frame.metadata?.mentioned_skills
      ? { mentioned_skills: frame.metadata.mentioned_skills }
      : {}),
    ...(frame.metadata?.selected_mcp_connectors
      ? { selected_mcp_connectors: frame.metadata.selected_mcp_connectors }
      : {}),
  };
}
