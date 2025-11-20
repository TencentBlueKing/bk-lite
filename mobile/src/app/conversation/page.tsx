'use client';

import React, { useState, useEffect, useRef, useMemo } from 'react';
import { Flex } from 'antd';
import { Toast } from 'antd-mobile';
import { useRouter, useSearchParams } from 'next/navigation';
import { mockChatData, mockChatHistory } from '@/constants/mockData';
import { ChatInfo } from '@/types/conversation';
import MarkdownIt from 'markdown-it';
import { ConversationHeader, MessageList, VoiceInput, MessageContent } from './components';
import { useMessages } from './hooks';
import { sleep, getRandomRecommendations, LAST_VISIT_KEY, conversationStyles } from './utils';

export default function ConversationDetail() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const chatId = searchParams?.get('id');

  const [chatInfo, setChatInfo] = useState<ChatInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [content, setContent] = useState('');
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const [recommendations, setRecommendations] = useState<string[]>(getRandomRecommendations());
  const welcomeMessageAddedRef = useRef(false);
  const welcomeCheckedRef = useRef(false);
  const [isVoiceMode, setIsVoiceMode] = useState(false);

  // 使用消息管理 hook
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
  } = useMessages(scrollContainerRef);

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

  // 重新生成推荐内容
  const handleRegenerateRecommendations = () => {
    const newRecommendations = getRandomRecommendations();
    setRecommendations(newRecommendations);

    setMessages((prev) =>
      prev.map((msg) => {
        if (msg.id === 'welcome-message' && msg.isWelcome) {
          return {
            ...msg,
            message: {
              ...(msg.message as any),
              suggestions: newRecommendations,
            },
          };
        }
        return msg;
      })
    );
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
        } else if (typeof message === 'string') {
          textContent = message;
        } else {
          textContent = '内容包含富文本，无法直接复制';
        }

        navigator.clipboard.writeText(textContent);
        Toast.show({ content: '已复制到剪贴板', icon: 'success' });
        break;
      case 'regenerate':
        if (messageId === 'welcome-recommendations') {
          handleRegenerateRecommendations();
        } else {
          Toast.show({ content: '正在重新生成...', icon: 'loading' });
        }
        break;
    }
  };

  // 检查是否需要显示欢迎消息
  useEffect(() => {
    if (loading) return;
    if (welcomeCheckedRef.current) return;
    welcomeCheckedRef.current = true;

    const checkAndAddWelcomeMessage = () => {
      const lastVisitTime = localStorage.getItem(LAST_VISIT_KEY);
      const currentTime = Date.now();
      let shouldShow = false;

      if (!lastVisitTime) {
        shouldShow = true;
        localStorage.setItem(LAST_VISIT_KEY, currentTime.toString());
      } else {
        const timeDiff = currentTime - parseInt(lastVisitTime);
        const hours24 = 24 * 60 * 60 * 1000;

        if (timeDiff >= hours24) {
          shouldShow = true;
          localStorage.setItem(LAST_VISIT_KEY, currentTime.toString());
        }
      }

      if (shouldShow && !welcomeMessageAddedRef.current) {
        welcomeMessageAddedRef.current = true;

        setTimeout(() => {
          const welcomeTimestamp = Date.now();

          const welcomeMessage = {
            id: 'welcome-message',
            message: {
              text: '您好，请问有什么可以帮助您的吗？可以点击或下面的问题进行快速提问。',
              suggestions: recommendations,
            },
            status: 'ai' as const,
            timestamp: welcomeTimestamp,
            isWelcome: true,
          };

          setMessages((prev) => {
            if (prev.length > 0) {
              return [...prev, welcomeMessage];
            } else {
              return [welcomeMessage];
            }
          });
        }, 100);
      }
    };

    checkAndAddWelcomeMessage();
  }, [loading, setMessages, recommendations]);

  // 加载历史聊天记录
  useEffect(() => {
    if (chatId === '1' && messages.length === 0 && !welcomeMessageAddedRef.current) {
      const history =
        mockChatHistory.find((item) => item.id === 1)?.chatHistory.map((msg: any) => {
          // AG-UI 协议：历史消息不需要打字效果，直接显示

          if (typeof msg.content === 'string') {
            messageMarkdownRef.current.set(msg.id, msg.content);
          }

          return {
            id: msg.id,
            message:
              typeof msg.content === 'string' ? renderMarkdown(msg.content) : msg.content,
            status: msg.role,
            timestamp: msg.timestamp,
            thinking: msg.thinking,
          };
        }) || [];

      if (history.length > 0) {
        setMessages(history);
        setTimeout(() => {
          scrollToBottom();
        }, 100);
      }
    }
  }, [chatId, messages.length, setMessages]);

  // 加载聊天信息
  useEffect(() => {
    if (!chatId) {
      router.replace('/chats');
      return;
    }

    const fetchChatData = async () => {
      setLoading(true);
      try {
        await sleep(500);

        const chat = mockChatData.find((c) => c.id === chatId);
        if (chat) {
          setChatInfo({
            id: chatId,
            name: chat.name,
            avatar: chat.avatar,
            status: 'online',
          });
        }
      } catch {
        Toast.show('加载聊天数据失败');
      } finally {
        setLoading(false);
        setTimeout(() => {
          scrollToBottom();
        }, 150);
      }
    };

    fetchChatData();
  }, [chatId, router]);

  if (loading || !chatInfo) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-[var(--color-text-3)]">加载中...</div>
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
              chatInfo={chatInfo}
              router={router}
              thinkingExpanded={thinkingExpanded}
              setThinkingExpanded={setThinkingExpanded}
              thinkingTypingText={thinkingTypingText}
              renderMarkdown={renderMarkdown}
              onActionClick={handleActionClick}
              onRecommendationClick={handleRecommendationClick}
              onRegenerateRecommendations={handleRegenerateRecommendations}
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