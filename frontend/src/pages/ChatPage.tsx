import { useState, useRef, useEffect, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { api } from '../api/client';
import { useChatStore } from '../store/chatStore';
import { formatRelativeTime } from '../lib/utils';
import { SummaryModal } from '../components/SummaryModal';
import { Button, Textarea, Card } from '../components/ui';
import { PageHeader } from '../components/layout';
import { useWebSocket } from '../hooks/useWebSocket';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  memory_refs?: number[];
  tool_calls?: ToolCall[];
  thinking?: string;
  images?: string[]; // base64 encoded images
}

interface ToolCall {
  id: string;
  name: string;
  arguments?: unknown;
  result?: unknown;
  status?: 'pending' | 'executing' | 'completed' | 'failed';
}

interface StreamToolCall {
  id?: string;
  name?: string;
  arguments?: unknown;
  function?: {
    name?: string;
    arguments?: unknown;
  };
}

function MarkdownContent({ content }: { content: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      className="prose prose-sm max-w-none dark:prose-invert"
      components={{
        code({
          inline,
          className,
          children,
          ...props
        }: {
          inline?: boolean;
          className?: string;
          children?: React.ReactNode;
        }) {
          return !inline ? (
            <pre className="bg-[var(--color-bg-tertiary)] rounded-[var(--radius-md)] p-3 overflow-x-auto text-sm">
              <code className={className} {...props}>
                {children}
              </code>
            </pre>
          ) : (
            <code
              className="bg-[var(--color-bg-tertiary)] px-1.5 py-0.5 rounded text-sm"
              {...props}
            >
              {children}
            </code>
          );
        },
        table({ children }) {
          return (
            <div className="overflow-x-auto">
              <table className="min-w-full border-collapse border border-[var(--color-border)]">
                {children}
              </table>
            </div>
          );
        },
        th({ children }) {
          return (
            <th className="border border-[var(--color-border)] px-4 py-2 bg-[var(--color-bg-tertiary)] font-semibold">
              {children}
            </th>
          );
        },
        td({ children }) {
          return <td className="border border-[var(--color-border)] px-4 py-2">{children}</td>;
        },
      }}
    >
      {content}
    </ReactMarkdown>
  );
}

