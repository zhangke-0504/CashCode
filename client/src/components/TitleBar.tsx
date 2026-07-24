// TitleBar: app header with CashLogo and title
import type { WsConnectionState } from '../types';

interface TitleBarProps {
  wsState: WsConnectionState;
}

const stateColors: Record<WsConnectionState, string> = {
  connected: 'bg-emerald-500',
  connecting: 'bg-yellow-500',
  disconnected: 'bg-zinc-500',
  error: 'bg-red-500',
};

export function TitleBar({ wsState }: TitleBarProps) {
  return (
    <header className="flex items-center gap-2 px-4 h-11 shrink-0 bg-[#0a0a0a] border-b border-zinc-800 select-none">
      <img src="/CashLogo.png" alt="CashCode logo" className="w-6 h-6 object-contain" />
      <span className="text-sm font-semibold text-zinc-100 tracking-tight">CashCode</span>
      <div className="ml-auto flex items-center gap-1.5">
        <span className={`w-2 h-2 rounded-full ${stateColors[wsState]}`} title={wsState} />
        <span className="text-xs text-zinc-500">{wsState}</span>
      </div>
    </header>
  );
}
