import React, {ReactNode, useCallback, useEffect, useMemo, useRef, useState} from 'react';
import {Button, ButtonProps, Flex, Image, Input, message as antMessage, Popconfirm, Tooltip, Upload} from 'antd';
import {DeleteOutlined, DownloadOutlined, FullscreenExitOutlined, FullscreenOutlined, LoadingOutlined, PaperClipOutlined, RightOutlined, SendOutlined} from '@ant-design/icons';
import DOMPurify from 'dompurify';
import Icon from '@/components/icon';
import {useTranslation} from '@/utils/i18n';
import MarkdownIt from 'markdown-it';
import hljs from 'highlight.js';
import 'highlight.js/styles/atom-one-dark.css';
import styles from '../custom-chat/index.module.scss';
import MessageActions from '../custom-chat/actions';
import PermissionWrapper from '@/components/permission';
import BrowserStepProgress from './BrowserStepProgress';
import AgentStepProgress from './AgentStepProgress';
import PlannedExecutionSteps from './PlannedExecutionSteps';
import PlannedExecutionStatus, { isActivePlannedExecutionStatus } from './PlannedExecutionStatus';
import WikiCitations from './WikiCitations';
import ApprovalCard from './ApprovalCard';
import UserChoiceCard from './UserChoiceCard';
import { applyAnsweredUserChoices, stripChoicePromptFromContent } from './userChoiceOptions';
import DiffReportCard from './DiffReportCard';
import ConfigAnalysisReportCard from './ConfigAnalysisReportCard';
import ReportDownloadCard from './ReportDownloadCard';
import RepairCommandsCard from './RepairCommandsCard';
import SkillView from './SkillView';
import { hydrateGeneratedFileLinks, isRenderableReportDownload, rewriteAttachmentDownloadMentions } from './downloadUrl';
import {CustomChatMessage} from '@/app/opspilot/types/global';
import {useSession} from 'next-auth/react';
import {useAuth} from '@/context/auth';
import {CustomChatSSEProps, GuideParseResult} from '@/app/opspilot/types/chat';
import {useSSEStream} from './hooks/useSSEStream';
import {useSendMessage} from './hooks/useSendMessage';
import {initToolCallTooltips, setToolCallRendererLocale} from './toolCallRenderer';
import { setOpspilotModuleLocale } from './i18n';
import { getStoredLocale } from '@/utils/userPreferences';
import { stripPlannedExecutionDumps } from './plannedExecutionPayload';
import ContextUsageRing from './ContextUsageRing';
import SessionFileBar from './SessionFileBar';
import { collectSessionFiles } from './sessionFiles';
import type { LlmContextUsage } from './llmContextUsage';
import { useImeEnterGuard } from '@/app/opspilot/utils/imeKeyboard';
import {
  CHAT_ATTACHMENT_ACCEPT,
  ChatAttachmentMeta,
  clientFileError,
  downloadChatAttachmentBlob,
  fetchChatAttachmentStatus,
  isImageMime,
  uploadChatAttachment,
} from './chatAttachments';

const normalizeThinkingText = (value?: string) => {
  if (!value) return '';

  return value
    .replace(/<\/?think>/gi, '')
    .replace(/^\s+/, '')
    .replace(/\s+$/, '');
};

const ThinkingPanel: React.FC<{ thinking?: string; isThinking?: boolean }> = ({ thinking, isThinking }) => {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(Boolean(isThinking));
  const previousThinkingRef = useRef(Boolean(isThinking));

  useEffect(() => {
    if (isThinking) {
      setExpanded(true);
    } else if (previousThinkingRef.current) {
      setExpanded(false);
    }

    previousThinkingRef.current = Boolean(isThinking);
  }, [isThinking]);

  const normalizedThinking = normalizeThinkingText(thinking);

  if (!normalizedThinking && !isThinking) {
    return null;
  }

  const statusText = isThinking
    ? t('chat.thinking', '思考中...')
    : t('chat.thinkingDone', '已完成思考');

  return (
    <div className="my-1.5">
      <button
        type="button"
        className="inline-flex items-center gap-1.5 py-0.5 px-1 -ml-1 text-xs text-[var(--color-text-3)] hover:text-[var(--color-text-2)] hover:bg-[var(--color-fill-1)] rounded transition-colors cursor-pointer select-none group border-0 bg-transparent"
        onClick={() => setExpanded(prev => !prev)}
      >
        <RightOutlined className={`text-[9px] text-[var(--color-text-4)] group-hover:text-[var(--color-text-3)] transition-transform duration-200 ${expanded ? 'rotate-90' : 'rotate-0'}`} />
        <span className="flex items-center gap-1.5 font-normal">
          <span className={`inline-block h-1.5 w-1.5 rounded-full ${isThinking ? 'bg-[var(--color-primary)] animate-neutral-pulse' : 'bg-emerald-500'}`} />
          <span>{statusText}</span>
        </span>
        {isThinking && (
          <span className="flex items-center gap-0.5 ml-0.5">
            <span className="h-1 w-1 rounded-full bg-[var(--color-primary)] animate-bounce" />
            <span className="h-1 w-1 rounded-full bg-[var(--color-primary)] animate-bounce [animation-delay:0.2s]" />
            <span className="h-1 w-1 rounded-full bg-[var(--color-primary)] animate-bounce [animation-delay:0.4s]" />
          </span>
        )}
      </button>
      {expanded && (
        <div className="my-1.5 ml-1 pl-3 border-l-2 border-[var(--color-fill-3)] text-xs text-[var(--color-text-3)] leading-relaxed whitespace-pre-wrap">
          {normalizedThinking ? (
            <div>{normalizedThinking}</div>
          ) : (
            <div className="text-[var(--color-text-4)]">{t('chat.organizing', '正在整理思路...')}</div>
          )}
        </div>
      )}
    </div>
  );
};

const md = new MarkdownIt({
  html: true, // Enable raw HTML (sanitized by DOMPurify)
  highlight: function (str: string, lang: string) {
    if (lang && hljs.getLanguage(lang)) {
      try {
        return hljs.highlight(str, { language: lang }).value;
      } catch {}
    }
    return '';
  },
});

