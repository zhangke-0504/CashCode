// REST API wrappers for CashCode backend
import type { Session } from '../types';

const BASE = 'http://127.0.0.1:8000/api';

async function apiRequest<T>(path: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`API ${opts?.method ?? 'GET'} ${path} failed (${res.status}): ${text}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export async function fetchSessions(): Promise<Session[]> {
  const data = await apiRequest<{ sessions: Session[] }>('/sessions');
  return data.sessions;
}

export async function renameSession(chat_id: string, title: string): Promise<void> {
  await apiRequest<void>(`/sessions/${chat_id}`, {
    method: 'PATCH',
    body: JSON.stringify({ title }),
  });
}

export async function deleteSession(chat_id: string): Promise<void> {
  await apiRequest<void>(`/sessions/${chat_id}`, { method: 'DELETE' });
}
