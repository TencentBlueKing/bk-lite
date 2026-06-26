import React, {ReactNode, useCallback, useEffect, useMemo, useRef, useState} from 'react';
import {Button, ButtonProps, Flex, Image, message as antMessage, Popconfirm, Tooltip, Upload} from 'antd';
import {FullscreenExitOutlined, FullscreenOutlined, PictureOutlined, SendOutlined} from '@ant-design/icons';
import type {UploadFile} from 'antd/es/upload/interface';
import {Bubble, Sender} from '@ant-design/x';
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
import WikiCitations from './WikiCitations';
import ApprovalCard from './ApprovalCard';
import UserChoiceCard from './UserChoiceCard';
import {postUserChoice} from './submitUserChoice';
import DiffReportCard from './DiffReportCard';
import ConfigAnalysisReportCard from './ConfigAnalysisReportCard';
import ReportDownloadCard from './ReportDownloadCard';
import RepairCommandsCard from './RepairCommandsCard';
import {CustomChatMessage, ReportFileDownload} from '@/app/opspilot/types/global';
import {useSession} from 'next-auth/react';
import {useAuth} from '@/context/auth';
import {CustomChatSSEProps, GuideParseResult} from '@/app/opspilot/types/chat';
import {useSSEStream} from './hooks/useSSEStream';
import {useSendMessage} from './hooks/useSendMessage';
import {initToolCallTooltips} from './toolCallRenderer';

const normalizeThinkingText = (value?: string) => {
  if (!value) return '';

  return value
    .replace(/<\/?think>/gi, '')
    .replace(/^\s+/, '')
    .replace(/\s+$/, '');
};

