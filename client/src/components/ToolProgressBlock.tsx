// ToolProgressBlock: shows tool call progress during streaming
import { Check, Loader, Wrench } from 'lucide-react';
import type { ToolCallBlock } from '../types';

interface ToolProgressBlockProps {
  block: ToolCallBlock;
}

export function ToolProgressBlock({ block }: ToolProgressBlockProps) {
  return (
    <div className="flex items-start gap-2 px-3 py-2 bg-zinc-900/60 border border-zinc-800 rounded-lg text-xs text-zinc-400 max-w-sm">
      <Wrench className="w-3.5 h-3.5 mt-0.5 shrink-0 text-zinc-500" />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5">
          <span className="font-mono text-zinc-300">{block.tool_name}</span>
          {block.done ? (
            <Check className="w-3 h-3 text-emerald-400" />
          ) : (
            <Loader className="w-3 h-3 animate-spin text-blue-400" />
          )}
        </div>
        {block.done && block.result && (
          <p className="mt-0.5 text-zinc-500 truncate">{block.result.slice(0, 120)}</p>
        )}
      </div>
    </div>
  );
}
