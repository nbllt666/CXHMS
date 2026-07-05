import { useState, useEffect, useCallback, useRef } from 'react';
import { api } from '../api';

export function ConnectionCheck({ children }: { children: React.ReactNode }) {
  const [connected, setConnected] = useState<boolean | null>(null); // null = checking
  const [showConfig, setShowConfig] = useState(false);
  const [host, setHost] = useState('localhost');
  const [port, setPort] = useState('8001');
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<'success' | 'fail' | null>(null);
  const isMountedRef = useRef(true);

  useEffect(() => {
    // 在 effect 体中重置为 true，确保 React StrictMode 重新挂载时 ref 状态正确
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  // 从当前 API URL 解析 host/port
  useEffect(() => {
    const currentUrl = api.getApiUrl();
    try {
      const url = new URL(currentUrl);
      setHost(url.hostname);
      setPort(url.port || (url.protocol === 'https:' ? '443' : '80'));
    } catch {
      setHost('localhost');
      setPort('8001');
    }
  }, []);

  const checkConnection = useCallback(async () => {
    const ok = await api.checkHealth();
    if (!isMountedRef.current) return;
    setConnected(ok);
    if (!ok) {
      setShowConfig(true);
    }
  }, []);

  useEffect(() => {
    checkConnection();
    // 每 10 秒重试连接
    const interval = setInterval(async () => {
      if (!connected) {
        const ok = await api.checkHealth();
        if (ok && isMountedRef.current) {
          setConnected(true);
          setShowConfig(false);
        }
      }
    }, 10000);
    return () => clearInterval(interval);
  }, [checkConnection, connected]);

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    const url = `http://${host}:${port}`;
    const ok = await api.checkHealth(url);
    if (!isMountedRef.current) return;
    setTestResult(ok ? 'success' : 'fail');
    setTesting(false);
  };

  const handleConnect = () => {
    const url = `http://${host}:${port}`;
    api.setBaseUrls(url);
    setConnected(null);
    // 重新检查
    api.checkHealth().then((ok) => {
      if (!isMountedRef.current) return;
      setConnected(ok);
      if (ok) {
        setShowConfig(false);
        window.location.reload();
      }
    });
  };

  const handleUseProxy = () => {
    // 清除自定义地址，使用 Vite 代理
    api.setBaseUrls('');
    localStorage.removeItem('cxhms-api-url');
    setConnected(null);
    api.checkHealth().then((ok) => {
      if (!isMountedRef.current) return;
      setConnected(ok);
      if (ok) {
        setShowConfig(false);
        window.location.reload();
      }
    });
  };

  if (connected === null && !showConfig) {
    return (
      // F6: 统一 CSS 变量，移除 bg-gray-50/dark:bg-gray-900 与硬编码颜色
      <div className="flex items-center justify-center h-screen bg-[var(--color-bg-secondary)]">
        <div className="text-center">
          <div
            className="animate-spin rounded-full h-12 w-12 border-b-2 mx-auto mb-4"
            style={{ borderColor: 'var(--color-accent)' }}
          />
          <p className="text-[var(--color-text-secondary)]">正在连接后端服务...</p>
        </div>
      </div>
    );
  }

  if (connected && !showConfig) {
    return <>{children}</>;
  }

  // 无法连接时显示配置界面
  return (
    <div className="flex items-center justify-center min-h-screen bg-[var(--color-bg-secondary)] p-4">
      <div className="w-full max-w-md">
        <div className="bg-[var(--color-bg-primary)] rounded-2xl shadow-lg p-8">
          {/* 图标 */}
          <div className="flex justify-center mb-6">
            <div
              className="w-16 h-16 rounded-full flex items-center justify-center"
              style={{ backgroundColor: 'var(--color-error-light)' }}
            >
              <svg
                className="w-8 h-8"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
                style={{ color: 'var(--color-error)' }}
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                />
              </svg>
            </div>
          </div>

          <h2 className="text-xl font-semibold text-center text-[var(--color-text-primary)] mb-2">
            无法连接后端服务
          </h2>
          <p className="text-sm text-[var(--color-text-secondary)] text-center mb-6">
            请确认后端服务已启动，并输入正确的地址和端口
          </p>

          {/* 输入框 */}
          <div className="space-y-4">
            <div className="flex gap-3">
              <div className="flex-1">
                <label className="block text-sm font-medium text-[var(--color-text-secondary)] mb-1">
                  主机地址
                </label>
                <input
                  type="text"
                  value={host}
                  onChange={(e) => setHost(e.target.value)}
                  placeholder="localhost"
                  className="w-full px-3 py-2 border border-[var(--color-border)] rounded-lg bg-[var(--color-bg-primary)] text-[var(--color-text-primary)] focus:ring-2 focus:border-transparent outline-none"
                  style={{ '--tw-ring-color': 'var(--color-accent)' } as React.CSSProperties}
                />
              </div>
              <div className="w-28">
                <label className="block text-sm font-medium text-[var(--color-text-secondary)] mb-1">
                  端口
                </label>
                <input
                  type="text"
                  value={port}
                  onChange={(e) => setPort(e.target.value)}
                  placeholder="8001"
                  className="w-full px-3 py-2 border border-[var(--color-border)] rounded-lg bg-[var(--color-bg-primary)] text-[var(--color-text-primary)] focus:ring-2 focus:border-transparent outline-none"
                  style={{ '--tw-ring-color': 'var(--color-accent)' } as React.CSSProperties}
                />
              </div>
            </div>

            {/* 测试结果 */}
            {testResult && (
              <div
                className="text-sm px-3 py-2 rounded-lg"
                style={{
                  backgroundColor:
                    testResult === 'success'
                      ? 'var(--color-success-light)'
                      : 'var(--color-error-light)',
                  color:
                    testResult === 'success'
                      ? 'var(--color-success)'
                      : 'var(--color-error)',
                }}
              >
                {testResult === 'success' ? '连接成功！' : '连接失败，请检查地址和端口'}
              </div>
            )}

            {/* 按钮 */}
            <div className="flex gap-3">
              <button
                onClick={handleTest}
                disabled={testing || !host || !port}
                className="flex-1 px-4 py-2 border border-[var(--color-border)] text-[var(--color-text-secondary)] rounded-lg hover:bg-[var(--color-bg-hover)] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {testing ? '测试中...' : '测试连接'}
              </button>
              <button
                onClick={handleConnect}
                disabled={!host || !port}
                className="flex-1 px-4 py-2 text-white rounded-lg hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed transition-opacity"
                style={{ backgroundColor: 'var(--color-accent)' }}
              >
                连接
              </button>
            </div>
            <button
              onClick={handleUseProxy}
              className="w-full px-4 py-2 border rounded-lg hover:bg-[var(--color-accent-light)] transition-colors text-sm"
              style={{
                borderColor: 'var(--color-accent)',
                color: 'var(--color-accent)',
              }}
            >
              使用代理连接（推荐）
            </button>
          </div>

          {/* 自动重连提示 */}
          <p className="text-xs text-[var(--color-text-muted)] text-center mt-4">
            系统将每 10 秒自动尝试重新连接
          </p>
        </div>
      </div>
    </div>
  );
}
