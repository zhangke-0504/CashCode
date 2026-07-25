// REST API wrappers for CashCode backend
import type {
  McpServer,
  McpServerCreate,
  McpServerUpdate,
  McpToolsResponse,
  PersistedMessage,
  Session,
  SkillContent,
  SkillListParams,
  SkillListResponse,
  SkillReplaceRequest,
  SkillSummary,
} from '../types';

const BASE = 'http://127.0.0.1:8000/api';

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;
  readonly method: string;
  readonly path: string;

  constructor(status: number, detail: string, method: string, path: string) {
    super(detail);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
    this.method = method;
    this.path = path;
  }
}

function formatApiDetail(value: unknown): string | null {
  if (typeof value === 'string' && value.trim()) return value.trim();
  if (Array.isArray(value)) {
    const details = value
      .map((item) => {
        if (!item || typeof item !== 'object') return null;
        const message = 'msg' in item ? item.msg : null;
        const location = 'loc' in item && Array.isArray(item.loc) ? item.loc.join('.') : null;
        return typeof message === 'string' ? `${location ? `${location}: ` : ''}${message}` : null;
      })
      .filter((item): item is string => Boolean(item));
    return details.length > 0 ? details.join('; ') : null;
  }
  return null;
}

async function readErrorDetail(response: Response): Promise<string> {
  const fallback = response.statusText || `请求失败 (${response.status})`;
  const contentType = response.headers.get('content-type') ?? '';
  if (contentType.includes('application/json')) {
    const body = await response.json().catch(() => null) as { detail?: unknown } | null;
    return formatApiDetail(body?.detail) ?? fallback;
  }
  const text = await response.text().catch(() => '');
  return text.trim() || fallback;
}

export function buildApiRequestInit(opts?: RequestInit): RequestInit {
  const headers = new Headers(opts?.headers);
  const isFormData = typeof FormData !== 'undefined' && opts?.body instanceof FormData;
  if (!isFormData && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }
  return { ...opts, headers };
}

async function apiRequest<T>(path: string, opts?: RequestInit): Promise<T> {
  const method = opts?.method ?? 'GET';
  const res = await fetch(`${BASE}${path}`, buildApiRequestInit(opts));
  if (!res.ok) {
    throw new ApiError(res.status, await readErrorDetail(res), method, path);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export async function fetchSessions(): Promise<Session[]> {
  const data = await apiRequest<{ sessions: Session[] }>('/sessions');
  return data.sessions;
}

export async function fetchSessionMessages(chat_id: string): Promise<PersistedMessage[]> {
  const data = await apiRequest<{ messages: PersistedMessage[] }>(
    `/sessions/${encodeURIComponent(chat_id)}/messages`
  );
  return data.messages;
}

export async function renameSession(chat_id: string, title: string): Promise<void> {
  await apiRequest<void>(`/sessions/${chat_id}`, {
    method: 'PATCH',
    body: JSON.stringify({ title }),
  });
}

export async function deleteSession(chat_id: string): Promise<void> {
  await apiRequest<void>(`/sessions/${encodeURIComponent(chat_id)}`, { method: 'DELETE' });
}

export async function fetchMcpServers(): Promise<McpServer[]> {
  const data = await apiRequest<{ servers: McpServer[] }>('/mcp/servers');
  return data.servers;
}

export function createMcpServer(payload: McpServerCreate): Promise<McpServer> {
  return apiRequest<McpServer>('/mcp/servers', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function updateMcpServer(name: string, payload: McpServerUpdate): Promise<McpServer> {
  return apiRequest<McpServer>(`/mcp/servers/${encodeURIComponent(name)}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}

export function deleteMcpServer(name: string): Promise<void> {
  return apiRequest<void>(`/mcp/servers/${encodeURIComponent(name)}`, { method: 'DELETE' });
}

export function connectMcpServer(name: string): Promise<McpServer> {
  return apiRequest<McpServer>(`/mcp/servers/${encodeURIComponent(name)}/connect`, {
    method: 'POST',
  });
}

export function disconnectMcpServer(name: string): Promise<McpServer> {
  return apiRequest<McpServer>(`/mcp/servers/${encodeURIComponent(name)}/disconnect`, {
    method: 'POST',
  });
}

export function fetchMcpServerTools(name: string): Promise<McpToolsResponse> {
  return apiRequest<McpToolsResponse>(`/mcp/servers/${encodeURIComponent(name)}/tools`);
}

export async function fetchSelectableSkills(): Promise<SkillSummary[]> {
  const data = await fetchSkills({ enabled: true, availability: 'available', page_size: 200 });
  return data.items.filter((skill) => skill.enabled && skill.availability === 'available');
}

export function buildSkillsQuery(params: SkillListParams = {}): string {
  const query = new URLSearchParams();
  if (params.source) query.set('source', params.source);
  if (params.enabled !== undefined) query.set('enabled', String(params.enabled));
  if (params.availability) query.set('availability', params.availability);
  if (params.query?.trim()) query.set('query', params.query.trim());
  if (params.page !== undefined) query.set('page', String(params.page));
  if (params.page_size !== undefined) query.set('page_size', String(params.page_size));
  const value = query.toString();
  return value ? `?${value}` : '';
}

export function fetchSkills(params: SkillListParams = {}): Promise<SkillListResponse> {
  return apiRequest<SkillListResponse>(`/skills${buildSkillsQuery(params)}`);
}

export function fetchSkillContent(name: string): Promise<SkillContent> {
  return apiRequest<SkillContent>(`/skills/${encodeURIComponent(name)}/content`);
}

export function importSkill(file: File): Promise<SkillSummary> {
  const body = new FormData();
  body.append('file', file);
  return apiRequest<SkillSummary>('/skills/import', { method: 'POST', body });
}

export function updateSkill(name: string, payload: SkillReplaceRequest): Promise<SkillSummary> {
  return apiRequest<SkillSummary>(`/skills/${encodeURIComponent(name)}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}

export function setSkillEnabled(name: string, enabled: boolean): Promise<SkillSummary> {
  return apiRequest<SkillSummary>(`/skills/${encodeURIComponent(name)}/enabled`, {
    method: 'PATCH',
    body: JSON.stringify({ enabled }),
  });
}

export function deleteSkill(name: string): Promise<void> {
  return apiRequest<void>(`/skills/${encodeURIComponent(name)}`, { method: 'DELETE' });
}

export function deleteInvalidSkill(
  source: SkillSummary['source'],
  directory: string,
): Promise<{ source: string; directory: string; snapshot: string }> {
  return apiRequest(buildInvalidSkillDeletePath(source, directory), { method: 'DELETE' });
}

export function buildInvalidSkillDeletePath(
  source: SkillSummary['source'],
  directory: string,
): string {
  return `/skills/invalid/${encodeURIComponent(source)}/${encodeURIComponent(directory)}`;
}

export interface SelectableMcpServer extends McpServer {
  tools: McpToolsResponse['tools'];
}

export async function fetchSelectableMcpServers(): Promise<SelectableMcpServer[]> {
  const connected = (await fetchMcpServers()).filter(
    (server) => server.connected && server.status === 'connected' && server.tool_count > 0
  );
  const withTools = await Promise.all(
    connected.map(async (server) => ({
      ...server,
      tools: (await fetchMcpServerTools(server.name)).tools,
    }))
  );
  return withTools.filter((server) => server.tools.some((tool) => tool.callable));
}
