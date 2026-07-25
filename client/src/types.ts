// TypeScript types for CashCode frontend

export interface Session {
  chat_id: string;
  title: string;
  updated_at: string;
}

export const APP_VIEWS = ['chat', 'mcp-market', 'skill-market', 'llm-settings'] as const;
export type AppView = (typeof APP_VIEWS)[number];

export type LlmProvider = 'openai_compatible' | 'ollama';

export interface LlmSelection {
  provider: LlmProvider;
  model: string;
}

export interface OpenAICompatibleSettings {
  base_url: string;
  ready: boolean;
  api_key_configured: boolean;
}

export interface OllamaSettings {
  base_url: string;
  ready: boolean;
}

export interface LlmSettings {
  configured: boolean;
  openai_compatible: OpenAICompatibleSettings;
  ollama: OllamaSettings;
}

export interface OpenAICompatibleSettingsInput {
  base_url: string;
  api_key?: string;
  clear_api_key: boolean;
}

export interface OllamaSettingsInput {
  base_url: string;
}

export interface LlmSettingsUpdate {
  openai_compatible: OpenAICompatibleSettingsInput;
  ollama: OllamaSettingsInput;
}

export interface LlmConnectionTestRequest {
  provider: LlmProvider;
  openai_compatible: OpenAICompatibleSettingsInput;
  ollama: OllamaSettingsInput;
}

export interface LlmConnectionTestResult {
  success: boolean;
  provider: LlmProvider;
  model_count: number;
  message: string;
}

export interface LlmModelRecord {
  provider: LlmProvider;
  id: string;
}

export interface LlmModelProviderState {
  ready: boolean;
  error: string | null;
}

export interface LlmModelsResponse {
  models: Array<{ provider: LlmProvider; id: string }>;
  providers: Record<LlmProvider, LlmModelProviderState>;
}

export type McpLifecycleStatus = 'disconnected' | 'connecting' | 'connected' | 'error';
export type McpTransport = 'sse' | 'stdio';

export interface McpServer {
  name: string;
  display_name: string;
  description: string;
  type: McpTransport;
  url: string;
  headers: Record<string, string>;
  builtin: boolean;
  mutable: boolean;
  status: McpLifecycleStatus;
  connected: boolean;
  status_error: string | null;
  tool_count: number;
}

export interface McpServerCreate {
  name: string;
  type: 'sse';
  display_name: string;
  description: string;
  url: string;
  headers: Record<string, string>;
}

export type McpServerUpdate = Omit<McpServerCreate, 'name'>;

export interface McpTool {
  name: string;
  original_name: string;
  description: string;
  input_schema: Record<string, unknown>;
  source: 'live' | 'cache';
  callable: boolean;
}

export interface McpToolsResponse {
  server: string;
  display_name: string;
  tools: McpTool[];
  source: 'live' | 'cache' | 'none';
  status: McpLifecycleStatus;
  connected: boolean;
  status_error: string | null;
  tool_count: number;
}

export interface SkillSummary {
  name: string;
  display_name: string;
  description: string;
  version: number;
  tags: string[];
  triggers: string[];
  always: boolean;
  source: 'builtin' | 'user' | 'agent';
  enabled: boolean;
  availability: 'available' | 'missing_dependency' | 'disabled' | 'invalid';
  missing: string[];
  mutable: boolean;
  hash: string;
  shadowed_sources: string[];
  validation_errors: string[];
  requires: SkillDependencies;
  optional: SkillDependencies;
}

export interface SkillDependencies {
  tools: string[];
  mcp_servers: string[];
  bins: string[];
  env: string[];
}

export interface SkillListResponse {
  items: SkillSummary[];
  total: number;
  page: number;
  page_size: number;
  invalid: Record<string, string[]>;
}

export interface SkillInvalidDiagnostic {
  key: string;
  source: SkillSummary['source'];
  directory: string;
  errors: string[];
  selectable: false;
  manageable: false;
}

export interface SkillListParams {
  source?: SkillSummary['source'];
  enabled?: boolean;
  availability?: SkillSummary['availability'];
  query?: string;
  page?: number;
  page_size?: number;
}

export interface SkillContent {
  name: string;
  display_name: string;
  content: string;
  hash: string;
  source: SkillSummary['source'];
  mutable: boolean;
}

export interface SkillReplaceRequest {
  content: string;
  expected_hash: string;
}

export interface SkillSelectionReceipt {
  name: string;
  label?: string;
}

export interface McpSelectionReceipt {
  server: string;
  label?: string;
}

export interface CapabilitySelections {
  mentioned_skills?: SkillSelectionReceipt[];
  selected_mcp_connectors?: McpSelectionReceipt[];
  llm?: LlmSelection;
}

export interface ToolCallBlock {
  stream_id: number;
  tool_name: string;
  result?: string;
  done: boolean;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  streaming?: boolean;
  tool_calls?: ToolCallBlock[];
  mentioned_skills?: SkillSelectionReceipt[];
  selected_mcp_connectors?: McpSelectionReceipt[];
}

export interface PersistedMessage {
  role: 'user' | 'assistant';
  content: string;
  mentioned_skills?: SkillSelectionReceipt[];
  selected_mcp_connectors?: McpSelectionReceipt[];
}

export type OutboundWsFrame =
  | { type: 'new_chat' }
  | { type: 'attach'; chat_id: string }
  | { type: 'cancel'; chat_id: string }
  | { type: 'message'; chat_id: string; content: string; metadata: CapabilitySelections & { llm: LlmSelection } };

export type WsConnectionState = 'connecting' | 'connected' | 'disconnected' | 'error';

export type WsFrame =
  | { event: 'ready'; chat_id: string; client_id: string }
  | { event: 'attached'; chat_id: string }
  | { event: 'delta'; chat_id: string; text: string; stream_id: number }
  | { event: 'stream_end'; chat_id: string; stream_id: number }
  | { event: 'done'; chat_id: string; duration_sec: number }
  | { event: 'tool_call'; chat_id: string; tool_name: string; stream_id: number }
  | { event: 'tool_result'; chat_id: string; tool_name: string; result: string; stream_id: number }
  | { event: 'error'; detail: string; chat_id?: string }
  | { event: 'pong' }
  | { event: 'stop_ack'; chat_id: string }
  | { event: 'message'; chat_id: string; text: string };
