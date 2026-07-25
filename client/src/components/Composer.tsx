import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Network, Send, Sparkles, Square, X } from 'lucide-react';
import { useChatContext } from '../context/ChatContext';
import {
  ApiError,
  fetchSelectableMcpServers,
  fetchSelectableSkills,
} from '../lib/api';
import type { SelectableMcpServer } from '../lib/api';
import {
  addMcpSelection,
  addSkillSelection,
  buildMessageFrame,
  filterCapabilities,
  movePickerIndex,
  parseCapabilityTrigger,
  pickerBackLevel,
  removeCapabilitySelection,
  replaceCapabilityTrigger,
  SelectionError,
} from '../lib/selections';
import type {
  CapabilityTrigger,
  PickerLevel,
  SelectionDraft,
} from '../lib/selections';
import type { SkillSummary } from '../types';
import { CapabilityPicker } from './CapabilityPicker';

interface PickerState {
  level: PickerLevel;
  trigger: CapabilityTrigger;
}

const emptySelections = (): SelectionDraft => ({ skills: [], mcps: [] });

function errorMessage(error: unknown): string {
  return error instanceof ApiError || error instanceof SelectionError
    ? error.message
    : error instanceof Error
      ? error.message
      : '操作失败';
}

export function Composer() {
  const { state, send, dispatch } = useChatContext();
  const { activeSessionId, streaming } = state;
  const [text, setText] = useState('');
  const [selections, setSelections] = useState<SelectionDraft>(emptySelections);
  const [selectionError, setSelectionError] = useState<string | null>(null);
  const [picker, setPicker] = useState<PickerState | null>(null);
  const [skills, setSkills] = useState<SkillSummary[]>([]);
  const [mcps, setMcps] = useState<SelectableMcpServer[]>([]);
  const [pickerLoading, setPickerLoading] = useState(false);
  const [pickerError, setPickerError] = useState<string | null>(null);
  const [pickerReload, setPickerReload] = useState(0);
  const [activeIndex, setActiveIndex] = useState(0);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const composerRef = useRef<HTMLDivElement>(null);
  const dismissedTriggerStart = useRef<number | null>(null);
  const pickerLevel = picker?.level;

  const closePicker = useCallback((suppressTrigger = false) => {
    setPicker((current) => {
      if (suppressTrigger && current) dismissedTriggerStart.current = current.trigger.start;
      return null;
    });
    setPickerError(null);
  }, []);

  const syncPicker = useCallback((value: string, caret: number) => {
    const trigger = parseCapabilityTrigger(value, caret);
    if (!trigger) {
      dismissedTriggerStart.current = null;
      setPicker(null);
      return;
    }
    if (dismissedTriggerStart.current === trigger.start) return;
    setPicker((current) => current?.trigger.start === trigger.start
      ? { ...current, trigger }
      : { level: 'category', trigger });
  }, []);

  useEffect(() => {
    textareaRef.current?.focus();
    setSelections(emptySelections());
    setSelectionError(null);
    setPicker(null);
    dismissedTriggerStart.current = null;
  }, [activeSessionId]);

  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = 'auto';
    ta.style.height = `${Math.min(ta.scrollHeight, 200)}px`;
  }, [text]);

  useEffect(() => {
    if (!pickerLevel || pickerLevel === 'category') return;
    let cancelled = false;
    setPickerLoading(true);
    setPickerError(null);
    if (pickerLevel === 'skill') setSkills([]);
    else setMcps([]);

    const request = pickerLevel === 'skill' ? fetchSelectableSkills() : fetchSelectableMcpServers();
    request
      .then((items) => {
        if (cancelled) return;
        if (pickerLevel === 'skill') setSkills(items as SkillSummary[]);
        else setMcps(items as SelectableMcpServer[]);
      })
      .catch((error) => {
        if (!cancelled) setPickerError(errorMessage(error));
      })
      .finally(() => {
        if (!cancelled) setPickerLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [pickerLevel, pickerReload]);

  useEffect(() => {
    const handleOutsidePointer = (event: PointerEvent) => {
      if (!composerRef.current?.contains(event.target as Node)) closePicker(true);
    };
    document.addEventListener('pointerdown', handleOutsidePointer);
    return () => document.removeEventListener('pointerdown', handleOutsidePointer);
  }, [closePicker]);

  const query = picker?.trigger.query ?? '';
  const filteredSkills = useMemo(
    () => filterCapabilities(skills, query, (skill) => [skill.name, skill.description]),
    [skills, query],
  );
  const filteredMcps = useMemo(
    () => filterCapabilities(mcps, query, (server) => [server.display_name, server.name, server.description]),
    [mcps, query],
  );

  const pickerItemCount = picker?.level === 'category'
    ? 2
    : picker?.level === 'skill'
      ? filteredSkills.length
      : picker?.level === 'mcp'
        ? filteredMcps.length
        : 0;

  useEffect(() => {
    setActiveIndex(0);
  }, [pickerLevel, query, pickerLoading]);

  const restoreCaret = (caret: number) => {
    requestAnimationFrame(() => {
      textareaRef.current?.focus();
      textareaRef.current?.setSelectionRange(caret, caret);
    });
  };

  const consumeTrigger = () => {
    if (!picker) return;
    const result = replaceCapabilityTrigger(text, picker.trigger);
    setText(result.text);
    dismissedTriggerStart.current = null;
    closePicker();
    restoreCaret(result.caret);
  };

  const selectSkill = (skill: SkillSummary) => {
    try {
      setSelections(addSkillSelection(selections, { name: skill.name, label: skill.name }));
      setSelectionError(null);
      consumeTrigger();
    } catch (error) {
      setSelectionError(errorMessage(error));
    }
  };

  const selectMcp = (server: SelectableMcpServer) => {
    try {
      setSelections(addMcpSelection(selections, {
        server: server.name,
        label: server.display_name || server.name,
      }));
      setSelectionError(null);
      consumeTrigger();
    } catch (error) {
      setSelectionError(errorMessage(error));
    }
  };

  const chooseCategory = (level: 'mcp' | 'skill') => {
    setPicker((current) => current ? { ...current, level } : null);
    setActiveIndex(0);
  };

  const chooseActivePickerItem = () => {
    if (!picker || pickerLoading || pickerError) return;
    if (picker.level === 'category') chooseCategory(activeIndex === 0 ? 'mcp' : 'skill');
    else if (picker.level === 'skill' && filteredSkills[activeIndex]) selectSkill(filteredSkills[activeIndex]);
    else if (picker.level === 'mcp' && filteredMcps[activeIndex]) selectMcp(filteredMcps[activeIndex]);
  };

  const goBack = () => {
    if (!picker) return;
    const level = pickerBackLevel(picker.level);
    if (level) setPicker({ ...picker, level });
    else closePicker(true);
    setActiveIndex(0);
    textareaRef.current?.focus();
  };

  const handleSubmit = () => {
    if (!activeSessionId || streaming) return;
    try {
      const frame = buildMessageFrame(activeSessionId, text, selections);
      if (!send(frame)) {
        setSelectionError('连接尚未就绪，消息未发送');
        return;
      }
      dispatch({ type: 'USER_MESSAGE_SENT', frame });
      setText('');
      setSelections(emptySelections());
      setSelectionError(null);
      dismissedTriggerStart.current = null;
      closePicker();
    } catch (error) {
      setSelectionError(errorMessage(error));
    }
  };

  const handleStop = () => {
    if (activeSessionId) send({ type: 'cancel', chat_id: activeSessionId });
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (picker) {
      if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        event.preventDefault();
        setActiveIndex((current) => movePickerIndex(current, event.key === 'ArrowDown' ? 'next' : 'previous', pickerItemCount));
        return;
      }
      if (event.key === 'Enter') {
        event.preventDefault();
        chooseActivePickerItem();
        return;
      }
      if (event.key === 'Escape') {
        event.preventDefault();
        closePicker(true);
        return;
      }
      if (event.key === 'Backspace' && picker.level !== 'category' && !picker.trigger.query) {
        event.preventDefault();
        goBack();
        return;
      }
    }
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div ref={composerRef} className="relative shrink-0 px-3 pb-3 pt-2 sm:px-4 sm:pb-4">
      {picker && (
        <CapabilityPicker
          level={picker.level}
          query={query}
          loading={pickerLoading}
          error={pickerError}
          skills={filteredSkills}
          mcps={filteredMcps}
          activeIndex={activeIndex}
          onActiveIndex={setActiveIndex}
          onCategory={chooseCategory}
          onSkill={selectSkill}
          onMcp={selectMcp}
          onBack={goBack}
          onRetry={() => setPickerReload((value) => value + 1)}
        />
      )}

      <div className="rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2.5 transition-colors focus-within:border-zinc-500 sm:px-4 sm:py-3">
        {(selections.skills.length > 0 || selections.mcps.length > 0) && (
          <div className="mb-2 flex max-h-20 flex-wrap gap-1.5 overflow-y-auto" aria-label="已选择的能力">
            {selections.skills.map((skill) => (
              <span key={`skill:${skill.name}`} className="inline-flex max-w-full items-center gap-1 rounded border border-amber-800/70 bg-amber-950/30 px-2 py-1 text-xs text-amber-300">
                <Sparkles className="h-3 w-3 shrink-0" />
                <span className="truncate">{skill.label || skill.name}</span>
                <button type="button" onClick={() => setSelections(removeCapabilitySelection(selections, 'skill', skill.name))} className="ml-0.5 shrink-0 text-amber-500 hover:text-amber-200" aria-label={`移除 Skill ${skill.label || skill.name}`}>
                  <X className="h-3 w-3" />
                </button>
              </span>
            ))}
            {selections.mcps.map((mcp) => (
              <span key={`mcp:${mcp.server}`} className="inline-flex max-w-full items-center gap-1 rounded border border-cyan-800/70 bg-cyan-950/30 px-2 py-1 text-xs text-cyan-300">
                <Network className="h-3 w-3 shrink-0" />
                <span className="truncate">{mcp.label || mcp.server}</span>
                <button type="button" onClick={() => setSelections(removeCapabilitySelection(selections, 'mcp', mcp.server))} className="ml-0.5 shrink-0 text-cyan-500 hover:text-cyan-200" aria-label={`移除 MCP ${mcp.label || mcp.server}`}>
                  <X className="h-3 w-3" />
                </button>
              </span>
            ))}
          </div>
        )}

        <div className="flex items-end gap-2">
          <textarea
            ref={textareaRef}
            value={text}
            onChange={(event) => {
              const value = event.target.value;
              setText(value);
              setSelectionError(null);
              syncPicker(value, event.target.selectionStart ?? value.length);
            }}
            onSelect={(event) => syncPicker(event.currentTarget.value, event.currentTarget.selectionStart ?? event.currentTarget.value.length)}
            onKeyDown={handleKeyDown}
            placeholder="输入消息"
            disabled={streaming}
            rows={1}
            aria-expanded={Boolean(picker)}
            aria-controls={picker ? 'capability-picker' : undefined}
            className="flex-1 resize-none bg-transparent text-sm leading-relaxed text-zinc-200 outline-none placeholder:text-zinc-600 disabled:opacity-50"
            style={{ minHeight: '24px', maxHeight: '200px' }}
          />
          {streaming ? (
            <button onClick={handleStop} className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-red-500/20 text-red-400 transition-colors hover:bg-red-500/30" title="停止生成" aria-label="停止生成">
              <Square className="h-3.5 w-3.5 fill-current" />
            </button>
          ) : (
            <button onClick={handleSubmit} disabled={!text.trim() || !activeSessionId} className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-zinc-700 text-zinc-300 transition-colors hover:bg-zinc-600 disabled:cursor-not-allowed disabled:opacity-30" title="发送" aria-label="发送消息">
              <Send className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
        {selectionError && <p role="alert" className="mt-2 break-words text-xs text-red-400">{selectionError}</p>}
      </div>
    </div>
  );
}
