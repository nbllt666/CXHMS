import { useState, useRef, useEffect, useCallback, memo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useTranslation } from 'react-i18next';
import { api } from '../api';
import { useChatStore } from '../store/chatStore';
import { formatRelativeTime } from '../lib/utils';
import { SummaryModal } from '../components/SummaryModal';
import { Button, Textarea, Card } from '../components/ui';
import { PageHeader } from '../components/layout';
import { useWebSocket } from '../hooks/useWebSocket';
import {
  applyStreamChunk,
  isStreamFinished,
  type Message,
  type ToolCall,
  type StreamChunk,
} from './chatStreamReducer';

const MarkdownContent = memo(function MarkdownContent({ content }: { content: string }) {
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
});

function ThinkingProcess({ thinking, toolCalls }: { thinking?: string; toolCalls?: ToolCall[] }) {
  const { t } = useTranslation();
  const [isExpanded, setIsExpanded] = useState(false);

  if (!thinking && (!toolCalls || toolCalls.length === 0)) return null;

  // 根据内容类型决定标题
  const hasThinking = Boolean(thinking);
  const hasToolCalls = Boolean(toolCalls && toolCalls.length > 0);
  const title = hasThinking ? t('chat.thinkingProcess') : t('chat.toolCalls');

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
          {title}
          {hasToolCalls && (
            <span className="px-1.5 py-0.5 bg-[var(--color-accent-light)] text-[var(--color-accent)] rounded-full text-[10px]">
              {t('chat.toolCallsCount', { count: toolCalls!.length })}
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
          {hasThinking && (
            <div>
              {hasToolCalls && (
                <div className="text-[var(--color-text-secondary)] font-medium mb-1">{t('chat.thinkingProcess')}</div>
              )}
              <div className="text-[var(--color-text-tertiary)] whitespace-pre-wrap">{thinking}</div>
            </div>
          )}

          {hasToolCalls && (
            <div className={hasThinking ? 'space-y-2 mt-2' : 'space-y-2'}>
              {hasThinking && (
                <div className="text-[var(--color-text-secondary)] font-medium mb-1">{t('chat.toolCalls')}</div>
              )}
              {toolCalls!.map((toolCall, idx) => (
                <div
                  key={toolCall.id || `${toolCall.name}_${idx}`}
                  className="p-2 bg-[var(--color-bg-tertiary)] rounded border border-[var(--color-border)]"
                >
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-medium text-[var(--color-text-primary)]">
                      🔧 {toolCall.name}
                    </span>
                    {toolCall.status === 'executing' && (
                      <span className="animate-pulse text-[var(--color-info)]">{t('chat.executing')}</span>
                    )}
                    {toolCall.status === 'completed' && (
                      <span className="text-[var(--color-success)]">{t('chat.completed')}</span>
                    )}
                    {toolCall.status === 'failed' && (
                      <span className="text-[var(--color-error)]">{t('chat.failed')}</span>
                    )}
                  </div>
                  {Boolean(toolCall.arguments) && (
                    <div className="text-[var(--color-text-tertiary)] font-mono text-[10px] mb-1">
                      {t('chat.parameters')}: {JSON.stringify(toolCall.arguments, null, 2)}
                    </div>
                  )}
                  {toolCall.result !== undefined && (
                    <div className="text-[var(--color-text-tertiary)] font-mono text-[10px]">
                      {t('chat.result')}: {JSON.stringify(toolCall.result, null, 2)}
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

// F1: 消息列表项 memo 化——仅当 message 引用或 isStreaming 变化时重渲染。
// 配合 reducer 的结构性共享（slice + push），流式期间仅最后一条消息重渲染，
// 前序项因 message 引用不变被 memo 跳过，满足 200+ 条会话 < 16ms/chunk。
const MessageItem = memo(
  function MessageItem({ message, isStreaming }: { message: Message; isStreaming: boolean }) {
    const { t } = useTranslation();
    return (
      <div className={`flex gap-3 ${message.role === 'user' ? 'flex-row-reverse' : ''}`}>
        <div
          className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ${
            message.role === 'user'
              ? 'bg-[var(--color-accent)] text-white'
              : 'bg-[var(--color-bg-tertiary)]'
          }`}
        >
          {message.role === 'user' ? (
            <span className="text-sm font-medium">{t('chat.me')}</span>
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
            {message.role === 'assistant' && isStreaming && (
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
                  {t('chat.memoryRef', { ref })}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>
    );
  },
  (prev, next) => prev.message === next.message && prev.isStreaming === next.isStreaming
);

export function ChatPage() {
  const { t, i18n } = useTranslation();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [showSummaryModal, setShowSummaryModal] = useState(false);
  const [autoStartSummary, setAutoStartSummary] = useState(false);
  const [selectedImages, setSelectedImages] = useState<string[]>([]);
  const [alarms, setAlarms] = useState<{ id: string; message: string; triggeredAt: string }[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const tempAssistantIdRef = useRef<string>('');
  const abortControllerRef = useRef<AbortController | null>(null);
  const alarmTimeoutRef = useRef<ReturnType<typeof setTimeout>[]>([]);

  const { agents, currentAgentId, currentSessionId, fetchAgents } = useChatStore();

  const handleWebSocketMessage = useCallback(
    (data: StreamChunk) => {
      setMessages((prev) => applyStreamChunk(prev, data, tempAssistantIdRef.current));
      if (isStreamFinished(data)) {
        setIsLoading(false);
      }
    },
    []
  );

  const handleAlarm = useCallback((message: string, triggeredAt: string) => {
    const alarmId = crypto.randomUUID();
    setAlarms((prev) => [...prev, { id: alarmId, message, triggeredAt }]);
    const id = setTimeout(() => {
      setAlarms((prev) => prev.filter((a) => a.id !== alarmId));
    }, 5000);
    alarmTimeoutRef.current.push(id);
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
    // WS 断开时清除加载态，避免 done/error/cancelled 未送达时 UI 卡在 loading
    onDisconnect: () => {
      setIsLoading(false);
    },
  });

  useEffect(() => {
    fetchAgents();
  }, [fetchAgents]);

  const currentAgent = agents.find((a) => a.id === currentAgentId);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const loadAgentHistory = useCallback(async (agentId: string) => {
    try {
      // 统一口径：优先真实 sessionId，回退到 `agent-${agentId}`，与 handleClearContext 保持一致
      const sessionKey = currentSessionId || `agent-${agentId}`;
      const data = await api.getChatHistory(sessionKey);
      if (data.messages) {
        const formattedMessages = data.messages.map(
          (msg: {
            id?: string;
            role: 'user' | 'assistant';
            content: string;
            created_at?: string;
            thinking?: string;
            images?: string[];
            metadata?: { tool_calls?: ToolCall[]; thinking?: string };
          }) => ({
            id: msg.id || Math.random().toString(),
            role: msg.role,
            content: msg.content,
            timestamp: msg.created_at || new Date().toISOString(),
            thinking: msg.thinking || msg.metadata?.thinking,
            images: msg.images,
            tool_calls: msg.metadata?.tool_calls,
          })
        );
        setMessages(formattedMessages);
        setShouldAutoScroll(true);
      }
    } catch (error) {
      console.error('加载历史消息失败:', error);
      setMessages([]);
    }
  }, [currentSessionId]);

  useEffect(() => {
    if (currentAgentId) {
      loadAgentHistory(currentAgentId);
    } else {
      setMessages([]);
    }
  }, [currentAgentId, currentSessionId, loadAgentHistory]);

  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort();
      alarmTimeoutRef.current.forEach((id) => clearTimeout(id));
      alarmTimeoutRef.current = [];
    };
  }, []);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const [shouldAutoScroll, setShouldAutoScroll] = useState(false);

  useEffect(() => {
    if (shouldAutoScroll) {
      scrollToBottom();
      setShouldAutoScroll(false);
    }
  }, [messages, shouldAutoScroll]);

  const handleImageSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files) return;

    if (selectedImages.length >= 4) {
      alert(t('chat.maxImagesAlert'));
      e.target.value = '';
      return;
    }

    const imageFiles = Array.from(files).filter((file) => file.type.startsWith('image/'));
    const remaining = 4 - selectedImages.length;
    const filesToAdd = imageFiles.slice(0, remaining);

    if (imageFiles.length > remaining) {
      alert(t('chat.maxImagesAlert'));
    }

    filesToAdd.forEach((file) => {
      const reader = new FileReader();
      reader.onload = (event) => {
        const base64 = event.target?.result as string;
        setSelectedImages((prev) => (prev.length >= 4 ? prev : [...prev, base64]));
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
      id: crypto.randomUUID(),
      role: 'user',
      content: input,
      timestamp: new Date().toISOString(),
      images: selectedImages.length > 0 ? selectedImages : undefined,
    };

    const tempAssistantId = crypto.randomUUID();
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
        const abortController = new AbortController();
        abortControllerRef.current = abortController;
        await api.sendMessageStream(
          userMessage.content,
          (chunk) => {
            // F2: WS/SSE 共用 reducer，行为一致（含 error 分支不再 throw，统一写入消息内容）
            setMessages((prev) => applyStreamChunk(prev, chunk, tempAssistantId));
            if (isStreamFinished(chunk)) {
              setIsLoading(false);
            }
          },
          currentAgentId || 'default',
          userMessage.images,
          abortController.signal
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
                content: t('chat.serviceUnavailable'),
              },
            ];
          }
          return prev;
        });
      } finally {
        setIsLoading(false);
        abortControllerRef.current = null;
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
    const formatTime = (timestamp: string) => {
      try {
        const date = new Date(timestamp);
        return date.toLocaleTimeString(i18n.language, { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
      } catch {
        return '';
      }
    };

    return messages.map((m) => {
      const time = m.timestamp ? formatTime(m.timestamp) : '';
      return `[${time} ${m.role === 'user' ? t('chat.contextUser') : t('chat.contextAssistant')}] ${m.content}`;
    }).join('\n\n');
  };

  const handleClearContext = async () => {
    if (!confirm(t('chat.confirmClearContext'))) return;

    try {
      const sessionId = currentSessionId || `agent-${currentAgentId || 'default'}`;
      await api.clearSessionMessages(sessionId);
      // 清空后重新加载历史（会创建新的空会话）
      await loadAgentHistory(currentAgentId || 'default');
      alert(t('chat.contextCleared'));
    } catch (error) {
      console.error('清空上下文失败:', error);
      alert(t('chat.clearContextFailed'));
    }
  };

  const handleArchiveMemory = async () => {
    if (!confirm(t('chat.confirmArchive'))) return;

    try {
      const result = await api.autoArchiveProcess();
      alert(
        t('chat.archiveComplete', {
          archived: result.results?.archived?.length || 0,
          merged: result.results?.merged?.length || 0,
        })
      );
    } catch (error) {
      console.error('记忆归档失败:', error);
      alert(t('chat.archiveFailed'));
    }
  };

  const handleAutoSummary = async () => {
    setAutoStartSummary(true);
    setShowSummaryModal(true);
  };

  return (
    <div className="w-full h-[calc(100vh-var(--header-height)-3rem)] flex flex-col">
      <PageHeader
        title={currentAgent?.name || t('chat.defaultTitle')}
        description={currentAgent?.description}
        className="flex-shrink-0"
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
              {t('chat.archiveMemory')}
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
              {t('chat.clearContext')}
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
                  {t('chat.autoSummary')}
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
                  {t('chat.customSummary')}
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
              {t('chat.startConversation')}
            </h3>
            <p className="text-[var(--color-text-secondary)] max-w-md mb-4">
              {t('chat.conversationIntro')}
            </p>
            {currentAgent?.system_prompt && (
              <Card className="max-w-md p-3">
                <div className="text-sm font-medium text-[var(--color-text-secondary)] mb-1">
                  {t('chat.systemPromptLabel')}
                </div>
                <div className="text-sm text-[var(--color-text-tertiary)] line-clamp-3">
                  {currentAgent.system_prompt}
                </div>
              </Card>
            )}
          </div>
        ) : (
          messages.map((message, index) => (
            <MessageItem
              key={message.id}
              message={message}
              isStreaming={isLoading && index === messages.length - 1}
            />
          ))
        )}
        <div ref={messagesEndRef} />
      </div>

      <div className="border-t border-[var(--color-border)] pt-4 flex-shrink-0">
        {/* 图片预览 */}
        {selectedImages.length > 0 && (
          <div className="flex gap-2 mb-2 flex-wrap">
            {selectedImages.map((img, index) => (
              <div key={index} className="relative">
                <img
                  src={img}
                  alt={t('chat.imagePreview', { index: index + 1 })}
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
              title={t('chat.uploadImageTitle')}
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
            placeholder={t('chat.messagePlaceholder', { name: currentAgent?.name || t('chat.assistant') })}
            className="flex-1 min-h-[48px] max-h-[200px]"
            disabled={isLoading}
          />
          {isLoading ? (
            <Button
              variant="secondary"
              onClick={cancelGeneration}
              className="self-end"
              title={t('chat.stopGeneration')}
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
            {t('chat.enterToSend')}
            {currentAgent?.vision_enabled && t('chat.supportsImageUpload')}
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
          {alarms.map((alarm) => (
            <div
              key={alarm.id}
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
                  <p className="font-medium">{t('chat.alarmTitle')}</p>
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
        autoStart={autoStartSummary}
        targetSessionId={currentSessionId || `agent-${currentAgentId || 'default'}`}
      />
    </div>
  );
}
