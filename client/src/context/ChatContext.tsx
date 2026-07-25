import React, {
  createContext,
  useCallback,
  useContext,
  useReducer,
  useRef,
} from 'react';
import { v4 as uuid } from 'uuid';
import type {
  Message,
  OutboundWsFrame,
  Session,
  ToolCallBlock,
  WsConnectionState,
  WsFrame,
} from '../types';
import { useWebSocket } from '../hooks/useWebSocket';
import { fetchSessionMessages, fetchSessions } from '../lib/api';
import {
  applyAttachedDraft,
  applyLoadedSessions,
  applyReadyDraft,
  removeSession,
  upsertSessionUpdate,
} from '../lib/chat-session-state';
import { setChatGenerating, type GenerationByChat } from '../lib/generation-state';
import { normalizePersistedMessage, optimisticMessageFromFrame } from '../lib/selections';

// ---------------------------------------------------------------------------
// State shape
// ---------------------------------------------------------------------------
interface ChatState {
  sessions: Session[];
  activeSessionId: string | null;
  // messages per session: sessionId -> Message[]
  messages: Record<string, Message[]>;
  loadedSessionIds: Record<string, boolean>;
  generatingByChat: GenerationByChat;
  wsState: WsConnectionState;
  error: string | null;
}

const initialState: ChatState = {
  sessions: [],
  activeSessionId: null,
  messages: {},
  loadedSessionIds: {},
  generatingByChat: {},
  wsState: 'connecting',
  error: null,
};

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------
type Action =
  | { type: 'WS_STATE'; state: WsConnectionState }
  | { type: 'SESSIONS_LOADED'; sessions: Session[] }
  | { type: 'SESSION_ADDED'; session: Session }
  | { type: 'SESSION_RENAMED'; chat_id: string; title: string }
  | { type: 'SESSION_DELETED'; chat_id: string }
  | { type: 'SWITCH_SESSION'; chat_id: string }
  | { type: 'MESSAGES_LOADED'; chat_id: string; messages: Message[] }
  | { type: 'WS_READY'; chat_id: string }
  | { type: 'WS_ATTACHED'; chat_id: string }
  | { type: 'WS_SESSION_UPDATED'; session: Session }
  | { type: 'WS_DELTA'; chat_id: string; text: string }
  | { type: 'WS_STREAM_END'; chat_id: string }
  | { type: 'WS_DONE'; chat_id: string }
  | { type: 'WS_TOOL_CALL'; chat_id: string; tool_name: string; stream_id: number }
  | { type: 'WS_TOOL_RESULT'; chat_id: string; tool_name: string; result: string; stream_id: number }
  | { type: 'WS_ERROR'; detail: string; chat_id?: string }
  | { type: 'USER_MESSAGE_SENT'; frame: Extract<OutboundWsFrame, { type: 'message' }> };

function ensureSession(messages: Record<string, Message[]>, id: string) {
  return messages[id] ?? [];
}

