import { useState, useRef, useEffect } from 'react'
import { Send, Sparkles, Brain } from 'lucide-react'
import { api } from '../api/client'
import { useChatStore } from '../store/chatStore'
import { formatRelativeTime } from '../lib/utils'

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: string
  memory_refs?: number[]
  tool_calls?: ToolCall[]
}

interface ToolCall {
  id: string
  name: string
  arguments?: any
  result?: any
  status?: 'pending' | 'executing' | 'completed' | 'failed'
}

export function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  
  const {
    agents,
    currentAgentId,
    currentSessionId,
    setCurrentSessionId,
    setSessions,
  } = useChatStore()

  const currentAgent = agents.find(a => a.id === currentAgentId)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  // 当会话改变时，加载消息历史
  useEffect(() => {
    if (currentSessionId) {
      loadSessionHistory(currentSessionId)
    } else {
      setMessages([])
    }
  }, [currentSessionId])

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  const loadSessionHistory = async (sessionId: string) => {
    try {
      const data = await api.getChatHistory(sessionId)
      if (data.messages) {
        const formattedMessages = data.messages.map((msg: {id?: string; role: 'user' | 'assistant'; content: string; created_at?: string}) => ({
          id: msg.id || Math.random().toString(),
          role: msg.role,
          content: msg.content,
          timestamp: msg.created_at || new Date().toISOString()
        }))
        setMessages(formattedMessages)
      }
    } catch (error) {
      console.error('加载历史消息失败:', error)
    }
  }

  const refreshSessions = async () => {
    try {
      const data = await api.getSessions()
      setSessions(data.sessions || [])
    } catch (error) {
      console.error('刷新会话列表失败:', error)
    }
  }

  const handleSend = async () => {
    if (!input.trim() || isLoading) return

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: input,
      timestamp: new Date().toISOString()
    }

    const tempAssistantId = (Date.now() + 1).toString()
    const streamingMessage: Message = {
      id: tempAssistantId,
      role: 'assistant',
      content: '',
      timestamp: new Date().toISOString(),
      tool_calls: []
    }

    setMessages(prev => [...prev, userMessage, streamingMessage])
    setInput('')
    setIsLoading(true)

    try {
      await api.sendMessageStream(
        userMessage.content,
        currentSessionId || tempAssistantId,
        (chunk) => {
          if (chunk.session_id && !currentSessionId) {
            setCurrentSessionId(chunk.session_id)
            refreshSessions()
          }

          if (chunk.type === 'content' && chunk.content) {
            setMessages(prev => {
              const lastMsg = prev[prev.length - 1]
              if (lastMsg && lastMsg.id === tempAssistantId) {
                return [...prev.slice(0, -1), {
                  ...lastMsg,
                  content: lastMsg.content + chunk.content!
                }]
              }
              return prev
            })
          } else if (chunk.type === 'tool_call' && chunk.tool_call) {
            setMessages(prev => {
              const lastMsg = prev[prev.length - 1]
              if (lastMsg && lastMsg.id === tempAssistantId) {
                return [...prev.slice(0, -1), {
                  ...lastMsg,
                  tool_calls: [...(lastMsg.tool_calls || []), {
                    id: chunk.tool_call.id || Date.now().toString(),
                    name: chunk.tool_call.name || chunk.tool_call.function?.name || 'unknown',
                    arguments: chunk.tool_call.arguments || chunk.tool_call.function?.arguments,
                    status: 'pending'
                  }]
                }]
              }
              return prev
            })
          } else if (chunk.type === 'tool_start' && chunk.tool_name) {
            setMessages(prev => {
              const lastMsg = prev[prev.length - 1]
              if (lastMsg && lastMsg.id === tempAssistantId && lastMsg.tool_calls) {
                return [...prev.slice(0, -1), {
                  ...lastMsg,
                  tool_calls: lastMsg.tool_calls.map(tc =>
                    tc.name === chunk.tool_name ? { ...tc, status: 'executing' } : tc
                  )
                }]
              }
              return prev
            })
          } else if (chunk.type === 'tool_result' && chunk.tool_name && chunk.result) {
            setMessages(prev => {
              const lastMsg = prev[prev.length - 1]
              if (lastMsg && lastMsg.id === tempAssistantId && lastMsg.tool_calls) {
                return [...prev.slice(0, -1), {
                  ...lastMsg,
                  tool_calls: lastMsg.tool_calls.map(tc =>
                    tc.name === chunk.tool_name ? { ...tc, status: 'completed', result: chunk.result } : tc
                  )
                }]
              }
              return prev
            })
          } else if (chunk.type === 'done') {
            setMessages(prev => {
              const lastMsg = prev[prev.length - 1]
              if (lastMsg && lastMsg.id === tempAssistantId) {
                return [...prev.slice(0, -1), {
                  ...lastMsg,
                  content: lastMsg.content || '响应已完成'
                }]
              }
              return prev
            })
          } else if (chunk.type === 'error') {
            throw new Error(chunk.error || '未知错误')
          }
        },
        currentAgentId || undefined
      )
    } catch (error) {
      console.error('发送消息失败:', error)
      setMessages(prev => {
        const lastMsg = prev[prev.length - 1]
        if (lastMsg && lastMsg.id === tempAssistantId) {
          return [...prev.slice(0, -1), {
            ...lastMsg,
            content: '抱歉，服务暂时不可用，请稍后重试。'
          }]
        }
        return prev
      })
    } finally {
      setIsLoading(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="flex flex-col h-full">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-6 space-y-6">
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <div className="w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center mb-4">
              <Sparkles className="w-8 h-8 text-primary" />
            </div>
            <h3 className="text-xl font-semibold mb-2">
              {currentAgent?.name || '开始对话'}
            </h3>
            <p className="text-muted-foreground max-w-md mb-4">
              {currentAgent?.description || '与 AI 助手进行对话，系统会自动检索相关记忆来辅助回答您的问题。'}
            </p>
            {currentAgent?.system_prompt && (
              <div className="max-w-md p-3 bg-muted rounded-lg text-sm text-muted-foreground">
                <div className="font-medium mb-1">系统提示词:</div>
                <div className="line-clamp-3">{currentAgent.system_prompt}</div>
              </div>
            )}
          </div>
        ) : (
          messages.map((message) => (
            <div
              key={message.id}
              className={`flex gap-4 ${message.role === 'user' ? 'flex-row-reverse' : ''}`}
            >
              <div className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ${
                message.role === 'user'
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-muted'
              }`}>
                {message.role === 'user' ? (
                  <span className="text-sm font-medium">我</span>
                ) : (
                  <Brain className="w-5 h-5" />
                )}
              </div>
              <div className={`max-w-[80%] ${message.role === 'user' ? 'items-end' : 'items-start'}`}>
                <div className={`px-4 py-3 rounded-2xl ${
                  message.role === 'user'
                    ? 'bg-primary text-primary-foreground'
                    : 'bg-muted'
                }`}>
                  <p className="whitespace-pre-wrap">
                    {message.content}
                    {message.role === 'assistant' && isLoading && message.id === messages[messages.length - 1]?.id && (
                      <span className="inline-block w-2 h-4 ml-1 bg-primary/60 animate-pulse" />
                    )}
                  </p>
                </div>
                <span className="text-xs text-muted-foreground mt-1 px-1">
                  {formatRelativeTime(message.timestamp)}
                </span>
                {message.memory_refs && message.memory_refs.length > 0 && (
                  <div className="mt-2 flex gap-2">
                    {message.memory_refs.map(ref => (
                      <span
                        key={ref}
                        className="text-xs px-2 py-1 bg-primary/10 text-primary rounded-full"
                      >
                        引用记忆 #{ref}
                      </span>
                    ))}
                  </div>
                )}
                {message.tool_calls && message.tool_calls.length > 0 && (
                  <div className="mt-2 space-y-2">
                    {message.tool_calls.map((toolCall, idx) => (
                      <div
                        key={idx}
                        className="text-xs p-2 bg-muted/50 rounded-lg border border-border"
                      >
                        <div className="flex items-center gap-2 mb-1">
                          <span className="font-medium text-foreground">
                            🔧 {toolCall.name}
                          </span>
                          {toolCall.status === 'executing' && (
                            <span className="animate-pulse text-blue-500">执行中...</span>
                          )}
                          {toolCall.status === 'completed' && (
                            <span className="text-green-500">✓ 完成</span>
                          )}
                          {toolCall.status === 'failed' && (
                            <span className="text-red-500">✗ 失败</span>
                          )}
                        </div>
                        {toolCall.arguments && (
                          <div className="text-muted-foreground font-mono text-[10px] mb-1">
                            参数: {JSON.stringify(toolCall.arguments, null, 2)}
                          </div>
                        )}
                        {toolCall.result && (
                          <div className="text-muted-foreground font-mono text-[10px]">
                            结果: {JSON.stringify(toolCall.result, null, 2)}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
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
            placeholder={`给 ${currentAgent?.name || '助手'} 发送消息...`}
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
          按 Enter 发送，Shift + Enter 换行
        </p>
      </div>
    </div>
  )
}
