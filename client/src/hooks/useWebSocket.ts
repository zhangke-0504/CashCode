import { useCallback, useEffect, useRef, useState } from 'react';
import type { WsConnectionState } from '../types';

const WS_URL = 'ws://127.0.0.1:8765/';
const MAX_RETRY_MS = 30000;

export function useWebSocket(onFrame: (frame: unknown) => void) {
  const [state, setState] = useState<WsConnectionState>('connecting');
  const wsRef = useRef<WebSocket | null>(null);
  const retryTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);
  const retryDelay = useRef(1000);
  const onFrameRef = useRef(onFrame);
  onFrameRef.current = onFrame;

  const connect = useCallback(() => {
    if (wsRef.current) return; // already connecting/open
    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;
    setState('connecting');

    ws.onopen = () => {
      setState('connected');
      retryDelay.current = 1000;
    };

    ws.onmessage = (e) => {
      try {
        const frame = JSON.parse(e.data as string);
        onFrameRef.current(frame);
      } catch { /* ignore parse errors */ }
    };

    ws.onclose = () => {
      setState('disconnected');
      wsRef.current = null;
      const delay = retryDelay.current;
      retryDelay.current = Math.min(delay * 2, MAX_RETRY_MS);
      retryTimeout.current = setTimeout(connect, delay);
    };

    ws.onerror = () => {
      setState('error');
    };
  }, []);

  useEffect(() => {
    connect();
    return () => {
      if (retryTimeout.current) clearTimeout(retryTimeout.current);
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [connect]);

  const send = useCallback((frame: object): boolean => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(frame));
      return true;
    }
    return false;
  }, []);

  return { state, send };
}
