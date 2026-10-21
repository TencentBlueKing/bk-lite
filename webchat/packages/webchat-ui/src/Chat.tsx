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
  isSilentCustomEvent,
  normalizeWebChatConfig,
  parseLlmContextUsage,
  type LlmContextUsage,
} from '@webchat/core';
import { AGUIHandler, AGUIEvent, type CustomProtocolEvent } from './agui';
import type { WebchatChoiceValue } from './choiceDisplay';
import type { ChatProps } from './chatProps';
import { createAGUIEventHandler, shouldShowAnalyzingIndicator, shouldShowTypingPlaceholder } from './aguiEventHandler';
import { parseLegacyMessage } from './legacyMessage';
import { useMessageHandlers } from './hooks/useMessageHandlers';
import { ConfirmDialog } from './components/ConfirmDialog';
import { formatDegradedCustomEvent, HitlPanels, isBlockingHitlEvent } from './components/HitlPanels';
import { ConversationSkeleton } from './components/ConversationSkeleton';
import { PillComposer } from './components/PillComposer';
import ContextUsageRing from './components/ContextUsageRing';
import { collectSessionAttachmentFiles } from './sessionFiles';
import { applyPlannedExecutionStep, createPlannedExecutionState } from './plannedExecution';
import { attachmentMetadata, chatAttachmentEndpoints, fetchChatAttachmentStatus, isAllowedChatFile, uploadChatFile, type StoredChatAttachment } from './chatAttachments';
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
import { useTranslator, WebChatLocaleProvider } from './useTranslator';

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

/** 已有 Api-Authorization 或 Authorization 时不改写。仅有 apiKey 时按平台约定补 Bearer。 */
function chatAuthHeaders(
  requestHeaders: Record<string, string> | undefined,
  apiKey?: string,
): Record<string, string> {
  const headers: Record<string, string> = { ...(requestHeaders || {}) };
  if (apiKey && !headers['Api-Authorization'] && !headers.Authorization) {
    headers.Authorization = `Bearer ${apiKey}`;
  }
  return headers;
}

