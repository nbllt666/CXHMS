import { useEffect, useRef, useCallback, useState } from 'react';

const WS_BASE_URL =
  import.meta.env.VITE_WS_URL ||
  (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace('http', 'ws');

export interface WebSocketMessage {
  type: string;
  content?: string;
  message?: string;
  done?: boolean;
  error?: string;
  session_id?: string;
  tool_call?: Record<string, unknown>;
  tool_name?: string;
  result?: unknown;
  triggered_at?: string;
}

export interface WebSocketOptions {
  agentId: string;
  timeout?: number;
  onMessage?: (data: WebSocketMessage) => void;
  onAlarm?: (message: string, triggeredAt: string) => void;
  onError?: (error: string) => void;
  onConnect?: () => void;
  onDisconnect?: () => void;
}

export interface UseWebSocketReturn {
  isConnected: boolean;
  isGenerating: boolean;
  sendMessage: (message: string, images?: string[]) => void;
  cancelGeneration: () => void;
  disconnect: () => void;
  reconnect: () => void;
}

export function useWebSocket(options: WebSocketOptions): UseWebSocketReturn {
  const {
    agentId,
    timeout: propTimeout,
    onMessage,
    onAlarm,
    onError,
    onConnect,
    onDisconnect,
  } = options;

  const getStoredTimeout = useCallback(() => {
    const stored = localStorage.getItem('cxhms-offline-timeout');
    return stored ? parseInt(stored, 10) : 60;
  }, []);

  const [timeout, setTimeoutState] = useState(propTimeout || getStoredTimeout());

  const wsRef = useRef<WebSocket | null>(null);
  const pingIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);

  const clearPingInterval = useCallback(() => {
    if (pingIntervalRef.current) {
      clearInterval(pingIntervalRef.current);
      pingIntervalRef.current = null;
    }
  }, []);

  const startPingInterval = useCallback(() => {
    clearPingInterval();
    pingIntervalRef.current = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: 'ping' }));
      }
    }, 30000);
  }, [clearPingInterval]);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return;
    }

    const wsUrl = `${WS_BASE_URL}/ws/${agentId}?timeout=${timeout}`;
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      setIsConnected(true);
      startPingInterval();
      onConnect?.();
    };

    ws.onclose = () => {
      setIsConnected(false);
      setIsGenerating(false);
      clearPingInterval();
      onDisconnect?.();
    };

    ws.onerror = (event) => {
      console.error('WebSocket error:', event);
      onError?.('WebSocket connection error');
    };

    ws.onmessage = (event) => {
      try {
        const data: WebSocketMessage = JSON.parse(event.data);

        switch (data.type) {
          case 'pong':
            break;
          case 'alarm':
            onAlarm?.(data.message || '', data.triggered_at || '');
            break;
          case 'content':
          case 'tool_call':
          case 'tool_result':
            onMessage?.(data);
            break;
          case 'done':
            setIsGenerating(false);
            onMessage?.(data);
            break;
          case 'error':
            setIsGenerating(false);
            onError?.(data.error || 'Unknown error');
            break;
          case 'cancelled':
            setIsGenerating(false);
            onMessage?.(data);
            break;
          default:
            onMessage?.(data);
        }
      } catch (e) {
        console.error('Failed to parse WebSocket message:', e);
      }
    };

    wsRef.current = ws;
  }, [
    agentId,
    timeout,
    onMessage,
    onAlarm,
    onError,
    onConnect,
    onDisconnect,
    startPingInterval,
    clearPingInterval,
  ]);

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    clearPingInterval();
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
  }, [clearPingInterval]);

  const reconnect = useCallback(() => {
    disconnect();
    window.setTimeout(connect, 100);
  }, [connect, disconnect]);

  const sendMessage = useCallback(
    (message: string, images?: string[]) => {
      if (wsRef.current?.readyState !== WebSocket.OPEN) {
        onError?.('WebSocket is not connected');
        return;
      }

      setIsGenerating(true);
      wsRef.current.send(
        JSON.stringify({
          type: 'chat',
          message,
          images: images && images.length > 0 ? images : undefined,
        })
      );
    },
    [onError]
  );

  const cancelGeneration = useCallback(() => {
    if (wsRef.current?.readyState !== WebSocket.OPEN) {
      return;
    }

    wsRef.current.send(JSON.stringify({ type: 'cancel' }));
  }, []);

  useEffect(() => {
    connect();

    const handleTimeoutChange = (e: CustomEvent) => {
      const newTimeout = parseInt(e.detail, 10);
      if (!isNaN(newTimeout)) {
        setTimeoutState(newTimeout);
      }
    };

    window.addEventListener('offline-timeout-change', handleTimeoutChange as EventListener);

    return () => {
      disconnect();
      window.removeEventListener('offline-timeout-change', handleTimeoutChange as EventListener);
    };
  }, [connect, disconnect]);

  useEffect(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(
        JSON.stringify({
          type: 'config',
          timeout,
        })
      );
    }
  }, [timeout]);

  return {
    isConnected,
    isGenerating,
    sendMessage,
    cancelGeneration,
    disconnect,
    reconnect,
  };
}

export default useWebSocket;
