import React, { useState, useCallback, ReactNode } from 'react';
import { Popconfirm, Button, Tooltip, Flex, ButtonProps } from 'antd';
import { FullscreenOutlined, FullscreenExitOutlined, SendOutlined } from '@ant-design/icons';
import { Bubble, Sender } from '@ant-design/x';
import { v4 as uuidv4 } from 'uuid';
import Icon from '@/components/icon';
import { useTranslation } from '@/utils/i18n';
import MarkdownIt from 'markdown-it';
import hljs from 'highlight.js';
import 'highlight.js/styles/atom-one-dark.css';
import styles from './index.module.scss';
import MessageActions from './actions';
import KnowledgeBase from './knowledgeBase';
import AnnotationModal from './annotationModal';
import PermissionWrapper from '@/components/permission';
import { CustomChatMessage, Annotation } from '@/app/opspilot/types/global';


interface CustomChatProps {
  handleSendMessage?: (newMessages: CustomChatMessage[]) => Promise<CustomChatMessage[]>;
  showMarkOnly?: boolean;
  initialMessages?: CustomChatMessage[];
  mode?: 'preview' | 'chat';
}

// 定义 action 渲染器类型
type ActionRender = (_: any, info: { components: { SendButton: React.ComponentType<ButtonProps>; LoadingButton: React.ComponentType<ButtonProps>; }; }) => ReactNode;

const md = new MarkdownIt({
  highlight: function (str: string, lang: string) {
    if (lang && hljs.getLanguage(lang)) {
      try {
        return hljs.highlight(str, { language: lang }).value;
      } catch { }
    }
    return '';
  },
});