function reducer(state: ChatState, action: Action): ChatState {
  switch (action.type) {
    case 'WS_STATE':
      return { ...state, wsState: action.state };

    case 'SESSIONS_LOADED':
      return {
        ...state,
        ...applyLoadedSessions(state, action.sessions),
      };

    case 'SESSION_ADDED': {
      const exists = state.sessions.find((s) => s.chat_id === action.session.chat_id);
      return {
        ...state,
        sessions: exists ? state.sessions : [action.session, ...state.sessions],
        activeSessionId: action.session.chat_id,
        loadedSessionIds: { ...state.loadedSessionIds, [action.session.chat_id]: true },
      };
    }

    case 'SESSION_RENAMED':
      return {
        ...state,
        sessions: state.sessions.map((s) =>
          s.chat_id === action.chat_id ? { ...s, title: action.title } : s
        ),
      };

    case 'SESSION_DELETED': {
      const sessionState = removeSession(state, action.chat_id);
      const { [action.chat_id]: _removed, ...msgs } = state.messages;
      const generatingByChat = setChatGenerating(state.generatingByChat, action.chat_id, false);
      return {
        ...state,
        ...sessionState,
        messages: msgs,
        generatingByChat,
      };
    }

    case 'SWITCH_SESSION':
      return { ...state, activeSessionId: action.chat_id, error: null };

    case 'MESSAGES_LOADED':
      return {
        ...state,
        messages: { ...state.messages, [action.chat_id]: action.messages },
        loadedSessionIds: { ...state.loadedSessionIds, [action.chat_id]: true },
      };

    case 'WS_READY': {
      return {
        ...state,
        ...applyReadyDraft(state, action.chat_id),
      };
    }

    case 'WS_ATTACHED': {
      return {
        ...state,
        ...applyAttachedDraft(state, action.chat_id),
      };
    }

    case 'WS_SESSION_UPDATED':
      return { ...state, ...upsertSessionUpdate(state, action.session) };

    case 'USER_MESSAGE_SENT': {
      const msg = optimisticMessageFromFrame(action.frame, uuid());
      const prev = ensureSession(state.messages, action.frame.chat_id);
      return {
        ...state,
        generatingByChat: setChatGenerating(
          state.generatingByChat,
          action.frame.chat_id,
          true,
        ),
        error: null,
        messages: { ...state.messages, [action.frame.chat_id]: [...prev, msg] },
      };
    }

    case 'WS_DELTA': {
      const prev = ensureSession(state.messages, action.chat_id);
      // find or create streaming assistant message
      const last = prev[prev.length - 1];
      if (last?.role === 'assistant' && last.streaming) {
        const updated = { ...last, content: last.content + action.text };
        return {
          ...state,
          messages: {
            ...state.messages,
            [action.chat_id]: [...prev.slice(0, -1), updated],
          },
        };
      }
      // New streaming assistant message
      const newMsg: Message = {
        id: uuid(),
        role: 'assistant',
        content: action.text,
        streaming: true,
        tool_calls: [],
      };
      return {
        ...state,
        messages: { ...state.messages, [action.chat_id]: [...prev, newMsg] },
      };
    }

    case 'WS_STREAM_END': {
      const prev = ensureSession(state.messages, action.chat_id);
      const updated = prev.map((m) =>
        m.streaming ? { ...m, streaming: false } : m
      );
      return { ...state, messages: { ...state.messages, [action.chat_id]: updated } };
    }

    case 'WS_DONE':
      return {
        ...state,
        generatingByChat: setChatGenerating(state.generatingByChat, action.chat_id, false),
      };

    case 'WS_TOOL_CALL': {
      const prev = ensureSession(state.messages, action.chat_id);
      const last = prev[prev.length - 1];
      const toolBlock: ToolCallBlock = {
        stream_id: action.stream_id,
        tool_name: action.tool_name,
        done: false,
      };
      if (last?.role === 'assistant' && last.streaming) {
        const updated: Message = {
          ...last,
          tool_calls: [...(last.tool_calls ?? []), toolBlock],
        };
        return {
          ...state,
          messages: { ...state.messages, [action.chat_id]: [...prev.slice(0, -1), updated] },
        };
      }
      // Create a new streaming message to hold tool calls
      const newMsg: Message = {
        id: uuid(),
        role: 'assistant',
        content: '',
        streaming: true,
        tool_calls: [toolBlock],
      };
      return {
        ...state,
        messages: { ...state.messages, [action.chat_id]: [...prev, newMsg] },
      };
    }

    case 'WS_TOOL_RESULT': {
      const prev = ensureSession(state.messages, action.chat_id);
      const updated = prev.map((m) => {
        if (!m.tool_calls) return m;
        return {
          ...m,
          tool_calls: m.tool_calls.map((tc) =>
            tc.stream_id === action.stream_id
              ? { ...tc, result: action.result, done: true }
              : tc
          ),
        };
      });
      return { ...state, messages: { ...state.messages, [action.chat_id]: updated } };
    }

    case 'WS_ERROR': {
      const chatId = action.chat_id ?? state.activeSessionId;
      return {
        ...state,
        error: action.detail,
        generatingByChat: chatId
          ? setChatGenerating(state.generatingByChat, chatId, false)
          : state.generatingByChat,
      };
    }

    default:
      return state;
  }
}

