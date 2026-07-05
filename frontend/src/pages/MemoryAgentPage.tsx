import { useState, useRef, useEffect } from 'react';
import { Send, Database, Brain, ChevronDown, ChevronUp, X } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useTranslation } from 'react-i18next';
import { api } from '../api';
import { formatRelativeTime } from '../lib/utils';

import type { Message, ToolCall, StreamToolCall } from '../types';

// F8: Message / ToolCall / StreamToolCall 类型统一到 types/，此处不再重复声明。

interface CodeProps {
  inline?: boolean;
  className?: string;
  children?: React.ReactNode;
}

function MarkdownContent({ content }: { content: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      className="prose prose-sm dark:prose-invert max-w-none"
      components={{
        code({ inline, className, children, ...props }: CodeProps) {
          const match = /language-(\w+)/.exec(className || '');
          return !inline && match ? (
            <div className="relative group">
              <div className="absolute right-2 top-2 text-xs text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity">
                {match[1]}
              </div>
              <pre className="bg-muted/80 rounded-lg p-4 overflow-x-auto">
                <code className={className} {...props}>
                  {children}
                </code>
              </pre>
            </div>
          ) : (
            <code className="bg-muted/50 px-1.5 py-0.5 rounded text-sm" {...props}>
              {children}
            </code>
          );
        },
      }}
    >
      {content}
    </ReactMarkdown>
  );
}

