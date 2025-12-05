import React, { useState, useCallback, useRef, ReactNode, useEffect } from 'react';
import { Popconfirm, Button, Tooltip, Flex, Spin, Drawer, ButtonProps } from 'antd';
import { FullscreenOutlined, FullscreenExitOutlined, SendOutlined } from '@ant-design/icons';
import { Bubble, Sender } from '@ant-design/x';
import Icon from '@/components/icon';
import { useTranslation } from '@/utils/i18n';
import MarkdownIt from 'markdown-it';
import hljs from 'highlight.js';
import 'highlight.js/styles/atom-one-dark.css';
import styles from '../custom-chat/index.module.scss';
import MessageActions from '../custom-chat/actions';
import KnowledgeBase from '../custom-chat/knowledgeBase';
import AnnotationModal from '../custom-chat/annotationModal';
import KnowledgeGraphView from '../knowledge/knowledgeGraphView';
import PermissionWrapper from '@/components/permission';
import { CustomChatMessage, Annotation } from '@/app/opspilot/types/global';
import { useSession } from 'next-auth/react';
import { useAuth } from '@/context/auth';
import { CustomChatSSEProps, GuideParseResult } from '@/app/opspilot/types/chat';
import { useSSEStream } from './hooks/useSSEStream';
import { useSendMessage } from './hooks/useSendMessage';
import { useReferenceHandler } from './hooks/useReferenceHandler';

const md = new MarkdownIt({
  html: true,
  highlight: function (str: string, lang: string) {
    if (lang && hljs.getLanguage(lang)) {
      try {
        return hljs.highlight(str, { language: lang }).value;
      } catch {}
    }
    return '';
  },
});

