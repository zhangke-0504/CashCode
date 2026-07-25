import { ArrowLeft, Network, RefreshCw, Sparkles } from 'lucide-react';
import type { SelectableMcpServer } from '../lib/api';
import type { PickerLevel } from '../lib/selections';
import type { SkillSummary } from '../types';

interface CapabilityPickerProps {
  level: PickerLevel;
  query: string;
  loading: boolean;
  error: string | null;
  skills: SkillSummary[];
  mcps: SelectableMcpServer[];
  activeIndex: number;
  onActiveIndex: (index: number) => void;
  onCategory: (category: 'mcp' | 'skill') => void;
  onSkill: (skill: SkillSummary) => void;
  onMcp: (server: SelectableMcpServer) => void;
  onBack: () => void;
  onRetry: () => void;
}

function activeClass(active: boolean): string {
  return active ? 'bg-zinc-800 text-zinc-100' : 'text-zinc-300 hover:bg-zinc-800/70';
}

export function CapabilityPicker({
  level,
  query,
  loading,
  error,
  skills,
  mcps,
  activeIndex,
  onActiveIndex,
  onCategory,
  onSkill,
  onMcp,
  onBack,
  onRetry,
}: CapabilityPickerProps) {
  return (
    <section
      id="capability-picker"
      aria-label="选择 Skill 或 MCP"
      className="absolute bottom-full left-4 right-4 z-30 mb-2 overflow-hidden rounded-lg border border-zinc-700 bg-zinc-900 shadow-2xl sm:right-auto sm:w-96"
    >
      {level === 'category' ? (
        <div role="listbox" aria-label="能力类型" className="p-1.5">
          <button
            type="button"
            role="option"
            aria-selected={activeIndex === 0}
            onMouseEnter={() => onActiveIndex(0)}
            onMouseDown={(event) => event.preventDefault()}
            onClick={() => onCategory('mcp')}
            className={`flex w-full items-start gap-3 rounded-md px-3 py-2.5 text-left ${activeClass(activeIndex === 0)}`}
          >
            <Network className="mt-0.5 h-4 w-4 shrink-0 text-cyan-400" />
            <span className="min-w-0">
              <span className="block text-sm font-medium">MCP</span>
              <span className="mt-0.5 block text-xs text-zinc-500">已连接的工具服务</span>
            </span>
          </button>
          <button
            type="button"
            role="option"
            aria-selected={activeIndex === 1}
            onMouseEnter={() => onActiveIndex(1)}
            onMouseDown={(event) => event.preventDefault()}
            onClick={() => onCategory('skill')}
            className={`flex w-full items-start gap-3 rounded-md px-3 py-2.5 text-left ${activeClass(activeIndex === 1)}`}
          >
            <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-amber-400" />
            <span className="min-w-0">
              <span className="block text-sm font-medium">Skill</span>
              <span className="mt-0.5 block text-xs text-zinc-500">当前可用的本地技能</span>
            </span>
          </button>
        </div>
      ) : (
        <>
          <header className="flex h-10 items-center gap-2 border-b border-zinc-800 px-2">
            <button
              type="button"
              onMouseDown={(event) => event.preventDefault()}
              onClick={onBack}
              className="flex h-7 w-7 items-center justify-center rounded-md text-zinc-500 hover:bg-zinc-800 hover:text-zinc-200"
              title="返回类型选择"
              aria-label="返回类型选择"
            >
              <ArrowLeft className="h-4 w-4" />
            </button>
            <span className="text-xs font-medium text-zinc-300">{level === 'mcp' ? 'MCP' : 'Skill'}</span>
            {query && <span className="min-w-0 truncate text-xs text-zinc-600">筛选：{query}</span>}
          </header>

          <div role="listbox" aria-label={`${level === 'mcp' ? 'MCP' : 'Skill'} 列表`} className="max-h-72 overflow-y-auto p-1.5">
            {loading && Array.from({ length: 3 }, (_, index) => (
              <div key={index} className="h-14 animate-pulse px-3 py-2">
                <div className="h-3 w-32 rounded bg-zinc-800" />
                <div className="mt-2 h-2.5 w-3/4 rounded bg-zinc-800/60" />
              </div>
            ))}

            {!loading && error && (
              <div role="alert" className="p-3 text-xs text-red-300">
                <p className="break-words">{error}</p>
                <button type="button" onMouseDown={(event) => event.preventDefault()} onClick={onRetry} className="mt-2 inline-flex items-center gap-1 rounded-md px-2 py-1 text-zinc-300 hover:bg-zinc-800">
                  <RefreshCw className="h-3.5 w-3.5" />重试
                </button>
              </div>
            )}

            {!loading && !error && level === 'skill' && skills.length === 0 && (
              <p className="px-3 py-6 text-center text-xs text-zinc-600">没有匹配的可用 Skill</p>
            )}
            {!loading && !error && level === 'mcp' && mcps.length === 0 && (
              <p className="px-3 py-6 text-center text-xs text-zinc-600">没有已连接且可用的 MCP</p>
            )}

            {!loading && !error && level === 'skill' && skills.map((skill, index) => (
              <button
                key={skill.name}
                type="button"
                role="option"
                aria-selected={activeIndex === index}
                onMouseEnter={() => onActiveIndex(index)}
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => onSkill(skill)}
                className={`flex w-full items-start gap-3 rounded-md px-3 py-2.5 text-left ${activeClass(activeIndex === index)}`}
              >
                <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-amber-400" />
                <span className="min-w-0">
                  <span className="block truncate text-sm font-medium">{skill.name}</span>
                  <span className="mt-0.5 block line-clamp-2 text-xs text-zinc-500">{skill.description || '暂无描述'}</span>
                </span>
              </button>
            ))}

            {!loading && !error && level === 'mcp' && mcps.map((server, index) => (
              <button
                key={server.name}
                type="button"
                role="option"
                aria-selected={activeIndex === index}
                onMouseEnter={() => onActiveIndex(index)}
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => onMcp(server)}
                className={`flex w-full items-start gap-3 rounded-md px-3 py-2.5 text-left ${activeClass(activeIndex === index)}`}
              >
                <Network className="mt-0.5 h-4 w-4 shrink-0 text-cyan-400" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium">{server.display_name || server.name}</span>
                  <span className="mt-0.5 block line-clamp-2 text-xs text-zinc-500">{server.description || server.name}</span>
                </span>
                <span className="shrink-0 text-[11px] text-zinc-600">{server.tools.length} 工具</span>
              </button>
            ))}
          </div>
        </>
      )}
    </section>
  );
}

