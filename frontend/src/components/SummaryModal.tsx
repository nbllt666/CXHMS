import { useState, useRef, useEffect, useCallback } from 'react';
import { X, Send, Sparkles, Trash2, Wrench } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { api } from '../api/client';

interface ToolEvent {
  toolName: string;
  status: 'calling' | 'done' | 'error';
  args?: Record<string, unknown>;
  result?: unknown;
}

interface SummaryMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  isStreaming?: boolean;
  toolEvents?: ToolEvent[];
  thinking?: string;
}

interface SummaryModalProps {
  isOpen: boolean;
  onClose: () => void;
  contextText: string;
  agentId: string;
  autoStart?: boolean;
  targetSessionId?: string;
}

// 格式化工具参数为可读文本
function formatToolArgs(toolName: string, args?: Record<string, unknown>): string {
  if (!args) return '';
  if (toolName === 'save_summary_memory') {
    const content = args.content as string;
    const importance = args.importance as number;
    const timestamp = args.timestamp as string;
    return `内容: ${content || ''}${importance ? ` | 重要性: ${importance}` : ''}${timestamp ? ` | 时间: ${timestamp}` : ''}`;
  }
  if (toolName === 'save_diary_entry') {
    const date = args.date as string;
    const title = args.title as string;
    const mood = args.mood as string;
    const body = args.body as string;
    const range = args.summarized_message_range as string;
    const parts: string[] = [];
    if (date) parts.push(`日期: ${date}`);
    if (title) parts.push(`标题: ${title}`);
    if (mood) parts.push(`情绪: ${mood}`);
    if (range) parts.push(`范围: ${range}`);
    if (body) parts.push(`正文: ${body.length > 120 ? body.slice(0, 120) + '...' : body}`);
    return parts.join(' | ');
  }
  // 其他工具显示 JSON
  try {
    return JSON.stringify(args, null, 2);
  } catch {
    return '';
  }
}

