// MessageBubble: renders user or assistant messages
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Check, Copy } from 'lucide-react';
import { useState } from 'react';
import type { Message } from '../types';
import { ToolProgressBlock } from './ToolProgressBlock';

interface MessageBubbleProps {
  message: Message;
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <button
      onClick={copy}
      className="absolute top-2 right-2 p-1.5 rounded bg-zinc-700/70 hover:bg-zinc-600 text-zinc-300 opacity-0 group-hover/code:opacity-100 transition-opacity"
    >
      {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
    </button>
  );
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === 'user';

  if (isUser) {
    return (
      <div className="flex justify-end px-4 py-1">
        <div className="max-w-[75%] bg-zinc-700 text-zinc-100 px-4 py-2.5 rounded-2xl rounded-tr-sm text-sm leading-relaxed whitespace-pre-wrap">
          {message.content}
        </div>
      </div>
    );
  }

  // Assistant message
  return (
    <div className="flex flex-col px-4 py-1 gap-1">
      {/* Tool call blocks */}
      {message.tool_calls && message.tool_calls.length > 0 && (
        <div className="flex flex-col gap-1 mb-1">
          {message.tool_calls.map((tc) => (
            <ToolProgressBlock key={tc.stream_id} block={tc} />
          ))}
        </div>
      )}

      {/* Assistant text */}
      {(message.content || message.streaming) && (
        <div className="prose prose-invert prose-sm max-w-none text-zinc-200">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              code({ className, children, ...props }) {
                const isBlock = /language-/.test(className ?? '');
                const codeStr = String(children).replace(/\n$/, '');
                if (isBlock) {
                  return (
                    <div className="relative group/code my-3">
                      <pre className="bg-zinc-900 border border-zinc-700 rounded-lg p-4 overflow-x-auto text-xs">
                        <code className={className} {...props}>{children}</code>
                      </pre>
                      <CopyButton text={codeStr} />
                    </div>
                  );
                }
                return (
                  <code className="bg-zinc-800 text-zinc-200 px-1.5 py-0.5 rounded text-xs font-mono" {...props}>
                    {children}
                  </code>
                );
              },
              table({ children }) {
                return (
                  <div className="overflow-x-auto my-3">
                    <table className="border-collapse border border-zinc-700 text-xs">{children}</table>
                  </div>
                );
              },
              th({ children }) {
                return <th className="border border-zinc-700 px-3 py-1.5 bg-zinc-800 text-left">{children}</th>;
              },
              td({ children }) {
                return <td className="border border-zinc-700 px-3 py-1.5">{children}</td>;
              },
              a({ href, children }) {
                return <a href={href} target="_blank" rel="noreferrer" className="text-blue-400 hover:underline">{children}</a>;
              },
            }}
          >
            {message.content}
          </ReactMarkdown>
          {message.streaming && (
            <span className="inline-block w-1.5 h-4 bg-zinc-400 animate-pulse ml-0.5 align-text-bottom" />
          )}
        </div>
      )}
    </div>
  );
}
