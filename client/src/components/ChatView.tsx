// ChatView: main chat area with messages and composer
import { useEffect, useRef, useState } from 'react';
import { ArrowDown } from 'lucide-react';
import { useChatContext } from '../context/ChatContext';
import { MessageBubble } from './MessageBubble';
import { Composer } from './Composer';

export function ChatView() {
  const { state } = useChatContext();
  const { activeSessionId, messages } = state;

  const activeMessages = activeSessionId ? (messages[activeSessionId] ?? []) : [];
  const bottomRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const [showScrollBtn, setShowScrollBtn] = useState(false);
  const userScrolledUp = useRef(false);

  // Auto-scroll to bottom when new content arrives
  useEffect(() => {
    if (!userScrolledUp.current) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [activeMessages]);

  // Detect manual scroll
  const handleScroll = () => {
    const el = scrollContainerRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    userScrolledUp.current = !atBottom;
    setShowScrollBtn(!atBottom);
  };

  const scrollToBottom = () => {
    userScrolledUp.current = false;
    setShowScrollBtn(false);
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  // Reset scroll state when switching sessions
  useEffect(() => {
    userScrolledUp.current = false;
    setShowScrollBtn(false);
  }, [activeSessionId]);

  // Empty state
  if (activeMessages.length === 0) {
    return (
      <div className="flex-1 flex flex-col">
        <div className="flex-1 flex flex-col items-center justify-center gap-6 pb-16">
          <img src="/CashMe.png" alt="CashCode" className="w-40 h-40 object-contain opacity-90" />
          <div className="text-center">
            <h2 className="text-lg font-semibold text-zinc-200">你好，我是 CashCode</h2>
            <p className="text-sm text-zinc-500 mt-1">有什么我可以帮你的？</p>
          </div>
        </div>
        <Composer />
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Messages */}
      <div
        ref={scrollContainerRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto py-4"
      >
        {activeMessages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Scroll to bottom button */}
      {showScrollBtn && (
        <button
          onClick={scrollToBottom}
          className="absolute bottom-24 right-6 flex items-center gap-1.5 px-3 py-1.5 bg-zinc-800 border border-zinc-700 rounded-full text-xs text-zinc-300 hover:bg-zinc-700 shadow-lg transition-colors z-10"
        >
          <ArrowDown className="w-3.5 h-3.5" />
          跳到最新
        </button>
      )}

      <Composer />
    </div>
  );
}
