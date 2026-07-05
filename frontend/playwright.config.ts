import { defineConfig, devices } from '@playwright/test';

/**
 * CXHMS Playwright 配置
 *
 * 自动串起两个 webServer：
 *   1. 模拟后端（FastAPI + FakeLLMClient，端口 8001）
 *   2. Vite 前端开发服务器（端口 3000）
 *
 * 由于模拟后端是单例（内存状态），强制 workers: 1 与 fullyParallel: false
 * 避免并发请求互相污染上下文。
 */
export default defineConfig({
  testDir: './e2e',
  timeout: 60000,
  expect: {
    timeout: 10000,
  },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: 'http://localhost:3000',
    trace: 'on-first-retry',
    actionTimeout: 15000,
  },

  webServer: [
    {
      // 模拟后端：CXHMS_SIMULATION=1 启动 uvicorn，装配 FakeLLMClient 等假实现
      // 用 scripts/start_sim_backend.py 避免在 TS 中处理跨平台环境变量转义
      command: 'python scripts/start_sim_backend.py',
      url: 'http://localhost:8001/health',
      timeout: 30000,
      reuseExistingServer: true,
      cwd: 'c:\\CXHMS',
    },
    {
      command: 'npm run dev',
      url: 'http://localhost:3000',
      timeout: 30000,
      reuseExistingServer: true,
      cwd: 'c:\\CXHMS\\frontend',
    },
  ],

  projects: [
    {
      name: 'chromium',
      // 使用系统已安装的 Microsoft Edge（Chromium 内核，v149）作为浏览器，
      // 避免 Playwright CDN 下载 chromium 过慢。Edge 与 chromium 行为一致，
      // 不影响测试有效性。若后续 chromium 下载完成可移除 channel 字段。
      use: { ...devices['Desktop Chrome'], channel: 'msedge' },
    },
  ],
});