// Sanitize HTML to prevent XSS and CSS injection.
// SECURITY: 'style' tag (block CSS) is intentionally excluded: allowing it
// enables CSS injection via LLM prompt injection.
// Inline style attributes are kept because guide/reference link renderers use them.
const sanitizeHtml = (html: string): string => {
  return DOMPurify.sanitize(html, {
    ALLOWED_TAGS: ['p', 'br', 'strong', 'em', 'u', 'code', 'pre', 'span', 'div', 'a', 'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'blockquote', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'img', 'svg', 'use', 'button'],
    ALLOWED_ATTR: ['class', 'style', 'href', 'target', 'rel', 'data-ref-number', 'data-chunk-id', 'data-knowledge-id', 'data-chunk-type', 'data-content', 'data-suggestion', 'data-expanded', 'data-tool-id', 'data-has-detail', 'src', 'alt', 'width', 'height', 'aria-hidden'],
    ALLOW_DATA_ATTR: false,
  });
};

const CustomChatSSE: React.FC<CustomChatSSEProps> = ({
  handleSendMessage,
  initialMessages = [],
  mode = 'chat',
  guide,
  useAGUIProtocol = false,
  showHeader = true,
  requirePermission = true,
  removePendingBotMessageOnCancel = false,
  conversationHistoryEnabled = true,
  initialContextUsage = null,
  onConversationCleared,
}) => {
  const { t } = useTranslation();
  const imeEnterGuard = useImeEnterGuard();

  let session = null;
  try {
    const sessionData = useSession();
    session = sessionData.data;
  } catch (error) {
    console.warn('useSession hook error, falling back to auth context:', error);
  }

  const authContext = useAuth();
  const token = authContext?.token || (session?.user as any)?.token || null;

  const [isFullscreen, setIsFullscreen] = useState(false);
  const [value, setValue] = useState('');
  const [loading, setLoading] = useState(false);
  const [drafts, setDrafts] = useState<Array<ChatAttachmentMeta & { localId: string; file?: File }>>([]);
  const [markdownPreview, setMarkdownPreview] = useState<{ src: string; alt: string } | null>(null);
  const [messages, setMessages] = useState<CustomChatMessage[]>(
    initialMessages.length ? initialMessages : []
  );
  const [contextUsage, setContextUsage] = useState<LlmContextUsage | null>(
    conversationHistoryEnabled ? initialContextUsage : null
  );
  const currentBotMessageRef = useRef<CustomChatMessage | null>(null);
  const chatContentRef = useRef<HTMLDivElement>(null);
  const scrollAnimationFrameRef = useRef<number | null>(null);

  // 仅在父级提供历史消息时同步；空数组不得把正在流式的会话清空
  useEffect(() => {
    if (initialMessages.length) {
      setMessages(initialMessages);
    }
  }, [initialMessages]);

  // 初始化工具调用事件处理；渲染器与协议处理器不在 React 树内，需同步当前语言
  useEffect(() => {
    const locale = getStoredLocale() === 'en' ? 'en' : 'zh';
    setToolCallRendererLocale(locale);
    setOpspilotModuleLocale(locale);
    initToolCallTooltips();
  }, []);

  // Auto scroll
  const scrollToBottom = useCallback(() => {
    if (chatContentRef.current) {
      chatContentRef.current.scrollTo({
        top: chatContentRef.current.scrollHeight,
        behavior: 'auto'
      });
    }
  }, []);

  const scheduleScrollToBottom = useCallback(() => {
    if (scrollAnimationFrameRef.current !== null) {
      cancelAnimationFrame(scrollAnimationFrameRef.current);
    }

    scrollAnimationFrameRef.current = requestAnimationFrame(() => {
      scrollAnimationFrameRef.current = null;
      scrollToBottom();
    });
  }, [scrollToBottom]);

  useEffect(() => {
    if (messages.length > 0) {
      scheduleScrollToBottom();
    }
  }, [messages, scheduleScrollToBottom]);

  useEffect(() => {
    return () => {
      if (scrollAnimationFrameRef.current !== null) {
        cancelAnimationFrame(scrollAnimationFrameRef.current);
      }
    };
  }, []);

  const updateMessages = useCallback(
    (newMessages: CustomChatMessage[] | ((prev: CustomChatMessage[]) => CustomChatMessage[])) => {
      setMessages(prevMessages => {
        const updatedMessages =
          typeof newMessages === 'function' ? newMessages(prevMessages) : newMessages;
        return updatedMessages;
      });
      scheduleScrollToBottom();
    },
    [scheduleScrollToBottom]
  );

  // 使用自定义 Hooks
  const removeCurrentPendingBotMessage = useCallback(() => {
    const currentBotMessage = currentBotMessageRef.current;
    if (!currentBotMessage) {
      return;
    }

    // 只删尚未产出可见内容的占位气泡；已有正文/工具/卡片时保留，避免「问着问着内容没了」
    updateMessages(prevMessages => {
      const target = prevMessages.find(msg => msg.id === currentBotMessage.id);
      if (!target) {
        return prevMessages;
      }
      const hasVisibleContent = Boolean(
        target.content ||
        target.thinking ||
        target.isThinking ||
        (target.toolCalls && target.toolCalls.length > 0) ||
        (target.userChoiceRequests && target.userChoiceRequests.length > 0) ||
        (target.approvalRequests && target.approvalRequests.length > 0) ||
        (target.configDiffReports && target.configDiffReports.length > 0) ||
        (target.configAnalysisReports && target.configAnalysisReports.length > 0) ||
        (target.reportFileDownloads && target.reportFileDownloads.length > 0) ||
        (target.repairCommands && target.repairCommands.length > 0) ||
        (target.plannedExecutionSteps && target.plannedExecutionSteps.length > 0) ||
        (target.browserStepsHistory && target.browserStepsHistory.steps.length > 0)
      );
      if (hasVisibleContent) {
        return prevMessages;
      }
      return prevMessages.filter(msg => msg.id !== currentBotMessage.id);
    });
    currentBotMessageRef.current = null;
  }, [updateMessages]);

  const { handleSSEStream, stopSSEConnection } = useSSEStream({
    token,
    useAGUIProtocol,
    updateMessages,
    setLoading,
    t,
    onCancelCleanup: removePendingBotMessageOnCancel ? removeCurrentPendingBotMessage : undefined,
    onContextUsage: setContextUsage,
  });

  const { sendMessage } = useSendMessage({
    loading,
    token,
    messages,
    updateMessages,
    setLoading,
    handleSendMessage,
    handleSSEStream,
    currentBotMessageRef,
    t
  });

  const pendingChoice = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      const requests = messages[i].userChoiceRequests;
      if (requests?.length) {
        const pending = requests.find(request => request.status === 'pending');
        if (pending) return pending;
      }
    }
    return null;
  }, [messages]);

  const displayMessages = useMemo(() => applyAnsweredUserChoices(messages), [messages]);

  // Parse guide with proper HTML escaping
  const parseGuideItems = useCallback((guideText: string): GuideParseResult => {
    if (!guideText) return { text: '', items: [], renderedHtml: '' };

    const regex = /\[([^\]]+)\]/g;
    const items: string[] = [];
    let match;

    while ((match = regex.exec(guideText)) !== null) {
      items.push(match[1]);
    }

    // Escape HTML entities to prevent XSS
    const escapeHtml = (text: string) => {
      return text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
    };

    // 纯文本引导语（去掉 [问题] 标签）
    const pureIntro = escapeHtml(guideText.replace(/\[([^\]]+)\]/g, '').trim()).replace(/\n/g, '<br>');

    return { text: guideText, items, renderedHtml: pureIntro };
  }, []);

  // Parse links with proper HTML escaping
  const parseReferenceLinks = useCallback((content: string) => {
    // Escape HTML entities to prevent XSS
    const escapeAttr = (text: string) => {
      return text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
    };

    const referenceRegex = /\[\[(\d+)\]\]\(([^)]+)\)/g;
    return content.replace(referenceRegex, (match, refNumber, params) => {
      const paramPairs = params.split('|');
      const urlParams = new Map();

      paramPairs.forEach((pair: string) => {
        const [key, value] = pair.split(':');
        if (key && value) urlParams.set(key, escapeAttr(value));
      });

      const chunkId = urlParams.get('chunk_id') || '';
      const knowledgeId = urlParams.get('knowledge_id') || '';
      const chunkType = urlParams.get('chunk_type') || 'Document';
      const iconType =
        chunkType === 'QA'
          ? 'wendaduihua'
          : chunkType === 'Graph'
            ? 'zhishitupu'
            : 'wendangguanlixitong-wendangguanlixitongtubiao';

      // Escape all dynamic values
      const escapedRefNumber = escapeAttr(refNumber);
      const escapedIconType = escapeAttr(iconType);

      return `<span class="reference-link inline-flex items-center gap-1" data-ref-number="${escapedRefNumber}" data-chunk-id="${chunkId}" data-knowledge-id="${knowledgeId}" data-chunk-type="${chunkType}" style="color: #1890ff; cursor: pointer; margin: 0 2px;"><svg class="icon icon-${escapedIconType} inline-block" style="width: 1em; height: 1em; vertical-align: text-bottom;" aria-hidden="true"><use href="#icon-${escapedIconType}"></use></svg></span>`;
    });
  }, []);

  const parseSuggestionLinks = useCallback((content: string) => {
    // Escape HTML entities to prevent XSS
    const escapeHtml = (text: string) => {
      return text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
    };

    const suggestionRegex = /\[(\d+)\]\(suggest:\s*([^)]+)\)/g;
    return content.replace(suggestionRegex, (match, number, suggestionText) => {
      const trimmedText = escapeHtml(suggestionText.trim());
      return `<button class="suggestion-button inline-block text-[var(--color-text-1)] text-left border border-[var(--color-border-1)] rounded-full px-3 py-1.5 mx-1 my-1 cursor-pointer text-xs transition-all duration-200 ease-in-out hover:shadow-md hover:-translate-y-0.5 hover:border-blue-400 active:scale-95" data-suggestion="${trimmedText}">${trimmedText}</button>`;
    });
  }, []);

  // Handle clicks
  const handleGuideClick = useCallback(
    (event: React.MouseEvent<HTMLDivElement>) => {
      if (mode !== 'chat') return;
      const target = event.target as HTMLElement;
      if (target.classList.contains('guide-clickable-item')) {
        const content = target.getAttribute('data-content');
        if (content) sendMessage(content);
      }
    },
    [mode, sendMessage]
  );

  const handleSuggestionClick = useCallback(
    (event: React.MouseEvent<HTMLDivElement>) => {
      if (mode !== 'chat') return;
      const target = event.target as HTMLElement;
      if (target.classList.contains('suggestion-button')) {
        const suggestionText = target.getAttribute('data-suggestion');
        if (suggestionText) sendMessage(suggestionText);
      }
    },
    [mode, sendMessage]
  );

  // 处理工具调用组的展开/折叠
  const handleToolCallClick = useCallback(
    (event: React.MouseEvent<HTMLDivElement>) => {
      const target = event.target as HTMLElement;
      
      // 处理工具组头部点击（展开/折叠工具列表）
      const groupHeader = target.closest('.tool-call-group-header') as HTMLElement | null;
      if (groupHeader) {
        event.preventDefault();
        event.stopPropagation();
        
        const group = groupHeader.closest('.tool-call-group') as HTMLElement | null;
        if (group) {
          const body = group.querySelector('.tool-call-group-body') as HTMLElement | null;
          if (body) {
            const isHidden = body.style.display === 'none';
            body.style.display = isHidden ? '' : 'none';
          }
          // 旋转箭头图标
          const expandIcon = groupHeader.querySelector('.tool-call-expand-icon') as HTMLElement | null;
          if (expandIcon) {
            const isExpanded = expandIcon.style.transform === 'rotate(90deg)';
            expandIcon.style.transform = isExpanded ? 'rotate(0deg)' : 'rotate(90deg)';
          }
        }
        return;
      }
      
      // 处理单个工具项点击（展开/折叠工具详情）
      const itemHeader = target.closest('.tool-call-item-header') as HTMLElement | null;
      if (itemHeader) {
        event.preventDefault();
        event.stopPropagation();
        
        const item = itemHeader.closest('.tool-call-item') as HTMLElement | null;
        if (item && item.getAttribute('data-has-detail') === 'true') {
          const detail = item.querySelector('.tool-call-item-detail') as HTMLElement | null;
          if (detail) {
            const isHidden = detail.style.display === 'none';
            detail.style.display = isHidden ? '' : 'none';
          }
          // 旋转箭头图标
          const expandIcon = itemHeader.querySelector('.tool-call-item-expand-icon') as HTMLElement | null;
          if (expandIcon) {
            const isExpanded = expandIcon.style.transform === 'rotate(90deg)';
            expandIcon.style.transform = isExpanded ? 'rotate(0deg)' : 'rotate(90deg)';
          }
        }
        return;
      }
    },
    []
  );

  const handleMarkdownBodyClick = useCallback(
    (event: React.MouseEvent<HTMLDivElement>) => {
      const target = event.target;
      if (target instanceof HTMLImageElement || (target instanceof HTMLElement && target.tagName === 'IMG')) {
        const image = target as HTMLImageElement;
        const src = image.currentSrc || image.getAttribute('src') || image.src;
        if (src) {
          event.preventDefault();
          event.stopPropagation();
          setMarkdownPreview({ src, alt: image.alt || '' });
          return;
        }
      }
      handleToolCallClick(event);
      handleSuggestionClick(event);
    },
    [handleSuggestionClick, handleToolCallClick]
  );

  const handleFullscreenToggle = () => setIsFullscreen(!isFullscreen);

  const handleClearMessages = () => {
    stopSSEConnection();
    updateMessages([]);
    currentBotMessageRef.current = null;
    setContextUsage(null);
    onConversationCleared?.();
  };

  const attachmentPreviews = useRef(new Map<number, { url?: string }>());

  useEffect(() => {
    const previews = attachmentPreviews.current;
    return () => {
      previews.forEach(({ url }) => {
        if (url) URL.revokeObjectURL(url);
      });
      previews.clear();
    };
  }, []);

  useEffect(() => {
    const previews = attachmentPreviews.current;
    const visibleIds = new Set(messages.flatMap((msg) => (
      (msg.attachments || []).filter((item) => isImageMime(item.mime)).map((item) => item.id)
    )));
    previews.forEach(({ url }, id) => {
      if (!visibleIds.has(id)) {
        if (url) URL.revokeObjectURL(url);
        previews.delete(id);
      }
    });
    if (!token) return;
    const applyPreview = (id: number, previewUrl: string) => {
      updateMessages((prev) => prev.map((item) => ({
        ...item,
        attachments: item.attachments?.map((current) => (
          current.id === id ? { ...current, previewUrl } : current
        )),
      })));
    };
    messages.forEach((msg) => {
      (msg.attachments || []).forEach((attachment) => {
        if (!isImageMime(attachment.mime) || attachment.previewUrl) {
          return;
        }
        const existing = previews.get(attachment.id);
        if (existing) {
          if (existing.url) applyPreview(attachment.id, existing.url);
          return;
        }
        const preview: { url?: string } = {};
        previews.set(attachment.id, preview);
        downloadChatAttachmentBlob(attachment.id, token)
          .then((blob) => {
            if (previews.get(attachment.id) !== preview) return;
            const previewUrl = URL.createObjectURL(blob);
            preview.url = previewUrl;
            applyPreview(attachment.id, previewUrl);
          })
          .catch(() => undefined);
      });
    });
  }, [messages, token, updateMessages]);

  useEffect(() => {
    if (!conversationHistoryEnabled) {
      setContextUsage(null);
      return;
    }
    setContextUsage(initialContextUsage ?? null);
  }, [conversationHistoryEnabled, initialContextUsage]);

  const hasPendingDraft = drafts.some((item) => item.status === 'pending');
  const readyDrafts = drafts.filter((item) => item.status === 'ready' && item.id);

  const handleSend = useCallback(
    async (msg: string, attachments?: ChatAttachmentMeta[]) => {
      const ready = (attachments || []).filter((item) => item.status === 'ready' && item.id);
      if ((msg.trim() || ready.length > 0) && !loading && token && !hasPendingDraft) {
        currentBotMessageRef.current = null;
        await sendMessage(msg, messages, ready.map((item) => ({
          id: item.id,
          name: item.name,
          mime: item.mime,
          size: item.size,
          status: item.status,
          previewUrl: item.previewUrl,
        })));
      }
    },
    [hasPendingDraft, loading, token, sendMessage, messages]
  );

  useEffect(() => {
    const pending = drafts.filter((item) => item.status === 'pending' && item.id);
    if (!pending.length || !token) {
      return undefined;
    }
    const timer = window.setInterval(() => {
      pending.forEach((item) => {
        fetchChatAttachmentStatus(item.id, token)
          .then((next) => {
            setDrafts((current) => current.map((draft) => (
              draft.id === item.id ? { ...draft, status: next.status, failure_reason: next.failure_reason } : draft
            )));
          })
          .catch(() => undefined);
      });
    }, 1500);
    return () => window.clearInterval(timer);
  }, [drafts, token]);

  const enqueueFile = useCallback(async (file: File) => {
    const error = clientFileError(file, drafts.length);
    if (error) {
      antMessage.error(error);
      return;
    }
    const localId = `${file.name}-${Date.now()}`;
    const previewUrl = isImageMime(file.type) ? URL.createObjectURL(file) : undefined;
    setDrafts((current) => [...current, {
      localId,
      id: 0,
      name: file.name,
      mime: file.type || 'application/octet-stream',
      size: file.size,
      status: 'pending',
      previewUrl,
      file,
    }]);
    try {
      const uploaded = await uploadChatAttachment(file, token);
      setDrafts((current) => current.map((draft) => (
        draft.localId === localId ? { ...draft, ...uploaded, previewUrl: draft.previewUrl } : draft
      )));
    } catch (uploadError) {
      setDrafts((current) => current.map((draft) => (
        draft.localId === localId ? { ...draft, status: 'failed', failure_reason: uploadError instanceof Error ? uploadError.message : '上传失败' } : draft
      )));
    }
  }, [drafts.length, token]);

  const handleCopyMessage = (content: string) => {
    // 移除 HTML 标签，保留纯文本
    const tempDiv = document.createElement('div');
    tempDiv.innerHTML = content;
    const plainText = tempDiv.textContent || tempDiv.innerText || content;

    // 使用现代 API 或降级方案
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(plainText).catch(
        err => console.error(`${t('chat.copyFailed')}:`, err)
      );
    } else {
      // 降级方案：使用 execCommand
      const textArea = document.createElement('textarea');
      textArea.value = plainText;
      textArea.style.position = 'fixed';
      textArea.style.left = '-999999px';
      textArea.style.top = '-999999px';
      document.body.appendChild(textArea);
      textArea.focus();
      textArea.select();
      try {
        document.execCommand('copy');
      } catch (err) {
        console.error(`${t('chat.copyFailed')}:`, err);
      }
      document.body.removeChild(textArea);
    }
  };

  const handleDeleteMessage = (id: string) => {
    updateMessages(messages.filter(msg => msg.id !== id));
  };

  const handleRegenerateMessage = useCallback(
    async (id: string) => {
      if (!token) return;

      const targetIndex = messages.findIndex(msg => msg.id === id);
      if (targetIndex === -1) return;

      // 从被点击的消息往前找到对应的用户提问（而非始终取最后一个问题）
      let userIndex = -1;
      for (let i = targetIndex; i >= 0; i--) {
        if (messages[i].role === 'user') {
          userIndex = i;
          break;
        }
      }
      if (userIndex === -1) return;

      const userMessage = messages[userIndex];
      // 保留全部对话记录，仅用被点击消息对应的问题重新生成（在末尾追加新答案）
      await sendMessage(userMessage.content, messages, userMessage.attachments);
    },
    [messages, token, sendMessage]
  );

  const handleApprovalDecision = useCallback((toolCallId: string, decision: 'approved' | 'rejected') => {
    updateMessages(prev => prev.map(msg => {
      if (!msg.approvalRequests) return msg;
      const updated = msg.approvalRequests.map(req =>
        req.tool_call_id === toolCallId ? { ...req, status: decision } : req
      );
      return { ...msg, approvalRequests: updated };
    }));
  }, [updateMessages]);

  const handleUserChoiceSubmit = useCallback((choiceId: string, status: 'pending' | 'submitted' | 'timeout', selected: string[]) => {
    updateMessages(prev => prev.map(msg => {
      if (!msg.userChoiceRequests) return msg;
      const updated = msg.userChoiceRequests.map(req =>
        req.choice_id === choiceId
          ? { ...req, status, selected: status === 'pending' ? undefined : selected }
          : req
      );
      return { ...msg, userChoiceRequests: updated };
    }));
  }, [updateMessages]);

  const renderContent = (msg: CustomChatMessage) => {
    const { content, browserStepsHistory, thinking, isThinking, approvalRequests, userChoiceRequests, configDiffReports, configAnalysisReports, reportFileDownloads, repairCommands, agentStepProgress, skillViews, plannedExecutionSteps, plannedExecutionStatus, toolCalls, isStreamingTools } = msg;
    const visibleReportFileDownloads = Array.isArray(reportFileDownloads)
      ? reportFileDownloads.filter(isRenderableReportDownload)
      : [];

    // 工具全部完成但模型还没吐字：这轮最容易被误读成「已结束」，显式提示仍在分析
    const hasTools = Array.isArray(toolCalls) && toolCalls.length > 0;
    const allToolsFinished = hasTools && toolCalls!.every(tool => tool.status !== 'calling');
    const isAwaitingAssistant = Boolean(isStreamingTools) && allToolsFinished && !(content || '').trim() && !isThinking;

    let replacedContent = parseReferenceLinks(stripPlannedExecutionDumps(content || ''));
    replacedContent = stripChoicePromptFromContent(replacedContent, userChoiceRequests);
    replacedContent = parseSuggestionLinks(replacedContent);
    replacedContent = rewriteAttachmentDownloadMentions(replacedContent, reportFileDownloads);

    // Split content at placeholder markers and render components inline
    const renderContentWithInlineComponents = () => {
      // 规划执行时正文常为空，仍要渲染 userChoice / approval 卡片
      const markerPattern = /<!--(CONFIG_DIFF|CONFIG_ANALYSIS|USER_CHOICE):([^>]+)-->/g;
      const hasMarkers = markerPattern.test(replacedContent);

      if (!hasMarkers) {
        const html = replacedContent.trim()
          ? sanitizeHtml(hydrateGeneratedFileLinks(sanitizeHtml(md.render(replacedContent)), reportFileDownloads))
          : '';
        return (
          <>
            {html ? (
              <div
                dangerouslySetInnerHTML={{ __html: html }}
                className={styles.markdownBody}
                onClick={handleMarkdownBodyClick}
              />
            ) : null}
            {Array.isArray(configDiffReports) && configDiffReports.length > 0 && (
              <div className="mt-2">
                {[...configDiffReports].sort((a, b) => (a.received_at || 0) - (b.received_at || 0)).map(report => (
                  <DiffReportCard key={report.report_id} report={report} />
                ))}
              </div>
            )}
            {Array.isArray(configAnalysisReports) && configAnalysisReports.length > 0 && (
              <div className="mt-2">
                {[...configAnalysisReports].sort((a, b) => (a.received_at || 0) - (b.received_at || 0)).map(report => (
                  <ConfigAnalysisReportCard key={report.report_id} report={report} />
                ))}
              </div>
            )}
            {visibleReportFileDownloads.length > 0 && (
              <div className="mt-2">
                {visibleReportFileDownloads.map(dl => (
                  <ReportDownloadCard key={dl.download_id} download={dl} />
                ))}
              </div>
            )}
            {Array.isArray(repairCommands) && repairCommands.length > 0 && (
              <div className="mt-2">
                {repairCommands.map(cmd => (
                  <RepairCommandsCard key={cmd.commands_id} commands={cmd} />
                ))}
              </div>
            )}
            {Array.isArray(approvalRequests) && approvalRequests.length > 0 && (
              <div className="mt-2">
                {approvalRequests.map(req => (
                  <ApprovalCard
                    key={req.tool_call_id}
                    request={req}
                    token={token || ''}
                    onDecision={handleApprovalDecision}
                    readOnly={mode === 'display'}
                  />
                ))}
              </div>
            )}
            {Array.isArray(userChoiceRequests) && userChoiceRequests.length > 0 && (
              <div className="mt-2">
                {userChoiceRequests.map(req => (
                  <UserChoiceCard
                    key={req.choice_id}
                    request={req}
                    token={token || ''}
                    onSubmit={handleUserChoiceSubmit}
                    onSendMessage={(text) => { void handleSend(text); }}
                    readOnly={mode === 'display'}
                  />
                ))}
              </div>
            )}
          </>
        );
      }

      // Has markers — split and interleave
      const segments = replacedContent.split(/<!--(?:CONFIG_DIFF|CONFIG_ANALYSIS|USER_CHOICE):[^>]+-->/);
      const markers: Array<{ type: string; id: string }> = [];
      let match;
      const re = /<!--(CONFIG_DIFF|CONFIG_ANALYSIS|USER_CHOICE):([^>]+)-->/g;
      while ((match = re.exec(replacedContent)) !== null) {
        markers.push({ type: match[1], id: match[2] });
      }

      // Track which reports/choices are rendered inline
      const renderedDiffIds = new Set<string>();
      const renderedConfigAnalysisIds = new Set<string>();
      const renderedChoiceIds = new Set<string>();

      const elements: React.ReactNode[] = [];
      for (let i = 0; i < segments.length; i++) {
        const segment = segments[i].trim();
        if (segment) {
          const segHtml = sanitizeHtml(hydrateGeneratedFileLinks(sanitizeHtml(md.render(segment)), reportFileDownloads));
          elements.push(
            <div
              key={`seg-${i}`}
              dangerouslySetInnerHTML={{ __html: segHtml }}
              className={styles.markdownBody}
              onClick={handleMarkdownBodyClick}
            />
          );
        }
        // Render the marker component after this segment
        if (i < markers.length) {
          const marker = markers[i];
          if (marker.type === 'CONFIG_DIFF') {
            const report = configDiffReports?.find(r => r.report_id === marker.id);
            if (report) {
              renderedDiffIds.add(marker.id);
              elements.push(<DiffReportCard key={`diff-${marker.id}`} report={report} />);
            }
          } else if (marker.type === 'CONFIG_ANALYSIS') {
            const report = configAnalysisReports?.find(r => r.report_id === marker.id);
            if (report) {
              renderedConfigAnalysisIds.add(marker.id);
              elements.push(<ConfigAnalysisReportCard key={`config-analysis-${marker.id}`} report={report} />);
            }
          } else if (marker.type === 'USER_CHOICE') {
            const req = userChoiceRequests?.find(r => r.choice_id === marker.id);
            if (req) {
              renderedChoiceIds.add(marker.id);
              elements.push(
                <UserChoiceCard
                  key={`choice-${marker.id}`}
                  request={req}
                  token={token || ''}
                  onSubmit={handleUserChoiceSubmit}
                  onSendMessage={(text) => { void handleSend(text); }}
                  readOnly={mode === 'display'}
                />
              );
            }
          }
        }
      }

      // Render any remaining items not matched by markers (fallback)
      const remainingDiffs = configDiffReports?.filter(r => !renderedDiffIds.has(r.report_id)) || [];
      const remainingConfigAnalysisReports = configAnalysisReports?.filter(
        r => !renderedConfigAnalysisIds.has(r.report_id)
      ) || [];
      const remainingChoices = userChoiceRequests?.filter(r => !renderedChoiceIds.has(r.choice_id)) || [];

      if (remainingDiffs.length > 0) {
        elements.push(
          <div key="remaining-diffs" className="mt-2">
            {remainingDiffs.map(report => (
              <DiffReportCard key={report.report_id} report={report} />
            ))}
          </div>
        );
      }
      if (remainingConfigAnalysisReports.length > 0) {
        elements.push(
          <div key="remaining-config-analysis" className="mt-2">
            {remainingConfigAnalysisReports.map(report => (
              <ConfigAnalysisReportCard key={report.report_id} report={report} />
            ))}
          </div>
        );
      }
      if (visibleReportFileDownloads.length > 0) {
        elements.push(
          <div key="file-downloads" className="mt-2">
            {visibleReportFileDownloads.map(dl => (
              <ReportDownloadCard key={dl.download_id} download={dl} />
            ))}
          </div>
        );
      }
      if (Array.isArray(repairCommands) && repairCommands.length > 0) {
        elements.push(
          <div key="repair-commands" className="mt-2">
            {repairCommands.map(cmd => (
              <RepairCommandsCard key={cmd.commands_id} commands={cmd} />
            ))}
          </div>
        );
      }
      if (Array.isArray(approvalRequests) && approvalRequests.length > 0) {
        elements.push(
          <div key="approvals" className="mt-2">
            {approvalRequests.map(req => (
              <ApprovalCard
                key={req.tool_call_id}
                request={req}
                token={token || ''}
                onDecision={handleApprovalDecision}
                readOnly={mode === 'display'}
              />
            ))}
          </div>
        );
      }
      if (remainingChoices.length > 0) {
        elements.push(
          <div key="remaining-choices" className="mt-2">
            {remainingChoices.map(req => (
              <UserChoiceCard
                key={req.choice_id}
                request={req}
                token={token || ''}
                onSubmit={handleUserChoiceSubmit}
                onSendMessage={(text) => { void handleSend(text); }}
                readOnly={mode === 'display'}
              />
            ))}
          </div>
        );
      }

      return <>{elements}</>;
    };

    return (
      <>
        {Array.isArray(msg.attachments) && msg.attachments.length > 0 && (
          <div className="mb-2 flex flex-wrap gap-2">
            {msg.attachments.map((item) => (
              isImageMime(item.mime) && item.previewUrl ? (
                <img key={item.id} src={item.previewUrl} alt={item.name} className="h-[120px] w-[120px] rounded object-cover" />
              ) : (
                <button
                  key={item.id}
                  type="button"
                  title={t('chat.downloadFile', '点击下载')}
                  className="group inline-flex cursor-pointer items-center gap-1.5 rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg)] px-3 py-1.5 text-xs text-[var(--color-text-1)] shadow-xs transition-all hover:border-[var(--color-primary)] hover:bg-[var(--color-primary-bg)] hover:text-[var(--color-primary)]"
                  onClick={() => {
                    downloadChatAttachmentBlob(item.id, token)
                      .then((blob) => {
                        const url = URL.createObjectURL(blob);
                        const link = document.createElement('a');
                        link.href = url;
                        link.download = item.name;
                        link.click();
                        URL.revokeObjectURL(url);
                      })
                      .catch(() => antMessage.error(t('chat.downloadFailed', '下载失败')));
                  }}
                >
                  <span>{item.name}</span>
                  <DownloadOutlined className="text-[11px] opacity-0 transition-opacity group-hover:opacity-100" />
                </button>
              )
            ))}
          </div>
        )}
        <ThinkingPanel thinking={thinking} isThinking={isThinking} />
        <SkillView items={skillViews} />
        {Array.isArray(agentStepProgress) && agentStepProgress.length > 0 && (
          <AgentStepProgress steps={agentStepProgress} />
        )}
        {plannedExecutionStatus && isActivePlannedExecutionStatus(plannedExecutionStatus.phase) && (
          <PlannedExecutionStatus status={plannedExecutionStatus} />
        )}
        {Array.isArray(plannedExecutionSteps) && plannedExecutionSteps.length > 0 && (
          <PlannedExecutionSteps
            steps={plannedExecutionSteps}
            toolCalls={Array.isArray(toolCalls) ? toolCalls : []}
            isStreaming={Boolean(isStreamingTools)}
          />
        )}
        {browserStepsHistory && browserStepsHistory.steps.length > 0 && (
          <BrowserStepProgress history={browserStepsHistory} />
        )}
        {renderContentWithInlineComponents()}
        {isAwaitingAssistant && (
          <div
            className="my-1.5 flex items-center gap-1.5 py-0.5 text-xs text-[var(--color-text-3)]"
            role="status"
            aria-live="polite"
          >
            <LoadingOutlined className="text-[var(--color-primary)] text-xs" spin />
            <span>{t('chat.analyzingResult')}</span>
          </div>
        )}
        {!!msg.wikiCitations?.length && <WikiCitations citations={msg.wikiCitations} content={replacedContent} />}
      </>
    );
  };

  const renderSend = (props: { ignoreLoading?: boolean; placeholder?: string } = {}) => {
    const { ignoreLoading, placeholder } = props;

    const composerComponent = (
      <div className="relative rounded-xl border border-[var(--color-border-1)] bg-[var(--color-bg)] transition-all focus-within:border-[var(--color-primary)] focus-within:ring-2 focus-within:ring-[var(--color-primary-bg-active)]">
        {drafts.length > 0 && (
          <div className="flex flex-wrap gap-2 p-2.5 pb-0">
            {drafts.map((draft) => (
              <div key={draft.localId} className="flex items-center gap-1 rounded-md border border-[var(--color-border-1)] px-2 py-1 text-xs" data-testid="attachment-chip">
                {draft.status === 'pending' ? <LoadingOutlined spin /> : null}
                {draft.previewUrl ? <img src={draft.previewUrl} alt={draft.name} className="h-8 w-8 rounded object-cover" /> : null}
                <span className={draft.status === 'failed' ? 'text-[var(--color-fail)]' : 'text-[var(--color-text-2)]'}>
                  {draft.name}
                  {draft.status === 'pending' ? ` · ${t('chat.fileParsing', '文件解析中')}` : ''}
                  {draft.status === 'failed' ? ` · ${draft.failure_reason || t('chat.fileFailed', '解析失败')}` : ''}
                </span>
                <button
                  type="button"
                  onClick={() => {
                    if (draft.previewUrl) URL.revokeObjectURL(draft.previewUrl);
                    setDrafts((current) => current.filter((item) => item.localId !== draft.localId));
                  }}
                  aria-label={t('chat.deleteImage', '删除图片')}
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        )}

        <div className="px-3 pt-2.5">
          <Input.TextArea
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder={pendingChoice ? t('chat.replyToPendingChoice', '回复上面的问题...') : (placeholder || t('chat.inputPlaceholder', '请输入消息...'))}
            autoSize={{ minRows: 2, maxRows: 6 }}
            bordered={false}
            className="!p-0 text-[13px] leading-relaxed resize-none bg-transparent placeholder:text-[var(--color-text-4)] focus:shadow-none"
            onCompositionStart={imeEnterGuard.onCompositionStart}
            onCompositionEnd={imeEnterGuard.onCompositionEnd}
            onKeyDown={(e) => {
              if (!imeEnterGuard.handleEnterKey(e)) {
                return;
              }
              if ((value.trim() || readyDrafts.length > 0) && !loading && !hasPendingDraft) {
                const currentDrafts = [...readyDrafts];
                currentDrafts.forEach((draft) => {
                  if (draft.previewUrl) URL.revokeObjectURL(draft.previewUrl);
                });
                setDrafts([]);
                setValue('');
                handleSend(value, currentDrafts);
              }
            }}
            onPaste={(event: React.ClipboardEvent) => {
              const items = event.clipboardData?.items;
              if (!items) return;
              for (let i = 0; i < items.length; i++) {
                const file = items[i].getAsFile();
                if (!file) continue;
                event.preventDefault();
                void enqueueFile(file);
              }
            }}
          />
        </div>

        <div className="flex items-center justify-between px-3 pb-2 pt-1 border-t border-[var(--color-fill-2)]/60 mt-1">
          <div className="flex items-center gap-1.5">
            <Upload
              accept={CHAT_ATTACHMENT_ACCEPT}
              fileList={[]}
              beforeUpload={(file) => {
                void enqueueFile(file);
                return Upload.LIST_IGNORE;
              }}
              showUploadList={false}
            >
              <Tooltip title={t('chat.uploadFile', '上传文件')}>
                <button
                  type="button"
                  disabled={loading}
                  className="flex h-7 w-7 items-center justify-center rounded-md text-[var(--color-text-3)] hover:bg-[var(--color-fill-2)] hover:text-[var(--color-text-1)] transition-colors disabled:opacity-40"
                  aria-label={t('chat.uploadFile', '上传文件')}
                >
                  <PaperClipOutlined className="text-sm" />
                </button>
              </Tooltip>
            </Upload>

            <Popconfirm
              title={t('chat.clearConfirm')}
              okButtonProps={{ danger: true }}
              onConfirm={handleClearMessages}
              okText={t('chat.clear')}
              cancelText={t('common.cancel')}
              getPopupContainer={(trigger) => trigger.parentElement || document.body}
            >
              <Tooltip title={t('chat.clear', '清除对话')}>
                <button
                  type="button"
                  className="flex h-7 w-7 items-center justify-center rounded-md text-[var(--color-text-3)] hover:bg-[var(--color-fail)]/10 hover:text-[var(--color-fail)] transition-colors"
                  aria-label={t('chat.clearChat', '清空对话')}
                >
                  <DeleteOutlined className="text-sm" />
                </button>
              </Tooltip>
            </Popconfirm>

            {conversationHistoryEnabled ? (
              <div className="ml-1 flex items-center">
                <ContextUsageRing usage={contextUsage} />
              </div>
            ) : null}
          </div>

          <div className="flex items-center gap-2.5">
            <span className="hidden select-none text-[11px] text-[var(--color-text-4)] sm:inline">
              {t('chat.enterHint', 'Enter 发送 · Shift+Enter 换行')}
            </span>

            {loading && !pendingChoice && !ignoreLoading ? (
              <Tooltip title={t('chat.clickCancel', '点击以取消')}>
                <button
                  type="button"
                  onClick={stopSSEConnection}
                  className="flex h-7 w-7 items-center justify-center rounded-full bg-red-500 text-white shadow-xs hover:bg-red-600 active:scale-95 transition-all cursor-pointer"
                  aria-label={t('chat.stopGenerating', '停止生成')}
                >
                  <span className="h-2.5 w-2.5 rounded-xs bg-white" />
                </button>
              </Tooltip>
            ) : (
              <Tooltip title={hasPendingDraft ? t('chat.fileParsing', '文件解析中') : (value.trim() || readyDrafts.length > 0 ? `${t('chat.send')} ↵` : t('chat.inputMessage'))}>
                <button
                  type="button"
                  disabled={hasPendingDraft || (!value.trim() && readyDrafts.length === 0)}
                  onClick={() => {
                    if (hasPendingDraft) return;
                    if (value.trim() || readyDrafts.length > 0) {
                      const currentDrafts = [...readyDrafts];
                      currentDrafts.forEach((draft) => {
                        if (draft.previewUrl) URL.revokeObjectURL(draft.previewUrl);
                      });
                      setDrafts([]);
                      setValue('');
                      handleSend(value, currentDrafts);
                    }
                  }}
                  className={`flex h-7 w-7 items-center justify-center rounded-full shadow-xs transition-all ${
                    (!hasPendingDraft && (value.trim() || readyDrafts.length > 0))
                      ? 'bg-[var(--color-primary)] text-white hover:scale-105 active:scale-95 cursor-pointer'
                      : 'bg-[var(--color-fill-2)] text-[var(--color-text-4)] cursor-not-allowed'
                  }`}
                  aria-label={t('chat.sendMessage', '发送消息')}
                >
                  <SendOutlined className="text-xs" />
                </button>
              </Tooltip>
            )}
          </div>
        </div>
      </div>
    );

    return requirePermission ? (
      <PermissionWrapper requiredPermissions={['Test']}>
        {composerComponent}
      </PermissionWrapper>
    ) : composerComponent;
  };

  const stopSSEConnectionRef = useRef(stopSSEConnection);
  stopSSEConnectionRef.current = stopSSEConnection;

  // 仅在真正卸载时中断；勿把 stopSSEConnection 放进依赖，避免 identity 变化误清会话
  useEffect(() => {
    return () => {
      stopSSEConnectionRef.current();
    };
  }, []);

  const guideData = parseGuideItems(guide || '');

  return (
    <div className={`rounded-lg h-full ${isFullscreen ? styles.fullscreen : ''}`}>
      {markdownPreview ? <span data-testid="markdown-preview-open" hidden>{markdownPreview.src}</span> : null}
      <Image
        alt={markdownPreview?.alt || ''}
        src={markdownPreview?.src}
        wrapperStyle={{ display: 'none' }}
        preview={{
          visible: Boolean(markdownPreview),
          src: markdownPreview?.src,
          onVisibleChange: (visible) => {
            if (!visible) setMarkdownPreview(null);
          },
          getContainer: () => document.body,
          zIndex: 10000,
        }}
      />
      {mode === 'chat' && showHeader && (
        <div className="flex justify-between items-center mb-3">
          <h2 className="text-base font-semibold">{t('chat.test')}</h2>
          <div>
            <button title="fullScreen" onClick={handleFullscreenToggle} aria-label="Toggle Fullscreen">
              {isFullscreen ? <FullscreenExitOutlined /> : <FullscreenOutlined />}
            </button>
          </div>
        </div>
      )}
      <div
        className={`flex flex-col rounded-lg ${mode === 'display' ? 'px-0 py-2' : 'p-4'} h-full overflow-hidden ${styles.chatContainer}`}
        style={{
          height: isFullscreen ? 'calc(100vh - 70px)' : mode === 'chat' ? (showHeader ? 'calc(100% - 40px)' : '100%') : '100%'
        }}
      >
        <div
          ref={chatContentRef}
          className={`flex-1 chat-content-wrapper overflow-y-auto overflow-x-hidden pb-4 ${mode === 'display' ? 'px-6' : ''}`}
        >
          {guide && (guideData.renderedHtml || guideData.items.length > 0) && (
            <div className="mb-4 space-y-2.5" onClick={handleGuideClick}>
              {guideData.renderedHtml && (
                <div
                  dangerouslySetInnerHTML={{ __html: sanitizeHtml(guideData.renderedHtml) }}
                  className="text-[13px] leading-relaxed text-[var(--color-text-1)]"
                />
              )}
              {guideData.items.length > 0 && (
                <div className="flex flex-wrap gap-2 pt-1">
                  {guideData.items.map((item, idx) => (
                    <button
                      key={idx}
                      type="button"
                      onClick={() => handleSend(item, [])}
                      className="inline-flex items-center gap-1.5 rounded-md bg-[var(--color-fill-1)]/70 hover:bg-[var(--color-fill-2)] hover:text-[var(--color-primary)] px-3 py-1.5 text-xs text-[var(--color-text-2)] font-normal transition-all cursor-pointer group active:scale-95"
                    >
                      <svg
                        className="w-3.5 h-3.5 text-[var(--color-text-3)] group-hover:text-[var(--color-primary)] transition-colors"
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                      >
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
                      </svg>
                      <span>{item}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
          <div className="space-y-4">
            {displayMessages.map(msg => {
              const isUser = msg.role === 'user';
              const hasBrowserSteps = msg.browserStepsHistory && msg.browserStepsHistory.steps.length > 0;
              const hasThinking = Boolean(normalizeThinkingText(msg.thinking)) || Boolean(msg.isThinking);
              const hasPlanStatus = isActivePlannedExecutionStatus(msg.plannedExecutionStatus?.phase);
              const hasPlanSteps = Array.isArray(msg.plannedExecutionSteps) && msg.plannedExecutionSteps.length > 0;
              const isEmptyMessage = !msg.content && !hasBrowserSteps && !hasThinking && !hasPlanStatus && !hasPlanSteps;
              const isCurrentBotLoading = loading && currentBotMessageRef.current?.id === msg.id;

              if (isUser) {
                return (
                  <div key={msg.id} className="group flex flex-col items-end w-full my-1.5">
                    <div className={`${styles.userMessageBubble}`}>
                      {renderContent(msg)}
                    </div>
                    {mode === 'chat' && (
                      <div className="mt-1 opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 transition-opacity">
                        <MessageActions
                          message={msg}
                          onCopy={handleCopyMessage}
                          onRegenerate={handleRegenerateMessage}
                          onDelete={handleDeleteMessage}
                        />
                      </div>
                    )}
                  </div>
                );
              }

              return (
                <div key={msg.id} className="group flex flex-col items-start w-full my-1.5 text-[13px] leading-relaxed text-[var(--color-text-1)]">
                  <div className="w-full">
                    {isEmptyMessage && isCurrentBotLoading ? (
                      <div className="flex items-center gap-2 py-2 text-[var(--color-text-3)] text-xs">
                        <LoadingOutlined className="text-[var(--color-primary)]" spin />
                        <span>{t('chat.thinkingAndReplying', '正在思考与生成回复...')}</span>
                      </div>
                    ) : (
                      renderContent(msg)
                    )}
                  </div>
                  {!isCurrentBotLoading && mode === 'chat' && (
                    <div className="mt-1 opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 transition-opacity">
                      <MessageActions
                        message={msg}
                        onCopy={handleCopyMessage}
                        onRegenerate={handleRegenerateMessage}
                        onDelete={handleDeleteMessage}
                      />
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {mode === 'chat' && (
          <div className="flex-shrink-0 pt-2">
            <SessionFileBar files={collectSessionFiles(messages)} />
            {renderSend({
              placeholder: t('chat.inputPlaceholder'),
            })}
          </div>
        )}
      </div>
    </div>
  );
};

export default CustomChatSSE;
