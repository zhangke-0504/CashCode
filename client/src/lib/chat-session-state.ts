import type { Session } from '../types';

export interface SessionStateSlice {
  sessions: Session[];
  activeSessionId: string | null;
  loadedSessionIds: Record<string, boolean>;
}

export function applyLoadedSessions(
  state: SessionStateSlice,
  sessions: Session[],
): SessionStateSlice {
  return {
    ...state,
    sessions,
    activeSessionId: state.activeSessionId ?? sessions[0]?.chat_id ?? null,
  };
}

export function applyReadyDraft(
  state: SessionStateSlice,
  chatId: string,
): SessionStateSlice {
  if (state.activeSessionId) return state;
  return {
    ...state,
    activeSessionId: chatId,
    loadedSessionIds: { ...state.loadedSessionIds, [chatId]: true },
  };
}

export function applyAttachedDraft(
  state: SessionStateSlice,
  chatId: string,
): SessionStateSlice {
  const persisted = state.sessions.some((session) => session.chat_id === chatId);
  return {
    ...state,
    activeSessionId: chatId,
    loadedSessionIds: persisted
      ? state.loadedSessionIds
      : { ...state.loadedSessionIds, [chatId]: true },
  };
}

export function upsertSessionUpdate(
  state: SessionStateSlice,
  session: Session,
): SessionStateSlice {
  const persisted = state.sessions.some((item) => item.chat_id === session.chat_id);
  return {
    sessions: [session, ...state.sessions.filter((item) => item.chat_id !== session.chat_id)],
    activeSessionId: state.activeSessionId ?? session.chat_id,
    loadedSessionIds: persisted
      ? state.loadedSessionIds
      : { ...state.loadedSessionIds, [session.chat_id]: true },
  };
}

export function removeSession(
  state: SessionStateSlice,
  chatId: string,
): SessionStateSlice {
  const sessions = state.sessions.filter((session) => session.chat_id !== chatId);
  const activeSessionId = state.activeSessionId === chatId
    ? (sessions[0]?.chat_id ?? null)
    : state.activeSessionId;
  const { [chatId]: _removed, ...loadedSessionIds } = state.loadedSessionIds;
  return { sessions, activeSessionId, loadedSessionIds };
}
