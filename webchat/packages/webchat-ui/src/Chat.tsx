'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Bubble, Sender } from '@ant-design/x';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  SessionManager,
  StateMachine,
  SSEHandler,
  WebChatConfig,
  ChatState,
  Message,
  generateId,
} from '@webchat/core';
import { AGUIHandler, AGUIConfig, AGUIEvent } from './agui';
import { ToolCallDisplay, type ToolCall } from './components/ToolCallDisplay';
import { MessageBubble } from './components/MessageBubble';
import { useMessageHandlers } from './hooks/useMessageHandlers';
import { ConfirmDialog } from './components/ConfirmDialog';
import './styles/tailwind.css';

export interface ChatProps extends WebChatConfig {
  onStateChange?: (state: ChatState) => void;
  onMessageReceived?: (message: Message) => void;
  onError?: (error: Error) => void;
  onClose?: () => void;
  botAvatarUrl?: string;
  userAvatarUrl?: string;
  agui?: AGUIConfig;
  showFullscreenButton?: boolean;
  showClearButton?: boolean;
}

const defaultBotAvatar = 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMzIiIGhlaWdodD0iMzIiIHZpZXdCb3g9IjAgMCAzMiAzMiIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj4KICA8Y2lyY2xlIGN4PSIxNiIgY3k9IjE2IiByPSIxNiIgZmlsbD0iIzgxODVmZiIvPgogIDxjaXJjbGUgY3g9IjExIiBjeT0iMTIiIHI9IjIiIGZpbGw9IndoaXRlIi8+CiAgPGNpcmNsZSBjeD0iMjEiIGN5PSIxMiIgcj0iMiIgZmlsbD0id2hpdGUiLz4KICA8cGF0aCBkPSJNIDEwIDIwIFEgMTYgMjQgMjIgMjAiIHN0cm9rZT0id2hpdGUiIHN0cm9rZS13aWR0aD0iMiIgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIiBmaWxsPSJub25lIi8+Cjwvc3ZnPg==';
const defaultUserAvatar = 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMzIiIGhlaWdodD0iMzIiIHZpZXdCb3g9IjAgMCAzMiAzMiIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj4KICA8Y2lyY2xlIGN4PSIxNiIgY3k9IjE2IiByPSIxNiIgZmlsbD0iIzEwYjk4MSIvPgogIDxjaXJjbGUgY3g9IjE2IiBjeT0iMTIiIHI9IjUiIGZpbGw9IndoaXRlIi8+CiAgPHBhdGggZD0iTSA2IDI4IFEgNiAyMCAxNiAyMCBRIDI2IDIwIDI2IDI4IiBmaWxsPSJ3aGl0ZSIvPgo8L3N2Zz4=';