const CustomChatSSE: React.FC<CustomChatSSEProps> = ({
  handleSendMessage,
  showMarkOnly = false,
  initialMessages = [],
  mode = 'chat',
  guide,
  useAGUIProtocol = false,
  showHeader = true,
  requirePermission = true
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
  const token = session?.user?.token || authContext?.token || null;

  const [isFullscreen, setIsFullscreen] = useState(false);
  const [value, setValue] = useState('');
  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState<CustomChatMessage[]>(
    initialMessages.length ? initialMessages : []
  );
  const [annotationModalVisible, setAnnotationModalVisible] = useState(false);
  const [annotation, setAnnotation] = useState<Annotation | null>(null);
  const currentBotMessageRef = useRef<CustomChatMessage | null>(null);
  const chatContentRef = useRef<HTMLDivElement>(null);

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
  const { handleSSEStream, stopSSEConnection } = useSSEStream({
    token,
    useAGUIProtocol,
    updateMessages,
    setLoading,
    t
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

  const { referenceModal, drawerContent, handleReferenceClick, closeDrawer } =
    useReferenceHandler(t);

  // Parse guide
  const parseGuideItems = useCallback((guideText: string): GuideParseResult => {
    if (!guideText) return { text: '', items: [], renderedHtml: '' };

    const regex = /\[([^\]]+)\]/g;
    const items: string[] = [];
    let match;

    while ((match = regex.exec(guideText)) !== null) {
      items.push(match[1]);
    }

    const processedText = guideText.replace(/\n/g, '<br>');
    const renderedHtml = processedText.replace(regex, (match, content) => {
      return `<span class="guide-clickable-item" data-content="${content}" style="color: #1890ff; cursor: pointer; font-weight: 600; margin: 0 2px;">${content}</span>`;
    });

    return { text: guideText, items, renderedHtml };
  }, []);

  // Parse links
  const parseReferenceLinks = useCallback((content: string) => {
    const referenceRegex = /\[\[(\d+)\]\]\(([^)]+)\)/g;
    return content.replace(referenceRegex, (match, refNumber, params) => {
      const paramPairs = params.split('|');
      const urlParams = new Map();

      paramPairs.forEach((pair: string) => {
        const [key, value] = pair.split(':');
        if (key && value) urlParams.set(key, value);
      });

      const chunkId = urlParams.get('chunk_id');
      const knowledgeId = urlParams.get('knowledge_id');
      const chunkType = urlParams.get('chunk_type') || 'Document';
      const iconType =
        chunkType === 'QA'
          ? 'wendaduihua'
          : chunkType === 'Graph'
            ? 'zhishitupu'
            : 'wendangguanlixitong-wendangguanlixitongtubiao';

      return `<span class="reference-link inline-flex items-center gap-1" 
                data-ref-number="${refNumber}" 
                data-chunk-id="${chunkId}" 
                data-knowledge-id="${knowledgeId}"
                data-chunk-type="${chunkType}"
                style="color: #1890ff; cursor: pointer; margin: 0 2px;">
                <svg class="icon icon-${iconType} inline-block" style="width: 1em; height: 1em; vertical-align: text-bottom;" aria-hidden="true">
                  <use href="#icon-${iconType}"></use>
                </svg>
              </span>`;
    });
  }, []);

  const parseSuggestionLinks = useCallback((content: string) => {
    const suggestionRegex = /\[(\d+)\]\(suggest:\s*([^)]+)\)/g;
    return content.replace(suggestionRegex, (match, number, suggestionText) => {
      const trimmedText = suggestionText.trim();
      return `<button class="suggestion-button inline-block text-[var(--color-text-1)] text-left border border-[var(--color-border-1)] rounded-full px-3 py-1.5 mx-1 my-1 cursor-pointer text-xs transition-all duration-200 ease-in-out hover:shadow-md hover:-translate-y-0.5 hover:border-blue-400 active:scale-95" 
                data-suggestion="${trimmedText}">
                ${trimmedText}
              </button>`;
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

  const handleFullscreenToggle = () => setIsFullscreen(!isFullscreen);

  const handleClearMessages = () => {
    stopSSEConnection();
    updateMessages([]);
    currentBotMessageRef.current = null;
  };

  const handleSend = useCallback(
    async (msg: string) => {
      if (msg.trim() && !loading && token) {
        currentBotMessageRef.current = null;
        await sendMessage(msg);
      }
    },
    [loading, token, sendMessage]
  );

  const handleCopyMessage = (content: string) => {
    navigator.clipboard.writeText(content).then(
      () => console.log(t('chat.copied')),
      err => console.error(`${t('chat.copyFailed')}:`, err)
    );
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

  const renderContent = (msg: CustomChatMessage) => {
    const { content, knowledgeBase } = msg;
    const parsedContent = parseReferenceLinks(content || '');
    const parsedSuggestionContent = parseSuggestionLinks(parsedContent);

    return (
      <>
        <div
          dangerouslySetInnerHTML={{ __html: md.render(parsedSuggestionContent) }}
          className={styles.markdownBody}
          onClick={e => {
            handleReferenceClick(e);
            handleSuggestionClick(e);
          }}
        />
        {Array.isArray(knowledgeBase) && knowledgeBase.length ? (
          <KnowledgeBase knowledgeList={knowledgeBase} />
        ) : null}
      </>
    );
  };

  const renderSend = (props: ButtonProps & { ignoreLoading?: boolean; placeholder?: string } = {}) => {
    const { ignoreLoading, placeholder, ...btnProps } = props;

    const senderComponent = (
      <Sender
        className={styles.sender}
        value={value}
        onChange={setValue}
        loading={loading}
        onSubmit={(msg: string) => {
          setValue('');
          handleSend(msg);
        }}
        placeholder={placeholder}
        onCancel={stopSSEConnection}
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
              <Tooltip title={value ? `${t('chat.send')}\u21B5` : t('chat.inputMessage')}>
                {node}
              </Tooltip>
            );
          }
          return node;
        }}
      />
    );

    return requirePermission ? (
      <PermissionWrapper requiredPermissions={['Test']}>
        {senderComponent}
      </PermissionWrapper>
    ) : senderComponent;
  };

  const toggleAnnotationModal = (message: CustomChatMessage) => {
    if (message?.annotation) {
      setAnnotation(message.annotation);
    } else {
      const lastUserMessage = messages
        .slice(0, messages.indexOf(message))
        .reverse()
        .find(msg => msg.role === 'user') as CustomChatMessage;
      setAnnotation({
        answer: message,
        question: lastUserMessage,
        selectedKnowledgeBase: '',
        tagId: 0,
      });
    }
    setAnnotationModalVisible(!annotationModalVisible);
  };

  const updateMessagesAnnotation = (id: string | undefined, newAnnotation?: Annotation) => {
    if (!id) return;
    updateMessages(prevMessages =>
      prevMessages.map(msg => (msg.id === id ? { ...msg, annotation: newAnnotation } : msg))
    );
    setAnnotationModalVisible(false);
  };

  const handleSaveAnnotation = (annotation?: Annotation) => {
    updateMessagesAnnotation(annotation?.answer?.id, annotation);
  };

  const handleRemoveAnnotation = (id: string | undefined) => {
    if (!id) return;
    updateMessagesAnnotation(id, undefined);
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

        <div ref={chatContentRef} className="flex-1 chat-content-wrapper overflow-y-auto overflow-x-hidden pb-4">
          <Flex gap="small" vertical>
            {messages.map(msg => (
              <Bubble
                key={msg.id}
                className={styles.bubbleWrapper}
                placement={msg.role === 'user' ? 'end' : 'start'}
                loading={msg.content === '' && loading && currentBotMessageRef.current?.id === msg.id}
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
                  msg.content === '' && loading && currentBotMessageRef.current?.id === msg.id ? null : (
                    <MessageActions
                      message={msg}
                      onCopy={handleCopyMessage}
                      onRegenerate={handleRegenerateMessage}
                      onDelete={handleDeleteMessage}
                      onMark={toggleAnnotationModal}
                      showMarkOnly={showMarkOnly}
                    />
                  )
                }
              />
            ))}
          </Flex>
        </div>

        {mode === 'chat' && (
          <>
            <div className="flex justify-end pb-2">
              <Popconfirm
                title={t('chat.clearConfirm')}
                okButtonProps={{ danger: true }}
                onConfirm={handleClearMessages}
                okText={t('chat.clear')}
                cancelText={t('common.cancel')}
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
          </>
        )}
      </div>
      {annotation && (
        <AnnotationModal
          visible={annotationModalVisible}
          showMarkOnly={showMarkOnly}
          annotation={annotation}
          onSave={handleSaveAnnotation}
          onRemove={handleRemoveAnnotation}
          onCancel={() => setAnnotationModalVisible(false)}
        />
      )}

      <Drawer
        width={drawerContent.chunkType === 'Graph' ? 800 : 480}
        visible={drawerContent.visible}
        title={drawerContent.title}
        onClose={closeDrawer}
      >
        {referenceModal.loading ? (
          <div className="flex justify-center items-center h-32">
            <Spin size="large" />
          </div>
        ) : (
          <>
            {drawerContent.chunkType === 'Graph' ? (
              <KnowledgeGraphView data={drawerContent.graphData || { nodes: [], edges: [] }} height={500} />
            ) : (
              <div className="whitespace-pre-wrap leading-6">{drawerContent.content}</div>
            )}
          </>
        )}
      </Drawer>
    </div>
  );
};

export default CustomChatSSE;
