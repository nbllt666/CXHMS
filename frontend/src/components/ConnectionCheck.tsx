import { useState, useEffect, useCallback } from 'react';
import { api } from '../api/client';

export function ConnectionCheck({ children }: { children: React.ReactNode }) {
  const [connected, setConnected] = useState<boolean | null>(null); // null = checking
  const [showConfig, setShowConfig] = useState(false);
  const [host, setHost] = useState('localhost');
  const [port, setPort] = useState('8000');
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<'success' | 'fail' | null>(null);

  // 从当前 API URL 解析 host/port
  useEffect(() => {
    const currentUrl = api.getApiUrl();
    try {
      const url = new URL(currentUrl);
      setHost(url.hostname);
      setPort(url.port || (url.protocol === 'https:' ? '443' : '80'));
    } catch {
      setHost('localhost');
      setPort('8000');
    }
  }, []);

  const checkConnection = useCallback(async () => {
    const ok = await api.checkHealth();
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
        if (ok) {
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
    setTestResult(ok ? 'success' : 'fail');
    setTesting(false);
  };

  const handleConnect = () => {
    const url = `http://${host}:${port}`;
    api.setBaseUrls(url);
    setConnected(null);
    // 重新检查
    api.checkHealth().then((ok) => {
      setConnected(ok);
      if (ok) {
        setShowConfig(false);
        window.location.reload();
      }
    });
  };

  if (connected === null && !showConfig) {
    return (
      <div className="flex items-center justify-center h-screen bg-gray-50 dark:bg-gray-900">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4" />
          <p className="text-gray-600 dark:text-gray-400">正在连接后端服务...</p>
        </div>
      </div>
    );
  }

  if (connected && !showConfig) {
    return <>{children}</>;
  }

  // 无法连接时显示配置界面
  return (
    <div className="flex items-center justify-center min-h-screen bg-gray-50 dark:bg-gray-900 p-4">
      <div className="w-full max-w-md">
        <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-xl p-8">
          {/* 图标 */}
          <div className="flex justify-center mb-6">
            <div className="w-16 h-16 rounded-full bg-red-100 dark:bg-red-900/30 flex items-center justify-center">
              <svg className="w-8 h-8 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
          </div>

          <h2 className="text-xl font-semibold text-center text-gray-900 dark:text-white mb-2">
            无法连接后端服务
          </h2>
          <p className="text-sm text-gray-500 dark:text-gray-400 text-center mb-6">
            请确认后端服务已启动，并输入正确的地址和端口
          </p>

          {/* 输入框 */}
          <div className="space-y-4">
            <div className="flex gap-3">
              <div className="flex-1">
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  主机地址
                </label>
                <input
                  type="text"
                  value={host}
                  onChange={(e) => setHost(e.target.value)}
                  placeholder="localhost"
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none"
                />
              </div>
              <div className="w-28">
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  端口
                </label>
                <input
                  type="text"
                  value={port}
                  onChange={(e) => setPort(e.target.value)}
                  placeholder="8000"
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none"
                />
              </div>
            </div>

            {/* 测试结果 */}
            {testResult && (
              <div className={`text-sm px-3 py-2 rounded-lg ${
                testResult === 'success'
                  ? 'bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-400'
                  : 'bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400'
              }`}>
                {testResult === 'success' ? '连接成功！' : '连接失败，请检查地址和端口'}
              </div>
            )}

            {/* 按钮 */}
            <div className="flex gap-3">
              <button
                onClick={handleTest}
                disabled={testing || !host || !port}
                className="flex-1 px-4 py-2 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {testing ? '测试中...' : '测试连接'}
              </button>
              <button
                onClick={handleConnect}
                disabled={!host || !port}
                className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                连接
              </button>
            </div>
          </div>

          {/* 自动重连提示 */}
          <p className="text-xs text-gray-400 dark:text-gray-500 text-center mt-4">
            系统将每 10 秒自动尝试重新连接
          </p>
        </div>
      </div>
    </div>
  );
}
