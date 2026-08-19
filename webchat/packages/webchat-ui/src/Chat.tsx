'use client';

import React, {
  useState,
  useEffect,
  useLayoutEffect,
  useRef,
  useCallback,
  useMemo,
} from 'react';
import {
  SessionManager,
  StateMachine,
  SSEStreamParser,
  Message,
  MessageContent,
  MessageType,
  generateId,
  normalizeWebChatConfig,
} from '@webchat/core';
import { AGUIHandler, AGUIEvent, type CustomProtocolEvent } from './agui';
import type { ChatProps } from './chatProps';
import { createAGUIEventHandler } from './aguiEventHandler';
import { parseLegacyMessage } from './legacyMessage';
import { useMessageHandlers } from './hooks/useMessageHandlers';
import { ConfirmDialog } from './components/ConfirmDialog';
import { formatDegradedCustomEvent, HitlPanels, isBlockingHitlEvent } from './components/HitlPanels';
import { ConversationSkeleton } from './components/ConversationSkeleton';
import { PillComposer } from './components/PillComposer';
import {
  pendingImagesReducer,
  readFileAsDataUrl,
  readImageBatch,
  inspectImageBatch,
  resolveImageBudget,
  validateImageBatch,
  validateImagePixelBudget,
  type ImageBudgetViolation,
  type PendingImage,
  type PendingImageAction,
} from './imageBudget';
import {
  isAbortError,
  runOwnedStream,
  StreamLifecycle,
  toError,
} from './streamLifecycle';
import { WC } from './chrome';

export type { ChatProps };

const MessageBubble = React.lazy(async () => {
  const mod = await import('./components/MessageBubble');
  return { default: mod.MessageBubble };
});

// 图片大小上限（字节），默认 4MB，可通过 NEXT_PUBLIC_MAX_IMAGE_SIZE 环境变量覆盖
const MAX_IMAGE_SIZE =
  (typeof process !== 'undefined' && process.env?.NEXT_PUBLIC_MAX_IMAGE_SIZE
    ? parseInt(process.env.NEXT_PUBLIC_MAX_IMAGE_SIZE, 10)
    : 0) || 4 * 1024 * 1024;

const avatarImgClass = 'h-8 w-8 min-h-8 min-w-8 flex-shrink-0 rounded-full object-cover';

const DefaultAvatar: React.FC<{ kind: 'bot' | 'user' }> = ({ kind }) => (
  <span
    className={`${avatarImgClass} inline-flex items-center justify-center`}
    style={{
      background: kind === 'bot' ? WC.indigo : WC.success,
      color: WC.onPrimary,
    }}
    aria-hidden
  >
    {kind === 'bot' ? (
      <svg width="18" height="18" viewBox="0 0 24 24">
        <rect x="4" y="8" width="16" height="12" rx="3.5" fill="currentColor" />
        <circle cx="12" cy="4.5" r="1.5" fill="currentColor" />
        <rect x="11.25" y="5.6" width="1.5" height="2.6" rx="0.6" fill="currentColor" />
        <circle cx="9.2" cy="13.2" r="1.4" fill={WC.indigo} />
        <circle cx="14.8" cy="13.2" r="1.4" fill={WC.indigo} />
      </svg>
    ) : (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
        <circle cx="12" cy="8" r="4" />
        <path d="M4.2 20.2C5.1 16.8 8.2 14.5 12 14.5s6.9 2.3 7.8 5.7c.1.4-.2.8-.6.8H4.8c-.4 0-.7-.4-.6-.8z" />
      </svg>
    )}
  </span>
);