const ThinkingPanel: React.FC<{ thinking?: string; isThinking?: boolean }> = ({ thinking, isThinking }) => {
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

  const statusText = isThinking ? '思考中' : '已完成思考';

  return (
    <div className={`${styles.thinkingPanel} ${isThinking ? styles.thinkingPanelActive : styles.thinkingPanelDone}`}>
      <button
        type="button"
        className={styles.thinkingToggle}
        onClick={() => setExpanded(prev => !prev)}
      >
        <span className={styles.thinkingMeta}>
          <span className={`${styles.thinkingBadge} ${isThinking ? styles.thinkingBadgeActive : styles.thinkingBadgeDone}`}>
            <span className={styles.thinkingBadgeDot} />
            {statusText}
          </span>
        </span>
        <span className={styles.thinkingAside}>
          {isThinking && <span className={styles.thinkingDots}><span /><span /><span /></span>}
          <span className={`${styles.thinkingIconButton} ${expanded ? styles.thinkingIconButtonExpanded : ''}`}>
            <span className={`${styles.thinkingArrow} ${expanded ? styles.thinkingArrowExpanded : ''}`}>⌟</span>
          </span>
        </span>
      </button>
      {expanded && (
        <div className={styles.thinkingBody}>
          {normalizedThinking ? (
            <div className={styles.thinkingText}>{normalizedThinking}</div>
          ) : (
            <div className={styles.thinkingPlaceholder}>正在整理思路...</div>
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
// SECURITY: 'style' tag (block CSS) is intentionally excluded — allowing it enables CSS injection
// via LLM prompt injection (e.g. `<style>*{background:url(//attacker.com)}</style>`).
// Inline 'style' attribute is kept in ALLOWED_ATTR as it is used by guide/reference link renderers.
// ALLOW_DATA_ATTR is false; all required data-* attributes are listed explicitly in ALLOWED_ATTR.
const sanitizeHtml = (html: string): string => {
  return DOMPurify.sanitize(html, {
    ALLOWED_TAGS: ['p', 'br', 'strong', 'em', 'u', 'code', 'pre', 'span', 'div', 'a', 'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'blockquote', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'img', 'svg', 'use', 'button'],
    ALLOWED_ATTR: ['class', 'style', 'href', 'target', 'rel', 'data-ref-number', 'data-chunk-id', 'data-knowledge-id', 'data-chunk-type', 'data-content', 'data-suggestion', 'data-expanded', 'data-tool-id', 'src', 'alt', 'width', 'height', 'aria-hidden'],
    ALLOW_DATA_ATTR: false,
  });
};

const normalizeDownloadUrl = (url?: string): string => {
  if (!url) {
    return '';
  }

  if (url.startsWith('/api/v1/')) {
    return url.replace('/api/v1/', '/api/proxy/');
  }

  return url;
};

const hydrateGeneratedFileLinks = (html: string, downloads?: ReportFileDownload[]): string => {
  if (!html || !downloads?.length || typeof window === 'undefined') {
    return html;
  }

  const linkableDownloads = downloads.filter(download => download.file_url);
  if (linkableDownloads.length === 0 || !html.includes('<a')) {
    return html;
  }

  const parser = new DOMParser();
  const doc = parser.parseFromString(html, 'text/html');
  const anchors = Array.from(doc.querySelectorAll('a:not([href])'));
  if (anchors.length === 0) {
    return html;
  }

  const normalizeText = (value: string) => value.replace(/^下载/, '').replace(/\.[^.]+$/, '').trim().toLowerCase();

  anchors.forEach(anchor => {
    const anchorText = normalizeText(anchor.textContent || '');
    const matchedDownload = linkableDownloads.length === 1
      ? linkableDownloads[0]
      : linkableDownloads.find(download => {
        const fileName = normalizeText(download.filename);
        return anchorText && (fileName.includes(anchorText) || anchorText.includes(fileName));
      });

    if (!matchedDownload?.file_url) {
      return;
    }

    anchor.setAttribute('href', normalizeDownloadUrl(matchedDownload.file_url));
    anchor.setAttribute('target', '_blank');
    anchor.setAttribute('rel', 'noopener noreferrer');
  });

  return doc.body.innerHTML;
};

const CustomChatSSE: React.FC<CustomChatSSEProps> = ({
  handleSendMessage,
  initialMessages = [],
  mode = 'chat',
  guide,
  useAGUIProtocol = false,
  showHeader = true,
  requirePermission = true,
  removePendingBotMessageOnCancel = false
}) => {
  const { t } = useTranslation();

  let session = null;
  try {
    const sessionData = useSession();
    session = sessionData.data;
  } catch (error) {
    console.warn('useSession hook error, falling back to auth context:', error);
  }

  const authContext = useAuth();
  const token = (session?.user as any)?.token || authContext?.token || null;

  const [isFullscreen, setIsFullscreen] = useState(false);
  const [value, setValue] = useState('');
  const [loading, setLoading] = useState(false);
  const [imageList, setImageList] = useState<UploadFile[]>([]);
  const [messages, setMessages] = useState<CustomChatMessage[]>(
    initialMessages.length ? initialMessages : []
  );
  const currentBotMessageRef = useRef<CustomChatMessage | null>(null);
  const chatContentRef = useRef<HTMLDivElement>(null);

  // 监听 initialMessages 变化
  useEffect(() => {
    setMessages(initialMessages.length ? initialMessages : []);
  }, [initialMessages]);

  // 初始化工具调用事件处理
  useEffect(() => {
    initToolCallTooltips();
  }, []);

  // Auto scroll
  const scrollToBottom = useCallback(() => {
    if (chatContentRef.current) {
      chatContentRef.current.scrollTo({
        top: chatContentRef.current.scrollHeight,
        behavior: 'smooth'
      });
    }
  }, []);

  useEffect(() => {
    if (messages.length > 0) {
      requestAnimationFrame(() => {
        scrollToBottom();
      });
    }
  }, [messages, scrollToBottom]);

  const updateMessages = useCallback(
    (newMessages: CustomChatMessage[] | ((prev: CustomChatMessage[]) => CustomChatMessage[])) => {
      setMessages(prevMessages => {
        const updatedMessages =
          typeof newMessages === 'function' ? newMessages(prevMessages) : newMessages;
        setTimeout(() => scrollToBottom(), 50);
        return updatedMessages;
      });
    },
    [scrollToBottom]
  );

  // 使用自定义 Hooks
  const removeCurrentPendingBotMessage = useCallback(() => {
    const currentBotMessage = currentBotMessageRef.current;
    if (!currentBotMessage) {
      return;
    }

    updateMessages(prevMessages => prevMessages.filter(msg => msg.id !== currentBotMessage.id));
    currentBotMessageRef.current = null;
  }, [updateMessages]);

  const { handleSSEStream, stopSSEConnection } = useSSEStream({
    token,
    useAGUIProtocol,
    updateMessages,
    setLoading,
    t,
    onCancelCleanup: removePendingBotMessageOnCancel ? removeCurrentPendingBotMessage : undefined,
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

    const processedText = escapeHtml(guideText).replace(/\n/g, '<br>');
    const renderedHtml = processedText.replace(/\[([^\]]+)\]/g, (match, content) => {
      const escapedContent = escapeHtml(content);
      return `<span class="guide-clickable-item" data-content="${escapedContent}" style="color: #1890ff; cursor: pointer; font-weight: 600; margin: 0 2px;">${escapedContent}</span>`;
    });

    return { text: guideText, items, renderedHtml: sanitizeHtml(renderedHtml) };
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
      const target = event.target as HTMLElement;
      if (target.classList.contains('guide-clickable-item')) {
        const content = target.getAttribute('data-content');
        if (content) sendMessage(content);
      }
    },
    [sendMessage]
  );

  const handleSuggestionClick = useCallback(
    (event: React.MouseEvent<HTMLDivElement>) => {
      const target = event.target as HTMLElement;
      if (target.classList.contains('suggestion-button')) {
        const suggestionText = target.getAttribute('data-suggestion');
        if (suggestionText) sendMessage(suggestionText);
      }
    },
    [sendMessage]
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

  const handleFullscreenToggle = () => setIsFullscreen(!isFullscreen);

  const handleClearMessages = () => {
    stopSSEConnection();
    updateMessages([]);
    currentBotMessageRef.current = null;
  };

  // 当前是否有正在等待用户回答的选择（B 在等待）：用于把主对话框输入直接投递给该节点，
  // 而非新建对话；同时让发送框在等待期间可交互（不显示"停止"态）。
  const pendingChoice = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      const reqs = messages[i].userChoiceRequests;
      if (reqs && reqs.length) {
        const pending = reqs.find(r => r.status === 'pending');
        if (pending) return pending;
      }
    }
    return null;
  }, [messages]);

  const handleSend = useCallback(
    async (msg: string, images?: UploadFile[]) => {
      // 命中"正在等待回答的选择"：把本条消息当作该选择的答案投递给等待中的节点，
      // 不新建对话、不中断原流（B 会在原 SSE 流上继续输出）。
      if (pendingChoice && msg.trim() && token) {
        const answer = msg.trim();
        try {
          await postUserChoice(token, {
            execution_id: pendingChoice.execution_id,
            node_id: pendingChoice.node_id,
            choice_id: pendingChoice.choice_id,
            selected: [answer],
          });
          updateMessages(prev => prev.map(m => {
            if (!m.userChoiceRequests) return m;
            return {
              ...m,
              userChoiceRequests: m.userChoiceRequests.map(r =>
                r.choice_id === pendingChoice.choice_id
                  ? { ...r, status: 'submitted' as const, selected: [answer] }
                  : r
              ),
            };
          }));
        } catch {
          antMessage.error(t('chat.choiceSubmitFailed'));
        }
        return;
      }

      if ((msg.trim() || (images && images.length > 0)) && !loading && token) {
        currentBotMessageRef.current = null;

        // Convert images to base64
        let imageData: any[] | undefined;
        if (images && images.length > 0) {
          imageData = await Promise.all(
            images.map(async (file) => {
              if (file.originFileObj) {
                const base64 = await new Promise<string>((resolve) => {
                  const reader = new FileReader();
                  reader.onloadend = () => resolve(reader.result as string);
                  reader.readAsDataURL(file.originFileObj as File);
                });
                return {
                  id: file.uid,
                  url: base64,
                  name: file.name,
                  status: 'done'
                };
              }
              return null;
            })
          ).then(results => results.filter(Boolean));
        }

        await sendMessage(msg, messages, imageData);
      }
    },
    [pendingChoice, loading, token, sendMessage, messages, updateMessages, t]
  );

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
    async () => {
      const lastUserMessage = messages.filter(msg => msg.role === 'user').pop();
      if (lastUserMessage && token) {
        await sendMessage(lastUserMessage.content, messages);
      }
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

  const handleUserChoiceSubmit = useCallback((choiceId: string, status: 'submitted' | 'timeout', selected: string[]) => {
    updateMessages(prev => prev.map(msg => {
      if (!msg.userChoiceRequests) return msg;
      const updated = msg.userChoiceRequests.map(req =>
        req.choice_id === choiceId ? { ...req, status, selected } : req
      );
      return { ...msg, userChoiceRequests: updated };
    }));
  }, [updateMessages]);

  const renderContent = (msg: CustomChatMessage) => {
    const { content, images, browserStepsHistory, thinking, isThinking, approvalRequests, userChoiceRequests, configDiffReports, configAnalysisReports, reportFileDownloads, repairCommands, agentStepProgress } = msg;
    const visibleReportFileDownloads = Array.isArray(reportFileDownloads)
      ? reportFileDownloads.filter(download => Boolean(download.content_base64))
      : [];

    const replacedContent = parseSuggestionLinks(content || '');

    // Split content at placeholder markers and render components inline
    const renderContentWithInlineComponents = () => {
      if (!content) return null;

      // Check if content has inline markers
      const markerPattern = /<!--(CONFIG_DIFF|CONFIG_ANALYSIS|USER_CHOICE):([^>]+)-->/g;
      const hasMarkers = markerPattern.test(replacedContent);

      if (!hasMarkers) {
        // No markers — render as single block with fallback positions
        const html = hydrateGeneratedFileLinks(sanitizeHtml(md.render(replacedContent)), reportFileDownloads);
        return (
          <>
            <div
              dangerouslySetInnerHTML={{ __html: html }}
              className={styles.markdownBody}
              onClick={e => {
                handleToolCallClick(e);
                handleSuggestionClick(e);
              }}
            />
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
          const segHtml = hydrateGeneratedFileLinks(sanitizeHtml(md.render(segment)), reportFileDownloads);
          elements.push(
            <div
              key={`seg-${i}`}
              dangerouslySetInnerHTML={{ __html: segHtml }}
              className={styles.markdownBody}
              onClick={e => {
                handleToolCallClick(e);
                handleSuggestionClick(e);
              }}
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
              />
            ))}
          </div>
        );
      }

      return <>{elements}</>;
    };

    return (
      <>
        {images && images.length > 0 && (
          <div className="flex flex-wrap gap-2 mb-2">
            <Image.PreviewGroup>
              {images.map((img) => (
                <Image
                  key={img.id}
                  src={img.url}
                  alt={img.name || 'image'}
                  width={120}
                  height={120}
                  className="rounded object-cover"
                />
              ))}
            </Image.PreviewGroup>
          </div>
        )}
        <ThinkingPanel thinking={thinking} isThinking={isThinking} />
        {Array.isArray(agentStepProgress) && agentStepProgress.length > 0 && (
          <AgentStepProgress steps={agentStepProgress} />
        )}
        {browserStepsHistory && browserStepsHistory.steps.length > 0 && (
          <BrowserStepProgress history={browserStepsHistory} />
        )}
        {renderContentWithInlineComponents()}
        {!!msg.wikiCitations?.length && <WikiCitations citations={msg.wikiCitations} content={msg.content} />}
      </>
    );
  };

  const renderSend = (props: ButtonProps & { ignoreLoading?: boolean; placeholder?: string } = {}) => {
    const { ignoreLoading, placeholder, ...btnProps } = props;

    const uploadButton = (
      <Upload
        accept="image/*"
        fileList={[]}
        beforeUpload={(file) => {
          const isImage = file.type.startsWith('image/');
          if (!isImage) {
            antMessage.error(t('chat.onlyImageAllowed') || '只能上传图片文件');
            return Upload.LIST_IGNORE;
          }
          const isLt5M = file.size / 1024 / 1024 < 5;
          if (!isLt5M) {
            antMessage.error(t('chat.imageTooLarge') || '图片大小不能超过 5MB');
            return Upload.LIST_IGNORE;
          }
          setImageList(prev => [...prev, {
            uid: file.uid,
            name: file.name,
            status: 'done',
            originFileObj: file
          } as any]);
          return Upload.LIST_IGNORE;
        }}
        showUploadList={false}
      >
        <Button
          type="text"
          icon={<PictureOutlined />}
          disabled={loading}
          title={t('chat.uploadImage') || '上传图片'}
        />
      </Upload>
    );

    const senderComponent = (
      <div className="relative">
        {imageList.length > 0 && (
          <div className="flex flex-wrap gap-2 mb-2 p-2 bg-gray-50 rounded">
            {imageList.map((file) => {
              const previewUrl = file.originFileObj && typeof window !== 'undefined'
                ? URL.createObjectURL(file.originFileObj)
                : '';

              return (
                <div key={file.uid} className="relative group">
                  {previewUrl && (
                    <img
                      src={previewUrl}
                      alt={file.name}
                      className="w-16 h-16 object-cover rounded"
                    />
                  )}
                  <Button
                    type="text"
                    danger
                    size="small"
                    className="absolute top-0 right-0 opacity-0 group-hover:opacity-100 transition-opacity"
                    onClick={() => setImageList(imageList.filter(item => item.uid !== file.uid))}
                  >
                    ×
                  </Button>
                </div>
              );
            })}
          </div>
        )}
        <Sender
          className={styles.sender}
          value={value}
          onChange={setValue}
          loading={loading && !pendingChoice}
          onSubmit={(msg: string) => {
            setValue('');
            const currentImages = [...imageList];
            setImageList([]);
            handleSend(msg, currentImages);
          }}
          placeholder={pendingChoice ? (t('chat.replyToPendingChoice') || '回复上面的问题…') : placeholder}
          onCancel={stopSSEConnection}
          prefix={uploadButton}
          onPaste={(event: React.ClipboardEvent) => {
            const items = event.clipboardData?.items;
            if (!items) return;

            for (let i = 0; i < items.length; i++) {
              const item = items[i];
              if (item.type.startsWith('image/')) {
                event.preventDefault();
                const file = item.getAsFile();
                if (file) {
                  const isLt5M = file.size / 1024 / 1024 < 5;
                  if (!isLt5M) {
                    antMessage.error(t('chat.imageTooLarge') || '图片大小不能超过 5MB');
                    continue;
                  }
                  setImageList(prev => [...prev, {
                    uid: `paste-${Date.now()}-${i}`,
                    name: file.name || `pasted-image-${Date.now()}.png`,
                    status: 'done',
                    originFileObj: file
                  } as any]);
                }
              }
            }
          }}
          actions={(
            _: any,
            info: {
              components: {
                SendButton: React.ComponentType<ButtonProps>;
                LoadingButton: React.ComponentType<ButtonProps>;
              };
            }
          ) => {
            const { SendButton, LoadingButton } = info.components;
            if (!ignoreLoading && loading) {
              return (
                <Tooltip title={t('chat.clickCancel')}>
                  <LoadingButton />
                </Tooltip>
              );
            }
            let node: ReactNode = <SendButton {...btnProps} />;
            if (!ignoreLoading) {
              node = (
                <Tooltip title={value || imageList.length > 0 ? `${t('chat.send')}\u21B5` : t('chat.inputMessage')}>
                  {node}
                </Tooltip>
              );
            }
            return node;
          }}
        />
      </div>
    );

    return requirePermission ? (
      <PermissionWrapper requiredPermissions={['Test']}>
        {senderComponent}
      </PermissionWrapper>
    ) : senderComponent;
  };

  useEffect(() => {
    return () => {
      stopSSEConnection();
    };
  }, [stopSSEConnection]);

  const guideData = parseGuideItems(guide || '');

  return (
    <div className={`rounded-lg h-full ${isFullscreen ? styles.fullscreen : ''}`}>
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
        className={`flex flex-col rounded-lg p-4 h-full overflow-hidden ${styles.chatContainer}`}
        style={{
          height: isFullscreen ? 'calc(100vh - 70px)' : mode === 'chat' ? (showHeader ? 'calc(100% - 40px)' : '100%') : '100%'
        }}
      >
        <div ref={chatContentRef} className="flex-1 chat-content-wrapper overflow-y-auto overflow-x-hidden pb-4">
          {guide && guideData.renderedHtml && (
            <div className="mb-4 flex items-start gap-3" onClick={handleGuideClick}>
              <div className="flex-shrink-0 mt-1">
                <Icon type="jiqiren3" className={styles.guideAvatar} />
              </div>
              <div
                dangerouslySetInnerHTML={{ __html: guideData.renderedHtml }}
                className={`${styles.markdownBody} flex-1 p-3 bg-[var(--color-bg)] rounded-lg`}
              />
            </div>
          )}
          <Flex gap="small" vertical>
            {messages.map(msg => {
              const hasBrowserSteps = msg.browserStepsHistory && msg.browserStepsHistory.steps.length > 0;
              const hasThinking = Boolean(normalizeThinkingText(msg.thinking)) || Boolean(msg.isThinking);
              const isEmptyMessage = !msg.content && !hasBrowserSteps && !hasThinking;
              const isCurrentBotLoading = loading && currentBotMessageRef.current?.id === msg.id;
              return (
                <Bubble
                  key={msg.id}
                  className={styles.bubbleWrapper}
                  placement={msg.role === 'user' ? 'end' : 'start'}
                  loading={isEmptyMessage && isCurrentBotLoading}
                  content={renderContent(msg)}
                  avatar={{
                    icon: (
                      <Icon
                        type={msg.role === 'user' ? 'yonghu' : 'jiqiren3'}
                        className={styles.avatar}
                      />
                    )
                  }}
                  footer={
                    isCurrentBotLoading ? null : (
                      <MessageActions
                        message={msg}
                        onCopy={handleCopyMessage}
                        onRegenerate={handleRegenerateMessage}
                        onDelete={handleDeleteMessage}
                      />
                    )
                  }
                />
              );
            })}
          </Flex>
        </div>

        {mode === 'chat' && (
          <div className="flex-shrink-0">
            <div className="flex justify-end pb-2">
              <Popconfirm
                title={t('chat.clearConfirm')}
                okButtonProps={{ danger: true }}
                onConfirm={handleClearMessages}
                okText={t('chat.clear')}
                cancelText={t('common.cancel')}
                getPopupContainer={(trigger) => trigger.parentElement || document.body}
              >
                <Button type="text" className="mr-2" icon={<Icon type="shanchu" className="text-2xl" />} />
              </Popconfirm>
            </div>
            <Flex vertical gap="middle">
              {renderSend({
                variant: 'text',
                placeholder: `${t('chat.inputPlaceholder')}`,
                color: 'primary',
                icon: <SendOutlined />,
                shape: 'default',
              })}
            </Flex>
          </div>
        )}
      </div>
    </div>
  );
};

export default CustomChatSSE;
