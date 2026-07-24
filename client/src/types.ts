// TypeScript types for CashCode frontend

export interface Session {
  chat_id: string;
  title: string;
  updated_at: string;
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
}

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
