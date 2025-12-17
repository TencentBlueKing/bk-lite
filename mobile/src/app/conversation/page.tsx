'use client';

import React, { useState, useEffect, useRef, useMemo } from 'react';
import { Flex } from 'antd';
import { Toast, SpinLoading, ImageViewer } from 'antd-mobile';
import { useRouter, useSearchParams } from 'next/navigation';
import { ChatInfo } from '@/types/conversation';
import MarkdownIt from 'markdown-it';
import { ConversationHeader, MessageList, CustomInput, MessageContent } from './components';
import { useMessages } from './hooks';
import { conversationStyles, parseHistoryEvents } from './utils';
import { useTranslation } from '@/utils/i18n';
import { getApplication, getSessionMessages, getWelcomeMessage } from '@/api/bot';
import { getAvatar } from '@/utils/avatar';
import { MessageContentItem } from '@/types/conversation';

// localStorage key 用于存储用户最后打开的对话页
const LAST_CONVERSATION_KEY = 'bk_lite_last_conversation';

export default function ConversationDetail() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const botId = searchParams?.get('bot_id');
  const sessionId = searchParams?.get('session_id');
  const { t } = useTranslation();

  const [chatInfo, setChatInfo] = useState<ChatInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [content, setContent] = useState('');
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const [isVoiceMode, setIsVoiceMode] = useState(false);
  const [imageViewerVisible, setImageViewerVisible] = useState(false);
  const [currentImage, setCurrentImage] = useState<string>('');

  // 应用详情状态（包含 bot 和 node_id）
  const [appDetail, setAppDetail] = useState<{ bot: number; nodeId: string } | null>(null);

  // 打开图片查看器
  const handleImageClick = (imageUrl: string) => {
    setCurrentImage(imageUrl);
    setImageViewerVisible(true);
  };

  // 生成或获取 sessionId
  const currentSessionId = useMemo(() => {
    if (sessionId) {
      return sessionId;
    }
    // 如果 URL 没有 sessionId，使用时间戳生成一个
    const now = new Date();
    const dateStr = now.toISOString().slice(0, 10).replace(/-/g, '');
    const timestamp = now.getTime();
    return `session-${dateStr}-${timestamp}`;
  }, [sessionId]);

  // 使用消息管理 hook，传入国际化的错误消息和应用配置
  const {
    messages,
    setMessages,
    handleSendMessage: sendMessage,
    triggerAIResponse,
    thinkingExpanded,
    setThinkingExpanded,
    thinkingTypingText,
    messageMarkdownRef,
    scrollToBottom,
    isAIRunning,
  } = useMessages(scrollContainerRef, {
    errorMessage: t('chat.responseError'),
    bot: appDetail?.bot,
    nodeId: appDetail?.nodeId,
    sessionId: currentSessionId,
  });

  // 初始化 markdown-it
  const md = useMemo(() => {
    return new MarkdownIt({
      html: true,
      linkify: true,
      typographer: true,
      breaks: true,
    });
  }, []);

  // Markdown 渲染函数
  const renderMarkdown = (text: string) => {
    const html = md.render(text);
    return <div dangerouslySetInnerHTML={{ __html: html }} className="markdown-body" />;
  };

  // 包装发送消息函数
  const handleSendMessage = (message: string | MessageContent) => {
    // 如果是字符串，直接发送文本
    if (typeof message === 'string') {
      sendMessage(message, renderMarkdown);
      return;
    }

    // 如果是文件消息
    if (message.type === 'files') {
      const { files, fileType, text, base64Data } = message;

      const timestamp = Date.now();

      // 创建图片/文件预览组件 - 横向排列，可滚动
      let filePreview: React.ReactNode;

      if (fileType === 'image') {
        // 图片类型：横向排列，可滚动
        filePreview = (
          <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-hide" style={{ maxWidth: '100%' }}>
            {files.map((file, index) => {
              const url = URL.createObjectURL(file);
              return (
                <div
                  key={index}
                  className="flex-shrink-0 cursor-pointer"
                  style={{ width: '80px', height: '80px' }}
                  onClick={() => handleImageClick(url)}
                >
                  <img
                    src={url}
                    alt={file.name}
                    className="w-full h-full rounded-lg object-cover"
                  />
                </div>
              );
            })}
          </div>
        );
      } else {
        // 文件类型：横向排列，显示文件卡片
        filePreview = (
          <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-hide" style={{ maxWidth: '100%' }}>
            {files.map((file, index) => {
              const size = (file.size / 1024).toFixed(2);
              return (
                <div
                  key={index}
                  className="flex-shrink-0 flex flex-col items-center justify-center p-3 rounded-lg"
                  style={{
                    width: '100px',
                    height: '100px',
                    backgroundColor: 'var(--color-fill-2)',
                    border: '1px solid var(--color-border)'
                  }}
                >
                  <span className="text-4xl mb-2">📎</span>
                  <span className="text-[var(--color-text-1)] text-xs text-center truncate w-full px-1">
                    {file.name}
                  </span>
                  <span className="text-[var(--color-text-3)] text-xs mt-1">
                    {size} KB
                  </span>
                </div>
              );
            })}
          </div>
        );
      }

      // 先添加图片/文件消息（无背景、无边框样式）
      const fileMsgId = `user-file-${timestamp}`;
      setMessages((prev) => [
        ...prev,
        {
          id: fileMsgId,
          message: filePreview,
          status: 'local' as const,
          timestamp: timestamp,
          isFileMessage: true, // 标记为文件消息，用于特殊样式处理
        }
      ]);

      // 如果有文字，添加文字消息（正常气泡样式）
      if (text) {
        const textMsgId = `user-text-${timestamp}`;
        setMessages((prev) => [
          ...prev,
          {
            id: textMsgId,
            message: text,
            status: 'local' as const,
            timestamp: timestamp + 1, // 稍微延后，确保顺序
          }
        ]);
      }

      const formattedData: MessageContentItem[] = [];

      // 添加文件数据
      base64Data.forEach((base64) => {
        if (fileType === 'image') {
          formattedData.push({
            type: 'image_url',
            image_url: base64
          });
        } else {
          formattedData.push({
            type: 'file_url',
            file_url: base64
          });
        }
      });

      // 如果有文本消息，添加到最后
      if (text) {
        formattedData.push({
          type: 'message',
          message: text
        });
      }

      // 使用 triggerAIResponse 触发 AI 响应，直接传递数组格式
      triggerAIResponse(formattedData, renderMarkdown);
    }
  };

  // 点击推荐内容
  const handleRecommendationClick = (text: string) => {
    handleSendMessage(text);
  };

  // 语音相关处理函数
  const toggleVoiceMode = () => {
    setIsVoiceMode(!isVoiceMode);
    setContent('');
  };

  const handleActionClick = (
    key: string,
    messageId?: string
  ) => {
    switch (key) {
      case 'copy':
        let textContent = '';
        if (messageId && messageMarkdownRef.current.has(messageId)) {
          textContent = messageMarkdownRef.current.get(messageId) || '';
        }
        navigator.clipboard.writeText(textContent);
        Toast.show({ content: t('common.copiedToClipboard'), icon: 'success' });
        break;
      case 'regenerate':
        // 找到对应的 AI 消息，获取 userInput
        if (messageId) {
          const targetMessage = messages.find(msg => msg.id === messageId);
          if (targetMessage && targetMessage.userInput) {
            triggerAIResponse(targetMessage.userInput, renderMarkdown);
          }
        }
        break;
    }
  };

  // 获取引导语
  const fetchWelcomeMessage = async (bot_id: number, node_id: string) => {
    try {
      const response = await getWelcomeMessage(bot_id, node_id);
      if (!response.result) {
        throw new Error(response.message || 'getWelcomeMessage failed');
      }
      const guide = response.data.guide || t('chat.welcomeMessage');
      const [guideText, ...suggestions] = guide.split('\n').filter((line: string) => line.trim() !== '');
      const welcomeMessage = {
        id: 'welcome-message',
        message: {
          text: guideText,
          suggestions: suggestions.length > 0 ? suggestions.map((line: string) => {
            if (line.startsWith('[') && line.endsWith(']')) {
              return line.slice(1, -1);
            }
            return line;
          }) : []
        },
        status: 'ai' as const,
        timestamp: Date.now(),
        isWelcome: true,
      };
      setMessages((prev) => {
        if (prev.length > 0) {
          return [...prev, welcomeMessage];
        } else {
          return [welcomeMessage];
        }
      });

    } catch (error) {
      console.error('getWelcomeMessage error:', error);
    }
  }

  // 加载历史对话
  const loadHistoryMessages = async (sessionId: string, bot_id: number, node_id: string) => {
    try {
      const historyResponse = await getSessionMessages(sessionId);
      if (historyResponse.result && historyResponse.data) {
        if (historyResponse.data.length > 0) {
          const historyMessages: any[] = [];

          historyResponse.data.forEach((msg: any) => {
            const msgId = `history-${msg.id}`;
            const timestamp = new Date(msg.conversation_time).getTime();

            // 处理 Bot 消息
            if (msg.conversation_role === 'bot') {
              const content = msg.conversation_content;

              // 判断是否为新格式的事件流（以 [{ 开头）
              const trimmed = content.trim();
              if ((trimmed.startsWith('[{') || trimmed.startsWith("['")) && trimmed.endsWith(']')) {
                // 解析事件流格式
                const parsed = parseHistoryEvents(content);

                // 保存完整的原始文本用于复制功能
                messageMarkdownRef.current.set(msgId, parsed.fullTextContent);

                // 将 contentParts 转换为渲染后的格式
                const renderedContentParts = parsed.contentParts.map(part => {
                  if (part.type === 'text' && part.textContent) {
                    // 渲染 markdown
                    return {
                      type: 'text' as const,
                      content: renderMarkdown(part.textContent),
                      segmentIndex: part.segmentIndex,
                    };
                  } else if (part.type === 'tool_call' && part.toolCall) {
                    return {
                      type: 'tool_call' as const,
                      toolCall: part.toolCall,
                    };
                  } else if (part.type === 'component' && part.component) {
                    return {
                      type: 'component' as const,
                      component: part.component,
                    };
                  }
                  return part;
                });

                // 构建历史消息对象
                const historyMessage: any = {
                  id: msgId,
                  message: null, // 使用 contentParts 渲染，不需要 message 字段
                  status: 'history' as const,
                  timestamp: timestamp,
                  contentParts: renderedContentParts,
                };

                // 如果有思考过程，添加到消息中
                if (parsed.thinking) {
                  historyMessage.thinking = parsed.thinking;
                }

                historyMessages.push(historyMessage);
              } else {
                // 旧格式：直接当作文本处理
                messageMarkdownRef.current.set(msgId, content);
                historyMessages.push({
                  id: msgId,
                  message: renderMarkdown(content),
                  status: 'history' as const,
                  timestamp: timestamp,
                });
              }
            }
            // 处理用户消息
            else if (msg.conversation_role === 'user') {
              const content = msg.conversation_content;
              const trimmed = content.trim();
              // 判断是否为数组格式的 JSON 字符串
              if (trimmed.startsWith('[') && trimmed.endsWith(']')) {
                try {
                  // 将单引号替换为双引号，以兼容 Python 风格的字符串
                  const jsonString = trimmed.replace(/'/g, '"');
                  const parsedContent = JSON.parse(jsonString);
                  if (Array.isArray(parsedContent)) {
                    // 分离图片/文件和文本消息
                    const images: string[] = [];
                    const files: string[] = [];
                    let textMessage = '';

                    parsedContent.forEach((item: any) => {
                      if (item.type === 'image_url' && item.image_url) {
                        images.push(item.image_url);
                      } else if (item.type === 'file_url' && item.file_url) {
                        files.push(item.file_url);
                      } else if (item.type === 'message' && item.message) {
                        textMessage = item.message;
                      }
                    });

                    // 先添加图片消息（如果有）
                    if (images.length > 0) {
                      const imagePreview = (
                        <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-hide" style={{ maxWidth: '100%' }}>
                          {images.map((base64, index) => (
                            <div
                              key={index}
                              className="flex-shrink-0 cursor-pointer"
                              style={{ width: '80px', height: '80px' }}
                              onClick={() => handleImageClick(base64)}
                            >
                              <img
                                src={base64}
                                alt={`image-${index}`}
                                className="w-full h-full rounded-lg object-cover"
                              />
                            </div>
                          ))}
                        </div>
                      );

                      historyMessages.push({
                        id: `${msgId}-images`,
                        message: imagePreview,
                        status: 'local' as const,
                        timestamp: timestamp,
                        isFileMessage: true,
                      });
                    }

                    // 添加文件消息（如果有）
                    if (files.length > 0) {
                      const filePreview = (
                        <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-hide" style={{ maxWidth: '100%' }}>
                          {files.map((base64, index) => (
                            <div
                              key={index}
                              className="flex-shrink-0 flex flex-col items-center justify-center p-3 rounded-lg"
                              style={{
                                width: '100px',
                                height: '100px',
                                backgroundColor: 'var(--color-fill-2)',
                                border: '1px solid var(--color-border)'
                              }}
                            >
                              <span className="text-4xl mb-2">📎</span>
                              <span className="text-[var(--color-text-3)] text-xs">
                                文件
                              </span>
                            </div>
                          ))}
                        </div>
                      );

                      historyMessages.push({
                        id: `${msgId}-files`,
                        message: filePreview,
                        status: 'local' as const,
                        timestamp: timestamp,
                        isFileMessage: true,
                      });
                    }

                    // 添加文本消息（如果有）
                    if (textMessage) {
                      historyMessages.push({
                        id: `${msgId}-text`,
                        message: textMessage,
                        status: 'local' as const,
                        timestamp: timestamp + 1,
                      });
                    }
                  } else {
                    // 解析成功但不是数组，当普通文本处理
                    historyMessages.push({
                      id: msgId,
                      message: content,
                      status: 'local' as const,
                      timestamp: timestamp,
                    });
                  }
                } catch (parseError) {
                  console.error('JSON parsing failed:', parseError);
                  // JSON 解析失败，当普通文本处理
                  historyMessages.push({
                    id: msgId,
                    message: content,
                    status: 'local' as const,
                    timestamp: timestamp,
                  });
                }
              } else {
                // 普通文本消息
                historyMessages.push({
                  id: msgId,
                  message: content,
                  status: 'local' as const,
                  timestamp: timestamp,
                });
              }
            }
          });

          setMessages(historyMessages);

          // 检查最后一条消息的时间，如果超过24小时就获取引导语
          const lastMessage = historyResponse.data[historyResponse.data.length - 1];
          const lastMessageTime = new Date(lastMessage.conversation_time).getTime();
          const currentTime = Date.now();
          const timeDiff = currentTime - lastMessageTime;
          const hours24 = 24 * 60 * 60 * 1000;
          if (timeDiff >= hours24) {
            // 超过24小时，获取引导语
            await fetchWelcomeMessage(bot_id, node_id);
          }
        } else {
          // 没有历史消息，获取引导语
          await fetchWelcomeMessage(bot_id, node_id);
        }
      }
    } catch (Error) {
      console.error('loadHistoryMessages error:', Error);
    }
  }

  // 加载聊天信息和应用详情
  useEffect(() => {
    if (!botId) {
      router.replace('/conversations');
      return;
    }

    const fetchChatData = async () => {
      setLoading(true);
      try {
        // 获取应用详情
        const response = await getApplication({ bot: Number(botId) });
        if (!response.result) {
          throw new Error(t('chat.loadChatDataFailed'));
        }
        const data = response.data[0];
        setAppDetail({
          bot: data.bot,
          nodeId: data.node_id,
        });
        setChatInfo({
          id: botId,
          name: data.app_name,
          avatar: getAvatar(data.id),
        });

        // 如果 URL 中有 sessionId，加载历史对话
        if (sessionId) {
          await loadHistoryMessages(sessionId, data.bot, data.node_id);
        } else {
          await fetchWelcomeMessage(data.bot, data.node_id);
        }
      } catch (error) {
        console.error(error);
      } finally {
        setLoading(false);
        scrollToBottom();
      }
    };

    fetchChatData();
  }, [botId, router, sessionId]);

  // 保存当前对话信息到 localStorage
  useEffect(() => {
    if (botId && currentSessionId) {
      const lastConversation = {
        botId,
        sessionId: currentSessionId,
      };
      localStorage.setItem(LAST_CONVERSATION_KEY, JSON.stringify(lastConversation));
    }
  }, [botId, currentSessionId]);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-screen bg-[var(--color-background-body)]">
        <SpinLoading color="primary" />
      </div>
    );
  }

  if (!chatInfo) {
    return (
      <div className="flex flex-col items-center justify-center h-screen bg-[var(--color-background-body)]">
        <div className="text-[var(--color-text-3)] text-lg">{t('chat.loadChatDataFailed')}</div>
        <button
          onClick={() => router.replace('/conversations')}
          className="mt-4 px-6 py-2 bg-blue-500 text-white rounded-lg"
        >
          {t('common.back')}
        </button>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full bg-[var(--color-bg)]">
      <ConversationHeader chatInfo={chatInfo} />

      <div className="flex-1 bg-[var(--color-background-body)] overflow-hidden">
        <Flex vertical style={{ height: '100%', padding: '16px 0 16px 8px' }}>
          <div
            ref={scrollContainerRef}
            style={{
              flex: 1,
              overflow: 'auto',
              paddingBottom: '8px',
              paddingRight: '8px',
            }}
            className="custom-scrollbar"
          >
            <style dangerouslySetInnerHTML={{ __html: conversationStyles }} />

            <MessageList
              messages={messages}
              router={router}
              thinkingExpanded={thinkingExpanded}
              setThinkingExpanded={setThinkingExpanded}
              thinkingTypingText={thinkingTypingText}
              renderMarkdown={renderMarkdown}
              onActionClick={handleActionClick}
              onRecommendationClick={handleRecommendationClick}
              onFormSubmit={handleSendMessage}
            />
          </div>

          <CustomInput
            content={content}
            setContent={setContent}
            isVoiceMode={isVoiceMode}
            onSend={handleSendMessage}
            onToggleVoiceMode={() => toggleVoiceMode()}
            isAIRunning={isAIRunning}
          />
        </Flex>
      </div>

      <ImageViewer
        image={currentImage}
        visible={imageViewerVisible}
        onClose={() => setImageViewerVisible(false)}
      />
    </div>
  );
}