function ThinkingProcess({ thinking, toolCalls }: { thinking?: string; toolCalls?: ToolCall[] }) {
  const [isExpanded, setIsExpanded] = useState(false);

  if (!thinking && (!toolCalls || toolCalls.length === 0)) return null;

  return (
    <div className="mt-3 border border-[var(--color-border)] rounded-[var(--radius-md)] overflow-hidden">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center justify-between px-3 py-2 bg-[var(--color-bg-tertiary)] hover:bg-[var(--color-bg-hover)] transition-colors text-xs text-[var(--color-text-secondary)]"
      >
        <span className="flex items-center gap-2">
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"
            />
          </svg>
          思考过程
          {toolCalls && toolCalls.length > 0 && (
            <span className="px-1.5 py-0.5 bg-[var(--color-accent-light)] text-[var(--color-accent)] rounded-full text-[10px]">
              {toolCalls.length} 个工具调用
            </span>
          )}
        </span>
        <svg
          className={`w-4 h-4 transition-transform ${isExpanded ? 'rotate-180' : ''}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {isExpanded && (
        <div className="px-3 py-2 bg-[var(--color-bg-secondary)] text-xs space-y-2">
          {thinking && (
            <div className="text-[var(--color-text-tertiary)] whitespace-pre-wrap">{thinking}</div>
          )}

          {toolCalls && toolCalls.length > 0 && (
            <div className="space-y-2">
              {toolCalls.map((toolCall, idx) => (
                <div
                  key={idx}
                  className="p-2 bg-[var(--color-bg-tertiary)] rounded border border-[var(--color-border)]"
                >
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-medium text-[var(--color-text-primary)]">
                      🔧 {toolCall.name}
                    </span>
                    {toolCall.status === 'executing' && (
                      <span className="animate-pulse text-[var(--color-info)]">执行中...</span>
                    )}
                    {toolCall.status === 'completed' && (
                      <span className="text-[var(--color-success)]">✓ 完成</span>
                    )}
                    {toolCall.status === 'failed' && (
                      <span className="text-[var(--color-error)]">✗ 失败</span>
                    )}
                  </div>
                  {Boolean(toolCall.arguments) && (
                    <div className="text-[var(--color-text-tertiary)] font-mono text-[10px] mb-1">
                      参数: {JSON.stringify(toolCall.arguments, null, 2)}
                    </div>
                  )}
                  {toolCall.result !== undefined && (
                    <div className="text-[var(--color-text-tertiary)] font-mono text-[10px]">
                      结果: {JSON.stringify(toolCall.result, null, 2)}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [showSummaryModal, setShowSummaryModal] = useState(false);
  const [autoStartSummary, setAutoStartSummary] = useState(false);
  const [selectedImages, setSelectedImages] = useState<string[]>([]);
  const [alarms, setAlarms] = useState<{ message: string; triggeredAt: string }[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const tempAssistantIdRef = useRef<string>('');

  const { agents, currentAgentId, fetchAgents } = useChatStore();

  const handleWebSocketMessage = useCallback(
    (data: {
      type: string;
      content?: string;
      done?: boolean;
      error?: string;
      tool_call?: Record<string, unknown>;
      tool_name?: string;
      result?: unknown;
      thinking?: string;
    }) => {
      if (data.type === 'content' && data.content) {
        setMessages((prev) => {
          const lastMsg = prev[prev.length - 1];
          if (lastMsg && lastMsg.id === tempAssistantIdRef.current) {
            return [
              ...prev.slice(0, -1),
              {
                ...lastMsg,
                content: lastMsg.content + data.content!,
              },
            ];
          }
          return prev;
        });
      } else if (data.type === 'tool_call' && data.tool_call) {
        const tc = data.tool_call as StreamToolCall;
        setMessages((prev) => {
          const lastMsg = prev[prev.length - 1];
          if (lastMsg && lastMsg.id === tempAssistantIdRef.current) {
            return [
              ...prev.slice(0, -1),
              {
                ...lastMsg,
                tool_calls: [
                  ...(lastMsg.tool_calls || []),
                  {
                    id: tc.id || Date.now().toString(),
                    name: tc.name || tc.function?.name || 'unknown',
                    arguments: tc.arguments || tc.function?.arguments,
                    status: 'pending',
                  },
                ],
              },
            ];
          }
          return prev;
        });
      } else if (data.type === 'tool_start' && data.tool_name) {
        setMessages((prev) => {
          const lastMsg = prev[prev.length - 1];
          if (lastMsg && lastMsg.id === tempAssistantIdRef.current && lastMsg.tool_calls) {
            return [
              ...prev.slice(0, -1),
              {
                ...lastMsg,
                tool_calls: lastMsg.tool_calls.map((tc) =>
                  tc.name === data.tool_name ? { ...tc, status: 'executing' } : tc
                ),
              },
            ];
          }
          return prev;
        });
      } else if (data.type === 'tool_result' && data.tool_name && data.result !== undefined) {
        setMessages((prev) => {
          const lastMsg = prev[prev.length - 1];
          if (lastMsg && lastMsg.id === tempAssistantIdRef.current && lastMsg.tool_calls) {
            const updatedToolCalls: ToolCall[] = lastMsg.tool_calls.map((tc) =>
              tc.name === data.tool_name
                ? { ...tc, status: 'completed' as const, result: data.result }
                : tc
            );
            return [
              ...prev.slice(0, -1),
              {
                ...lastMsg,
                tool_calls: updatedToolCalls,
              },
            ];
          }
          return prev;
        });
      } else if (data.type === 'thinking' && data.content) {
        setMessages((prev) => {
          const lastMsg = prev[prev.length - 1];
          if (lastMsg && lastMsg.id === tempAssistantIdRef.current) {
            return [
              ...prev.slice(0, -1),
              {
                ...lastMsg,
                thinking: (lastMsg.thinking || '') + data.content,
              },
            ];
          }
          return prev;
        });
      } else if (data.type === 'done') {
        setIsLoading(false);
        setMessages((prev) => {
          const lastMsg = prev[prev.length - 1];
          if (lastMsg && lastMsg.id === tempAssistantIdRef.current) {
            return [
              ...prev.slice(0, -1),
              {
                ...lastMsg,
                content: lastMsg.content || '响应已完成',
              },
            ];
          }
          return prev;
        });
      } else if (data.type === 'error') {
        setIsLoading(false);
        setMessages((prev) => {
          const lastMsg = prev[prev.length - 1];
          if (lastMsg && lastMsg.id === tempAssistantIdRef.current) {
            return [
              ...prev.slice(0, -1),
              {
                ...lastMsg,
                content: `抱歉，发生错误：${data.error || '未知错误'}`,
              },
            ];
          }
          return prev;
        });
      } else if (data.type === 'cancelled') {
        setIsLoading(false);
        setMessages((prev) => {
          const lastMsg = prev[prev.length - 1];
          if (lastMsg && lastMsg.id === tempAssistantIdRef.current) {
            return [
              ...prev.slice(0, -1),
              {
                ...lastMsg,
                content: lastMsg.content || '响应已取消',
              },
            ];
          }
          return prev;
        });
      }
    },
    []
  );

  const handleAlarm = useCallback((message: string, triggeredAt: string) => {
    setAlarms((prev) => [...prev, { message, triggeredAt }]);
    setTimeout(() => {
      setAlarms((prev) => prev.slice(1));
    }, 5000);
  }, []);

  const {
    isConnected,
    sendMessage: wsSendMessage,
    cancelGeneration,
  } = useWebSocket({
    agentId: currentAgentId || 'default',
    timeout: 60,
    onMessage: handleWebSocketMessage,
    onAlarm: handleAlarm,
    onError: (error) => {
      console.error('WebSocket error:', error);
      setIsLoading(false);
    },
  });

  useEffect(() => {
    fetchAgents();
  }, [fetchAgents]);

  const currentAgent = agents.find((a) => a.id === currentAgentId);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (currentAgentId) {
      loadAgentHistory(currentAgentId);
    } else {
      setMessages([]);
    }
  }, [currentAgentId]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  // 只在用户发送消息或AI开始响应时自动滚动
  const [shouldAutoScroll, setShouldAutoScroll] = useState(false);

  useEffect(() => {
    if (shouldAutoScroll) {
      scrollToBottom();
      setShouldAutoScroll(false);
    }
  }, [messages, shouldAutoScroll]);

  const loadAgentHistory = async (agentId: string) => {
    try {
      const data = await api.getChatHistory(agentId);
      if (data.messages) {
        const formattedMessages = data.messages.map(
          (msg: {
            id?: string;
            role: 'user' | 'assistant';
            content: string;
            created_at?: string;
            thinking?: string;
            images?: string[];
          }) => ({
            id: msg.id || Math.random().toString(),
            role: msg.role,
            content: msg.content,
            timestamp: msg.created_at || new Date().toISOString(),
            thinking: msg.thinking,
            images: msg.images,
          })
        );
        setMessages(formattedMessages);
      }
    } catch (error) {
      console.error('加载历史消息失败:', error);
      setMessages([]);
    }
  };

  const handleImageSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files) return;

    Array.from(files).forEach((file) => {
      if (!file.type.startsWith('image/')) return;
      if (selectedImages.length >= 4) {
        alert('最多只能上传4张图片');
        return;
      }

      const reader = new FileReader();
      reader.onload = (event) => {
        const base64 = event.target?.result as string;
        setSelectedImages((prev) => [...prev, base64]);
      };
      reader.readAsDataURL(file);
    });

    e.target.value = '';
  };

  const removeImage = (index: number) => {
    setSelectedImages((prev) => prev.filter((_, i) => i !== index));
  };

  const handleSend = async () => {
    if ((!input.trim() && selectedImages.length === 0) || isLoading) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: input,
      timestamp: new Date().toISOString(),
      images: selectedImages.length > 0 ? selectedImages : undefined,
    };

    const tempAssistantId = (Date.now() + 1).toString();
    tempAssistantIdRef.current = tempAssistantId;
    const streamingMessage: Message = {
      id: tempAssistantId,
      role: 'assistant',
      content: '',
      timestamp: new Date().toISOString(),
      tool_calls: [],
      thinking: '',
    };

    setMessages((prev) => [...prev, userMessage, streamingMessage]);
    setInput('');
    setSelectedImages([]);
    setIsLoading(true);
    setShouldAutoScroll(true);

    if (isConnected) {
      wsSendMessage(userMessage.content, userMessage.images);
    } else {
      try {
        await api.sendMessageStream(
          userMessage.content,
          (chunk) => {
            if (chunk.type === 'content' && chunk.content) {
              setMessages((prev) => {
                const lastMsg = prev[prev.length - 1];
                if (lastMsg && lastMsg.id === tempAssistantId) {
                  return [
                    ...prev.slice(0, -1),
                    {
                      ...lastMsg,
                      content: lastMsg.content + chunk.content!,
                    },
                  ];
                }
                return prev;
              });
            } else if (chunk.type === 'tool_call' && chunk.tool_call) {
              const tc = chunk.tool_call as StreamToolCall;
              setMessages((prev) => {
                const lastMsg = prev[prev.length - 1];
                if (lastMsg && lastMsg.id === tempAssistantId) {
                  return [
                    ...prev.slice(0, -1),
                    {
                      ...lastMsg,
                      tool_calls: [
                        ...(lastMsg.tool_calls || []),
                        {
                          id: tc.id || Date.now().toString(),
                          name: tc.name || tc.function?.name || 'unknown',
                          arguments: tc.arguments || tc.function?.arguments,
                          status: 'pending',
                        },
                      ],
                    },
                  ];
                }
                return prev;
              });
            } else if (chunk.type === 'tool_start' && chunk.tool_name) {
              setMessages((prev) => {
                const lastMsg = prev[prev.length - 1];
                if (lastMsg && lastMsg.id === tempAssistantId && lastMsg.tool_calls) {
                  return [
                    ...prev.slice(0, -1),
                    {
                      ...lastMsg,
                      tool_calls: lastMsg.tool_calls.map((tc) =>
                        tc.name === chunk.tool_name ? { ...tc, status: 'executing' } : tc
                      ),
                    },
                  ];
                }
                return prev;
              });
            } else if (
              chunk.type === 'tool_result' &&
              chunk.tool_name &&
              chunk.result !== undefined
            ) {
              setMessages((prev) => {
                const lastMsg = prev[prev.length - 1];
                if (lastMsg && lastMsg.id === tempAssistantId && lastMsg.tool_calls) {
                  const updatedToolCalls: ToolCall[] = lastMsg.tool_calls.map((tc) =>
                    tc.name === chunk.tool_name
                      ? { ...tc, status: 'completed' as const, result: chunk.result }
                      : tc
                  );
                  return [
                    ...prev.slice(0, -1),
                    {
                      ...lastMsg,
                      tool_calls: updatedToolCalls,
                    },
                  ];
                }
                return prev;
              });
            } else if (chunk.type === 'thinking' && chunk.content) {
              setMessages((prev) => {
                const lastMsg = prev[prev.length - 1];
                if (lastMsg && lastMsg.id === tempAssistantId) {
                  return [
                    ...prev.slice(0, -1),
                    {
                      ...lastMsg,
                      thinking: (lastMsg.thinking || '') + chunk.content,
                    },
                  ];
                }
                return prev;
              });
            } else if (chunk.type === 'done') {
              setMessages((prev) => {
                const lastMsg = prev[prev.length - 1];
                if (lastMsg && lastMsg.id === tempAssistantId) {
                  return [
                    ...prev.slice(0, -1),
                    {
                      ...lastMsg,
                      content: lastMsg.content || '响应已完成',
                    },
                  ];
                }
                return prev;
              });
            } else if (chunk.type === 'error') {
              throw new Error(chunk.error || '未知错误');
            }
          },
          currentAgentId || 'default',
          userMessage.images
        );
      } catch (error) {
        console.error('发送消息失败:', error);
        setMessages((prev) => {
          const lastMsg = prev[prev.length - 1];
          if (lastMsg && lastMsg.id === tempAssistantId) {
            return [
              ...prev.slice(0, -1),
              {
                ...lastMsg,
                content: '抱歉，服务暂时不可用，请稍后重试。',
              },
            ];
          }
          return prev;
        });
      } finally {
        setIsLoading(false);
      }
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const getContextText = () => {
    return messages.map((m) => `${m.role === 'user' ? '用户' : '助手'}: ${m.content}`).join('\n\n');
  };

  const handleClearContext = async () => {
    if (!confirm('确定要清空当前对话的上下文吗？这将清除所有对话历史。')) return;

    try {
      const sessionId = `agent-${currentAgentId}`;
      await api.deleteSession(sessionId);
      // 清空后重新加载历史（会创建新的空会话）
      await loadAgentHistory(currentAgentId || 'default');
      alert('上下文已清空');
    } catch (error) {
      console.error('清空上下文失败:', error);
      alert('清空上下文失败');
    }
  };

  const handleArchiveMemory = async () => {
    if (!confirm('确定要执行记忆归档吗？这将归档旧的记忆数据。')) return;

    try {
      const result = await api.autoArchiveProcess();
      alert(
        `记忆归档完成：归档 ${result.results?.archived?.length || 0} 条，合并 ${result.results?.merged?.length || 0} 条`
      );
    } catch (error) {
      console.error('记忆归档失败:', error);
      alert('记忆归档失败');
    }
  };

  const handleAutoSummary = async () => {
    setAutoStartSummary(true);
    setShowSummaryModal(true);
  };

  return (
    <div className="max-w-4xl mx-auto h-full flex flex-col">
      <PageHeader
        title={currentAgent?.name || '对话'}
        description={currentAgent?.description}
        actions={
          <div className="flex gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={handleArchiveMemory}
              icon={
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4"
                  />
                </svg>
              }
            >
              记忆归档
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={handleClearContext}
              icon={
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                  />
                </svg>
              }
            >
              清空上下文
            </Button>
            {messages.length > 0 && (
              <>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={handleAutoSummary}
                  icon={
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M13 10V3L4 14h7v7l9-11h-7z"
                      />
                    </svg>
                  }
                >
                  自动摘要
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => setShowSummaryModal(true)}
                  icon={
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"
                      />
                    </svg>
                  }
                >
                  自定义摘要
                </Button>
              </>
            )}
          </div>
        }
      />

      <div className="flex-1 overflow-y-auto space-y-4 mb-4">
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center py-12">
            <div className="w-16 h-16 rounded-2xl bg-[var(--color-accent-light)] flex items-center justify-center mb-4">
              <svg
                className="w-8 h-8 text-[var(--color-accent)]"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
                />
              </svg>
            </div>
            <h3 className="text-xl font-semibold text-[var(--color-text-primary)] mb-2">
              开始对话
            </h3>
            <p className="text-[var(--color-text-secondary)] max-w-md mb-4">
              与 AI 助手进行对话，系统会自动检索相关记忆来辅助回答您的问题。
            </p>
            {currentAgent?.system_prompt && (
              <Card className="max-w-md p-3">
                <div className="text-sm font-medium text-[var(--color-text-secondary)] mb-1">
                  系统提示词:
                </div>
                <div className="text-sm text-[var(--color-text-tertiary)] line-clamp-3">
                  {currentAgent.system_prompt}
                </div>
              </Card>
            )}
          </div>
        ) : (
          messages.map((message) => (
            <div
              key={message.id}
              className={`flex gap-3 ${message.role === 'user' ? 'flex-row-reverse' : ''}`}
            >
              <div
                className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ${
                  message.role === 'user'
                    ? 'bg-[var(--color-accent)] text-white'
                    : 'bg-[var(--color-bg-tertiary)]'
                }`}
              >
                {message.role === 'user' ? (
                  <span className="text-sm font-medium">我</span>
                ) : (
                  <svg
                    className="w-5 h-5 text-[var(--color-text-secondary)]"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"
                    />
                  </svg>
                )}
              </div>
              <div
                className={`max-w-[80%] ${message.role === 'user' ? 'items-end' : 'items-start'}`}
              >
                <div
                  className={`px-4 py-3 rounded-2xl ${
                    message.role === 'user'
                      ? 'bg-[var(--color-accent)] text-white'
                      : 'bg-[var(--color-bg-primary)] border border-[var(--color-border)]'
                  }`}
                >
                  {message.role === 'user' ? (
                    <p className="whitespace-pre-wrap">{message.content}</p>
                  ) : (
                    <MarkdownContent content={message.content} />
                  )}
                  {message.role === 'assistant' &&
                    isLoading &&
                    message.id === messages[messages.length - 1]?.id && (
                      <span className="inline-block w-2 h-4 ml-1 bg-[var(--color-accent)] animate-pulse" />
                    )}
                </div>
                <span className="text-xs text-[var(--color-text-tertiary)] mt-1 px-1">
                  {formatRelativeTime(message.timestamp)}
                </span>

                {message.role === 'assistant' && (
                  <ThinkingProcess thinking={message.thinking} toolCalls={message.tool_calls} />
                )}

                {message.memory_refs && message.memory_refs.length > 0 && (
                  <div className="mt-2 flex gap-2">
                    {message.memory_refs.map((ref) => (
                      <span
                        key={ref}
                        className="text-xs px-2 py-1 bg-[var(--color-accent-light)] text-[var(--color-accent)] rounded-full"
                      >
                        引用记忆 #{ref}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))
        )}
        <div ref={messagesEndRef} />
      </div>

      <div className="border-t border-[var(--color-border)] pt-4">
        {/* 图片预览 */}
        {selectedImages.length > 0 && (
          <div className="flex gap-2 mb-2 flex-wrap">
            {selectedImages.map((img, index) => (
              <div key={index} className="relative">
                <img
                  src={img}
                  alt={`预览 ${index + 1}`}
                  className="w-16 h-16 object-cover rounded border border-[var(--color-border)]"
                />
                <button
                  onClick={() => removeImage(index)}
                  className="absolute -top-1 -right-1 w-5 h-5 bg-red-500 text-white rounded-full text-xs flex items-center justify-center hover:bg-red-600"
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        )}

        <div className="flex gap-2">
          {/* 图片上传按钮 - 仅当 Agent 启用视觉时显示 */}
          {currentAgent?.vision_enabled && (
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              multiple
              onChange={handleImageSelect}
              className="hidden"
            />
          )}
          {currentAgent?.vision_enabled && (
            <Button
              variant="secondary"
              onClick={() => fileInputRef.current?.click()}
              disabled={isLoading || selectedImages.length >= 4}
              className="self-end"
              title="上传图片（最多4张）"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"
                />
              </svg>
            </Button>
          )}
          <Textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={`给 ${currentAgent?.name || '助手'} 发送消息...`}
            className="flex-1 min-h-[48px] max-h-[200px]"
            disabled={isLoading}
          />
          {isLoading ? (
            <Button
              variant="secondary"
              onClick={cancelGeneration}
              className="self-end"
              title="停止生成"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                />
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M9 10a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1h-4a1 1 0 01-1-1v-4z"
                />
              </svg>
            </Button>
          ) : (
            <Button
              onClick={handleSend}
              disabled={(!input.trim() && selectedImages.length === 0) || isLoading}
              className="self-end"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"
                />
              </svg>
            </Button>
          )}
        </div>
        <div className="flex items-center justify-between mt-2">
          <p className="text-xs text-[var(--color-text-tertiary)]">
            按 Enter 发送，Shift + Enter 换行
            {currentAgent?.vision_enabled && ' · 支持图片上传'}
          </p>
          <div className="flex items-center gap-1 text-xs">
            <span
              className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'}`}
            />
            <span className="text-[var(--color-text-tertiary)]">
              {isConnected ? 'WebSocket' : 'SSE'}
            </span>
          </div>
        </div>
      </div>

      {/* 提醒通知 */}
      {alarms.length > 0 && (
        <div className="fixed top-4 right-4 z-50 space-y-2">
          {alarms.map((alarm, index) => (
            <div
              key={index}
              className="bg-[var(--color-accent)] text-white px-4 py-3 rounded-lg shadow-lg animate-slide-in max-w-sm"
            >
              <div className="flex items-center gap-2">
                <svg
                  className="w-5 h-5 flex-shrink-0"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9"
                  />
                </svg>
                <div>
                  <p className="font-medium">提醒</p>
                  <p className="text-sm opacity-90">{alarm.message}</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      <SummaryModal
        isOpen={showSummaryModal}
        onClose={() => {
          setShowSummaryModal(false);
          setAutoStartSummary(false);
        }}
        contextText={getContextText()}
        agentId={currentAgentId || 'default'}
        sessionId={currentAgentId || 'default'}
        autoStart={autoStartSummary}
      />
    </div>
  );
}
