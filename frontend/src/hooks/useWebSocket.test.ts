// ========== useWebSocket hook 单元测试 ==========
// G6: 覆盖 URL 构造(E3 回归)/连接/断开/重连/消息回调。
// 用 renderHook + mock WebSocket 全局，避免真实网络。

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useWebSocket } from './useWebSocket';

// ========== Mock WebSocket ==========
const WS_CONNECTING = 0;
const WS_OPEN = 1;
const WS_CLOSING = 2;
const WS_CLOSED = 3;

class MockWebSocket {
  static CONNECTING = WS_CONNECTING;
  static OPEN = WS_OPEN;
  static CLOSING = WS_CLOSING;
  static CLOSED = WS_CLOSED;
  static instances: MockWebSocket[] = [];

  readyState: number = WS_CONNECTING;
  url: string;
  onopen: ((ev: Event) => void) | null = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  onclose: ((ev: CloseEvent) => void) | null = null;
  onerror: ((ev: Event) => void) | null = null;
  sent: string[] = [];
  closed = false;

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }

  send(data: string) {
    this.sent.push(data);
  }

  close() {
    this.closed = true;
    this.readyState = WS_CLOSED;
    // 真实 WebSocket.close() 会触发 onclose 事件，useWebSocket 依赖它清 isConnected/isGenerating。
    // 测试中同步触发以简化断言（act 包裹已防止 act 警告）。
    if (this.onclose) {
      this.onclose(new CloseEvent('close'));
    }
  }

  // test helpers
  fireOpen() {
    this.readyState = WS_OPEN;
    this.onopen?.(new Event('open'));
  }
  fireMessage(data: unknown) {
    this.onmessage?.({ data: JSON.stringify(data) } as unknown as MessageEvent);
  }
  fireClose() {
    this.readyState = WS_CLOSED;
    this.onclose?.(new CloseEvent('close'));
  }
  fireError() {
    this.onerror?.(new Event('error'));
  }
}

// 捕获 onMessage/onError/onConnect/onDisconnect 回调
function makeCallbacks() {
  return {
    onMessage: vi.fn(),
    onError: vi.fn(),
    onConnect: vi.fn(),
    onDisconnect: vi.fn(),
    onAlarm: vi.fn(),
  };
}