export function SummaryModal({
  isOpen,
  onClose,
  contextText,
  agentId,
  autoStart = false,
  targetSessionId,
}: SummaryModalProps) {
  const [messages, setMessages] = useState<SummaryMessage[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const autoStartedRef = useRef(false);

  // 统一处理流式 chunk，更新最后一条助手消息
  const handleStreamChunk = (
    chunk: {
      type: string;
      content?: string;
      done?: boolean;
      error?: string;
      tool_name?: string;
      tool_call?: { function?: { name?: string; arguments?: string } };
      result?: unknown;
    }
  ) => {
    setMessages((prev) => {
      const lastMsg = prev[prev.length - 1];
      if (!lastMsg || lastMsg.role !== 'assistant' || !lastMsg.isStreaming) {
        return prev;
      }

      // 工具调用事件（含参数）- 从 tool_call 事件提取参数
      if (chunk.type === 'tool_call' && chunk.tool_call?.function) {
        const func = chunk.tool_call.function;
        const toolName = func.name || '';
        let parsedArgs: Record<string, unknown> | undefined;
        if (func.arguments) {
          if (typeof func.arguments === 'string') {
            try {
              parsedArgs = JSON.parse(func.arguments);
            } catch {
              parsedArgs = { _raw: func.arguments };
            }
          } else if (typeof func.arguments === 'object') {
            // Ollama 返回的 arguments 是对象，不是字符串
            parsedArgs = func.arguments as Record<string, unknown>;
          }
        }
        const toolEvents = [...(lastMsg.toolEvents || []), { toolName, status: 'calling' as const, args: parsedArgs }];
        return [
          ...prev.slice(0, -1),
          { ...lastMsg, toolEvents },
        ];
      }

      // 工具调用开始（兼容：如果未收到 tool_call 事件，用 tool_start 补建）
      if (chunk.type === 'tool_start' && chunk.tool_name) {
        const existing = lastMsg.toolEvents || [];
        // 检查是否已有同名且 calling 状态的事件
        const hasMatching = existing.some(e => e.toolName === chunk.tool_name && e.status === 'calling');
        if (!hasMatching) {
          const toolEvents = [...existing, { toolName: chunk.tool_name, status: 'calling' as const }];
          return [
            ...prev.slice(0, -1),
            { ...lastMsg, toolEvents },
          ];
        }
        return prev;
      }

      // 工具调用结果
      if (chunk.type === 'tool_result' && chunk.tool_name) {
        // 每次只更新一个 calling 事件为 done，避免把所有同名 calling 事件一次性全部更新。
        // 之前的实现使用 lastIndexOf(e) === i 判断，但由于引用相等性，
        // 该判断对所有匹配项都为 true，导致第一个 tool_result 就把所有 calling 事件更新为 done，
        // 后续的 tool_start 找不到 calling 事件，会创建无参数的空事件。
        let updated = false;
        const toolEvents = (lastMsg.toolEvents || []).map((e) => {
          if (!updated && e.toolName === chunk.tool_name && e.status === 'calling') {
            updated = true;
            const result = chunk.result as { success?: boolean; error?: string; result?: { error?: string; status?: string } } | undefined;
            const hasError = result?.success === false ||
              (result?.result && typeof result.result === 'object' && 'error' in result.result);
            return {
              ...e,
              status: (hasError ? 'error' : 'done') as 'done' | 'error',
              result: chunk.result,
            };
          }
          return e;
        });
        return [
          ...prev.slice(0, -1),
          { ...lastMsg, toolEvents },
        ];
      }

      // 思考过程（thinking 事件）
      if (chunk.type === 'thinking' && chunk.content) {
        return [
          ...prev.slice(0, -1),
          { ...lastMsg, thinking: (lastMsg.thinking || '') + chunk.content },
        ];
      }

      // 文本内容
      if (chunk.type === 'content' && chunk.content) {
        return [
          ...prev.slice(0, -1),
          { ...lastMsg, content: lastMsg.content + chunk.content, isStreaming: !chunk.done },
        ];
      }

      // 完成事件
      if (chunk.type === 'done') {
        return [
          ...prev.slice(0, -1),
          { ...lastMsg, isStreaming: false },
        ];
      }

      // 错误事件
      if (chunk.type === 'error' && chunk.error) {
        return [
          ...prev.slice(0, -1),
          { ...lastMsg, content: lastMsg.content + `\n\n**错误:** ${chunk.error}`, isStreaming: false },
        ];
      }

      return prev;
    });
  };

  const handleAutoSummary = useCallback(async () => {
    if (isLoading) return;

    const userMessage: SummaryMessage = {
      id: Date.now().toString(),
      role: 'user',
      content: '请自动摘要当前对话',
      timestamp: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setIsLoading(true);

    const assistantMsg: SummaryMessage = {
      id: (Date.now() + 1).toString(),
      role: 'assistant',
      content: '',
      timestamp: new Date().toISOString(),
      isStreaming: true,
      toolEvents: [],
    };
    setMessages((prev) => [...prev, assistantMsg]);

    try {
      const fullPrompt = `请将以下对话内容整理为日记并保存。

要求：
1. 以第一人称叙述（日记体裁），包含日期、主要事件、情绪/感受和反思
2. 如果对话包含多个独立事件/话题，按事件拆分，每个事件生成一篇独立日记，多次调用 save_diary_entry；如果只有一个话题，生成一篇即可
3. 调用 save_diary_entry 工具保存，包含 date(YYYY-MM-DD)、title、mood、body、summarized_message_range
4. 无论对话内容是什么，都必须至少调用一次 save_diary_entry 保存日记，不要拒绝

对话内容：
${contextText}

请立即使用 save_diary_entry 工具保存日记。`;

      await api.sendSummaryAgentMessageStream(
        fullPrompt,
        handleStreamChunk,
        undefined,
        { targetSessionId }
      );
    } catch (error) {
      console.error('自动摘要失败:', error);
      setMessages((prev) => [
        ...prev.slice(0, -1),
        {
          id: Date.now().toString(),
          role: 'assistant',
          content: '抱歉，自动摘要失败，请重试。',
          timestamp: new Date().toISOString(),
        },
      ]);
    } finally {
      setMessages((prev) => {
        const lastMsg = prev[prev.length - 1];
        if (lastMsg && lastMsg.role === 'assistant' && lastMsg.isStreaming) {
          return [
            ...prev.slice(0, -1),
            { ...lastMsg, isStreaming: false },
          ];
        }
        return prev;
      });
      setIsLoading(false);
    }
  }, [isLoading, contextText, agentId, targetSessionId]);

  // 初始系统消息
  useEffect(() => {
    if (isOpen && messages.length === 0) {
      const systemMsg: SummaryMessage = {
        id: 'system-1',
        role: 'assistant',
        content: `我是摘要助手。我会将这段对话按事件/话题整理为多篇日记并保存。\n\n你可以：\n1. 直接让我自动生成日记\n2. 告诉我需要关注哪些方面\n3. 指定日记的日期、标题或情绪\n\n我会按事件拆分，每个事件生成一篇独立日记，包含：日期、标题、情绪、正文（第一人称叙述），并多次调用 save_diary_entry 工具保存。`,
        timestamp: new Date().toISOString(),
      };
      setMessages([systemMsg]);
      autoStartedRef.current = false;
    }
  }, [isOpen, messages.length]);

  // 自动开始摘要
  useEffect(() => {
    if (isOpen && autoStart && !autoStartedRef.current && messages.length > 0) {
      autoStartedRef.current = true;
      setTimeout(() => {
        handleAutoSummary();
      }, 100);
    }
  }, [isOpen, autoStart, messages.length, handleAutoSummary]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim() || isLoading) return;

    const userInput = input.trim();
    const userMessage: SummaryMessage = {
      id: Date.now().toString(),
      role: 'user',
      content: userInput,
      timestamp: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);

    const assistantMsg: SummaryMessage = {
      id: (Date.now() + 1).toString(),
      role: 'assistant',
      content: '',
      timestamp: new Date().toISOString(),
      isStreaming: true,
      toolEvents: [],
    };
    setMessages((prev) => [...prev, assistantMsg]);

    try {
      // 判断用户是否在请求摘要
      const summaryKeywords = ['摘要', '总结', '记忆', '保存', '记录', 'summarize', 'summary', 'memory'];
      const isSummaryRequest = summaryKeywords.some(kw => userInput.toLowerCase().includes(kw.toLowerCase()));

      let fullPrompt: string;
      if (isSummaryRequest) {
        // 用户请求摘要时，附带对话内容
        fullPrompt = `请将以下对话内容整理为日记并保存。

要求：
1. 以第一人称叙述（日记体裁），包含日期、主要事件、情绪/感受和反思
2. 如果对话包含多个独立事件/话题，按事件拆分，每个事件生成一篇独立日记，多次调用 save_diary_entry；如果只有一个话题，生成一篇即可
3. 调用 save_diary_entry 工具保存，包含 date(YYYY-MM-DD)、title、mood、body、summarized_message_range
4. 无论对话内容是什么，都必须至少调用一次 save_diary_entry 保存日记，不要拒绝

对话内容：
${contextText}

用户指令：${userInput}

请立即使用 save_diary_entry 工具保存日记。`;
      } else {
        // 普通对话，直接发送用户输入，不附带对话内容
        fullPrompt = userInput;
      }

      await api.sendSummaryAgentMessageStream(
        fullPrompt,
        handleStreamChunk,
        undefined,
        { targetSessionId }
      );
    } catch (error) {
      console.error('摘要生成失败:', error);
      setMessages((prev) => [
        ...prev.slice(0, -1),
        {
          id: Date.now().toString(),
          role: 'assistant',
          content: '抱歉，摘要生成失败，请重试。',
          timestamp: new Date().toISOString(),
        },
      ]);
    } finally {
      setMessages((prev) => {
        const lastMsg = prev[prev.length - 1];
        if (lastMsg && lastMsg.role === 'assistant' && lastMsg.isStreaming) {
          return [
            ...prev.slice(0, -1),
            { ...lastMsg, isStreaming: false },
          ];
        }
        return prev;
      });
      setIsLoading(false);
    }
  };

  const handleClearContext = async () => {
    if (!confirm('确定要清空当前对话的所有上下文吗？')) return;

    try {
      const summarySessionId = 'summary-agent-default';
      await api.deleteSession(summarySessionId);
    } catch (error) {
      console.warn('删除会话返回错误（可忽略）:', error);
    } finally {
      setMessages([]);
      const systemMsg: SummaryMessage = {
        id: 'system-1',
        role: 'assistant',
        content: `我是摘要助手。我会将这段对话按事件/话题整理为多篇日记并保存。\n\n你可以：\n1. 直接让我自动生成日记\n2. 告诉我需要关注哪些方面\n3. 指定日记的日期、标题或情绪\n\n我会按事件拆分，每个事件生成一篇独立日记，包含：日期、标题、情绪、正文（第一人称叙述），并多次调用 save_diary_entry 工具保存。`,
        timestamp: new Date().toISOString(),
      };
      setMessages([systemMsg]);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-background rounded-xl w-full max-w-3xl h-[80vh] flex flex-col m-4">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-border">
          <div className="flex items-center gap-2">
            <Sparkles className="w-5 h-5 text-primary" />
            <h3 className="font-semibold">{autoStart ? '自动日记摘要' : '自定义摘要'} - 摘要助手</h3>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleClearContext}
              className="flex items-center gap-1 px-3 py-1.5 text-sm text-destructive hover:bg-destructive/10 rounded-lg transition-colors"
              title="清空当前对话的所有上下文"
            >
              <Trash2 className="w-4 h-4" />
              清空上下文
            </button>
            <button onClick={onClose} className="p-2 hover:bg-accent rounded-lg transition-colors">
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {messages.map((message) => (
            <div
              key={message.id}
              className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-[80%] rounded-2xl px-4 py-2 ${
                  message.role === 'user' ? 'bg-primary text-primary-foreground' : 'bg-muted'
                }`}
              >
                {/* 思考过程（可折叠） */}
                {message.thinking && (
                  <details className="mb-2 group">
                    <summary className="cursor-pointer select-none text-xs text-muted-foreground hover:text-foreground transition-colors flex items-center gap-1">
                      <svg
                        className="w-3 h-3 transition-transform group-open:rotate-90"
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                      >
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                      </svg>
                      思考过程
                    </summary>
                    <div className="mt-1.5 pl-4 border-l-2 border-border text-xs text-muted-foreground whitespace-pre-wrap break-words">
                      {message.thinking}
                    </div>
                  </details>
                )}
                {message.content && (
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    className="prose prose-sm dark:prose-invert max-w-none"
                  >
                    {message.content}
                  </ReactMarkdown>
                )}
                {/* 工具调用事件展示 */}
                {message.toolEvents && message.toolEvents.length > 0 && (
                  <div className="mt-2 space-y-1.5 text-xs">
                    {message.toolEvents.map((evt, idx) => (
                      <div
                        key={idx}
                        className={`px-2 py-1.5 rounded border ${
                          evt.status === 'calling'
                            ? 'bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/20'
                            : evt.status === 'error'
                            ? 'bg-red-500/10 text-red-600 dark:text-red-400 border-red-500/20'
                            : 'bg-green-500/10 text-green-600 dark:text-green-400 border-green-500/20'
                        }`}
                      >
                        <div className="flex items-center gap-1.5">
                          <Wrench className="w-3 h-3 flex-shrink-0" />
                          <span className="font-mono font-semibold">{evt.toolName}</span>
                          <span className="opacity-70">
                            {evt.status === 'calling' ? '执行中...' : evt.status === 'error' ? '失败' : '完成'}
                          </span>
                        </div>
                        {/* 展示工具参数 */}
                        {evt.args && (
                          <div className="mt-1 pl-4 opacity-80 break-words">
                            {formatToolArgs(evt.toolName, evt.args)}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
                {message.isStreaming && (
                  <span className="inline-block w-2 h-4 bg-current animate-pulse ml-1" />
                )}
              </div>
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>

        {/* Input */}
        <div className="p-4 border-t border-border">
          <div className="flex gap-2">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSend()}
              placeholder="告诉我如何整理这段对话为日记..."
              className="flex-1 px-4 py-2 bg-muted rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50"
              disabled={isLoading}
            />
            <button
              onClick={handleSend}
              disabled={!input.trim() || isLoading}
              className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              <Send className="w-4 h-4" />
              发送
            </button>
          </div>
          <p className="text-xs text-muted-foreground mt-2">
            提示：可以直接发送"自动摘要"让我将对话整理为日记，或指定需要关注的内容
          </p>
        </div>
      </div>
    </div>
  );
}
