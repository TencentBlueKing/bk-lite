'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Bubble, Sender } from '@ant-design/x';
import {
  SessionManager,
  StateMachine,
  SSEStreamParser,
  WebChatConfig,
  ChatState,
  Message,
  MessageContent,
  MessageType,
  generateId,
} from '@webchat/core';
import { AGUIHandler, AGUIConfig, AGUIEvent } from './agui';
import { createAGUIEventHandler } from './aguiEventHandler';
import { MessageBubble } from './components/MessageBubble';
import { useMessageHandlers } from './hooks/useMessageHandlers';
import { ConfirmDialog } from './components/ConfirmDialog';
import {
  isAbortError,
  runOwnedStream,
  StreamLifecycle,
  toError,
} from './streamLifecycle';
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
  apiKey?: string;
}

// 图片大小上限（字节），默认 4MB，可通过 NEXT_PUBLIC_MAX_IMAGE_SIZE 环境变量覆盖
const MAX_IMAGE_SIZE =
  (typeof process !== 'undefined' && process.env?.NEXT_PUBLIC_MAX_IMAGE_SIZE
    ? parseInt(process.env.NEXT_PUBLIC_MAX_IMAGE_SIZE, 10)
    : 0) || 4 * 1024 * 1024;

const defaultBotAvatar = 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMzIiIGhlaWdodD0iMzIiIHZpZXdCb3g9IjAgMCAzMiAzMiIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj4KICA8Y2lyY2xlIGN4PSIxNiIgY3k9IjE2IiByPSIxNiIgZmlsbD0iIzgxODVmZiIvPgogIDxjaXJjbGUgY3g9IjExIiBjeT0iMTIiIHI9IjIiIGZpbGw9IndoaXRlIi8+CiAgPGNpcmNsZSBjeD0iMjEiIGN5PSIxMiIgcj0iMiIgZmlsbD0id2hpdGUiLz4KICA8cGF0aCBkPSJNIDEwIDIwIFEgMTYgMjQgMjIgMjAiIHN0cm9rZT0id2hpdGUiIHN0cm9rZS13aWR0aD0iMiIgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIiBmaWxsPSJub25lIi8+Cjwvc3ZnPg==';
const defaultUserAvatar = 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMzIiIGhlaWdodD0iMzIiIHZpZXdCb3g9IjAgMCAzMiAzMiIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj4KICA8Y2lyY2xlIGN4PSIxNiIgY3k9IjE2IiByPSIxNiIgZmlsbD0iIzEwYjk4MSIvPgogIDxjaXJjbGUgY3g9IjE2IiBjeT0iMTIiIHI9IjUiIGZpbGw9IndoaXRlIi8+CiAgPHBhdGggZD0iTSA2IDI4IFEgNiAyMCAxNiAyMCBRIDI2IDIwIDI2IDI4IiBmaWxsPSJ3aGl0ZSIvPgo8L3N2Zz4=';