const ChatInner = React.forwardRef<HTMLDivElement, ChatProps>((props, ref) => {
  const t = useTranslator();
  const {
    sseUrl,
    customData,
    // theme = 'light',
    title = 'Chat',
    subtitle,
    placeholder,
    enableStorage = true,
    storageKey = 'webchat_session',
    storageScope,
    onStateChange,
    onMessageReceived,
    onError,
    onClose,
    agui,
    showFullscreenButton = true,
    showClearButton = false,
    conversationHistoryEnabled = true,
    initialContextUsage = null,
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
    onToolResult,
    onSessionFilesChange,
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
    collectContext,
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
  const [documentChips, setDocumentChips] = useState<Array<StoredChatAttachment & { localKey: string }>>([]);
  const pendingAttachmentIdsRef = useRef<Set<number>>(new Set());
  const attachmentPollMetaRef = useRef<Map<number, { failures: number }>>(new Map());
  const selectedFilesRef = useRef<File[]>([]);
  const [hitlEvent, setHitlEvent] = useState<CustomProtocolEvent | null>(null);
  const [contextUsage, setContextUsage] = useState<LlmContextUsage | null>(null);

  // Refs
  const sessionManagerRef = useRef<SessionManager | null>(null);
  const stateMachineRef = useRef<StateMachine | null>(null);
  const aguiHandlerRef = useRef<AGUIHandler | null>(null);
  const messagesScrollerRef = useRef<HTMLDivElement>(null);
  const streamingContentRef = useRef<string>('');
  const currentMessageIdRef = useRef<string | null>(null);
  const choiceMessageIdRef = useRef<string | null>(null);
  const plannedStateRef = useRef(createPlannedExecutionState());
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

  // Initialize core components
  useEffect(() => {
    const streamLifecycle = streamLifecycleRef.current;
    streamLifecycle?.mount();
    handleAGUIEvent.cancelPendingText();
    streamingContentRef.current = '';
    currentMessageIdRef.current = null;
    setIsLoading(false);
    setIsThinking(false);
    setHitlEvent(null);
    setContextUsage(null);

    // Initialize SessionManager
    sessionManagerRef.current = new SessionManager({
      enableStorage,
      storageKey,
      storageScope,
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
    const restoredMessages = initialMessages && initialMessages.length > 0
      ? [...initialMessages]
      : [...session.messages];
    session.messages = [...restoredMessages];
    setMessages(restoredMessages);

    return () => {
      handleAGUIEvent.cancelPendingText();
      cancelPendingImageBatches();
      void streamLifecycle?.dispose();
      aguiSubscription?.unsubscribe();
      aguiHandlerRef.current?.destroy();
      unsubscribeState();
      stateMachineRef.current?.destroy();
    };
  }, [cancelPendingImageBatches, enableStorage, storageKey, storageScope]);

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

  const onToolResultRef = useRef(onToolResult);
  onToolResultRef.current = onToolResult;
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
        onToolResultRef,
        streamingTextBatchingRef,
        plannedStateRef,
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
      if (initialMessages && initialMessages.length > 0) {
        setMessages(initialMessages);
      }
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
    setContextUsage(null);
    sessionManagerRef.current?.clearSession();
    sessionManagerRef.current?.initSession();
    setMessages(initialMessages && initialMessages.length > 0 ? initialMessages : []);
  }, [cancelPendingImageBatches, handleAGUIEvent, initialMessages, sessionId]);

  const appliedUsageSessionRef = useRef<string | null>(null);
  useEffect(() => {
    if (!conversationHistoryEnabled) {
      appliedUsageSessionRef.current = sessionId || null;
      setContextUsage(null);
      return;
    }
    if (!sessionId) {
      return;
    }
    if (appliedUsageSessionRef.current !== sessionId) {
      appliedUsageSessionRef.current = sessionId;
      setContextUsage(initialContextUsage ?? null);
      return;
    }
    if (initialContextUsage) {
      setContextUsage(initialContextUsage);
    }
  }, [conversationHistoryEnabled, initialContextUsage, sessionId]);

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
    if (event.name === 'planned_execution_step' && event.value && typeof event.value === 'object') {
      plannedStateRef.current = applyPlannedExecutionStep(
        plannedStateRef.current,
        event.value as Record<string, unknown>,
      );
      const steps = plannedStateRef.current.steps;
      const messageId = currentMessageIdRef.current;
      setMessages((prev) => prev.map((message) => (
        message.id === messageId
          ? { ...message, metadata: { ...message.metadata, plannedSteps: steps } }
          : message
      )));
    }
    if (event.name === 'assistant_text_retract') {
      handleAGUIEvent.retractLiveText();
      return;
    }
    if (event.name === 'llm_context_usage') {
      const usage = parseLlmContextUsage(event.value);
      if (usage) {
        setContextUsage(usage);
      }
      return;
    }
    if (isBlockingHitlEvent(event)) {
      if (event.name === 'user_choice_request' && event.value && typeof event.value === 'object') {
        const messageId = currentMessageIdRef.current;
        choiceMessageIdRef.current = messageId;
        setMessages((prev) => prev.map((message) => (
          message.id === messageId
            ? { ...message, metadata: { ...message.metadata, userChoice: event.value } }
            : message
        )));
      }
      setHitlEvent(event);
      return;
    }
    // 进度/元数据类事件（规划步骤、步骤进度、引用等）不降级成聊天气泡
    if (isSilentCustomEvent(event.name)) {
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
      reportImageError(
        new Error(t('image.limitPerMessage', '每条消息最多选择 {count} 张图片，本批次未添加。', { count: violation.limit }))
      );
      return;
    }
    if (violation.reason === 'bytes') {
      const limitMB = violation.limit / (1024 * 1024);
      reportImageError(
        new Error(t('image.totalSizeLimit', '每条消息的图片总大小不能超过 {count}MB，本批次未添加。', { count: limitMB }))
      );
      return;
    }
    const limitMP = Math.round((violation.limit / 1_000_000) * 10) / 10;
    const scope =
      violation.reason === 'image-pixels'
        ? t('image.pixelsScopeSingle', '单张图片')
        : t('image.pixelsScopeTotal', '每条消息的图片总计');
    reportImageError(
      new Error(t('image.pixelsLimit', '{scope}不能超过 {count} 百万像素，本批次未添加。', { scope, count: limitMP }))
    );
  }, [reportImageError, t]);

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
        selectedFilesRef.current.push(...files);
        updateUploadedImages({ images, type: 'append' });
      } catch (error) {
        if (generation !== imageSelectionGenerationRef.current) return;
        reportImageError(toError(error));
      } finally {
        pendingImageBatchesRef.current.delete(batchToken);
      }
    });
  }, [imageBudget, reportImageBudgetViolation, reportImageError, updateUploadedImages]);

  const uploadDocumentFiles = useCallback(async (files: readonly File[]) => {
    if (!sseUrl) {
      reportImageError(new Error(t('file.uploadUnavailable', '当前对话不能上传文件')));
      return;
    }
    const headers = chatAuthHeaders(requestHeaders, apiKey);
    for (const file of files) {
      const localKey = `${file.name}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      setDocumentChips((current) => [...current, {
        localKey,
        id: 0,
        name: file.name,
        mime: file.type || 'application/octet-stream',
        size: file.size,
        status: 'pending',
      }].slice(0, 5));
      try {
        const uploaded = await uploadChatFile(file, sseUrl, headers);
        setDocumentChips((current) => current.map((item) => (
          item.localKey === localKey ? { ...uploaded, localKey } : item
        )));
      } catch (error) {
        setDocumentChips((current) => current.map((item) => (
          item.localKey === localKey ? { ...item, status: 'failed' } : item
        )));
        reportImageError(toError(error));
      }
    }
  }, [apiKey, reportImageError, requestHeaders, sseUrl, t]);

  useEffect(() => {
    const pendingIds = new Set<number>();
    documentChips.forEach((item) => {
      if (item.status === 'pending' && item.id) {
        pendingIds.add(item.id);
      }
    });
    pendingAttachmentIdsRef.current = pendingIds;
  }, [documentChips]);

  useEffect(() => {
    if (!sseUrl) {
      return undefined;
    }
    const headers = chatAuthHeaders(requestHeaders, apiKey);
    const pollIntervalMs = 1500;
    const maxConsecutiveFailures = 12;
    const markAttachmentFailed = (attachmentId: number, reason: string) => {
      pendingAttachmentIdsRef.current.delete(attachmentId);
      attachmentPollMetaRef.current.delete(attachmentId);
      setDocumentChips((current) => current.map((chip) => (
        chip.id === attachmentId
          ? { ...chip, status: 'failed', failure_reason: reason }
          : chip
      )));
    };
    const timer = globalThis.setInterval(() => {
      const pendingIds = [...pendingAttachmentIdsRef.current];
      if (!pendingIds.length) {
        return;
      }
      pendingIds.forEach((attachmentId) => {
        const meta = attachmentPollMetaRef.current.get(attachmentId) ?? { failures: 0 };
        if (!attachmentPollMetaRef.current.has(attachmentId)) {
          attachmentPollMetaRef.current.set(attachmentId, meta);
        }
        fetchChatAttachmentStatus(attachmentId, sseUrl, headers)
          .then((next) => {
            meta.failures = 0;
            if (next.status === 'failed') {
              markAttachmentFailed(attachmentId, next.failure_reason || t('file.failed', '解析失败'));
              return;
            }
            if (next.status !== 'pending') {
              pendingAttachmentIdsRef.current.delete(attachmentId);
              attachmentPollMetaRef.current.delete(attachmentId);
            }
            setDocumentChips((current) => current.map((chip) => (
              chip.id === attachmentId
                ? { ...chip, status: next.status, failure_reason: next.failure_reason }
                : chip
            )));
          })
          .catch(() => {
            meta.failures += 1;
            if (meta.failures >= maxConsecutiveFailures) {
              markAttachmentFailed(attachmentId, t('file.statusUnavailable', '无法获取解析状态，请稍后重试'));
            }
          });
      });
    }, pollIntervalMs);
    return () => globalThis.clearInterval(timer);
  }, [apiKey, requestHeaders, sseUrl, t]);

  // Handle image upload
  const handleImageUpload = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    const imageFiles: File[] = [];
    const documentFiles: File[] = [];

    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      if (!file.type.startsWith('image/')) {
        if (isAllowedChatFile(file)) {
          documentFiles.push(file);
        }
        continue;
      }
      if (file.size > MAX_IMAGE_SIZE) {
        const limitMB = MAX_IMAGE_SIZE / (1024 * 1024);
        reportImageError(
          new Error(t('image.fileTooLarge', '图片"{name}"超过 {count}MB 大小限制，已跳过。', { name: file.name, count: limitMB }))
        );
        continue;
      }

      imageFiles.push(file);
    }
    if (documentFiles.length > 0) {
      void uploadDocumentFiles(documentFiles);
    }
    queueImageFiles(imageFiles);

    // Reset input
    e.target.value = '';
  }, [queueImageFiles, reportImageError, t, uploadDocumentFiles]);

  // Remove uploaded image
  const handleRemoveImage = useCallback((index: number) => {
    selectedFilesRef.current.splice(index, 1);
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
            reportImageError(
              new Error(t('image.pastedTooLarge', '粘贴的图片超过 {count}MB 大小限制，已跳过。', { count: limitMB }))
            );
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
  }, [queueImageFiles, reportImageError, t]);

  // Send message
  const handleSendMessage = useCallback(async (value: string) => {
    if ((!value.trim() && uploadedImages.length === 0 && documentChips.length === 0) || isLoading) return;
    if (documentChips.some((item) => item.status !== 'ready')) return;
    plannedStateRef.current = createPlannedExecutionState();

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
    if (hitlEvent?.name === 'user_choice_request' && hitlEvent.value && typeof hitlEvent.value === 'object') {
      const choice = hitlEvent.value as WebchatChoiceValue;
      const answer = value.trim();
      const matched = choice.options?.find((option) => option.label === answer || option.key === answer);
      const messageId = choiceMessageIdRef.current;
      setMessages((prev) => prev.map((message) => (
        message.id === messageId
          ? {
              ...message,
              metadata: {
                ...message.metadata,
                userChoice: { ...choice, answered: true, selected: matched?.key },
              },
            }
          : message
      )));
    }
    setInputValue('');
    setHitlEvent(null);
    cancelPendingImageBatches();
    const draftFiles = selectedFilesRef.current.slice();
    selectedFilesRef.current = [];
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
        let pageContext: unknown = null;
        if (collectContext) {
          try {
            pageContext = await collectContext({ message: value.trim() });
          } catch (error) {
            console.warn('page context collect failed', error);
          }
        }

        const uploadHeaders = chatAuthHeaders(requestHeaders, apiKey);
        const uploadedAttachments: StoredChatAttachment[] = [];
        for (const file of draftFiles) {
          uploadedAttachments.push(await uploadChatFile(file, sseUrl, uploadHeaders));
        }
        if (uploadedAttachments.some((item) => item.status !== 'ready') || documentChips.some((item) => item.status !== 'ready')) {
          reportImageError(new Error(t('file.notReady', '文件解析中，请稍后再发送')));
          setIsLoading(false);
          return;
        }
        const readyAttachments = [...documentChips, ...uploadedAttachments].filter((item) => item.status === 'ready');
        const requestBody = {
          message: value.trim(),
          attachment_ids: readyAttachments.map((item) => item.id),
          sessionId: currentSession?.sessionId,
          ...customData,
          ...(pageContext ? { page_context: pageContext } : {}),
        };
        setDocumentChips([]);
        const stored = sessionManagerRef.current?.getSession()?.messages.find((item) => item.id === userMsg.id);
        if (stored) {
          stored.content = value.trim();
          stored.metadata = {
            ...(stored.metadata || {}),
            attachments: attachmentMetadata(readyAttachments),
          };
          sessionManagerRef.current?.saveSession();
        }

        const headers: Record<string, string> = {
          'Content-Type': 'application/json',
          ...chatAuthHeaders(requestHeaders, apiKey),
        };
        
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
            stateMachineRef.current?.transition('connected');
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
    collectContext,
    documentChips,
    reportImageError,
    t,
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
    selectedFilesRef.current = [];
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
    setContextUsage(null);
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
  const sessionFiles = useMemo(() => collectSessionAttachmentFiles(messages), [messages]);
  useEffect(() => {
    onSessionFilesChange?.(sessionFiles);
  }, [onSessionFilesChange, sessionFiles]);
  const toggleFullscreen = useCallback(() => {
    const next = !panelFullscreen;
    setIsFullscreen(next);
    onFullscreenChange?.(next);
  }, [onFullscreenChange, panelFullscreen]);

  // 只滚动消息区。scrollIntoView 会连外层 overflow 一起滚，侧栏撑开后输入框会被顶到对话区顶部。
  useEffect(() => {
    const scroller = messagesScrollerRef.current;
    if (!scroller) return;
    scroller.scrollTop = scroller.scrollHeight;
  }, [messages]);

  return (
    <div 
      className={`flex min-h-0 flex-1 flex-col overflow-hidden ${
        showHeader ? 'rounded-lg' : ''
      } ${
        panelFullscreen && !onFullscreenChange
          ? 'fixed inset-0 z-50 h-full'
          : 'h-full'
      }`}
      style={{ background: WC.stage }}
      ref={ref}
    >
      {showHeader && (
      <div className="flex-shrink-0">
        <div
          className="flex items-center justify-between px-4 py-3"
          style={{
            background: WC.headerBg,
            color: WC.headerInk,
            borderBottom: `1px solid ${WC.botBorder}`,
          }}
        >
        <div>
          <div className="text-[13px] font-medium tracking-wide">{title}</div>
          <div className="mt-0.5 text-xs" style={{ color: WC.muted }}>{subtitle || t('chat.floatingSubtitle', '随时为你提供帮助')}</div>
        </div>
        <div className="flex items-center gap-1">
          {showFullscreenButton && (
            <button
              onClick={toggleFullscreen}
              className="flex h-8 w-8 items-center justify-center rounded-md hover:bg-[var(--color-fill-2,#f4f5f8)]"
              style={{ color: WC.muted }}
              title={panelFullscreen ? t('chat.exitFullscreen', '退出全屏') : t('chat.fullscreen', '全屏')}
            >
              {panelFullscreen ? (
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M8 3v3a2 2 0 0 1-2 2H3m18 0h-3a2 2 0 0 1-2-2V3m0 18v-3a2 2 0 0 1 2-2h3M3 16h3a2 2 0 0 1 2 2v3"/>
                </svg>
              ) : (
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/>
                </svg>
              )}
            </button>
          )}
          <button
            onClick={onClose}
            className="flex h-8 w-8 items-center justify-center rounded-md hover:bg-[var(--color-fill-2,#f4f5f8)]"
            style={{ color: WC.muted }}
            title={t('chat.closeConversation', '关闭对话')}
          >
            ✕
          </button>
        </div>
        </div>
      </div>
      )}

      <div className="flex min-h-0 flex-1">
        <div className="relative flex min-h-0 min-w-0 flex-1 flex-col">
      {/* Messages Area */}
      <div
        ref={messagesScrollerRef}
        className={`flex min-h-0 flex-1 basis-0 flex-col overflow-y-auto ${wideLayout || panelFullscreen ? 'px-6 pb-2 pt-5' : 'px-4 pb-1.5 pt-4'}`}
        style={{ background: WC.stage }}
      >
        <div className="flex min-h-0 w-full flex-1 flex-col space-y-5">
        {historyLoading ? (
          <ConversationSkeleton />
        ) : messages.length === 0 ? (
          <div className="flex h-full items-center justify-center">
            <p className="text-sm" style={{ color: WC.muted }}>
              {t('chat.emptyStart', '发一条消息开始对话')}
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
                isLastBotMessage={isPartOfLastQA}
                fillWidth={wideLayout || panelFullscreen}
                onRegenerate={handleRegenerate}
                onCopy={handleCopy}
                onDelete={handleDelete}
                loadAttachment={sseUrl ? async (id) => {
                  const endpoints = chatAttachmentEndpoints(sseUrl);
                  if (!endpoints) throw new Error('缺少附件下载地址');
                  const headers = chatAuthHeaders(requestHeaders, apiKey);
                  const response = await fetch(endpoints.download(id), { headers, credentials: 'include' });
                  if (!response.ok) throw new Error('下载失败');
                  return response.blob();
                } : undefined}
              />
            );
              })}
            </React.Suspense>
          );
        })()}
        
        {/* Show loading/thinking state */}
        {shouldShowTypingPlaceholder(isLoading, isThinking, messages) && (
          <div className="flex w-full items-center gap-1.5" role="status" aria-live="polite">
            <span
              className={`text-xs font-medium ${isThinking ? 'webchat-thinking-shimmer' : ''}`}
              style={isThinking ? undefined : { color: WC.muted }}
            >
              {isThinking ? t('chat.thinking', '思考中') : t('chat.replying', '正在回复')}
            </span>
            <span className="webchat-thinking-dots" aria-hidden>
              <span />
              <span />
              <span />
            </span>
          </div>
        )}

        {/* Tools done, model still analyzing: otherwise the turn looks frozen */}
        {shouldShowAnalyzingIndicator(isLoading, isThinking, messages) && (
          <div className="flex w-full items-center gap-1.5" role="status" aria-live="polite">
            <span className="text-xs font-medium webchat-thinking-shimmer">{t('chat.analyzingToolResult', '正在分析工具结果')}</span>
            <span className="webchat-thinking-dots" aria-hidden>
              <span />
              <span />
              <span />
            </span>
          </div>
        )}

        <HitlPanels
          event={hitlEvent}
          approvalUrl={platform?.approvalUrl}
          choiceUrl={platform?.choiceUrl}
          apiKey={apiKey}
          credentials={credentials}
          headers={requestHeaders}
          onSendMessage={handleSendMessage}
          onResolved={() => setHitlEvent(null)}
        />
        </div>
      </div>

      {/* Input Area */}
      <div
        className={`relative flex-shrink-0 ${wideLayout || panelFullscreen ? 'px-5 pb-3.5 pt-1.5' : 'px-3 pb-3 pt-1'}`}
        style={{ background: WC.composerWash }}
      >
        {/* Image preview area */}
        {imageSelectionError && (
          <p role="alert" className="px-4 pt-2 text-xs" style={{ color: 'var(--color-fail)' }}>
            {imageSelectionError}
          </p>
        )}
        {documentChips.length > 0 && (
          <div className="flex flex-wrap gap-2 px-4 pb-1 pt-2">
            {documentChips.map((chip) => (
              <div key={chip.localKey} className="flex items-center gap-1 rounded-md border px-2 py-1 text-xs" style={{ borderColor: 'var(--color-border-1,#e8eaf0)' }}>
                <span>
                  {chip.name}
                  {chip.status === 'pending' ? ` · ${t('file.parsing', '解析中')}` : ''}
                  {chip.status === 'failed' ? ` · ${chip.failure_reason || t('file.failed', '失败')}` : ''}
                </span>
                <button
                  type="button"
                  aria-label={t('file.remove', '移除文件')}
                  onClick={() => setDocumentChips((current) => current.filter((item) => item.localKey !== chip.localKey))}
                >
                  ×
                </button>
              </div>
            ))}
          </div>
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
                  <div role="status" aria-label={t('image.addedPlaceholder', '{name} 已添加（安全占位，不在浏览器预览）', { name: img.name })}>
                    <p className="max-w-[10rem] rounded-md px-2 py-1 text-xs text-[var(--color-text-3,#86909c)]">
                      {t('image.addedPlaceholder', '{name} 已添加（安全占位，不在浏览器预览）', { name: img.name })}
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
        
              {conversationHistoryEnabled ? (
                <div className="mb-1 flex h-8 items-center justify-end">
                  <ContextUsageRing usage={contextUsage} />
                </div>
              ) : null}
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
                leftExtra={
                  showClearButton ? (
                    <button
                      type="button"
                      onClick={() => setShowClearConfirm(true)}
                      className="flex h-7 w-7 items-center justify-center rounded"
                      style={{ color: WC.muted }}
                      title={t('chat.clearConversation', '清除对话')}
                    >
                      <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M3 6h18M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2M10 11v6M14 11v6"/>
                      </svg>
                    </button>
                  ) : undefined
                }
                imageSlot={
                  <label
                    title={t('file.upload', '上传文件')}
                    aria-label={t('file.upload', '上传文件')}
                    style={{
                      display: 'flex',
                      width: 28,
                      height: 28,
                      alignItems: 'center',
                      justifyContent: 'center',
                      margin: 0,
                      cursor: 'pointer',
                      color: WC.muted,
                      lineHeight: 0,
                    }}
                  >
                    <input
                      type="file"
                      accept=".pdf,.docx,.pptx,.xlsx,.csv,.txt,.md,.jpg,.jpeg,.png,.gif,.webp"
                      multiple
                      onChange={handleImageUpload}
                      style={{ display: 'none' }}
                    />
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      width="16"
                      height="16"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      style={{ display: 'block' }}
                      aria-hidden="true"
                    >
                      <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
                    </svg>
                  </label>
                }
              />
      </div>
        </div>
      </div>

      {/* Clear Confirmation Dialog */}
      <ConfirmDialog
        isOpen={showClearConfirm}
        title={t('sessions.clearConfirmTitle', '你即将清除当前对话，清除后将无法恢复，是否继续清除?')}
        message={t('sessions.clearConfirmBody', '删除后，聊天记录不可恢复，对话内的文件也将被彻底删除。')}
        confirmText={t('sessions.clearConfirmAction', '清除对话')}
        cancelText={t('common.cancel', '取消')}
        onConfirm={handleClear}
        onCancel={() => setShowClearConfirm(false)}
      />
    </div>
  );
});

ChatInner.displayName = 'Chat';

const ChatWithLocale = React.forwardRef<HTMLDivElement, ChatProps>((props, ref) => (
  <WebChatLocaleProvider locale={props.locale}>
    <ChatInner {...props} ref={ref} />
  </WebChatLocaleProvider>
));
ChatWithLocale.displayName = 'Chat';

export const Chat = React.memo(ChatWithLocale);
Chat.displayName = 'Chat';

export default Chat;
