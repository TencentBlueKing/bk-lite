'use client';

import React, { useState, useEffect, useRef, useMemo } from 'react';
import { Flex } from 'antd';
import { Toast, SpinLoading } from 'antd-mobile';
import { useRouter, useSearchParams } from 'next/navigation';
import { ChatInfo } from '@/types/conversation';
import MarkdownIt from 'markdown-it';
import { ConversationHeader, MessageList, VoiceInput, MessageContent } from './components';
import { useMessages } from './hooks';
import { conversationStyles } from './utils';
import { useTranslation } from '@/utils/i18n';
import { getApplication, getSessionMessages, getWelcomeMessage } from '@/api/bot';
import { getAvatar } from '@/utils/avatar';

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

  // 应用详情状态（包含 bot 和 node_id）
  const [appDetail, setAppDetail] = useState<{ bot: number; nodeId: string } | null>(null);

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
      const { files, fileType, text } = message;

      // 创建文件预览组件
      let filePreview: React.ReactNode;
      let textDescription = '';

      if (fileType === 'image') {
        // 图片类型：直接创建图片预览组件
        filePreview = (
          <div className="flex flex-col gap-2">
            {files.map((file, index) => {
              const url = URL.createObjectURL(file);
              return (
                <div key={index} className="max-w-xs">
                  <img
                    src={url}
                    alt={file.name}
                    className="w-full h-auto rounded-lg"
                    style={{ maxHeight: '300px', objectFit: 'contain' }}
                  />
                </div>
              );
            })}
          </div>
        );
        textDescription = text ? `${text} [附带 ${files.length} 张图片]` : `[发送了 ${files.length} 张图片]`;

      } else {
        // 文件类型：创建文件列表组件
        filePreview = (
          <div className="flex flex-col gap-1">
            {files.map((file, index) => {
              const size = (file.size / 1024).toFixed(2);
              return (
                <div key={index} className="flex items-center gap-2 text-sm">
                  <span>📎</span>
                  <span className="text-[var(--color-text-1)]">{file.name}</span>
                  <span className="text-[var(--color-text-3)] text-xs">({size} KB)</span>
                </div>
              );
            })}
          </div>
        );
        const fileNames = files.map(f => f.name).join(', ');
        textDescription = text ? `${text} [附带 ${files.length} 个文件: ${fileNames}]` : `[发送了 ${files.length} 个文件: ${fileNames}]`;
      }

      // 组合消息：如果有文字，先显示文字，再显示文件
      const userMessage = text ? (
        <div className="flex flex-col gap-2">
          <div>{text}</div>
          {filePreview}
        </div>
      ) : filePreview;

      // 添加用户文件消息
      const timestamp = Date.now();
      const userMsgId = `user-file-${timestamp}`;

      setMessages((prev) => [
        ...prev,
        {
          id: userMsgId,
          message: userMessage,
          status: 'local' as const,
          timestamp: timestamp,
        }
      ]);

      // 使用 triggerAIResponse 只触发 AI 响应，不再添加用户消息
      // 将文件描述作为用户输入传递给 AI
      triggerAIResponse(textDescription, renderMarkdown);
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
    message: string | React.ReactNode,
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
      const guide = response.data.guide || '您好，请问有什么可以帮助您的吗？';
      const [guideText, ...suggestions] = guide.split('\n');
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
      if (historyResponse.result && historyResponse.data && historyResponse.data.length > 0) {
        const historyMessages = historyResponse.data.map((msg: any) => {
          const msgId = `history-${msg.id}`;
          // 保存原始 Markdown 文本
          if (msg.conversation_role === 'bot') {
            messageMarkdownRef.current.set(msgId, msg.conversation_content);
          }
          return {
            id: msgId,
            message: msg.conversation_role === 'bot'
              ? renderMarkdown(msg.conversation_content)
              : msg.conversation_content,
            status: msg.conversation_role === 'user' ? 'local' as const : 'history' as const,
            timestamp: new Date(msg.conversation_time).getTime(),
          };
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

          <VoiceInput
            content={content}
            setContent={setContent}
            isVoiceMode={isVoiceMode}
            onSend={handleSendMessage}
            onToggleVoiceMode={() => toggleVoiceMode()}
            isAIRunning={isAIRunning}
          />
        </Flex>
      </div>
    </div>
  );
}