export const Chat = React.forwardRef<HTMLDivElement, ChatProps>((props, ref) => {
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
    apiKey,
  } = props;

  // State
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isThinking, setIsThinking] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [showClearConfirm, setShowClearConfirm] = useState(false);
  const [uploadedImages, setUploadedImages] = useState<string[]>([]);

  // Refs
  const sessionManagerRef = useRef<SessionManager | null>(null);
  const stateMachineRef = useRef<StateMachine | null>(null);
  const aguiHandlerRef = useRef<AGUIHandler | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const streamingContentRef = useRef<string>('');
  const currentMessageIdRef = useRef<string | null>(null);
  const streamLifecycleRef = useRef<StreamLifecycle | null>(null);
  if (!streamLifecycleRef.current) {
    streamLifecycleRef.current = new StreamLifecycle();
  }
  // 保持 onMessageReceived 最新引用，避免 useEffect 空 deps 闭包固化旧 prop
  const onMessageReceivedRef = useRef(onMessageReceived);
  useEffect(() => {
    onMessageReceivedRef.current = onMessageReceived;
  }, [onMessageReceived]);

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
    const streamLifecycle = streamLifecycleRef.current;
    streamLifecycle?.mount();

    // Initialize SessionManager
    sessionManagerRef.current = new SessionManager({
      enableStorage,
      storageKey,
      customData,
    });

    // Initialize StateMachine
    stateMachineRef.current = new StateMachine('idle');
    const unsubscribeState = stateMachineRef.current.on((event) => {
      onStateChange?.(event.to);
    });

    // Initialize SSEHandler - 不再需要，我们用 fetch 直接处理
    // Initialize AGUIHandler (默认启用)
    aguiHandlerRef.current = new AGUIHandler(agui || { enabled: true, debug: false });
    const aguiSubscription = setupAGUIEventHandlers();

    // Load previous session
    const session = sessionManagerRef.current.initSession();
    if (session && session.messages.length > 0) {
      setMessages(session.messages);
    }

    return () => {
      void streamLifecycle?.dispose();
      aguiSubscription?.unsubscribe();
      aguiHandlerRef.current?.destroy();
      unsubscribeState();
      stateMachineRef.current?.destroy();
    };
  }, []);

  // Setup AG-UI event handlers
  const setupAGUIEventHandlers = () => {
    if (!aguiHandlerRef.current) return;

    return aguiHandlerRef.current.getEventStream().subscribe((event: AGUIEvent) => {
      handleAGUIEvent(event);
    });
  };

  // Add message to state and session
  const addMessage = useCallback((message: Message) => {
    setMessages((prev) => {
      if (prev.some((msg) => msg.id === message.id)) {
        console.warn('Duplicate message detected, skipping:', message.id);
        return prev;
      }
      return [...prev, message];
    });
    sessionManagerRef.current?.addMessage(message);
    onMessageReceivedRef.current?.(message);
  }, []);

  const handleAGUIEvent = createAGUIEventHandler({
    currentMessageIdRef,
    streamingContentRef,
    sessionManagerRef,
    stateMachineRef,
    onMessageReceivedRef,
    setMessages,
    setIsLoading,
    setIsThinking,
    addMessage,
  });

  // Handle legacy message format (fallback)
  const handleLegacyMessage = (data: unknown) => {
    if (!data || typeof data !== 'object') {
      return;
    }
    const legacy = data as Partial<Message> & { content?: Message['content'] };
    if (legacy.content) {
      const botMsg: Message = {
        id: legacy.id || generateId(),
        type: legacy.type || 'text',
        content: legacy.content,
        sender: 'bot',
        timestamp: Date.now(),
        metadata: legacy.metadata,
      };
      addMessage(botMsg);
    }
  };

  // Handle image upload
  const handleImageUpload = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    const readers: Promise<string>[] = [];

    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      if (!file.type.startsWith('image/')) continue;
      if (file.size > MAX_IMAGE_SIZE) {
        const limitMB = MAX_IMAGE_SIZE / (1024 * 1024);
        onError?.(new Error(`图片"${file.name}"超过 ${limitMB}MB 大小限制，已跳过。`));
        continue;
      }

      const reader = new FileReader();
      const promise = new Promise<string>((resolve) => {
        reader.onload = (event) => {
          const base64 = event.target?.result as string;
          resolve(base64);
        };
        reader.readAsDataURL(file);
      });
      readers.push(promise);
    }

    Promise.all(readers).then((results) => {
      setUploadedImages((prev) => [...prev, ...results]);
    });

    // Reset input
    e.target.value = '';
  }, [onError]);

  // Remove uploaded image
  const handleRemoveImage = useCallback((index: number) => {
    setUploadedImages((prev) => prev.filter((_, i) => i !== index));
  }, []);

  // Handle paste event for images
  const handlePaste = useCallback((e: React.ClipboardEvent) => {
    const items = e.clipboardData?.items;
    if (!items) return;

    const imageFiles: File[] = [];
    for (let i = 0; i < items.length; i++) {
      const item = items[i];
      if (item.type.startsWith('image/')) {
        const file = item.getAsFile();
        if (file) {
          if (file.size > MAX_IMAGE_SIZE) {
            const limitMB = MAX_IMAGE_SIZE / (1024 * 1024);
            onError?.(new Error(`粘贴的图片超过 ${limitMB}MB 大小限制，已跳过。`));
            continue;
          }
          imageFiles.push(file);
        }
      }
    }

    if (imageFiles.length > 0) {
      e.preventDefault(); // 阻止默认粘贴行为
      
      const readers: Promise<string>[] = imageFiles.map(file => {
        return new Promise<string>((resolve) => {
          const reader = new FileReader();
          reader.onload = (event) => {
            const base64 = event.target?.result as string;
            resolve(base64);
          };
          reader.readAsDataURL(file);
        });
      });

      Promise.all(readers).then((results) => {
        setUploadedImages((prev) => [...prev, ...results]);
      });
    }
  }, [onError]);

  // Send message
  const handleSendMessage = useCallback(async (value: string) => {
    if ((!value.trim() && uploadedImages.length === 0) || isLoading) return;

    // Build message content
    let messageContent: string | MessageContent[];
    let messageType: MessageType = 'text';

    if (uploadedImages.length > 0) {
      // Multimodal message with images and text
      messageContent = [
        ...uploadedImages.map((url) => ({ type: 'image_url' as const, image_url: url })),
        ...(value.trim() ? [{ type: 'message' as const, message: value.trim() }] : []),
      ];
      messageType = 'multimodal';
    } else {
      // Text only message
      messageContent = value.trim();
      messageType = 'text';
    }

    const userMsg: Message = {
      id: generateId(),
      type: messageType,
      content: messageContent,
      sender: 'user',
      timestamp: Date.now(),
    };

    addMessage(userMsg);
    setInputValue('');
    setUploadedImages([]);
    setIsLoading(true);

    try {
      stateMachineRef.current?.transitionToChatting();

      if (sseUrl) {
        const streamLifecycle = streamLifecycleRef.current;
        const stream = streamLifecycle?.begin();
        if (!streamLifecycle || !stream) {
          return;
        }

        // Get current session data
        const currentSession = sessionManagerRef.current?.getSession();
        
        const requestBody = {
          message: messageType === 'multimodal' ? messageContent : value.trim(),
          sessionId: currentSession?.sessionId,
          ...customData,
        };
        
        // Use fetch with POST to send message and stream response
        const headers: HeadersInit = {
          'Content-Type': 'application/json',
        };
        
        // Add Authorization header if apiKey is provided
        if (apiKey) {
          headers['Authorization'] = `Bearer ${apiKey}`;
        }
        
        const decoder = new TextDecoder();
        const sseParser = new SSEStreamParser();
        await runOwnedStream({
          lifecycle: streamLifecycle,
          stream,
          request: (signal) =>
            fetch(sseUrl, {
              method: 'POST',
              headers,
              body: JSON.stringify(requestBody),
              ...(signal ? { signal } : {}),
            }),
          onChunk: (chunk) => {
            const text = decoder.decode(chunk, { stream: true });
            for (const data of sseParser.push(text)) {
              if (typeof data !== 'object' || data === null) {
                continue;
              }

              // Process through AG-UI handler; fall back to legacy messages
              if (aguiHandlerRef.current) {
                const result = aguiHandlerRef.current.processSSEData(data);
                if (result.type === 'legacy-message' && result.message) {
                  handleLegacyMessage(result.message);
                }
              } else {
                handleLegacyMessage(data);
              }
            }
          },
          onError: (error) => {
            console.error('Error reading stream:', error);
            onError?.(error);
          },
          onComplete: () => {
            setIsLoading(false);
            setIsThinking(false);
          },
        });
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
      if (isAbortError(error)) {
        return;
      }
      console.error('Error sending message:', error);
      onError?.(toError(error));
      setIsLoading(false);
    }
  }, [isLoading, sseUrl, customData, addMessage, onError, uploadedImages]);

  const handleStopStreaming = useCallback(() => {
    void streamLifecycleRef.current?.cancel('user-stopped');
    setIsLoading(false);
    setIsThinking(false);
  }, []);

  // Clear messages
  const handleClear = useCallback(() => {
    void streamLifecycleRef.current?.cancel('session-cleared');
    setMessages([]);
    // Clear and reinitialize session
    sessionManagerRef.current?.clearSession();
    sessionManagerRef.current?.initSession();
    // Reset all streaming states
    streamingContentRef.current = '';
    currentMessageIdRef.current = null;
    setIsLoading(false);
    setIsThinking(false);
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
  }, [messages]);

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
        
        {/* Show loading/thinking state */}
        {(isLoading || isThinking) && (
          <Bubble
            content={isThinking ? "思考中..." : "正在输入..."}
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
        
        {/* Image preview area */}
        {uploadedImages.length > 0 && (
          <div className="px-4 pt-2 pb-1 flex flex-wrap gap-2">
            {uploadedImages.map((img, index) => (
              <div key={index} className="relative group">
                <img 
                  src={img} 
                  alt={`Upload ${index + 1}`}
                  className="w-16 h-16 object-cover rounded border border-gray-200"
                />
                <button
                  onClick={() => handleRemoveImage(index)}
                  className="absolute -top-1 -right-1 w-4 h-4 bg-red-500 text-white rounded-full flex items-center justify-center text-xs opacity-0 group-hover:opacity-100 transition-opacity"
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        )}
        
        <div className="p-2 relative">
          <div className="relative">
            {/* Image upload button positioned inside Sender */}
            <label className="absolute left-3 top-1/2 -translate-y-1/2 z-10 cursor-pointer text-gray-400 hover:text-gray-600 transition-colors">
              <input
                type="file"
                accept="image/*"
                multiple
                onChange={handleImageUpload}
                className="hidden"
              />
              <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
                <circle cx="8.5" cy="8.5" r="1.5"/>
                <polyline points="21 15 16 10 5 21"/>
              </svg>
            </label>
            
            <div onPaste={handlePaste}>
              <Sender
                value={inputValue}
                onChange={setInputValue}
                onSubmit={handleSendMessage}
                onCancel={handleStopStreaming}
                placeholder={placeholder}
                loading={isLoading}
                styles={{
                  input: {
                    paddingLeft: '25px',
                  }
                }}
              />
            </div>
          </div>
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
