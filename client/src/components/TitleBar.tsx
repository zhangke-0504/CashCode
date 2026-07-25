// TitleBar: app header with CashLogo, mobile navigation, and connection state
import { Menu } from 'lucide-react';
import type { WsConnectionState } from '../types';

interface TitleBarProps {
  wsState: WsConnectionState;
  onToggleSidebar: () => void;
}

const stateColors: Record<WsConnectionState, string> = {
  connected: 'bg-emerald-500',
  connecting: 'bg-yellow-500',
  disconnected: 'bg-zinc-500',
  error: 'bg-red-500',
};

export function TitleBar({ wsState, onToggleSidebar }: TitleBarProps) {
  return (
    <header className="flex items-center gap-2 px-4 h-11 shrink-0 bg-[#0a0a0a] border-b border-zinc-800 select-none">
      <button
        type="button"
        onClick={onToggleSidebar}
        className="-ml-2 flex h-8 w-8 items-center justify-center rounded-md text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100 sm:hidden"
        aria-label="打开导航"
      >
        <Menu className="h-4 w-4" />
      </button>
      <span className="text-sm font-semibold text-zinc-100 tracking-tight">CashCode</span>
      <div className="ml-auto flex items-center gap-1.5">
        <span className={`w-2 h-2 rounded-full ${stateColors[wsState]}`} title={wsState} />
        <span className="text-xs text-zinc-500">{wsState}</span>
      </div>
    </header>
  );
}