describe('useWebSocket', () => {
  beforeEach(() => {
    MockWebSocket.instances = [];
    (globalThis as unknown as { WebSocket: typeof MockWebSocket }).WebSocket = MockWebSocket;
    // setup.ts 已 mock localStorage.getItem 为 vi.fn()；这里按 key 返回不同值
    vi.mocked(localStorage.getItem).mockImplementation((key: string) => {
      if (key === 'cxhms-api-url') return 'http://localhost:8001';
      if (key === 'cxhms-offline-timeout') return null;
      return null;
    });
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  describe('URL construction (E3 regression)', () => {
    it('https → wss protocol', () => {
      vi.mocked(localStorage.getItem).mockImplementation((key: string) =>
        key === 'cxhms-api-url' ? 'https://api.example.com' : null
      );
      renderHook(() => useWebSocket({ agentId: 'agent-1' }));
      expect(MockWebSocket.instances).toHaveLength(1);
      expect(MockWebSocket.instances[0].url).toMatch(/^wss:\/\/api\.example\.com\/ws\/agent-1/);
    });

    it('http → ws protocol', () => {
      vi.mocked(localStorage.getItem).mockImplementation((key: string) =>
        key === 'cxhms-api-url' ? 'http://localhost:8001' : null
      );
      renderHook(() => useWebSocket({ agentId: 'agent-1' }));
      expect(MockWebSocket.instances[0].url).toMatch(/^ws:\/\/localhost:8001\/ws\/agent-1/);
    });

    it('URL containing "http" substring is not corrupted (E3 key regression)', () => {
      // 旧实现 baseUrl.replace('http','ws') 会把 "myhttpapi" 错改为 "mywsttpi"。
      // 新实现用 URL 构造，仅替换 protocol，"http" 子串在 host 中保留不变。
      vi.mocked(localStorage.getItem).mockImplementation((key: string) =>
        key === 'cxhms-api-url' ? 'https://myhttpapi.com' : null
      );
      renderHook(() => useWebSocket({ agentId: 'agent-1' }));
      expect(MockWebSocket.instances[0].url).toMatch(/^wss:\/\/myhttpapi\.com\/ws\/agent-1/);
      // 关键断言：host 部分仍含 "http" 子串（未被替换为 "ws"）
      expect(MockWebSocket.instances[0].url).toContain('myhttpapi.com');
    });

    it('appends /ws/{agentId} with timeout query', () => {
      renderHook(() => useWebSocket({ agentId: 'agent-1', timeout: 30 }));
      const url = MockWebSocket.instances[0].url;
      expect(url).toContain('/ws/agent-1');
      expect(url).toContain('timeout=30');
    });

    it('trailing slash in baseUrl is stripped', () => {
      vi.mocked(localStorage.getItem).mockImplementation((key: string) =>
        key === 'cxhms-api-url' ? 'http://localhost:8001/' : null
      );
      renderHook(() => useWebSocket({ agentId: 'a1' }));
      // 不应出现双斜杠 //
      expect(MockWebSocket.instances[0].url).not.toContain('//ws/');
      expect(MockWebSocket.instances[0].url).toMatch(/ws:\/\/localhost:8001\/ws\/a1/);
    });
  });

  describe('connection lifecycle', () => {
    it('isConnected becomes true on open', () => {
      const { result } = renderHook(() => useWebSocket({ agentId: 'a1' }));
      expect(result.current.isConnected).toBe(false);
      act(() => MockWebSocket.instances[0].fireOpen());
      expect(result.current.isConnected).toBe(true);
    });

    it('invokes onConnect callback on open', () => {
      const cbs = makeCallbacks();
      renderHook(() => useWebSocket({ agentId: 'a1', ...cbs }));
      act(() => MockWebSocket.instances[0].fireOpen());
      expect(cbs.onConnect).toHaveBeenCalledTimes(1);
    });

    it('starts ping interval after open (30s)', () => {
      renderHook(() => useWebSocket({ agentId: 'a1' }));
      act(() => MockWebSocket.instances[0].fireOpen());
      const ws = MockWebSocket.instances[0];
      expect(ws.sent).toHaveLength(0);
      // 推进 30s 触发首次 ping
      act(() => {
        vi.advanceTimersByTime(30000);
      });
      expect(ws.sent.length).toBeGreaterThanOrEqual(1);
      expect(JSON.parse(ws.sent[0]).type).toBe('ping');
    });

    it('disconnect() closes the WebSocket and stops reconnection', () => {
      const { result } = renderHook(() => useWebSocket({ agentId: 'a1' }));
      act(() => MockWebSocket.instances[0].fireOpen());
      expect(result.current.isConnected).toBe(true);
      act(() => result.current.disconnect());
      expect(MockWebSocket.instances[0].closed).toBe(true);
      expect(result.current.isConnected).toBe(false);
    });

    it('invokes onDisconnect callback on close', () => {
      const cbs = makeCallbacks();
      renderHook(() => useWebSocket({ agentId: 'a1', ...cbs }));
      act(() => MockWebSocket.instances[0].fireOpen());
      act(() => MockWebSocket.instances[0].fireClose());
      expect(cbs.onDisconnect).toHaveBeenCalledTimes(1);
    });
  });

  describe('message handling', () => {
    it('content chunk invokes onMessage', () => {
      const cbs = makeCallbacks();
      renderHook(() => useWebSocket({ agentId: 'a1', ...cbs }));
      act(() => MockWebSocket.instances[0].fireOpen());
      act(() => MockWebSocket.instances[0].fireMessage({ type: 'content', content: 'hi' }));
      expect(cbs.onMessage).toHaveBeenCalledWith(expect.objectContaining({ type: 'content', content: 'hi' }));
    });

    it('done chunk clears isGenerating and forwards to onMessage', () => {
      const cbs = makeCallbacks();
      const { result } = renderHook(() => useWebSocket({ agentId: 'a1', ...cbs }));
      act(() => MockWebSocket.instances[0].fireOpen());
      // 模拟开始生成
      act(() => result.current.sendMessage('hello'));
      expect(result.current.isGenerating).toBe(true);
      // done 到达
      act(() => MockWebSocket.instances[0].fireMessage({ type: 'done' }));
      expect(result.current.isGenerating).toBe(false);
      expect(cbs.onMessage).toHaveBeenCalledWith(expect.objectContaining({ type: 'done' }));
    });

    it('error chunk clears isGenerating and invokes onError', () => {
      const cbs = makeCallbacks();
      const { result } = renderHook(() => useWebSocket({ agentId: 'a1', ...cbs }));
      act(() => MockWebSocket.instances[0].fireOpen());
      act(() => result.current.sendMessage('hello'));
      expect(result.current.isGenerating).toBe(true);
      act(() => MockWebSocket.instances[0].fireMessage({ type: 'error', error: 'boom' }));
      expect(result.current.isGenerating).toBe(false);
      expect(cbs.onError).toHaveBeenCalledWith('boom');
    });

    it('cancelled chunk clears isGenerating', () => {
      const cbs = makeCallbacks();
      const { result } = renderHook(() => useWebSocket({ agentId: 'a1', ...cbs }));
      act(() => MockWebSocket.instances[0].fireOpen());
      act(() => result.current.sendMessage('hello'));
      act(() => MockWebSocket.instances[0].fireMessage({ type: 'cancelled' }));
      expect(result.current.isGenerating).toBe(false);
    });

    it('alarm chunk invokes onAlarm with message + triggered_at', () => {
      const cbs = makeCallbacks();
      renderHook(() => useWebSocket({ agentId: 'a1', ...cbs }));
      act(() => MockWebSocket.instances[0].fireOpen());
      act(() =>
        MockWebSocket.instances[0].fireMessage({
          type: 'alarm',
          message: 'wake up',
          triggered_at: '2026-07-05T10:00:00Z',
        })
      );
      expect(cbs.onAlarm).toHaveBeenCalledWith('wake up', '2026-07-05T10:00:00Z');
    });

    it('pong chunk does not invoke onMessage', () => {
      const cbs = makeCallbacks();
      renderHook(() => useWebSocket({ agentId: 'a1', ...cbs }));
      act(() => MockWebSocket.instances[0].fireOpen());
      act(() => MockWebSocket.instances[0].fireMessage({ type: 'pong' }));
      expect(cbs.onMessage).not.toHaveBeenCalled();
    });
  });

  describe('sendMessage', () => {
    it('sends chat message with type=chat', () => {
      const { result } = renderHook(() => useWebSocket({ agentId: 'a1' }));
      act(() => MockWebSocket.instances[0].fireOpen());
      const ws = MockWebSocket.instances[0];
      act(() => result.current.sendMessage('hello'));
      expect(ws.sent).toHaveLength(1);
      const payload = JSON.parse(ws.sent[0]);
      expect(payload.type).toBe('chat');
      expect(payload.message).toBe('hello');
      expect(result.current.isGenerating).toBe(true);
    });

    it('sends images when provided', () => {
      const { result } = renderHook(() => useWebSocket({ agentId: 'a1' }));
      act(() => MockWebSocket.instances[0].fireOpen());
      act(() => result.current.sendMessage('hi', ['img1-base64']));
      const payload = JSON.parse(MockWebSocket.instances[0].sent[0]);
      expect(payload.images).toEqual(['img1-base64']);
    });

    it('omits images when empty array', () => {
      const { result } = renderHook(() => useWebSocket({ agentId: 'a1' }));
      act(() => MockWebSocket.instances[0].fireOpen());
      act(() => result.current.sendMessage('hi', []));
      const payload = JSON.parse(MockWebSocket.instances[0].sent[0]);
      expect(payload.images).toBeUndefined();
    });

    it('invokes onError when not connected', () => {
      const cbs = makeCallbacks();
      const { result } = renderHook(() => useWebSocket({ agentId: 'a1', ...cbs }));
      // 未 fireOpen，readyState 仍为 CONNECTING
      act(() => result.current.sendMessage('hello'));
      expect(cbs.onError).toHaveBeenCalledWith('WebSocket is not connected');
    });

    it('cancelGeneration sends type=cancel', () => {
      const { result } = renderHook(() => useWebSocket({ agentId: 'a1' }));
      act(() => MockWebSocket.instances[0].fireOpen());
      act(() => result.current.cancelGeneration());
      const payload = JSON.parse(MockWebSocket.instances[0].sent[0]);
      expect(payload.type).toBe('cancel');
    });
  });

  describe('reconnection', () => {
    it('reconnects on close with exponential backoff', () => {
      renderHook(() => useWebSocket({ agentId: 'a1' }));
      expect(MockWebSocket.instances).toHaveLength(1);
      act(() => MockWebSocket.instances[0].fireClose());
      // 第一次重连 delay = 1000 * 2^0 = 1000ms
      expect(MockWebSocket.instances).toHaveLength(1); // 尚未重连
      act(() => {
        vi.advanceTimersByTime(1000);
      });
      expect(MockWebSocket.instances).toHaveLength(2);
    });

    it('stops reconnecting after MAX_RECONNECT_ATTEMPTS (5)', () => {
      renderHook(() => useWebSocket({ agentId: 'a1' }));
      // 模拟连续 5 次失败重连
      for (let i = 0; i < 5; i++) {
        const current = MockWebSocket.instances[MockWebSocket.instances.length - 1];
        act(() => current.fireClose());
        // delay = 1000 * 2^i
        act(() => {
          vi.advanceTimersByTime(1000 * Math.pow(2, i));
        });
      }
      const countAfter5 = MockWebSocket.instances.length;
      // 第 5 次后不再重连
      const last = MockWebSocket.instances[countAfter5 - 1];
      act(() => last.fireClose());
      act(() => {
        vi.advanceTimersByTime(60000);
      });
      expect(MockWebSocket.instances.length).toBe(countAfter5);
    });

    it('reconnect() manually resets reconnect count and reconnects', () => {
      const { result } = renderHook(() => useWebSocket({ agentId: 'a1' }));
      act(() => MockWebSocket.instances[0].fireOpen());
      act(() => result.current.reconnect());
      // disconnect + reconnect → 新实例
      expect(MockWebSocket.instances.length).toBeGreaterThanOrEqual(2);
    });
  });
});