// 思考过程折叠组件
function ThinkingProcess({ thinking, toolCalls }: { thinking?: string; toolCalls?: ToolCall[] }) {
  const { t } = useTranslation();
  const [isExpanded, setIsExpanded] = useState(false);

  if (!thinking && (!toolCalls || toolCalls.length === 0)) return null;

  // 根据内容类型决定标题
  const hasThinking = Boolean(thinking);
  const hasToolCalls = Boolean(toolCalls && toolCalls.length > 0);
  const title = hasThinking ? t('memoryAgent.thinkingProcess') : t('memoryAgent.toolCalls');

  return (
    <div className="mt-2 border border-border/50 rounded-lg overflow-hidden">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center justify-between px-3 py-2 bg-muted/30 hover:bg-muted/50 transition-colors text-xs text-muted-foreground"
      >
        <span className="flex items-center gap-2">
          <Brain className="w-3 h-3" />
          {title}
          {hasToolCalls && (
            <span className="px-1.5 py-0.5 bg-primary/10 text-primary rounded-full text-[10px]">
              {t('memoryAgent.toolCallsCount', { count: toolCalls!.length })}
            </span>
          )}
        </span>
        {isExpanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
      </button>

      {isExpanded && (
        <div className="px-3 py-2 bg-muted/20 text-xs space-y-2">
          {hasThinking && (
            <div>
              {hasToolCalls && (
                <div className="text-foreground font-medium mb-1">{t('memoryAgent.thinkingProcess')}</div>
              )}
              <div className="text-muted-foreground whitespace-pre-wrap">{thinking}</div>
            </div>
          )}

          {hasToolCalls && (
            <div className={hasThinking ? 'space-y-2 mt-2' : 'space-y-2'}>
              {hasThinking && (
                <div className="text-foreground font-medium mb-1">{t('memoryAgent.toolCalls')}</div>
              )}
              {toolCalls!.map((toolCall, idx) => (
                <div key={idx} className="p-2 bg-muted/50 rounded border border-border/50">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-medium text-foreground">🔧 {toolCall.name}</span>
                    {toolCall.status === 'executing' && (
                      <span className="animate-pulse text-blue-500">{t('memoryAgent.executing')}</span>
                    )}
                    {toolCall.status === 'completed' && (
                      <span className="text-green-500">{t('memoryAgent.completed')}</span>
                    )}
                    {toolCall.status === 'failed' && <span className="text-red-500">{t('memoryAgent.failed')}</span>}
                  </div>
                  {toolCall.arguments && (
                    <div className="text-muted-foreground font-mono text-[10px] mb-1">
                      {t('memoryAgent.parameters')}: {JSON.stringify(toolCall.arguments, null, 2)}
                    </div>
                  )}
                  {toolCall.result !== undefined && (
                    <div className="text-muted-foreground font-mono text-[10px]">
                      {t('memoryAgent.result')}: {JSON.stringify(toolCall.result, null, 2)}
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

export function MemoryAgentPage() {
  const { t } = useTranslation();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // 组件卸载时取消正在进行的流式请求
  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort();
    };
  }, []);

  // 页面加载时获取历史消息
  useEffect(() => {
    const loadHistory = async () => {
      try {
        const data = await api.getAgentContext('memory-agent');
        if (data.recent_messages && data.recent_messages.length > 0) {
          const formattedMessages = data.recent_messages
            .filter((msg: { role: string; content: string; created_at?: string }) => msg.role === 'user' || msg.role === 'assistant')
            .map((msg: { role: string; content: string; created_at?: string }, idx: number) => ({
              id: `history-${idx}`,
              role: msg.role,
              content: msg.content,
              timestamp: msg.created_at || new Date().toISOString(),
            }));
          setMessages(formattedMessages);
        }
      } catch (error) {
        console.error('加载历史消息失败:', error);
      }
    };
    loadHistory();
  }, []);

  const handleSend = async () => {
    if (!input.trim() || isLoading) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: input,
      timestamp: new Date().toISOString(),
    };

    const tempAssistantId = (Date.now() + 1).toString();
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
    setIsLoading(true);

    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    try {
      await api.sendMemoryAgentMessageStream(userMessage.content, (chunk) => {
        if (chunk.session_id) {
          setSessionId(chunk.session_id);
        }
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
        } else if (chunk.type === 'tool_result' && chunk.tool_name && chunk.result) {
          setMessages((prev) => {
            const lastMsg = prev[prev.length - 1];
            if (lastMsg && lastMsg.id === tempAssistantId && lastMsg.tool_calls) {
              return [
                ...prev.slice(0, -1),
                {
                  ...lastMsg,
                  tool_calls: lastMsg.tool_calls.map((tc) =>
                    tc.name === chunk.tool_name
                      ? { ...tc, status: 'completed', result: chunk.result }
                      : tc
                  ),
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
                  content: lastMsg.content || t('memoryAgent.responseComplete'),
                },
              ];
            }
            return prev;
          });
        } else if (chunk.type === 'error') {
          throw new Error(chunk.error || t('memoryAgent.unknownError'));
        }
      }, abortController.signal);
    } catch (error) {
      console.error('发送消息失败:', error);
      setMessages((prev) => {
        const lastMsg = prev[prev.length - 1];
        if (lastMsg && lastMsg.id === tempAssistantId) {
          return [
            ...prev.slice(0, -1),
            {
              ...lastMsg,
              content: t('memoryAgent.serviceUnavailable'),
            },
          ];
        }
        return prev;
      });
    } finally {
      setIsLoading(false);
      abortControllerRef.current = null;
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const clearChat = async () => {
    setMessages([]);
    try {
      // Clear session messages
      await api.clearSessionMessages(sessionId || 'memory-agent');
      // Clear agent context
      await fetch(`${api.getApiUrl()}/api/agents/memory-agent/context`, {
        method: 'DELETE',
        headers: {
          Authorization: `Bearer ${localStorage.getItem('cxhms-token') || ''}`,
        },
      });
    } catch (error) {
      console.error('清空后端对话数据失败:', error);
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border bg-muted/30">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center">
            <Database className="w-4 h-4 text-primary" />
          </div>
          <div>
            <h2 className="font-semibold">{t('nav.memoryAgent')}</h2>
            <p className="text-xs text-muted-foreground">{t('memoryAgent.subtitle')}</p>
          </div>
        </div>
        <button
          onClick={clearChat}
          className="flex items-center gap-2 px-3 py-1.5 text-sm text-muted-foreground hover:text-foreground hover:bg-muted rounded-lg transition-colors"
        >
          <X className="w-4 h-4" />
          {t('memoryAgent.clearConversation')}
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-6 space-y-6">
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <div className="w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center mb-4">
              <Database className="w-8 h-8 text-primary" />
            </div>
            <h3 className="text-xl font-semibold mb-2">{t('nav.memoryAgent')}</h3>
            <p className="text-muted-foreground max-w-md mb-4">
              {t('memoryAgent.introDesc')}
            </p>
            <div className="max-w-md p-4 bg-muted rounded-lg text-sm text-muted-foreground">
              <div className="font-medium mb-2">{t('memoryAgent.exampleCommands')}</div>
              <ul className="space-y-1 text-left">
                <li>{t('memoryAgent.example1')}</li>
                <li>{t('memoryAgent.example2')}</li>
                <li>{t('memoryAgent.example3')}</li>
                <li>{t('memoryAgent.example4')}</li>
                <li>{t('memoryAgent.example5')}</li>
              </ul>
            </div>
          </div>
        ) : (
          messages.map((message) => (
            <div
              key={message.id}
              className={`flex gap-4 ${message.role === 'user' ? 'flex-row-reverse' : ''}`}
            >
              <div
                className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ${
                  message.role === 'user' ? 'bg-primary text-primary-foreground' : 'bg-muted'
                }`}
              >
                {message.role === 'user' ? (
                  <span className="text-sm font-medium">{t('memoryAgent.me')}</span>
                ) : (
                  <Database className="w-5 h-5" />
                )}
              </div>
              <div
                className={`max-w-[80%] ${message.role === 'user' ? 'items-end' : 'items-start'}`}
              >
                <div
                  className={`px-4 py-3 rounded-2xl ${
                    message.role === 'user' ? 'bg-primary text-primary-foreground' : 'bg-muted'
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
                      <span className="inline-block w-2 h-4 ml-1 bg-primary/60 animate-pulse" />
                    )}
                </div>
                <span className="text-xs text-muted-foreground mt-1 px-1">
                  {formatRelativeTime(message.timestamp)}
                </span>

                {/* 思考过程显示 */}
                {message.role === 'assistant' && (
                  <ThinkingProcess thinking={message.thinking} toolCalls={message.tool_calls} />
                )}
              </div>
            </div>
          ))
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div className="border-t border-border p-4">
        <div className="flex gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={t('memoryAgent.inputPlaceholder')}
            className="flex-1 resize-none bg-muted rounded-lg px-4 py-3 focus:outline-none focus:ring-2 focus:ring-primary/50 min-h-[48px] max-h-[200px]"
            rows={1}
            disabled={isLoading}
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || isLoading}
            className="px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            <Send className="w-5 h-5" />
          </button>
        </div>
        <p className="text-xs text-muted-foreground mt-2 text-center">
          {t('memoryAgent.enterToSend')}
        </p>
      </div>
    </div>
  );
}
