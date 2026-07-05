// ========== Vitest 独立配置 ==========
// G6: vite.config.ts 不含 test 字段，故独立配置。
// 与 vite.config.ts 的 resolve.alias 保持一致（@ → ./src），供测试文件复用路径别名。
// 覆盖率阈值（units > 80%）由 I1 全量回归阶段验证，本配置仅声明 provider/reporter，不强制 threshold。

import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __dirname = fileURLToPath(new URL('.', import.meta.url));

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    // 兼容现有 .test.tsx 风格（直接使用 describe/it/expect 而无需 import）
    globals: true,
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html'],
      // 阈值不在本任务强制（由 I1 验证 units > 80%）
    },
  },
});
