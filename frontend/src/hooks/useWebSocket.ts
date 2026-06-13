import { useEffect, useRef, useCallback, useState } from 'react';

// 动态获取 WebSocket 基础 URL
const getWsBaseUrl = () => {
  const savedApiUrl = localStorage.getItem('cxhms-api-url');
  const baseUrl = savedApiUrl || import.meta.env.VITE_API_URL || 'http://localhost:8001';
  return baseUrl.replace('http', 'ws');
};

const MAX_RECONNECT_ATTEMPTS = 5;
const BASE_RECONNECT_DELAY = 1000;

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
  const reconnectCountRef = useRef(0);
  const [isConnected, setIsConnected] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);

  const onMessageRef = useRef(onMessage);
  const onAlarmRef = useRef(onAlarm);
  const onErrorRef = useRef(onError);
  const onConnectRef = useRef(onConnect);
  const onDisconnectRef = useRef(onDisconnect);

  onMessageRef.current = onMessage;
  onAlarmRef.current = onAlarm;
  onErrorRef.current = onError;
  onConnectRef.current = onConnect;
  onDisconnectRef.current = onDisconnect;

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
    // 已有连接或正在连接中，跳过
    if (wsRef.current?.readyState === WebSocket.OPEN || wsRef.current?.readyState === WebSocket.CONNECTING) {
      return;
    }

    const wsBaseUrl = import.meta.env.VITE_WS_URL || getWsBaseUrl();
    const wsUrl = `${wsBaseUrl}/ws/${agentId}?timeout=${timeout}`;
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      setIsConnected(true);
      reconnectCountRef.current = 0;
      startPingInterval();
      onConnectRef.current?.();
    };

    ws.onclose = () => {
      setIsConnected(false);
      setIsGenerating(false);
      clearPingInterval();
      onDisconnectRef.current?.();

      if (reconnectCountRef.current < MAX_RECONNECT_ATTEMPTS) {
        const delay = BASE_RECONNECT_DELAY * Math.pow(2, reconnectCountRef.current);
        reconnectCountRef.current += 1;
        reconnectTimeoutRef.current = setTimeout(() => {
          connect();
        }, delay);
      }
    };

    ws.onerror = (event) => {
      console.error('WebSocket error:', event);
      onErrorRef.current?.('WebSocket connection error');
    };

    ws.onmessage = (event) => {
      try {
        const data: WebSocketMessage = JSON.parse(event.data);

        switch (data.type) {
          case 'pong':
            break;
          case 'alarm':
            onAlarmRef.current?.(data.message || '', data.triggered_at || '');
            break;
          case 'content':
          case 'tool_call':
          case 'tool_result':
            onMessageRef.current?.(data);
            break;
          case 'done':
            setIsGenerating(false);
            onMessageRef.current?.(data);
            break;
          case 'error':
            setIsGenerating(false);
            onErrorRef.current?.(data.error || 'Unknown error');
            break;
          case 'cancelled':
            setIsGenerating(false);
            onMessageRef.current?.(data);
            break;
          default:
            onMessageRef.current?.(data);
        }
      } catch (e) {
        console.error('Failed to parse WebSocket message:', e);
      }
    };

    wsRef.current = ws;
  }, [
    agentId,
    timeout,
    startPingInterval,
    clearPingInterval,
  ]);

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    reconnectCountRef.current = MAX_RECONNECT_ATTEMPTS;
    clearPingInterval();
    if (wsRef.current) {
      // 只关闭已连接或正在关闭的 WebSocket，避免中断正在连接的
      if (wsRef.current.readyState === WebSocket.OPEN || wsRef.current.readyState === WebSocket.CLOSING) {
        wsRef.current.close();
      }
      wsRef.current = null;
    }
  }, [clearPingInterval]);

  const reconnect = useCallback(() => {
    disconnect();
    reconnectCountRef.current = 0;
    connect();
  }, [connect, disconnect]);

  const sendMessage = useCallback(
    (message: string, images?: string[]) => {
      if (wsRef.current?.readyState !== WebSocket.OPEN) {
        onErrorRef.current?.('WebSocket is not connected');
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
    []
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
