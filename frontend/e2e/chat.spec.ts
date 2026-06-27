import { test, expect } from '@playwright/test';

/**
 * ChatPage 前端 E2E 测试（SubTask 11.1）
 *
 * 页面路由：/chat（见 src/App.tsx）
 * 关键 DOM 结构（基于 src/pages/ChatPage.tsx 调研）：
 *   - 输入框：<Textarea>（src/components/ui/Input.tsx）渲染为 <textarea>，
 *     placeholder = "给 {agent.name || '助手'} 发送消息..."
 *   - 发送方式：Enter 键（handleKeyDown 拦截 Enter/!shiftKey 调用 handleSend）。
 *     发送按钮只含 SVG 图标，无可用文本，故采用 Enter 触发。
 *   - 用户消息气泡：<p className="whitespace-pre-wrap">{content}</p>
 *   - AI 消息气泡：经 <MarkdownContent>（react-markdown）渲染，纯文本时为 <p>
 *   - 清空按钮：PageHeader actions 中的 "清空上下文" Button（文本可定位）
 *     触发 confirm() + alert() 对话框，需 page.on('dialog') 自动接受
 *   - 空状态：messages.length === 0 时渲染 <h3>开始对话</h3>
 *   - ConnectionCheck 包装：后端未就绪时显示 "正在连接后端服务..." 加载态，
 *     就绪后渲染子路由。
 *
 * FakeLLMClient 行为（见 backend/tests/simulation/fakes/fake_llm.py）：
 *   - 默认回复："收到：{user_text[:50]}"
 *   - 上下文感知："我叫X" → "我叫什么" 返回 "你叫X"
 *   - 无历史时："我叫什么" 返回 "我还不知道你的名字"
 */

test.beforeEach(async ({ request }) => {
  // 确保每个测试以干净的后端会话开始，避免跨测试状态污染模拟后端单例
  // sessionId 派生规则见 ChatPage.handleClearContext：`agent-${currentAgentId || 'default'}`
  await request.delete(
    'http://localhost:8001/api/context/sessions/agent-default/messages',
    { failOnStatusCode: false }
  );
});

test('流式聊天响应正确渲染', async ({ page }) => {
  await page.goto('/chat');

  // 等待输入框可见（隐含 ConnectionCheck 已通过、ChatPage 已渲染）
  const input = page.getByPlaceholder(/发送消息/);
  await expect(input).toBeVisible({ timeout: 20000 });

  // 输入并发送（用 Enter，发送按钮无可用文本选择器）
  await input.fill('你好');
  await input.press('Enter');

  // 等待用户消息渲染
  await expect(page.getByText('你好', { exact: true })).toBeVisible({ timeout: 15000 });

  // 等待 AI 流式回复完成（FakeLLMClient 默认回复："收到：你好"）
  await expect(page.getByText('收到：你好')).toBeVisible({ timeout: 15000 });
});

test('多轮对话上下文保持', async ({ page }) => {
  await page.goto('/chat');

  const input = page.getByPlaceholder(/发送消息/);
  await expect(input).toBeVisible({ timeout: 20000 });

  // 第一轮：声明名字（默认回复："收到：我叫小明"）
  await input.fill('我叫小明');
  await input.press('Enter');
  await expect(page.getByText('收到：我叫小明')).toBeVisible({ timeout: 15000 });

  // 第二轮：询问名字（FakeLLMClient 从历史回溯："你叫小明"）
  await input.fill('我叫什么');
  await input.press('Enter');
  await expect(page.getByText('你叫小明')).toBeVisible({ timeout: 15000 });
});

test('新会话清空上下文', async ({ page }) => {
  await page.goto('/chat');

  const input = page.getByPlaceholder(/发送消息/);
  await expect(input).toBeVisible({ timeout: 20000 });

  // 先建立上下文：声明名字 + 验证回溯成功（证明上下文确实生效）
  await input.fill('我叫小明');
  await input.press('Enter');
  await expect(page.getByText('收到：我叫小明')).toBeVisible({ timeout: 15000 });

  await input.fill('我叫什么');
  await input.press('Enter');
  await expect(page.getByText('你叫小明')).toBeVisible({ timeout: 15000 });

  // 点击 "清空上下文" 按钮（handleClearContext 触发 confirm + alert 两个对话框）
  page.on('dialog', (dialog) => dialog.accept());
  await page.getByRole('button', { name: '清空上下文' }).click();

  // 等待消息列表清空（messages=[] → 空状态 "开始对话" 出现）
  await expect(page.getByText('开始对话', { exact: true })).toBeVisible({ timeout: 15000 });

  // 再次询问名字 — 清空上下文后对话历史被清除
  // 注意：聊天路由不自动写记忆，所以记忆库中没有"我叫小明"的条目
  // （真实系统中记忆需通过 memory-agent 或显式 API 写入）
  // FakeLLMClient 找不到历史或记忆中的名字，返回"我还不知道你的名字"
  await input.fill('我叫什么');
  await input.press('Enter');
  await expect(page.getByText('我还不知道你的名字')).toBeVisible({ timeout: 15000 });
});
