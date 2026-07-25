// Sidebar: primary navigation and collapsible session history
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  BrainCircuit,
  ChevronDown,
  History,
  MessageSquare,
  MoreHorizontal,
  Network,
  Pencil,
  Plus,
  Settings,
  Trash2,
  Zap,
} from 'lucide-react';
import { useChatContext } from '../context/ChatContext';
import { renameSession, deleteSession } from '../lib/api';
import type { AppView } from '../types';

interface SidebarProps {
  activeView: AppView;
  mobileOpen: boolean;
  onCloseMobile: () => void;
  onViewChange: (view: AppView) => void;
}

function relativeTime(value: string): string {
  const timestamp = new Date(value).getTime();
  if (!Number.isFinite(timestamp)) return '';
  const seconds = Math.max(0, Math.round((Date.now() - timestamp) / 1000));
  if (seconds < 60) return '刚刚';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} 分钟前`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} 小时前`;
  const days = Math.floor(hours / 24);
  return days < 30 ? `${days} 天前` : new Date(value).toLocaleDateString('zh-CN');
}

export function Sidebar({ activeView, mobileOpen, onCloseMobile, onViewChange }: SidebarProps) {
  const { state, send, dispatch, reloadSessions } = useChatContext();
  const { sessions, activeSessionId } = state;
  const [menuOpenFor, setMenuOpenFor] = useState<string | null>(null);
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState('');
  const [historyExpanded, setHistoryExpanded] = useState(true);
  const [settingsMenuOpen, setSettingsMenuOpen] = useState(false);
  const renameInputRef = useRef<HTMLInputElement>(null);
  const settingsMenuRef = useRef<HTMLDivElement>(null);

  // Close menu when clicking outside
  useEffect(() => {
    const handler = () => setMenuOpenFor(null);
    document.addEventListener('click', handler);
    return () => document.removeEventListener('click', handler);
  }, []);

  useEffect(() => {
    const closeOnOutside = (event: MouseEvent) => {
      if (!settingsMenuRef.current?.contains(event.target as Node)) setSettingsMenuOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setSettingsMenuOpen(false);
    };
    document.addEventListener('mousedown', closeOnOutside);
    document.addEventListener('keydown', closeOnEscape);
    return () => {
      document.removeEventListener('mousedown', closeOnOutside);
      document.removeEventListener('keydown', closeOnEscape);
    };
  }, []);

  // Focus rename input when it appears
  useEffect(() => {
    if (renamingId) renameInputRef.current?.focus();
  }, [renamingId]);

  const handleNewChat = () => {
    onViewChange('chat');
    send({ type: 'new_chat' });
  };

  const handleSelectSession = (chat_id: string) => {
    onViewChange('chat');
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
    <>
      {mobileOpen && (
        <button
          type="button"
          className="absolute inset-0 z-30 bg-black/65 sm:hidden"
          onClick={onCloseMobile}
          aria-label="关闭导航"
        />
      )}
      <aside className={`absolute inset-y-0 left-0 z-40 flex h-full w-64 shrink-0 flex-col border-r border-zinc-800 bg-[#111111] transition-transform sm:static sm:translate-x-0 ${mobileOpen ? 'translate-x-0' : '-translate-x-full'}`}>
      <div className="p-3 space-y-1">
        <button
          onClick={handleNewChat}
          className="w-full flex items-center gap-2 px-3 py-2 rounded-md text-sm text-zinc-200 hover:bg-zinc-800 transition-colors"
        >
          <Plus className="w-4 h-4" />
          新建对话
        </button>
        <button
          onClick={() => onViewChange('mcp-market')}
          aria-current={activeView === 'mcp-market' ? 'page' : undefined}
          className={`w-full flex items-center gap-2 px-3 py-2 rounded-md text-sm transition-colors ${
            activeView === 'mcp-market'
              ? 'bg-zinc-800 text-zinc-100'
              : 'text-zinc-300 hover:bg-zinc-800'
          }`}
        >
          <Network className="w-4 h-4" />
          MCP 市场
        </button>
        <button
          onClick={() => onViewChange('skill-market')}
          aria-current={activeView === 'skill-market' ? 'page' : undefined}
          className={`w-full flex items-center gap-2 px-3 py-2 rounded-md text-sm transition-colors ${
            activeView === 'skill-market'
              ? 'bg-zinc-800 text-zinc-100'
              : 'text-zinc-300 hover:bg-zinc-800'
          }`}
        >
          <Zap className="w-4 h-4" />
          Skill 市场
        </button>
      </div>

      <div className="mx-3 border-t border-zinc-800" />
      <div className="flex min-h-0 flex-1 flex-col">
      <button
        type="button"
        className="mx-2 mt-2 flex items-center gap-2 px-3 py-2 rounded-md text-xs font-medium text-zinc-500 hover:bg-zinc-800/70 hover:text-zinc-300 transition-colors"
        aria-expanded={historyExpanded}
        aria-controls="sidebar-history"
        onClick={() => setHistoryExpanded((value) => !value)}
      >
        <History className="w-3.5 h-3.5" />
        <span>历史记录</span>
        <ChevronDown
          className={`ml-auto w-3.5 h-3.5 transition-transform ${historyExpanded ? '' : '-rotate-90'}`}
        />
      </button>

      <nav
        id="sidebar-history"
        aria-label="历史记录"
        hidden={!historyExpanded}
        className="min-h-0 flex-1 overflow-y-auto px-2 pb-2"
      >
        {sessions.length === 0 ? (
          <p className="text-xs text-zinc-600 px-2 py-4 text-center">暂无会话</p>
        ) : sessions.map((session) => (
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
              <span className="flex-1 min-w-0 ml-2 py-2 pr-7">
                <span className="block text-sm truncate">{session.title}</span>
                <span className="block mt-0.5 text-[11px] text-zinc-600 truncate">
                  {relativeTime(session.updated_at)}
                </span>
              </span>
            )}

            {/* Context menu trigger */}
            {renamingId !== session.chat_id && (
              <button
                className="absolute right-1 opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-zinc-700 transition-all"
                onClick={(e) => openMenu(e, session.chat_id)}
                aria-label={`管理会话 ${session.title}`}
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
      </div>
      <div ref={settingsMenuRef} className="relative border-t border-zinc-800 p-2">
        {settingsMenuOpen && (
          <div id="sidebar-settings-menu" role="menu" className="absolute bottom-full left-2 right-2 z-50 mb-1 rounded-md border border-zinc-700 bg-zinc-900 py-1 shadow-xl">
            <button
              type="button"
              role="menuitem"
              onClick={() => {
                setSettingsMenuOpen(false);
                onViewChange('llm-settings');
              }}
              className={`flex w-full items-center gap-2 px-3 py-2 text-left text-sm transition-colors ${activeView === 'llm-settings' ? 'bg-zinc-800 text-zinc-100' : 'text-zinc-300 hover:bg-zinc-800'}`}
            >
              <BrainCircuit className="h-4 w-4" />
              LLM 设置
            </button>
          </div>
        )}
        <button
          type="button"
          aria-haspopup="menu"
          aria-expanded={settingsMenuOpen}
          aria-controls="sidebar-settings-menu"
          onClick={(event) => {
            event.stopPropagation();
            setSettingsMenuOpen((open) => !open);
          }}
          className={`flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors ${activeView === 'llm-settings' ? 'bg-zinc-800 text-zinc-100' : 'text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200'}`}
        >
          <Settings className="h-4 w-4" />
          设置
          <ChevronDown className={`ml-auto h-3.5 w-3.5 transition-transform ${settingsMenuOpen ? 'rotate-180' : ''}`} />
        </button>
      </div>
      </aside>
    </>
  );
}
