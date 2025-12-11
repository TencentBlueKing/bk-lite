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
  apiKey?: string;
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
    apiKey,
  } = props;

  // State
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isThinking, setIsThinking] = useState(false);
  const [currentMessageId, setCurrentMessageId] = useState<string | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [showClearConfirm, setShowClearConfirm] = useState(false);
  const [uploadedImages, setUploadedImages] = useState<string[]>([]);

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
    }

    return () => {
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
        
        streamingContentRef.current = '';
        currentMessageIdRef.current = null;
        setCurrentMessageId(null);
        setIsLoading(true);
        
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
        const errorContent = `\n\n❌ **错误**: ${error}`;
        
        // 如果有当前消息，追加错误信息到末尾
        if (currentMessageIdRef.current) {
          streamingContentRef.current += errorContent;
          
          setMessages((prev) => {
            return prev.map(msg => {
              if (msg.id === currentMessageIdRef.current) {
                const chunks = msg.metadata?.contentChunks || [];
                const lastChunk = chunks[chunks.length - 1];
                
                let newChunks;
                if (lastChunk && lastChunk.type === 'text') {
                  newChunks = [
                    ...chunks.slice(0, -1),
                    { type: 'text', content: streamingContentRef.current }
                  ];
                } else {
                  newChunks = [
                    ...chunks,
                    { type: 'text', content: streamingContentRef.current }
                  ];
                }
                
                return {
                  ...msg,
                  content: streamingContentRef.current,
                  metadata: {
                    ...msg.metadata,
                    contentChunks: newChunks
                  }
                };
              }
              return msg;
            });
          });
          
          // 同步更新 session 数据
          const session = sessionManagerRef.current?.getSession();
          if (session) {
            const msgIndex = session.messages.findIndex((m: Message) => m.id === currentMessageIdRef.current);
            if (msgIndex !== -1) {
              const chunks = session.messages[msgIndex].metadata?.contentChunks || [];
              const lastChunk = chunks[chunks.length - 1];
              
              let newChunks;
              if (lastChunk && lastChunk.type === 'text') {
                newChunks = [
                  ...chunks.slice(0, -1),
                  { type: 'text', content: streamingContentRef.current }
                ];
              } else {
                newChunks = [
                  ...chunks,
                  { type: 'text', content: streamingContentRef.current }
                ];
              }
              
              session.messages[msgIndex] = { 
                ...session.messages[msgIndex], 
                content: streamingContentRef.current,
                metadata: {
                  ...session.messages[msgIndex].metadata,
                  contentChunks: newChunks
                }
              };
            }
          }
          
          // 保存到 session
          if (sessionManagerRef.current) {
            sessionManagerRef.current.saveSession();
          }
        } else {
          // 没有当前消息，创建新的错误消息
          const errorMsg: Message = {
            id: generateId(),
            type: 'text',
            content: `❌ **错误**\n\n${error}`,
            sender: 'bot',
            timestamp: Date.now(),
          };
          addMessage(errorMsg);
        }
        break;

      case 'TEXT_MESSAGE_START':
        const startEvent = event as any;
        const startRole = startEvent.role || startEvent.sender;
        
        // 如果是用户消息，跳过（用户消息已经在发送时添加了）
        if (startRole === 'user') {
          break;
        }
        
        // 如果还没有创建消息，现在创建
        if (!currentMessageIdRef.current) {
          const newAssistantMsg: Message = {
            id: generateId(),
            type: 'text',
            content: '',
            sender: 'bot',
            timestamp: Date.now(),
            metadata: {
              contentChunks: []
            },
          };
          
          currentMessageIdRef.current = newAssistantMsg.id;
          setCurrentMessageId(newAssistantMsg.id);
          
          setMessages((prev) => [...prev, newAssistantMsg]);
          sessionManagerRef.current?.addMessage(newAssistantMsg);
          onMessageReceived?.(newAssistantMsg);
          
        }
        
        // 重置当前文本内容累加器
        streamingContentRef.current = '';
        setIsThinking(false);
        setIsLoading(true);
        
        break;

      case 'TEXT_MESSAGE_CONTENT':  // 流式内容输出
        const chunkEvent = event as any;
        const delta = chunkEvent.delta || chunkEvent.content || '';
        const contentRole = chunkEvent.role || chunkEvent.sender;
        
        
        // 如果是用户消息，跳过
        if (contentRole === 'user') {
          break;
        }
        
        // 如果没有当前消息 ID，说明没有收到 START 事件，忽略
        if (!currentMessageIdRef.current) {
          console.warn('⚠️ Received CONTENT without START, ignoring');
          break;
        }
        
        // 收到第一个内容块时关闭 loading 状态
        if (streamingContentRef.current === '' && delta) {
          setIsLoading(false);
        }
        
        // 累加内容到 ref
        streamingContentRef.current += delta;
        
        // 更新消息的 contentChunks，更新或添加最后一个文本 chunk
        setMessages((prev) => {
          return prev.map(msg => {
            if (msg.id === currentMessageIdRef.current) {
              const chunks = msg.metadata?.contentChunks || [];
              const lastChunk = chunks[chunks.length - 1];
              
              let newChunks;
              if (lastChunk && lastChunk.type === 'text') {
                // 更新最后一个文本 chunk
                newChunks = [
                  ...chunks.slice(0, -1),
                  { type: 'text', content: streamingContentRef.current }
                ];
              } else {
                // 添加新的文本 chunk
                newChunks = [
                  ...chunks,
                  { type: 'text', content: streamingContentRef.current }
                ];
              }
              
              return {
                ...msg,
                content: streamingContentRef.current, // 保留 content 用于复制等操作
                metadata: {
                  ...msg.metadata,
                  contentChunks: newChunks
                }
              };
            }
            return msg;
          });
        });
        
        // 同步更新 session（内存中，不保存到 localStorage）
        const session = sessionManagerRef.current?.getSession();
        if (session) {
          const msgIndex = session.messages.findIndex((m: Message) => m.id === currentMessageIdRef.current);
          if (msgIndex !== -1) {
            const chunks = session.messages[msgIndex].metadata?.contentChunks || [];
            const lastChunk = chunks[chunks.length - 1];
            
            let newChunks;
            if (lastChunk && lastChunk.type === 'text') {
              newChunks = [
                ...chunks.slice(0, -1),
                { type: 'text', content: streamingContentRef.current }
              ];
            } else {
              newChunks = [
                ...chunks,
                { type: 'text', content: streamingContentRef.current }
              ];
            }
            
            session.messages[msgIndex] = { 
              ...session.messages[msgIndex], 
              content: streamingContentRef.current,
              metadata: {
                ...session.messages[msgIndex].metadata,
                contentChunks: newChunks
              }
            };
          }
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
        const newToolCall: ToolCall = {
          id: toolStartEvent.toolCallId,
          name: toolStartEvent.toolCallName || toolStartEvent.name || 'Unknown Tool',
          status: 'running' as const,
        };
        
        // 如果还没有创建消息，现在创建
        if (!currentMessageIdRef.current) {
          const newAssistantMsg: Message = {
            id: generateId(),
            type: 'text',
            content: '',
            sender: 'bot',
            timestamp: Date.now(),
            metadata: {
              contentChunks: []
            },
          };
          
          currentMessageIdRef.current = newAssistantMsg.id;
          setCurrentMessageId(newAssistantMsg.id);
          
          setMessages((prev) => [...prev, newAssistantMsg]);
          sessionManagerRef.current?.addMessage(newAssistantMsg);
          onMessageReceived?.(newAssistantMsg);
          
        }
        
        // Add tool call as a new separate chunk
        setMessages((prev) => {
          return prev.map(msg => {
            if (msg.id === currentMessageIdRef.current) {
              const chunks = msg.metadata?.contentChunks || [];
              
              // Check if this tool already exists in any chunk to prevent duplicates
              const toolExists = chunks.some((chunk: any) => 
                chunk.type === 'toolCalls' && 
                chunk.toolCalls.some((t: ToolCall) => t.id === newToolCall.id)
              );
              
              if (toolExists) {
                console.warn('⚠️ Tool call already exists:', newToolCall.id);
                return msg;
              }
              
              // Add as a new separate chunk for each tool call
              const newChunks = [
                ...chunks,
                { type: 'toolCalls', toolCalls: [newToolCall] }
              ];
              
              return { 
                ...msg, 
                metadata: { 
                  ...msg.metadata, 
                  contentChunks: newChunks
                } 
              };
            }
            return msg;
          });
        });
        
        // Also update session
        const session1 = sessionManagerRef.current?.getSession();
        if (session1) {
          const msgIndex1 = session1.messages.findIndex((m: Message) => m.id === currentMessageIdRef.current);
          if (msgIndex1 !== -1) {
            const chunks = session1.messages[msgIndex1].metadata?.contentChunks || [];
            
            // Check if this tool already exists to prevent duplicates
            const toolExists = chunks.some((chunk: any) => 
              chunk.type === 'toolCalls' && 
              chunk.toolCalls.some((t: ToolCall) => t.id === newToolCall.id)
            );
            
            if (!toolExists) {
              // Add as a new separate chunk
              const newChunks = [
                ...chunks,
                { type: 'toolCalls', toolCalls: [newToolCall] }
              ];
              
              session1.messages[msgIndex1].metadata = {
                ...session1.messages[msgIndex1].metadata,
                contentChunks: newChunks
              };
            }
          }
        }
        break;

      case 'TOOL_CALL_ARGS':
        const toolArgsEvent = event as any;
        setMessages((prev) => {
          return prev.map(msg => {
            if (msg.id === currentMessageIdRef.current && msg.metadata?.contentChunks) {
              const chunks = msg.metadata.contentChunks;
              const newChunks = chunks.map((chunk: any) => {
                if (chunk.type === 'toolCalls') {
                  return {
                    ...chunk,
                    toolCalls: chunk.toolCalls.map((tool: ToolCall) =>
                      tool.id === toolArgsEvent.toolCallId
                        ? { ...tool, args: toolArgsEvent.delta || toolArgsEvent.arguments }
                        : tool
                    )
                  };
                }
                return chunk;
              });
              
              return {
                ...msg,
                metadata: {
                  ...msg.metadata,
                  contentChunks: newChunks
                }
              };
            }
            return msg;
          });
        });
        
        // Also update session
        const session2 = sessionManagerRef.current?.getSession();
        if (session2) {
          const msgIndex2 = session2.messages.findIndex((m: Message) => m.id === currentMessageIdRef.current);
          if (msgIndex2 !== -1 && session2.messages[msgIndex2].metadata?.contentChunks) {
            const chunks = session2.messages[msgIndex2].metadata.contentChunks;
            session2.messages[msgIndex2].metadata.contentChunks = chunks.map((chunk: any) => {
              if (chunk.type === 'toolCalls') {
                return {
                  ...chunk,
                  toolCalls: chunk.toolCalls.map((tool: ToolCall) =>
                    tool.id === toolArgsEvent.toolCallId
                      ? { ...tool, args: toolArgsEvent.delta || toolArgsEvent.arguments }
                      : tool
                  )
                };
              }
              return chunk;
            });
          }
        }
        break;

      case 'TOOL_CALL_END':
        const toolEndEvent = event as any;
        setMessages((prev) => {
          return prev.map(msg => {
            if (msg.id === currentMessageIdRef.current && msg.metadata?.contentChunks) {
              const chunks = msg.metadata.contentChunks;
              const newChunks = chunks.map((chunk: any) => {
                if (chunk.type === 'toolCalls') {
                  return {
                    ...chunk,
                    toolCalls: chunk.toolCalls.map((tool: ToolCall) =>
                      tool.id === toolEndEvent.toolCallId
                        ? { ...tool, status: 'completed' as const }
                        : tool
                    )
                  };
                }
                return chunk;
              });
              
              return {
                ...msg,
                metadata: {
                  ...msg.metadata,
                  contentChunks: newChunks
                }
              };
            }
            return msg;
          });
        });
        
        // Also update session
        const session3 = sessionManagerRef.current?.getSession();
        if (session3) {
          const msgIndex3 = session3.messages.findIndex((m: Message) => m.id === currentMessageIdRef.current);
          if (msgIndex3 !== -1 && session3.messages[msgIndex3].metadata?.contentChunks) {
            const chunks = session3.messages[msgIndex3].metadata.contentChunks;
            session3.messages[msgIndex3].metadata.contentChunks = chunks.map((chunk: any) => {
              if (chunk.type === 'toolCalls') {
                return {
                  ...chunk,
                  toolCalls: chunk.toolCalls.map((tool: ToolCall) =>
                    tool.id === toolEndEvent.toolCallId
                      ? { ...tool, status: 'completed' as const }
                      : tool
                  )
                };
              }
              return chunk;
            });
          }
        }
        break;

      case 'TOOL_CALL_RESULT':
        const toolResultEvent = event as any;
        setMessages((prev) => {
          return prev.map(msg => {
            if (msg.id === currentMessageIdRef.current && msg.metadata?.contentChunks) {
              const chunks = msg.metadata.contentChunks;
              const newChunks = chunks.map((chunk: any) => {
                if (chunk.type === 'toolCalls') {
                  return {
                    ...chunk,
                    toolCalls: chunk.toolCalls.map((tool: ToolCall) =>
                      tool.id === toolResultEvent.toolCallId
                        ? { ...tool, result: toolResultEvent.content }
                        : tool
                    )
                  };
                }
                return chunk;
              });
              
              return {
                ...msg,
                metadata: {
                  ...msg.metadata,
                  contentChunks: newChunks
                }
              };
            }
            return msg;
          });
        });
        
        // Also update session
        const session4 = sessionManagerRef.current?.getSession();
        if (session4) {
          const msgIndex4 = session4.messages.findIndex((m: Message) => m.id === currentMessageIdRef.current);
          if (msgIndex4 !== -1 && session4.messages[msgIndex4].metadata?.contentChunks) {
            const chunks = session4.messages[msgIndex4].metadata.contentChunks;
            session4.messages[msgIndex4].metadata.contentChunks = chunks.map((chunk: any) => {
              if (chunk.type === 'toolCalls') {
                return {
                  ...chunk,
                  toolCalls: chunk.toolCalls.map((tool: ToolCall) =>
                    tool.id === toolResultEvent.toolCallId
                      ? { ...tool, result: toolResultEvent.content }
                      : tool
                  )
                };
              }
              return chunk;
            });
          }
        }
        break;

      case 'RUN_FINISHED':
        if (currentMessageIdRef.current && sessionManagerRef.current) {
          sessionManagerRef.current.saveSession();
        }
        setIsLoading(false);
        setIsThinking(false);
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
    setMessages((prev) => {
      // 防止重复添加：检查是否已存在相同 id 的消息
      if (prev.some(msg => msg.id === message.id)) {
        console.warn('⚠️ Duplicate message detected, skipping:', message.id);
        return prev;
      }
      return [...prev, message];
    });
    sessionManagerRef.current?.addMessage(message);
    onMessageReceived?.(message);
  }, [onMessageReceived]);

  // Handle image upload
  const handleImageUpload = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    const newImages: string[] = [];
    const readers: Promise<string>[] = [];

    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      if (!file.type.startsWith('image/')) continue;

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
  }, []);

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
  }, []);

  // Send message
  const handleSendMessage = useCallback(async (value: string) => {
    if ((!value.trim() && uploadedImages.length === 0) || isLoading) return;

    // Build message content
    let messageContent: string | any[];
    let messageType: MessageType = 'text';

    if (uploadedImages.length > 0) {
      // Multimodal message with images and text
      messageContent = [
        ...uploadedImages.map(url => ({ type: 'image_url', image_url: url })),
        ...(value.trim() ? [{ type: 'message', message: value.trim() }] : [])
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
      stateMachineRef.current?.transition('chatting');

      if (sseUrl) {
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
        
        const response = await fetch(sseUrl, {
          method: 'POST',
          headers,
          body: JSON.stringify(requestBody),
        });

        if (!response.ok || !response.body) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }

        // Process SSE stream
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        
        try {
          while (true) {
            const { done, value: chunk } = await reader.read();
            if (done) {
              console.log('✅ Stream complete');
              // Ensure loading state is reset when stream completes
              setIsLoading(false);
              setIsThinking(false);
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
        } catch (streamError) {
          console.error('Error reading stream:', streamError);
          setIsLoading(false);
          setIsThinking(false);
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
  }, [isLoading, sseUrl, customData, addMessage, onError, aguiHandlerRef, uploadedImages]);

  // Clear messages
  const handleClear = useCallback(() => {
    setMessages([]);
    // Clear and reinitialize session
    sessionManagerRef.current?.clearSession();
    const newSession = sessionManagerRef.current?.initSession();
    // Reset all streaming states
    streamingContentRef.current = '';
    setCurrentMessageId(null);
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
                placeholder={placeholder}
                loading={isLoading}
                styles={{
                  input: {
                    paddingLeft: '40px',
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
