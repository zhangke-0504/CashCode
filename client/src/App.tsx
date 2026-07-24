// App.tsx: main layout — TitleBar + Sidebar + ChatView
import './App.css';
import { ChatProvider } from './context/ChatContext';
import { TitleBar } from './components/TitleBar';
import { Sidebar } from './components/Sidebar';
import { ChatView } from './components/ChatView';
import { useChatContext } from './context/ChatContext';

function AppLayout() {
  const { state } = useChatContext();
  return (
    <div className="flex flex-col h-full">
      <TitleBar wsState={state.wsState} />
      <div className="flex flex-1 overflow-hidden relative">
        <Sidebar />
        <main className="flex-1 flex flex-col overflow-hidden bg-[#0a0a0a]">
          {state.error && (
            <div className="mx-4 mt-2 px-3 py-2 bg-red-900/30 border border-red-800 rounded-lg text-xs text-red-400">
              {state.error}
            </div>
          )}
          <ChatView />
        </main>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <ChatProvider>
      <AppLayout />
    </ChatProvider>
  );
}