export const Chat = React.forwardRef<any, ChatProps>((props, ref) => {
  const {
    sseUrl,
    // socketUrl,
    // socketPath,
    customData,
    // theme = 'light',
    title = 'Chat',
    subtitle,
    placeholder = 'Type a message...',
    // reconnectAttempts = 5,
    // reconnectDelay = 1000,
    // enableSSE = true,
    enableStorage = true,
    storageKey = 'webchat_session',
    onStateChange,
    onMessageReceived,
    onError,
    onClose,
    botAvatarUrl,
    userAvatarUrl,
    agui,
    showFullscreenButton = true,
    showClearButton = false,
  } = props;

  // State
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isThinking, setIsThinking] = useState(false);
  const [currentMessageId, setCurrentMessageId] = useState<string | null>(null);
  const [streamingContent, setStreamingContent] = useState<string>('');
  const [toolCalls, setToolCalls] = useState<ToolCall[]>([]);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [showClearConfirm, setShowClearConfirm] = useState(false);

  // Refs
  const sessionManagerRef = useRef<SessionManager | null>(null);
  const stateMachineRef = useRef<StateMachine | null>(null);
  const sseHandlerRef = useRef<SSEHandler | null>(null);
  const aguiHandlerRef = useRef<AGUIHandler | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const streamingContentRef = useRef<string>('');
  const currentMessageIdRef = useRef<string | null>(null);
  const streamingTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // Cache avatar elements to prevent re-fetching on every render
  const botAvatar = React.useMemo(
    () => <img src={botAvatarUrl || defaultBotAvatar} alt="bot" style={{ width: '32px', height: '32px', minWidth: '32px', minHeight: '32px', flexShrink: 0 }} className="rounded-full object-cover" />,
    [botAvatarUrl]
  );
  
  const userAvatar = React.useMemo(
    () => <img src={userAvatarUrl || defaultUserAvatar} alt="user" style={{ width: '32px', height: '32px', minWidth: '32px', minHeight: '32px', flexShrink: 0 }} className="rounded-full object-cover" />,
    [userAvatarUrl]
  );

  // Initialize core components
  useEffect(() => {
    // Initialize SessionManager
    sessionManagerRef.current = new SessionManager({
      enableStorage,
      storageKey,
      customData,
    });

    // Initialize StateMachine
    stateMachineRef.current = new StateMachine('idle');
    stateMachineRef.current.on((event) => {
      onStateChange?.(event.to);
    });

    // Initialize SSEHandler - 不再需要，我们用 fetch 直接处理
    // Initialize AGUIHandler (默认启用)
    aguiHandlerRef.current = new AGUIHandler(agui || { enabled: true, debug: true });
    setupAGUIEventHandlers();

    // Load previous session
    const session = sessionManagerRef.current.initSession();
    if (session && session.messages.length > 0) {
      setMessages(session.messages);
      console.log('📋 Loaded', session.messages.length, 'messages from session');
    }

    return () => {
      console.log('🧹 Chat component unmounting - cleaning up');
      sseHandlerRef.current?.disconnect();
      // 注意：组件卸载时不清理 sessionManager，保留历史记录
    };
  }, []);

  // Setup AG-UI event handlers
  const setupAGUIEventHandlers = () => {
    if (!aguiHandlerRef.current) return;

    aguiHandlerRef.current.getEventStream().subscribe((event: AGUIEvent) => {
      handleAGUIEvent(event);
    });
  };

  // Handle AG-UI protocol events
  const handleAGUIEvent = (event: AGUIEvent) => {
    const eventType = event.type as any;  // Cast to any to handle additional event types

    switch (eventType) {
      case 'RUN_STARTED':
        setIsThinking(true);
        stateMachineRef.current?.transition('chatting');
        break;

      case 'THINKING_START':
        setIsThinking(true);
        break;

      case 'THINKING_END':
        setIsThinking(false);
        break;

      case 'RUN_ERROR':
        setIsThinking(false);
        setIsLoading(false);
        const error = (event as any).error || 'Unknown error';
        const errorMsg: Message = {
          id: generateId(),
          type: 'text',
          content: `❌ **错误**\n\n${error}`,
          sender: 'bot',
          timestamp: Date.now(),
        };
        addMessage(errorMsg);
        break;

      case 'TEXT_MESSAGE_START':
        const startEvent = event as any;
        const startMessageId = startEvent.messageId || generateId();
        
        // 使用 ref 来同步检查（避免闭包和异步问题）
        const messagesSnapshot = sessionManagerRef.current?.getSession()?.messages || [];
        const existingMessage = messagesSnapshot.find((m: Message) => m.id === startMessageId);
        
        if (existingMessage) {
          console.warn('⚠️ Duplicate TEXT_MESSAGE_START for:', startMessageId);
          break;
        }
        
        // 立即清空上一轮的所有状态（同步执行）
        streamingContentRef.current = '';
        currentMessageIdRef.current = startMessageId;
        setCurrentMessageId(startMessageId);
        setToolCalls([]);
        setIsThinking(false);
        setIsLoading(true);
        
        // 创建新消息
        const newBotMsg: Message = {
          id: startMessageId,
          type: 'text',
          content: '',
          sender: 'bot',
          timestamp: Date.now(),
        };
        
        // 更新 session 和消息列表
        sessionManagerRef.current?.addMessage(newBotMsg);
        onMessageReceived?.(newBotMsg);
        setMessages((prev) => [...prev, newBotMsg]);
        break;

      case 'TEXT_MESSAGE_CONTENT':  // 流式内容输出
        const chunkEvent = event as any;
        const delta = chunkEvent.delta || chunkEvent.content || '';
        const contentMessageId = chunkEvent.messageId;
        
        // 如果 CONTENT 的 messageId 和 START 的不一样，更新 ref（后端 bug）
        if (contentMessageId && contentMessageId !== currentMessageIdRef.current) {
          currentMessageIdRef.current = contentMessageId;
          setCurrentMessageId(contentMessageId);
          
          // 检查是否需要创建新消息
          setMessages((prev) => {
            const exists = prev.find(m => m.id === contentMessageId);
            if (!exists) {
              return [...prev, {
                id: contentMessageId,
                type: 'text' as const,
                content: '',
                sender: 'bot' as const,
                timestamp: Date.now(),
              }];
            }
            return prev;
          });
        }
        
        // 累加内容
        streamingContentRef.current += delta;
        
        // 实时更新已存在的消息
        if (currentMessageIdRef.current) {
          setMessages((prev) => {
            const updated = prev.map(msg =>
              msg.id === currentMessageIdRef.current
                ? { ...msg, content: streamingContentRef.current }  // 创建新对象！
                : msg
            );
            
            // 同步更新 session（内存中）
            const session = sessionManagerRef.current?.getSession();
            if (session) {
              const msgIndex = session.messages.findIndex((m: Message) => m.id === currentMessageIdRef.current);
              if (msgIndex !== -1) {
                session.messages[msgIndex] = { ...session.messages[msgIndex], content: streamingContentRef.current };
                // 不在这里保存 localStorage，等 TEXT_MESSAGE_END 时一次性保存
              }
            }
            
            return updated;
          });
        }
        break;

      case 'TEXT_MESSAGE_END':
        // 保存最终内容到 localStorage
        if (currentMessageIdRef.current && sessionManagerRef.current) {
          sessionManagerRef.current.saveSession();
        }
        break;

      case 'TOOL_CALL_START':
        const toolStartEvent = event as any;
        setToolCalls(prev => [...prev, {
          id: toolStartEvent.toolCallId,
          name: toolStartEvent.toolCallName || toolStartEvent.name || 'Unknown Tool',
          status: 'running' as const,
        }]);
        break;

      case 'TOOL_CALL_ARGS':
        const toolArgsEvent = event as any;
        setToolCalls(prev => prev.map(tool =>
          tool.id === toolArgsEvent.toolCallId
            ? { ...tool, args: toolArgsEvent.delta || toolArgsEvent.arguments }
            : tool
        ));
        break;

      case 'TOOL_CALL_END':
        const toolEndEvent = event as any;
        setToolCalls(prev => prev.map(tool =>
          tool.id === toolEndEvent.toolCallId
            ? { ...tool, status: 'completed' as const }
            : tool
        ));
        break;

      case 'TOOL_CALL_RESULT':
        const toolResultEvent = event as any;
        setToolCalls(prev => prev.map(tool =>
          tool.id === toolResultEvent.toolCallId
            ? { ...tool, result: toolResultEvent.content }
            : tool
        ));
        break;

      case 'RUN_FINISHED':
        // ⚠️ 不清空任何 ref！所有清理在下次 TEXT_MESSAGE_START 时统一处理
        setIsLoading(false);
        stateMachineRef.current?.transition('connected');
        break;

      default:
        console.log('AG-UI event:', event);
    }
  };

  // Setup SSE handlers - 已移除，使用 fetch 直接处理

  // Handle legacy message format (fallback)
  const handleLegacyMessage = (data: any) => {
    if (data.content) {
      const botMsg: Message = {
        id: data.id || generateId(),
        type: data.type || 'text',
        content: data.content,
        sender: 'bot',
        timestamp: Date.now(),
        metadata: data.metadata,
      };
      addMessage(botMsg);
      setIsLoading(false);
    }
  };

  // Add message to state and session
  const addMessage = useCallback((message: Message) => {
    setMessages((prev) => [...prev, message]);
    sessionManagerRef.current?.addMessage(message);
    onMessageReceived?.(message);
  }, [onMessageReceived]);

  // Send message
  const handleSendMessage = useCallback(async (value: string) => {
    if (!value.trim() || isLoading) return;

    const userMsg: Message = {
      id: generateId(),
      type: 'text',
      content: value.trim(),
      sender: 'user',
      timestamp: Date.now(),
    };

    addMessage(userMsg);
    setInputValue('');
    setIsLoading(true);

    try {
      stateMachineRef.current?.transition('chatting');

      if (sseUrl) {
        // Get current session data
        const currentSession = sessionManagerRef.current?.getSession();
        
        const requestBody = {
          message: value.trim(),
          sessionId: currentSession?.sessionId,
          ...customData,
        };
        
        // Use fetch with POST to send message and stream response
        const response = await fetch(sseUrl, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            "AUTHORIZATION": "Bearer c96a6f28add4ecf7f59a49cc7e7af2b1ebc7444b745319ccb60a9203421da405"
          },
          body: JSON.stringify(requestBody),
        });

        if (!response.ok || !response.body) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }

        // Process SSE stream
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        
        while (true) {
          const { done, value: chunk } = await reader.read();
          if (done) {
            console.log('✅ Stream complete');
            break;
          }

          const text = decoder.decode(chunk, { stream: true });
          // console.log('📦 Received chunk:', text.substring(0, 100));
          const lines = text.split('\n');

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              const dataStr = line.slice(6);
              if (dataStr.trim()) {
                try {
                  const data = JSON.parse(dataStr);
                  
                  // Process through AG-UI handler
                  if (aguiHandlerRef.current) {
                    const result = aguiHandlerRef.current.processSSEData(data);
                    // AG-UI events are handled via Observable stream
                    // Only handle legacy messages here
                    if (result.type === 'legacy-message' && result.message) {
                      handleLegacyMessage(result.message);
                    }
                  } else {
                    handleLegacyMessage(data);
                  }
                } catch (e) {
                  console.error('Error parsing SSE data:', e);
                }
              }
            }
          }
        }
      } else {
        // Simulate response for demo
        setTimeout(() => {
          const botMsg: Message = {
            id: generateId(),
            type: 'text',
            content: `Echo: ${value}`,
            sender: 'bot',
            timestamp: Date.now(),
          };
          addMessage(botMsg);
          setIsLoading(false);
        }, 1000);
      }
    } catch (error) {
      console.error('Error sending message:', error);
      onError?.(error as Error);
      setIsLoading(false);
    }
  }, [isLoading, sseUrl, customData, addMessage, onError, aguiHandlerRef]);

  // Clear messages
  const handleClear = useCallback(() => {
    setMessages([]);
    // Clear and reinitialize session
    sessionManagerRef.current?.clearSession();
    const newSession = sessionManagerRef.current?.initSession();
    // Reset all streaming states
    setStreamingContent('');
    streamingContentRef.current = '';
    setCurrentMessageId(null);
    currentMessageIdRef.current = null;
    setIsLoading(false);
    setIsThinking(false);
    setToolCalls([]);
    // Reset state machine to initial state
    stateMachineRef.current?.transition('idle');
    // Close the confirmation dialog
    setShowClearConfirm(false);
  }, []);

  // Use message handlers hook
  const { handleRegenerate, handleCopy, handleDelete } = useMessageHandlers({
    messages,
    setMessages,
    sessionManagerRef,
    handleSendMessage,
  });

  // Toggle fullscreen
  const toggleFullscreen = useCallback(() => {
    setIsFullscreen(prev => !prev);
  }, []);

  // Scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingContent]);

  return (
    <div 
      className={`flex flex-col bg-white rounded-lg shadow-lg overflow-hidden transition-all duration-300 ${
        isFullscreen 
          ? 'fixed inset-4 z-50 h-auto' 
          : 'h-full'
      }`} 
      ref={ref}
    >
      {/* Header */}
      <div className="bg-gradient-to-r from-indigo-600 to-purple-600 text-white px-6 py-4 flex items-center justify-between flex-shrink-0">
        <div>
          <div className="text-lg font-semibold">{title}</div>
          {subtitle && <div className="text-sm opacity-90">{subtitle}</div>}
        </div>
        <div className="flex items-center gap-2">
          {showFullscreenButton && (
            <button
              onClick={toggleFullscreen}
              className="text-white hover:bg-white/20 rounded-full p-2 transition-colors w-10 h-10 flex items-center justify-center"
              title={isFullscreen ? 'Exit fullscreen' : 'Fullscreen'}
            >
              {isFullscreen ? (
                <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M8 3v3a2 2 0 0 1-2 2H3m18 0h-3a2 2 0 0 1-2-2V3m0 18v-3a2 2 0 0 1 2-2h3M3 16h3a2 2 0 0 1 2 2v3"/>
                </svg>
              ) : (
                <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/>
                </svg>
              )}
            </button>
          )}
          <button
            onClick={onClose}
            className="text-white hover:bg-white/20 rounded-full p-2 transition-colors w-10 h-10 flex items-center justify-center"
            title="Close chat"
          >
            ✕
          </button>
        </div>
      </div>

      {/* Messages Area */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3 flex flex-col">
        {messages.length === 0 ? (
          <div className="flex items-center justify-center h-full text-gray-400">
            <p className="text-sm">No messages yet. Start a conversation!</p>
          </div>
        ) : (
          messages.map((msg, index) => {
            // Find the last bot message in the conversation
            let lastBotMessageIndex = -1;
            for (let i = messages.length - 1; i >= 0; i--) {
              if (messages[i].sender === 'bot') {
                lastBotMessageIndex = i;
                break;
              }
            }
            
            // Check if this message is part of the last Q&A pair
            // A message is part of last Q&A if:
            // - It's the last bot message, OR
            // - It's a user message that comes right before the last bot message
            const isLastBotMessage = msg.sender === 'bot' && index === lastBotMessageIndex;
            const isLastUserMessage = msg.sender === 'user' && 
              lastBotMessageIndex !== -1 && 
              index === lastBotMessageIndex - 1;
            const isPartOfLastQA = isLastBotMessage || isLastUserMessage;
            
            return (
              <MessageBubble
                key={msg.id}
                message={msg}
                botAvatar={botAvatar}
                userAvatar={userAvatar}
                isLastBotMessage={isPartOfLastQA}
                onRegenerate={handleRegenerate}
                onCopy={handleCopy}
                onDelete={handleDelete}
              />
            );
          })
        )}
        
        {toolCalls.length > 0 && (
          <Bubble
            content={<ToolCallDisplay toolCalls={toolCalls} />}
            avatar={botAvatar}
            placement="start"
            variant="borderless"
            styles={{
              content: {
                background: 'transparent',
                padding: 0,
                border: 'none',
                boxShadow: 'none'
              }
            }}
          />
        )}
        
        {/* Show streaming content */}
        {streamingContent && (
          <Bubble
            content={
              <div className="prose prose-sm max-w-none prose-pre:bg-gray-100 prose-pre:text-gray-900 prose-hr:my-3 prose-h1:mt-3 prose-h1:mb-2 prose-h2:mt-3 prose-h2:mb-2 prose-h3:mt-2 prose-h3:mb-1 prose-h4:mt-2 prose-h4:mb-1 prose-p:my-1.5 prose-ul:my-1.5 prose-ol:my-1.5">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {streamingContent}
                </ReactMarkdown>
              </div>
            }
            avatar={botAvatar}
            placement="start"
          />
        )}
        
        {/* Show loading/thinking state */}
        {(isLoading || isThinking) && !streamingContent && (
          <Bubble
            content={isThinking ? "Thinking..." : "..."}
            avatar={botAvatar}
            placement="start"
            loading={true}
          />
        )}
        
        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div className="border-t border-gray-200 flex-shrink-0 relative">
        {showClearButton && (
          <button
            onClick={() => setShowClearConfirm(true)}
            className="absolute right-4 z-10 p-1.5 bg-white hover:bg-gray-100 transition-colors text-gray-400 hover:text-gray-600"
            style={{ top: '-2rem' }}
            title="清除对话"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M3 6h18M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2M10 11v6M14 11v6"/>
            </svg>
          </button>
        )}
        <div className="p-2">
          <Sender
            value={inputValue}
            onChange={setInputValue}
            onSubmit={handleSendMessage}
            placeholder={placeholder}
            loading={isLoading}
          />
        </div>
      </div>

      {/* Clear Confirmation Dialog */}
      <ConfirmDialog
        isOpen={showClearConfirm}
        title="你即将清除当前对话，清除后将无法恢复，是否继续清除?"
        message="删除后，聊天记录不可恢复，对话内的文件也将被彻底删除。"
        confirmText="清除对话"
        cancelText="取消"
        onConfirm={handleClear}
        onCancel={() => setShowClearConfirm(false)}
      />
    </div>
  );
});

Chat.displayName = 'Chat';

export default Chat;