// ---------------------------------------------------------------------------
// Context
// ---------------------------------------------------------------------------
interface ChatContextValue {
  state: ChatState;
  send: (frame: OutboundWsFrame) => boolean;
  dispatch: React.Dispatch<Action>;
  reloadSessions: () => Promise<void>;
}

const ChatContext = createContext<ChatContextValue | null>(null);

export function ChatProvider({ children }: { children: React.ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initialState);
  const stateRef = useRef(state);
  stateRef.current = state;

  const handleFrame = useCallback((frame: unknown) => {
    const f = frame as WsFrame;
    switch (f.event) {
      case 'ready':
        dispatch({ type: 'WS_READY', chat_id: f.chat_id });
        break;
      case 'attached':
        dispatch({ type: 'WS_ATTACHED', chat_id: f.chat_id });
        break;
      case 'session_updated':
        dispatch({
          type: 'WS_SESSION_UPDATED',
          session: {
            chat_id: f.chat_id,
            title: f.title,
            updated_at: f.updated_at,
          },
        });
        break;
      case 'delta':
        dispatch({ type: 'WS_DELTA', chat_id: f.chat_id, text: f.text });
        break;
      case 'stream_end':
        dispatch({ type: 'WS_STREAM_END', chat_id: f.chat_id });
        break;
      case 'done':
        dispatch({ type: 'WS_DONE', chat_id: f.chat_id });
        break;
      case 'tool_call':
        dispatch({ type: 'WS_TOOL_CALL', chat_id: f.chat_id, tool_name: f.tool_name, stream_id: f.stream_id });
        break;
      case 'tool_result':
        dispatch({ type: 'WS_TOOL_RESULT', chat_id: f.chat_id, tool_name: f.tool_name, result: f.result, stream_id: f.stream_id });
        break;
      case 'error':
        dispatch({ type: 'WS_ERROR', detail: f.detail, chat_id: f.chat_id });
        break;
    }
  }, []);

  const { state: wsState, send } = useWebSocket(handleFrame);

  // Keep wsState in sync
  React.useEffect(() => {
    dispatch({ type: 'WS_STATE', state: wsState });
  }, [wsState]);

  // Load sessions from REST API on mount
  const reloadSessions = useCallback(async () => {
    try {
      const sessions = await fetchSessions();
      dispatch({ type: 'SESSIONS_LOADED', sessions });
    } catch (e) {
      console.error('Failed to load sessions', e);
    }
  }, []);

  React.useEffect(() => {
    reloadSessions();
  }, [reloadSessions]);

  // Load persisted history for the active session once. The cancellation flag
  // prevents an obsolete request from committing after the session changed.
  React.useEffect(() => {
    const chatId = state.activeSessionId;
    if (!chatId || state.loadedSessionIds[chatId]) return;

    let cancelled = false;
    fetchSessionMessages(chatId)
      .then((messages) => {
        if (cancelled) return;
        dispatch({
          type: 'MESSAGES_LOADED',
          chat_id: chatId,
          messages: messages.map((message) => ({ ...normalizePersistedMessage(message), id: uuid() })),
        });
      })
      .catch((e) => {
        if (!cancelled) console.error('Failed to load session messages', e);
      });

    return () => {
      cancelled = true;
    };
  }, [state.activeSessionId, state.loadedSessionIds]);

  return (
    <ChatContext.Provider value={{ state, send, dispatch, reloadSessions }}>
      {children}
    </ChatContext.Provider>
  );
}

// oxlint-disable-next-line react/only-export-components
export function useChatContext() {
  const ctx = useContext(ChatContext);
  if (!ctx) throw new Error('useChatContext must be used within ChatProvider');
  return ctx;
}