const ChatInner = React.forwardRef<HTMLDivElement, ChatProps>((props, ref) => {
  const {
    sseUrl,
    customData,
    // theme = 'light',
    title = 'Chat',
    subtitle,
    placeholder = 'Type a message...',
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
    showHeader = true,
    apiKey,
    credentials,
    requestHeaders,
    initialMessages,
    historyLoading = false,
    wideLayout = false,
    fullscreen,
    onFullscreenChange,
    onStreamingStop,
    onCustomEvent,
    platform,
    kickoffMessage,
    onKickoffConsumed,
    streamingTextBatching = true,
    maxImageCount,
    maxImagePixels,
    maxTotalImageBytes,
    maxTotalImagePixels,
    imageReadConcurrency,
    allowUnknownImagePreview,
  } = normalizeWebChatConfig(props) as ChatProps;
  const imageBudget = React.useMemo(
    () => resolveImageBudget({
      allowUnknownImagePreview,
      imageReadConcurrency,
      maxImageCount,
      maxImagePixels,
      maxTotalImageBytes,
      maxTotalImagePixels,
    }),
    [
      allowUnknownImagePreview,
      imageReadConcurrency,
      maxImageCount,
      maxImagePixels,
      maxTotalImageBytes,
      maxTotalImagePixels,
    ],
  );

  // State
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isThinking, setIsThinking] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [showClearConfirm, setShowClearConfirm] = useState(false);
  const [imageSelectionError, setImageSelectionError] = useState<string | null>(null);
  const [uploadedImages, setUploadedImages] = useState<PendingImage[]>([]);
  const [hitlEvent, setHitlEvent] = useState<CustomProtocolEvent | null>(null);

  // Refs
  const sessionManagerRef = useRef<SessionManager | null>(null);
  const stateMachineRef = useRef<StateMachine | null>(null);
  const aguiHandlerRef = useRef<AGUIHandler | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const streamingContentRef = useRef<string>('');
  const currentMessageIdRef = useRef<string | null>(null);
  const streamingTextBatchingRef = useRef(streamingTextBatching);
  streamingTextBatchingRef.current = streamingTextBatching;
  const streamLifecycleRef = useRef<StreamLifecycle | null>(null);
  const uploadedImagesRef = useRef<PendingImage[]>([]);
  const pendingImageBatchesRef = useRef(new Map<symbol, { controller: AbortController; files: readonly File[] }>());
  const imageBatchQueueRef = useRef<Promise<void>>(Promise.resolve());
  const imageSelectionGenerationRef = useRef(0);
  if (!streamLifecycleRef.current) {
    streamLifecycleRef.current = new StreamLifecycle();
  }
  const cancelPendingImageBatches = useCallback(() => {
    imageSelectionGenerationRef.current += 1;
    pendingImageBatchesRef.current.forEach(({ controller }) => controller.abort());
    pendingImageBatchesRef.current.clear();
  }, []);
  const onStateChangeRef = useRef(onStateChange);
  useLayoutEffect(() => {
    onStateChangeRef.current = onStateChange;
  }, [onStateChange]);
  // 保持 onMessageReceived 最新引用，避免 useEffect 空 deps 闭包固化旧 prop
  const onMessageReceivedRef = useRef(onMessageReceived);
  useEffect(() => {
    onMessageReceivedRef.current = onMessageReceived;
  }, [onMessageReceived]);

  // Cache avatar elements to prevent re-fetching on every render
  const botAvatar = React.useMemo(
    () =>
      botAvatarUrl ? (
        <img src={botAvatarUrl} alt="bot" className={avatarImgClass} />
      ) : (
        <DefaultAvatar kind="bot" />
      ),
    [botAvatarUrl]
  );

  const userAvatar = React.useMemo(
    () =>
      userAvatarUrl ? (
        <img src={userAvatarUrl} alt="user" className={avatarImgClass} />
      ) : (
        <DefaultAvatar kind="user" />
      ),
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
      onStateChangeRef.current?.(event.to);
    });

    // Initialize SSEHandler - 不再需要，我们用 fetch 直接处理
    // Initialize AGUIHandler (默认启用)
    aguiHandlerRef.current = new AGUIHandler(agui || { enabled: true, debug: false });
    const aguiSubscription = setupAGUIEventHandlers();
    // Load previous session
    const session = sessionManagerRef.current.initSession();
    if (initialMessages && initialMessages.length > 0) {
      session.messages = initialMessages;
      setMessages(initialMessages);
    } else if (session && session.messages.length > 0) {
      setMessages(session.messages);
    }

    return () => {
      handleAGUIEvent.cancelPendingText();
      cancelPendingImageBatches();
      void streamLifecycle?.dispose();
      aguiSubscription?.unsubscribe();
      aguiHandlerRef.current?.destroy();
      unsubscribeState();
      stateMachineRef.current?.destroy();
    };
  }, [cancelPendingImageBatches]);

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

  const handleAGUIEvent = useMemo(
    () =>
      createAGUIEventHandler({
        currentMessageIdRef,
        streamingContentRef,
        sessionManagerRef,
        stateMachineRef,
        onMessageReceivedRef,
        setMessages,
        setIsLoading,
        setIsThinking,
        addMessage,
        streamingTextBatchingRef,
      }),
    [addMessage]
  );

  const sessionId =
    customData && typeof customData.session_id === 'string' ? customData.session_id : '';
  const appliedSessionRef = useRef<string | null>(null);
  useEffect(() => {
    if (!sessionId) {
      return;
    }
    if (appliedSessionRef.current === null) {
      appliedSessionRef.current = sessionId;
      return;
    }
    if (appliedSessionRef.current === sessionId) {
      if (initialMessages && initialMessages.length > 0) {
        setMessages((prev) => {
          if (
            prev.length === initialMessages.length &&
            prev.every((item, index) => item.id === initialMessages[index]?.id)
          ) {
            return prev;
          }
          return initialMessages;
        });
      }
      return;
    }
    appliedSessionRef.current = sessionId;
    handleAGUIEvent.cancelPendingText();
    cancelPendingImageBatches();
    streamingContentRef.current = '';
    currentMessageIdRef.current = null;
    setIsLoading(false);
    setIsThinking(false);
    setHitlEvent(null);
    sessionManagerRef.current?.clearSession();
    sessionManagerRef.current?.initSession();
    setMessages(initialMessages && initialMessages.length > 0 ? initialMessages : []);
  }, [cancelPendingImageBatches, handleAGUIEvent, initialMessages, sessionId]);

  // Handle legacy message format (fallback)
  const handleLegacyMessage = (data: unknown) => {
    const legacy = parseLegacyMessage(data);
    if (!legacy) return;

    const botMsg: Message = {
      id: legacy.id || generateId(),
      type: legacy.type,
      content: legacy.content,
      sender: 'bot',
      timestamp: Date.now(),
      metadata: legacy.metadata,
    };
    addMessage(botMsg);
  };

  const applyCustomEvent = (event: CustomProtocolEvent) => {
    onCustomEvent?.(event);
    if (isBlockingHitlEvent(event)) {
      setHitlEvent(event);
      return;
    }
    const degraded = formatDegradedCustomEvent(event);
    if (!degraded.trim()) {
      return;
    }
    addMessage({
      id: generateId(),
      type: 'text',
      content: degraded,
      sender: 'bot',
      timestamp: Date.now(),
    });
  };

  const updateUploadedImages = useCallback((action: PendingImageAction) => {
    const next = pendingImagesReducer(uploadedImagesRef.current, action);
    uploadedImagesRef.current = next;
    setUploadedImages(next);
  }, []);

  const reportImageError = useCallback((error: Error) => {
    setImageSelectionError(error.message);
    onError?.(error);
  }, [onError]);

  const reportImageBudgetViolation = useCallback((violation: ImageBudgetViolation) => {
    if (violation.reason === 'count') {
      reportImageError(new Error(`每条消息最多选择 ${violation.limit} 张图片，本批次未添加。`));
      return;
    }
    if (violation.reason === 'bytes') {
      const limitMB = violation.limit / (1024 * 1024);
      reportImageError(new Error(`每条消息的图片总大小不能超过 ${limitMB}MB，本批次未添加。`));
      return;
    }
    const limitMP = Math.round((violation.limit / 1_000_000) * 10) / 10;
    const scope = violation.reason === 'image-pixels' ? '单张图片' : '每条消息的图片总计';
    reportImageError(new Error(`${scope}不能超过 ${limitMP} 百万像素，本批次未添加。`));
  }, [reportImageError]);

  const queueImageFiles = useCallback((files: readonly File[]) => {
    if (files.length === 0) return;

    const pendingFiles = Array.from(pendingImageBatchesRef.current.values()).flatMap(({ files }) => files);
    const accountedImages = [...uploadedImagesRef.current, ...pendingFiles];
    const validation = validateImageBatch(accountedImages, files, imageBudget);
    if (validation.ok === false) {
      reportImageBudgetViolation(validation);
      return;
    }

    const batchToken = Symbol('pending-image-batch');
    const controller = new AbortController();
    pendingImageBatchesRef.current.set(batchToken, { controller, files });
    const generation = imageSelectionGenerationRef.current;
    imageBatchQueueRef.current = imageBatchQueueRef.current.then(async () => {
      try {
        if (generation !== imageSelectionGenerationRef.current) return;

        const inspectedFiles = await inspectImageBatch(
          files,
          imageBudget.imageReadConcurrency,
          controller.signal,
        );
        const pixelValidation = validateImagePixelBudget(
          uploadedImagesRef.current,
          inspectedFiles,
          imageBudget,
        );
        if (pixelValidation.ok === false) {
          reportImageBudgetViolation(pixelValidation);
          return;
        }

        const images = (await readImageBatch(
          inspectedFiles,
          imageBudget.imageReadConcurrency,
          readFileAsDataUrl,
          controller.signal,
        )).map((image) => ({
          ...image,
          previewable: image.previewable || imageBudget.allowUnknownImagePreview,
        }));
        if (generation !== imageSelectionGenerationRef.current) return;

        const latestValidation = validateImageBatch(uploadedImagesRef.current, files, imageBudget);
        if (latestValidation.ok === false) {
          reportImageBudgetViolation(latestValidation);
          return;
        }
        setImageSelectionError(null);
        updateUploadedImages({ images, type: 'append' });
      } catch (error) {
        if (generation !== imageSelectionGenerationRef.current) return;
        reportImageError(toError(error));
      } finally {
        pendingImageBatchesRef.current.delete(batchToken);
      }
    });
  }, [imageBudget, reportImageBudgetViolation, reportImageError, updateUploadedImages]);

  // Handle image upload
  const handleImageUpload = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    const imageFiles: File[] = [];

    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      if (!file.type.startsWith('image/')) continue;
      if (file.size > MAX_IMAGE_SIZE) {
        const limitMB = MAX_IMAGE_SIZE / (1024 * 1024);
        reportImageError(new Error(`图片"${file.name}"超过 ${limitMB}MB 大小限制，已跳过。`));
        continue;
      }

      imageFiles.push(file);
    }
    queueImageFiles(imageFiles);

    // Reset input
    e.target.value = '';
  }, [queueImageFiles, reportImageError]);

  // Remove uploaded image
  const handleRemoveImage = useCallback((index: number) => {
    updateUploadedImages({ index, type: 'remove' });
  }, [updateUploadedImages]);

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
            reportImageError(new Error(`粘贴的图片超过 ${limitMB}MB 大小限制，已跳过。`));
            continue;
          }
          imageFiles.push(file);
        }
      }
    }

    if (imageFiles.length > 0) {
      e.preventDefault(); // 阻止默认粘贴行为
      queueImageFiles(imageFiles);
    }
  }, [queueImageFiles, reportImageError]);

  // Send message
  const handleSendMessage = useCallback(async (value: string) => {
    if ((!value.trim() && uploadedImages.length === 0) || isLoading) return;

    // Build message content
    let messageContent: string | MessageContent[];
    let messageType: MessageType = 'text';

    if (uploadedImages.length > 0) {
      // Multimodal message with images and text
      messageContent = [
        ...uploadedImages.map(({ dataUrl }) => ({ type: 'image_url' as const, image_url: dataUrl })),
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
      ...(uploadedImages.some(({ previewable }) => !previewable)
        ? {
            metadata: {
              unpreviewedImageIndexes: uploadedImages.flatMap(({ previewable }, index) =>
                previewable ? [] : [index],
              ),
            },
          }
        : {}),
    };

    addMessage(userMsg);
    setInputValue('');
    setHitlEvent(null);
    cancelPendingImageBatches();
    setImageSelectionError(null);
    updateUploadedImages({ type: 'clear' });
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
          ...(requestHeaders || {}),
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
              credentials: credentials ?? 'same-origin',
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
                } else if (result.type === 'custom-event') {
                  applyCustomEvent(result.event);
                }
              } else {
                handleLegacyMessage(data);
              }
            }
          },
          onError: (error) => {
            handleAGUIEvent.flushPendingText();
            console.error('Error reading stream:', error);
            onError?.(error);
          },
          onComplete: () => {
            handleAGUIEvent.flushPendingText();
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
      handleAGUIEvent.flushPendingText();
      if (isAbortError(error)) {
        return;
      }
      console.error('Error sending message:', error);
      onError?.(toError(error));
      setIsLoading(false);
    }
  }, [
    isLoading,
    sseUrl,
    customData,
    addMessage,
    onError,
    uploadedImages,
    handleAGUIEvent,
    updateUploadedImages,
    cancelPendingImageBatches,
    apiKey,
    credentials,
    requestHeaders,
  ]);

  const handleStopStreaming = useCallback(() => {
    handleAGUIEvent.flushPendingText();
    void streamLifecycleRef.current?.cancel('user-stopped');
    setIsLoading(false);
    setIsThinking(false);
    onStreamingStop?.();
  }, [handleAGUIEvent, onStreamingStop]);

  // Clear messages
  const handleClear = useCallback(() => {
    handleAGUIEvent.cancelPendingText();
    void streamLifecycleRef.current?.cancel('session-cleared');
    setMessages([]);
    cancelPendingImageBatches();
    setImageSelectionError(null);
    updateUploadedImages({ type: 'clear' });
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
  }, [cancelPendingImageBatches, handleAGUIEvent, updateUploadedImages]);

  // Use message handlers hook
  const { handleRegenerate, handleCopy, handleDelete } = useMessageHandlers({
    messages,
    setMessages,
    sessionManagerRef,
    handleSendMessage,
  });

  const consumedKickoffRef = useRef<string | undefined>(undefined);
  useEffect(() => {
    if (!kickoffMessage?.trim() || consumedKickoffRef.current === kickoffMessage) {
      return;
    }
    consumedKickoffRef.current = kickoffMessage;
    void handleSendMessage(kickoffMessage);
    onKickoffConsumed?.();
  }, [handleSendMessage, kickoffMessage, onKickoffConsumed]);

  // Toggle fullscreen
  const panelFullscreen = fullscreen ?? isFullscreen;
  const toggleFullscreen = useCallback(() => {
    const next = !panelFullscreen;
    setIsFullscreen(next);
    onFullscreenChange?.(next);
  }, [onFullscreenChange, panelFullscreen]);

  // Scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  return (
    <div 
      className={`flex min-h-0 flex-1 flex-col overflow-hidden ${
        showHeader ? 'rounded-lg shadow-lg' : ''
      } ${
        panelFullscreen && !onFullscreenChange
          ? 'fixed inset-0 z-50 h-full'
          : 'h-full'
      }`}
      style={{ background: WC.white }}
      ref={ref}
    >
      {showHeader && (
      <div
        className="flex flex-shrink-0 items-center justify-between px-5 py-4"
        style={{ background: WC.indigo, color: WC.onPrimary }}
      >
        <div>
          <div className="text-sm font-semibold tracking-wide">{title}</div>
          <div className="mt-0.5 text-xs opacity-80">{subtitle || '随时为你提供帮助'}</div>
        </div>
        <div className="flex items-center gap-1">
          {showFullscreenButton && (
            <button
              onClick={toggleFullscreen}
              className="flex h-10 w-10 items-center justify-center rounded-full hover:bg-[var(--color-bg-6,rgba(255,255,255,0.16))]"
              style={{ color: WC.onPrimary }}
              title={panelFullscreen ? '退出全屏' : '全屏'}
            >
              {panelFullscreen ? (
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
            className="flex h-10 w-10 items-center justify-center rounded-full hover:bg-[var(--color-bg-6,rgba(255,255,255,0.16))]"
            style={{ color: WC.onPrimary }}
            title="关闭对话"
          >
            ✕
          </button>
        </div>
      </div>
      )}

      {/* Messages Area */}
      <div
        className={`flex min-h-0 flex-1 flex-col overflow-y-auto ${wideLayout || panelFullscreen ? 'px-5 py-4' : 'p-4'}`}
        style={{ background: WC.white }}
      >
        <div className="flex min-h-0 w-full flex-1 flex-col space-y-3">
        {historyLoading ? (
          <ConversationSkeleton />
        ) : messages.length === 0 ? (
          <div className="flex h-full items-center justify-center">
            <p className="text-sm" style={{ color: WC.muted }}>
              发一条消息开始对话
            </p>
          </div>
        ) : (() => {
          let lastBotMessageIndex = -1;
          for (let index = messages.length - 1; index >= 0; index -= 1) {
            if (messages[index].sender === 'bot') {
              lastBotMessageIndex = index;
              break;
            }
          }
          return (
            <React.Suspense fallback={null}>
              {messages.map((msg, index) => {
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
                fillWidth={wideLayout || panelFullscreen}
                onRegenerate={handleRegenerate}
                onCopy={handleCopy}
                onDelete={handleDelete}
              />
            );
              })}
            </React.Suspense>
          );
        })()}
        
        {/* Show loading/thinking state */}
        {(isLoading || isThinking) && (
          <div className="flex w-full items-start gap-2">
            <div className="h-8 w-8 flex-shrink-0 overflow-hidden rounded-full">{botAvatar}</div>
            <div
              className={`px-3.5 py-2.5 text-sm ${wideLayout || panelFullscreen ? 'min-w-0 flex-1' : 'max-w-[78%]'}`}
              style={{
                background: WC.botBubble,
                color: WC.muted,
                borderRadius: 18,
                borderBottomLeftRadius: 6,
              }}
            >
              {isThinking ? '思考中…' : '正在输入…'}
            </div>
          </div>
        )}

        <HitlPanels
          event={hitlEvent}
          approvalUrl={platform?.approvalUrl}
          choiceUrl={platform?.choiceUrl}
          apiKey={apiKey}
          credentials={credentials}
          headers={requestHeaders}
          onResolved={() => setHitlEvent(null)}
        />
        
        <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Input Area */}
      <div
        className={`relative flex-shrink-0 ${wideLayout || panelFullscreen ? 'px-5 py-3' : 'p-2.5'}`}
        style={{ background: WC.white }}
      >
        {showClearButton && (
          <button
            onClick={() => setShowClearConfirm(true)}
            className="absolute right-4 z-10 rounded p-1.5"
            style={{ color: WC.muted, top: '-2rem' }}
            title="清除对话"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M3 6h18M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2M10 11v6M14 11v6"/>
            </svg>
          </button>
        )}
        
        {/* Image preview area */}
        {imageSelectionError && (
          <p role="alert" className="px-4 pt-2 text-xs" style={{ color: 'var(--color-fail)' }}>
            {imageSelectionError}
          </p>
        )}
        {uploadedImages.length > 0 && (
          <div className="px-4 pt-2 pb-1 flex flex-wrap gap-2">
            {uploadedImages.map((img, index) => (
              <div key={index} className="relative group">
                {img.previewable ? (
                  <img
                    src={img.dataUrl}
                    alt={`Upload ${index + 1}`}
                    className="h-16 w-16 rounded-md border border-[var(--color-border-1,#e8eaf0)] object-cover"
                  />
                ) : (
                  <div role="status" aria-label={`${img.name} 已添加（安全占位，不在浏览器预览）`}>
                    <p className="max-w-[10rem] rounded-md px-2 py-1 text-xs text-[var(--color-text-3,#86909c)]">
                      {img.name} 已添加（安全占位，不在浏览器预览）
                    </p>
                  </div>
                )}
                <button
                  onClick={() => handleRemoveImage(index)}
                  className="absolute -top-1 -right-1 flex h-4 w-4 items-center justify-center rounded-full text-xs opacity-0 transition-opacity group-hover:opacity-100"
                  style={{ background: WC.fail, color: WC.onPrimary }}
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        )}
        
              <PillComposer
                value={inputValue}
                onChange={setInputValue}
                onSubmit={(text) => {
                  void handleSendMessage(text);
                }}
                onCancel={handleStopStreaming}
                placeholder={placeholder}
                loading={isLoading}
                onPaste={handlePaste}
                imageSlot={
                  <label className="cursor-pointer" style={{ color: WC.muted }}>
                    <input
                      type="file"
                      accept="image/*"
                      multiple
                      onChange={handleImageUpload}
                      className="hidden"
                    />
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
                      <circle cx="8.5" cy="8.5" r="1.5"/>
                      <polyline points="21 15 16 10 5 21"/>
                    </svg>
                  </label>
                }
              />
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

ChatInner.displayName = 'Chat';

export const Chat = React.memo(ChatInner);
Chat.displayName = 'Chat';

export default Chat;
