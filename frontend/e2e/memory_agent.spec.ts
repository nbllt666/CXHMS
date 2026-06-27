import { test, expect } from '@playwright/test';

/**
 * MemoryAgentPage 前端 E2E 测试（SubTask 11.2）
 *
 * 页面路由：/memory-agent（见 src/App.tsx）
 * 关键 DOM 结构（基于 src/pages/MemoryAgentPage.tsx 调研）：
 *   - 页面标题：<h2>记忆管理助手</h2>（header 中）
 *   - 副标题：<p>通过自然语言管理记忆库</p>
 *   - 输入框：原生 <textarea>（非 Textarea 组件），placeholder="输入记忆管理指令..."
 *   - 发送方式：Enter 键（handleKeyDown 拦截 Enter/!shiftKey 调用 handleSend）。
 *     发送按钮只含 <Send> 图标（lucide-react），无可用文本，故用 Enter 触发。
 *   - 用户消息：<p className="whitespace-pre-wrap">{content}</p>
 *   - AI 消息：经 <MarkdownContent>（react-markdown）渲染为 <p>
 *   - 空状态：<h3>记忆管理助手</h3> + 示例指令列表（"搜索关于工作的记忆" 等）
 *   - 清空按钮：header 中 "清空对话" 按钮（文本可定位）
 *
 * 流式端点：POST /api/memory-agent/chat/stream（body: { message }）
 * FakeLLMClient 默认回复："收到：{user_text[:50]}"
 */

test.beforeEach(async ({ request }) => {
  // 清空 memory-agent 会话与 agent context，避免跨测试状态污染
  // 对齐 MemoryAgentPage.clearChat 的两个清理调用
  await request.delete(
    'http://localhost:8001/api/context/sessions/memory-agent/messages',
    { failOnStatusCode: false }
  );
  await request.delete(
    'http://localhost:8001/api/agents/memory-agent/context',
    { failOnStatusCode: false }
  );
});

test('记忆 agent 页面加载', async ({ page }) => {
  await page.goto('/memory-agent');

  // 等待页面标题可见（隐含 ConnectionCheck 已通过、MemoryAgentPage 已渲染）
  await expect(
    page.getByRole('heading', { name: '记忆管理助手', level: 2 })
  ).toBeVisible({ timeout: 20000 });

  // 输入框应可见
  const input = page.getByPlaceholder('输入记忆管理指令...');
  await expect(input).toBeVisible({ timeout: 20000 });

  // 空状态应显示示例指令列表
  await expect(page.getByText('搜索关于工作的记忆')).toBeVisible({ timeout: 10000 });
});

test('记忆 agent 聊天响应', async ({ page }) => {
  await page.goto('/memory-agent');

  const input = page.getByPlaceholder('输入记忆管理指令...');
  await expect(input).toBeVisible({ timeout: 20000 });

  // 输入并发送（用 Enter，发送按钮无可用文本选择器）
  await input.fill('你好');
  await input.press('Enter');

  // 等待用户消息渲染
  await expect(page.getByText('你好', { exact: true })).toBeVisible({ timeout: 15000 });

  // 等待 AI 流式回复完成（FakeLLMClient 默认回复："收到：你好"）
  await expect(page.getByText('收到：你好')).toBeVisible({ timeout: 15000 });
});

test.skip('agent 切换', async () => {
  // 跳过原因：MemoryAgentPage（src/pages/MemoryAgentPage.tsx）没有 agent 选择/切换组件。
  // 该页面硬编码使用 'memory-agent' agent（见 api.sendMemoryAgentMessageStream 调用），
  // UI 不暴露在多个 agent 之间切换的能力。
  // 若未来在 MemoryAgentPage 中增加 agent 选择器，可在此补充切换后界面更新的测试。
});