const CustomChat: React.FC<CustomChatProps> = ({ handleSendMessage, showMarkOnly = false, initialMessages = [], mode = 'chat' }) => {
  const { t } = useTranslation();
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [value, setValue] = useState('');
  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState<CustomChatMessage[]>(initialMessages.length ? initialMessages : []);
  const [annotationModalVisible, setAnnotationModalVisible] = useState(false);
  const [annotation, setAnnotation] = useState<Annotation | null>(null);

  const handleFullscreenToggle = () => {
    setIsFullscreen(!isFullscreen);
  };

  const handleClearMessages = () => {
    setMessages([]);
  };

  const handleSendComplete = useCallback((newMessages: CustomChatMessage[]) => {
    setMessages(newMessages);
    setLoading(false);
  }, []);

  const handleSend = useCallback(async (msg: string) => {
    if (msg.trim() && !loading) {
      setLoading(true);
      const newMessage: CustomChatMessage = {
        id: uuidv4(),
        content: msg,
        role: 'user',
        createAt: new Date().toISOString(),
        updateAt: new Date().toISOString(),
      };
      const botLoadingMessage: CustomChatMessage = {
        id: uuidv4(),
        content: '...',
        role: 'bot',
        createAt: new Date().toISOString(),
        updateAt: new Date().toISOString(),
      };
      const updatedMessages = [...messages, newMessage, botLoadingMessage];
      setMessages(updatedMessages);
      try {
        if (handleSendMessage) {
          const responseMessages = await handleSendMessage([...messages, newMessage]);
          handleSendComplete(responseMessages);
        }
      } catch (error) {
        console.error(`${t('chat.sendFailed')}:`, error);
        setMessages(messages);
        setLoading(false);
      }
    }
  }, [loading, handleSendMessage, messages, handleSendComplete]);

  const handleCopyMessage = (content: string) => {
    navigator.clipboard.writeText(content).then(() => {
      console.log(t('chat.copied'));
    }).catch(err => {
      console.error(`${t('chat.copyFailed')}:`, err);
    });
  };

  const handleDeleteMessage = (id: string) => {
    setMessages(messages.filter(msg => msg.id !== id));
  };

  const handleRegenerateMessage = useCallback(async (id: string) => {
    const messageToRegenerate = messages.find(msg => msg.id === id);
    if (messageToRegenerate) {
      const lastUserMessage = messages.filter(msg => msg.role === 'user').pop();
      if (lastUserMessage) {
        const newMessage: CustomChatMessage = {
          id: uuidv4(),
          content: '...',
          role: 'bot',
          createAt: new Date().toISOString(),
          updateAt: new Date().toISOString(),
        };

        const updatedMessages = [...messages, newMessage];
        setMessages(updatedMessages);
        setLoading(true);
        try {
          if (handleSendMessage) {
            const responseMessages = await handleSendMessage([...messages]);
            handleSendComplete(responseMessages);
          }
        } catch (error) {
          console.error(`${t('chat.regenerateFailed')}:`, error);
          setLoading(false);
        }
      }
    }
  }, [messages, handleSendMessage, handleSendComplete]);

  const renderContent = (msg: CustomChatMessage) => {
    const { content, knowledgeBase } = msg;
    return (
      <>
        <div
          dangerouslySetInnerHTML={{ __html: md.render(content) }}
          className={styles.markdownBody}
        />
        {(Array.isArray(knowledgeBase) && knowledgeBase.length) ? <KnowledgeBase knowledgeList={knowledgeBase} /> : null}
      </>
    );
  };

  const renderSend = (props: ButtonProps & { ignoreLoading?: boolean; placeholder?: string } = {}) => {
    const { ignoreLoading, placeholder, ...btnProps } = props;

    return (
      <PermissionWrapper
        requiredPermissions={['Test']}>
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
          onCancel={() => {
            setLoading(false);
          }}
          actions={((_: any, info: { components: { SendButton: React.ComponentType<ButtonProps>; LoadingButton: React.ComponentType<ButtonProps> } }) => {
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
                <Tooltip title={value ? `${t('chat.send')}\u21B5` : t('chat.inputMessage')}>{node}</Tooltip>
              );
            }
            return node;
          }) as ActionRender}
        />
      </PermissionWrapper>
    );
  };

  const toggleAnnotationModal = (message: CustomChatMessage) => {
    if (message?.annotation) {
      setAnnotation(message.annotation);
    } else {
      const lastUserMessage = messages.slice(0, messages.indexOf(message)).reverse().find(msg => msg.role === 'user') as CustomChatMessage;
      setAnnotation({
        answer: message,
        question: lastUserMessage,
        selectedKnowledgeBase: '',
        tagId: 0,
      })
    }
    setAnnotationModalVisible(!annotationModalVisible);
  };

  const updateMessagesAnnotation = (id: string | undefined, newAnnotation?: Annotation) => {
    if (!id) return;
    setMessages((prevMessages) =>
      prevMessages.map((msg) =>
        msg.id === id
          ? { ...msg, annotation: newAnnotation }
          : msg
      )
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

  return (
    <div className={`rounded-lg h-full ${isFullscreen ? styles.fullscreen : ''}`}>
      {mode === 'chat' &&
        <div className="flex justify-between items-center mb-3">
          <h2 className="text-base font-semibold">{t('chat.test')}</h2>
          <div>
            <button title="fullScreen" onClick={handleFullscreenToggle} aria-label="Toggle Fullscreen">
              {isFullscreen ? <FullscreenExitOutlined /> : <FullscreenOutlined />}
            </button>
          </div>
        </div>
      }
      <div className={`flex flex-col rounded-lg p-4 h-full overflow-hidden ${styles.chatContainer}`} style={{ height: isFullscreen ? 'calc(100vh - 70px)' : (mode === 'chat' ? 'calc(100% - 40px)' : '100%') }}>
        <div className="flex-1 chat-content-wrapper overflow-y-auto overflow-x-hidden pb-4">
          <Flex gap="small" vertical>
            {messages.map((msg) => (
              <Bubble
                key={msg.id}
                className={styles.bubbleWrapper}
                placement={msg.role === 'user' ? 'end' : 'start'}
                loading={msg.content === '...'}
                content={renderContent(msg)}
                avatar={{ icon: <Icon type={msg.role === 'user' ? 'yonghu' : 'jiqiren3'} className={styles.avatar} /> }}
                footer={msg.content === '...' ? null : (
                  <MessageActions
                    message={msg}
                    onCopy={handleCopyMessage}
                    onRegenerate={handleRegenerateMessage}
                    onDelete={handleDeleteMessage}
                    onMark={toggleAnnotationModal}
                    showMarkOnly={showMarkOnly}
                  />
                )}
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
    </div>
  );
};

export default CustomChat;
