// Composer: text input with send/stop controls
import { useEffect, useRef, useState } from 'react';
import { Send, Square } from 'lucide-react';
import { useChatContext } from '../context/ChatContext';

export function Composer() {
  const { state, send, dispatch } = useChatContext();
  const { activeSessionId, streaming } = state;
  const [text, setText] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-focus when session switches
  useEffect(() => {
    textareaRef.current?.focus();
  }, [activeSessionId]);

  // Auto-resize textarea
  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = 'auto';
    ta.style.height = `${Math.min(ta.scrollHeight, 200)}px`;
  }, [text]);

  const handleSubmit = () => {
    const trimmed = text.trim();
    if (!trimmed || !activeSessionId || streaming) return;
    dispatch({ type: 'USER_MESSAGE_SENT', chat_id: activeSessionId, content: trimmed });
    send({ type: 'message', chat_id: activeSessionId, content: trimmed });
    setText('');
  };

  const handleStop = () => {
    if (!activeSessionId) return;
    send({ type: 'cancel', chat_id: activeSessionId });
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="shrink-0 px-4 pb-4 pt-2">
      <div className="flex items-end gap-2 bg-zinc-900 border border-zinc-700 rounded-2xl px-4 py-3 focus-within:border-zinc-500 transition-colors">
        <textarea
          ref={textareaRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="输入消息… (Enter 发送，Shift+Enter 换行)"
          disabled={streaming}
          rows={1}
          className="flex-1 bg-transparent text-sm text-zinc-200 placeholder-zinc-600 resize-none outline-none leading-relaxed disabled:opacity-50"
          style={{ minHeight: '24px', maxHeight: '200px' }}
        />
        {streaming ? (
          <button
            onClick={handleStop}
            className="shrink-0 flex items-center justify-center w-8 h-8 rounded-lg bg-red-500/20 hover:bg-red-500/30 text-red-400 transition-colors"
            title="停止生成"
          >
            <Square className="w-3.5 h-3.5 fill-current" />
          </button>
        ) : (
          <button
            onClick={handleSubmit}
            disabled={!text.trim() || !activeSessionId}
            className="shrink-0 flex items-center justify-center w-8 h-8 rounded-lg bg-zinc-700 hover:bg-zinc-600 text-zinc-300 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            title="发送 (Enter)"
          >
            <Send className="w-3.5 h-3.5" />
          </button>
        )}
      </div>
    </div>
  );
}
