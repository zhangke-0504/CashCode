// Sidebar: session list with new, rename, delete
import { useCallback, useEffect, useRef, useState } from 'react';
import { MessageSquare, MoreHorizontal, Plus, Pencil, Trash2 } from 'lucide-react';
import { useChatContext } from '../context/ChatContext';
import { renameSession, deleteSession } from '../lib/api';

export function Sidebar() {
  const { state, send, dispatch, reloadSessions } = useChatContext();
  const { sessions, activeSessionId } = state;
  const [menuOpenFor, setMenuOpenFor] = useState<string | null>(null);
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState('');
  const renameInputRef = useRef<HTMLInputElement>(null);

  // Close menu when clicking outside
  useEffect(() => {
    const handler = () => setMenuOpenFor(null);
    document.addEventListener('click', handler);
    return () => document.removeEventListener('click', handler);
  }, []);

  // Focus rename input when it appears
  useEffect(() => {
    if (renamingId) renameInputRef.current?.focus();
  }, [renamingId]);

  const handleNewChat = () => {
    send({ type: 'new_chat' });
  };

  const handleSelectSession = (chat_id: string) => {
    if (chat_id === activeSessionId) return;
    dispatch({ type: 'SWITCH_SESSION', chat_id });
    send({ type: 'attach', chat_id });
  };

  const openMenu = (e: React.MouseEvent, chat_id: string) => {
    e.stopPropagation();
    setMenuOpenFor((prev) => (prev === chat_id ? null : chat_id));
  };

  const startRename = (chat_id: string, currentTitle: string) => {
    setMenuOpenFor(null);
    setRenamingId(chat_id);
    setRenameValue(currentTitle);
  };

  const commitRename = async (chat_id: string) => {
    const trimmed = renameValue.trim();
    setRenamingId(null);
    if (!trimmed) return;
    try {
      await renameSession(chat_id, trimmed);
      dispatch({ type: 'SESSION_RENAMED', chat_id, title: trimmed });
    } catch (e) {
      console.error('Rename failed', e);
    }
  };

  const handleDelete = useCallback(async (chat_id: string) => {
    setMenuOpenFor(null);
    if (!window.confirm('确认删除这个会话吗？该操作无法撤销。')) return;
    try {
      await deleteSession(chat_id);
      dispatch({ type: 'SESSION_DELETED', chat_id });
      await reloadSessions();
    } catch (e) {
      console.error('Delete failed', e);
    }
  }, [dispatch, reloadSessions]);

  return (
    <aside className="flex flex-col w-60 shrink-0 bg-[#111111] border-r border-zinc-800 h-full">
      {/* New chat button */}
      <div className="p-3">
        <button
          onClick={handleNewChat}
          className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-zinc-300 hover:bg-zinc-800 transition-colors"
        >
          <Plus className="w-4 h-4" />
          新对话
        </button>
      </div>

      {/* Session list */}
      <nav className="flex-1 overflow-y-auto px-2 pb-2">
        {sessions.length === 0 && (
          <p className="text-xs text-zinc-600 px-2 py-4 text-center">暂无会话</p>
        )}
        {sessions.map((session) => (
          <div
            key={session.chat_id}
            className={`group relative flex items-center rounded-lg mb-0.5 cursor-pointer transition-colors ${
              activeSessionId === session.chat_id
                ? 'bg-zinc-800 text-zinc-100'
                : 'text-zinc-400 hover:bg-zinc-800/60 hover:text-zinc-200'
            }`}
            onClick={() => handleSelectSession(session.chat_id)}
          >
            <MessageSquare className="w-3.5 h-3.5 ml-3 shrink-0 opacity-60" />

            {renamingId === session.chat_id ? (
              <input
                ref={renameInputRef}
                className="flex-1 ml-2 mr-1 py-2 bg-transparent text-sm text-zinc-100 outline-none border-b border-zinc-500"
                value={renameValue}
                onChange={(e) => setRenameValue(e.target.value)}
                onBlur={() => commitRename(session.chat_id)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') commitRename(session.chat_id);
                  if (e.key === 'Escape') setRenamingId(null);
                }}
                onClick={(e) => e.stopPropagation()}
              />
            ) : (
              <span className="flex-1 ml-2 py-2 pr-6 text-sm truncate">
                {session.title}
              </span>
            )}

            {/* Context menu trigger */}
            {renamingId !== session.chat_id && (
              <button
                className="absolute right-1 opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-zinc-700 transition-all"
                onClick={(e) => openMenu(e, session.chat_id)}
              >
                <MoreHorizontal className="w-3.5 h-3.5" />
              </button>
            )}

            {/* Dropdown menu */}
            {menuOpenFor === session.chat_id && (
              <div
                className="absolute right-0 top-full mt-0.5 z-50 w-32 bg-zinc-900 border border-zinc-700 rounded-lg shadow-xl py-1"
                onClick={(e) => e.stopPropagation()}
              >
                <button
                  className="w-full flex items-center gap-2 px-3 py-1.5 text-sm text-zinc-300 hover:bg-zinc-800 transition-colors"
                  onClick={() => startRename(session.chat_id, session.title)}
                >
                  <Pencil className="w-3.5 h-3.5" />
                  重命名
                </button>
                <button
                  className="w-full flex items-center gap-2 px-3 py-1.5 text-sm text-red-400 hover:bg-zinc-800 transition-colors"
                  onClick={() => handleDelete(session.chat_id)}
                >
                  <Trash2 className="w-3.5 h-3.5" />
                  删除
                </button>
              </div>
            )}
          </div>
        ))}
      </nav>
    </aside>
  );
}
