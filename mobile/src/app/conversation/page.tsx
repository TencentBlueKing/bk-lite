'use client';

import React, { useState, useEffect, useRef, useMemo } from 'react';
import { Flex } from 'antd';
import { Toast, SpinLoading, ImageViewer } from 'antd-mobile';
import { useRouter, useSearchParams } from 'next/navigation';
import { ChatInfo } from '@/types/conversation';
import MarkdownIt from 'markdown-it';
import { ConversationHeader, ConversationSidebar, MessageList, CustomInput, MessageContent } from './components';
import { useMessages } from './hooks';
import { conversationStyles, parseHistoryEvents } from './utils';
import { useTranslation } from '@/utils/i18n';
import { getApplication, getSessionMessages, getWelcomeMessage } from '@/api/bot';
import { getAvatar } from '@/utils/avatar';
import { MessageContentItem } from '@/types/conversation';
import { useSessionsCache } from './hooks';
import { ExclamationTriangleOutline } from 'antd-mobile-icons';

// localStorage key 用于存储用户最后打开的对话页
const LAST_CONVERSATION_KEY = 'bk_lite_last_conversation';

export default function ConversationDetail() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const botId = searchParams?.get('bot_id') || '32';
  const sessionId = searchParams?.get('session_id');
  const timestamp = searchParams?.get('t'); // 获取时间戳参数用于触发刷新
  const { t } = useTranslation();

  const [chatInfo, setChatInfo] = useState<ChatInfo | null>(null);
  const [appLoading, setAppLoading] = useState(true);
  const [messagesLoading, setMessagesLoading] = useState(false);
  const [content, setContent] = useState('');
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const [isVoiceMode, setIsVoiceMode] = useState(false);
  const [imageViewerVisible, setImageViewerVisible] = useState(false);
  const [currentImage, setCurrentImage] = useState<string>('');
  const [sidebarVisible, setSidebarVisible] = useState(false);
  const [needRefreshSessions, setNeedRefreshSessions] = useState(false);
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const [isNewConversation, setIsNewConversation] = useState(false);
  const [appDetail, setAppDetail] = useState<{ bot: number; nodeId: string } | null>(null);

  // 使用对话缓存 hook
  const {
    cachedSessions,
    scrollPosition,
    isInitialized: cacheInitialized,
    hasFetched,
    updateSessionsCache,
    updateScrollPosition,
  } = useSessionsCache();

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
    const timestampValue = now.getTime();
    return `session-${dateStr}-${timestampValue}`;
  }, [sessionId, timestamp]);

  // 使用消息管理 hook，传入国际化的错误消息和应用配置
  const {
    messages,
    setMessages,
    handleSendMessage: sendMessage,
    triggerAIResponse,
    thinkingExpanded,
    setThinkingExpanded,
    thinkingTypingText,
    setThinkingTypingText,
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
    // 如果是新对话，用户发送第一条消息后，标记需要刷新侧边栏
    if (isNewConversation) {
      setNeedRefreshSessions(true);
      setIsNewConversation(false);
    }

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
  const fetchWelcomeMessage = async (bot_id: number, node_id: string, signal?: AbortSignal) => {
    try {
      const response = await getWelcomeMessage(bot_id, node_id, signal ? { signal } : undefined);

      if (signal?.aborted) {
        return;
      }

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

      // 再次检查是否被取消（防止在处理数据期间被取消）
      if (signal?.aborted) {
        return;
      }

      setMessages((prev) => {
        if (prev.length > 0) {
          return [...prev, welcomeMessage];
        } else {
          return [welcomeMessage];
        }
      });

      // 标记为新对话
      setIsNewConversation(true);

    } catch (error: any) {
      if (error.name === 'AbortError') {
        return;
      }
      console.error('getWelcomeMessage error:', error);
    }
  }

  // 加载历史对话
  const loadHistoryMessages = async (sessionId: string, bot_id: number, node_id: string, signal?: AbortSignal) => {
    try {
      const historyResponse = await getSessionMessages(sessionId, signal ? { signal } : undefined);

      if (signal?.aborted) {
        return;
      }

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

          // 再次检查是否被取消
          if (signal?.aborted) {
            return;
          }

          setMessages(historyMessages);

          // 检查最后一条消息的时间，如果超过24小时就获取引导语
          const lastMessage = historyResponse.data[historyResponse.data.length - 1];
          const lastMessageTime = new Date(lastMessage.conversation_time).getTime();
          const currentTime = Date.now();
          const timeDiff = currentTime - lastMessageTime;
          const hours24 = 24 * 60 * 60 * 1000;
          if (timeDiff >= hours24) {
            // 超过24小时，获取引导语
            if (!signal?.aborted) {
              await fetchWelcomeMessage(bot_id, node_id, signal);
            }
          }

          // 检查是否有用户消息，没有则标记为新对话
          const hasUserMessage = historyMessages.some(msg => msg.status === 'local');
          setIsNewConversation(!hasUserMessage);
        } else {
          // 没有历史消息，获取引导语
          if (!signal?.aborted) {
            await fetchWelcomeMessage(bot_id, node_id, signal);
          }
        }
      }
    } catch (error: any) {
      if (error.name === 'AbortError') {
        return;
      }
      console.error('loadHistoryMessages error:', error);
    }
  }

  // 获取应用详情
  useEffect(() => {
    const abortController = new AbortController();

    const fetchAppDetail = async () => {
      setAppLoading(true);
      try {
        const response = await getApplication(
          { bot: Number(botId) },
          { signal: abortController.signal }
        );

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
      } catch (error: any) {
        if (error.name === 'AbortError') {
          return;
        }
        console.error('Failed to load app detail:', error);
      } finally {
        if (!abortController.signal.aborted) {
          setAppLoading(false);
        }
      }
    };

    fetchAppDetail();

    // 清理函数：取消请求
    return () => {
      abortController.abort();
    };
  }, [botId]);

  // 加载消息
  useEffect(() => {
    // 等待应用详情加载完成
    if (!appDetail || appLoading) return;

    const abortController = new AbortController();

    const loadMessages = async () => {
      setMessagesLoading(true);

      // 清空之前的消息，确保新对话从空白开始
      setMessages([]);

      // 重置页面关键状态
      setContent('');  // 清空输入框
      setIsVoiceMode(false);  // 重置为文本模式
      setImageViewerVisible(false);  // 关闭图片查看器
      setCurrentImage('');  // 清空当前图片
      messageMarkdownRef.current.clear();  // 清空markdown缓存
      setThinkingExpanded({});  // 清空思考过程展开状态
      setThinkingTypingText({});  // 清空思考过程打字文本
      setIsNewConversation(false);  // 重置新对话标记
      setNeedRefreshSessions(false);  // 重置刷新标记

      try {
        // 如果 URL 中有 sessionId，加载历史对话
        if (sessionId) {
          await loadHistoryMessages(sessionId, appDetail.bot, appDetail.nodeId, abortController.signal);
        } else {
          await fetchWelcomeMessage(appDetail.bot, appDetail.nodeId, abortController.signal);
        }
      } catch (error: any) {
        if (error.name === 'AbortError') {
          return;
        }
        console.error('Failed to load messages:', error);
      } finally {
        if (!abortController.signal.aborted) {
          setMessagesLoading(false);
          scrollToBottom();
        }
      }
    };

    loadMessages();

    // 清理函数：取消请求
    return () => {
      abortController.abort();
    };
  }, [sessionId, timestamp, appDetail?.bot, appDetail?.nodeId]);

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

  // 如果应用详情加载失败，显示错误页面
  if (!appLoading && !chatInfo) {
    return (
      <div className="flex flex-col items-center justify-center h-screen bg-[var(--color-background-body)] px-6">
        <ExclamationTriangleOutline className="text-amber-400 text-7xl mb-2" />

        <div className="text-[var(--color-text-1)] text-xl font-medium mb-2">
          {t('chat.loadChatDataFailed')}
        </div>

        <div className="text-[var(--color-text-3)] text-sm text-center mb-8 max-w-sm">
          {t('chat.loadFailedDescription')}
        </div>

        <div className="flex flex-col gap-3 w-full max-w-xs">
          <button
            onClick={() => window.location.reload()}
            className="w-full px-6 py-3 bg-[var(--adm-color-primary)] text-white rounded-lg font-medium hover:opacity-90 transition-opacity"
          >
            {t('common.retry')}
          </button>

          <button
            onClick={() => router.replace('/workbench')}
            className="w-full px-6 py-3 bg-[var(--color-fill-4)] text-[var(--color-text-1)] rounded-lg font-medium hover:bg-[var(--color-fill-4)] transition-colors"
          >
            {t('chat.backToAppList')}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full bg-[var(--color-bg)]">
      <ConversationHeader
        chatInfo={chatInfo}
        onMenuClick={() => setSidebarVisible(true)}
        loading={appLoading}
      />

      <ConversationSidebar
        visible={sidebarVisible}
        onClose={() => setSidebarVisible(false)}
        currentBotId={botId}
        currentSessionId={currentSessionId}
        needRefresh={needRefreshSessions}
        onRefreshComplete={() => setNeedRefreshSessions(false)}
        sessions={cachedSessions}
        onSessionsUpdate={updateSessionsCache}
        loading={sessionsLoading}
        onLoadingChange={setSessionsLoading}
        scrollPosition={scrollPosition}
        onScrollPositionChange={updateScrollPosition}
        hasFetched={hasFetched}
        cacheInitialized={cacheInitialized}
      />

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

            {(appLoading || messagesLoading) ? (
              <div className="flex items-center justify-center h-full">
                <SpinLoading color="primary" />
              </div>
            ) : (
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
            )}
          </div>

          <CustomInput
            key={`${botId}-${sessionId || 'new'}-${timestamp || ''}`}
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