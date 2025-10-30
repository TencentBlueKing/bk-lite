'use client';

import React, { useState, useEffect } from 'react';
import { Flex, type GetProp } from 'antd';
import { Avatar, Toast } from 'antd-mobile';
import { LeftOutline } from 'antd-mobile-icons';
import { useRouter, useSearchParams } from 'next/navigation';
import { Bubble, Sender, useXAgent, useXChat, Actions } from '@ant-design/x';
import { UserOutlined, CopyOutlined, RedoOutlined } from '@ant-design/icons';
import { mockChatData } from '@/constants/mockData';
import { mockAIResponses, mockTextResponses } from '@/constants/mockResponses';
import { ChatInfo } from '@/types/conversation';

const sleep = (ms: number = 1000) =>
  new Promise((resolve) => setTimeout(resolve, ms));

const actionItems = [
  {
    key: 'copy',
    icon: <CopyOutlined />,
    label: '复制',
  },
  {
    key: 'regenerate',
    icon: <RedoOutlined />,
    label: '重新生成',
  },
];

const roles: GetProp<typeof Bubble.List, 'roles'> = {
  ai: {
    placement: 'start',
    avatar: {
      icon: <UserOutlined />,
      style: {
        background: '#fde3cf',
        color: '#f56a00',
      },
    },
    typing: { step: 5, interval: 20 },
    style: {
      maxWidth: '90%',
    },
  },
  local: {
    placement: 'end',
    avatar: {
      style: {
        background: '#1677ff',
        color: '#ffffff',
      },
      children: '我',
    },
    style: {
      maxWidth: '90%',
      color: '#ffffff',
      marginLeft: 'auto',
    },
  },
};

export default function ConversationDetail() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const chatId = searchParams?.get('id');

  const [chatInfo, setChatInfo] = useState<ChatInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [content, setContent] = useState('');

  // 模拟智能AI回复逻辑
  const getAIReply = (userMessage: string): string | React.ReactNode => {
    const message = userMessage.toLowerCase();

    if (message.includes('表格') || message.includes('table')) {
      return mockAIResponses.table();
    } else if (message.includes('代码') || message.includes('code')) {
      return mockAIResponses.code();
    } else if (message.includes('卡片') || message.includes('card')) {
      return mockAIResponses.card();
    } else if (message.includes('列表') || message.includes('list')) {
      return mockAIResponses.list();
    } else if (message.includes('产品') || message.includes('功能')) {
      return mockTextResponses.product;
    } else if (message.includes('技术') || message.includes('支持')) {
      return mockTextResponses.support;
    } else if (message.includes('谢谢') || message.includes('感谢')) {
      return mockTextResponses.thanks;
    } else if (message.includes('帮助') || message.includes('help')) {
      return mockTextResponses.help;
    } else {
      return mockTextResponses.default[
        Math.floor(Math.random() * mockTextResponses.default.length)
      ];
    }
  };

  const [agent] = useXAgent<
    string | React.ReactNode,
    { message: string },
    string | React.ReactNode
  >({
    request: async ({ message }, { onSuccess, onError }) => {
      await sleep(1500);
      try {
        const aiReply = getAIReply(message);
        onSuccess([aiReply as any]);
      } catch {
        onError(new Error('AI 回复失败，请稍后重试'));
      }
    },
  });

  const { onRequest, messages } = useXChat({
    agent,
    requestPlaceholder: '正在思考中...',
    requestFallback: 'AI 暂时无法回复，请稍后重试。',
  });

  const handleActionClick = (
    key: string,
    message: string | React.ReactNode
  ) => {
    switch (key) {
      case 'copy':
        const textContent =
          typeof message === 'string'
            ? message
            : '内容包含富文本，无法直接复制';
        navigator.clipboard.writeText(textContent);
        Toast.show({ content: '已复制到剪贴板', icon: 'success' });
        break;
      case 'regenerate':
        Toast.show({ content: '正在重新生成...', icon: 'loading' });
        break;
    }
  };

  useEffect(() => {
    if (!chatId) {
      router.replace('/chats');
      return;
    }

    // 模拟获取聊天信息
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
      {/* 顶部导航栏 */}
      <div className="flex items-center justify-center px-2 py-3 bg-[var(--color-bg)] border-b border-[var(--color-border)]">
        <button
          onClick={() => router.push('/conversations')}
          className="flex items-center justify-center w-6 h-8 absolute left-4"
        >
          <LeftOutline fontSize={24} className="text-[var(--color-text-1)]" />
        </button>
        <div className="flex items-center">
          <Avatar
            src={chatInfo.avatar}
            style={{ '--size': '36px' }}
            className="mr-2 flex-shrink-0"
          />
          <div className="text-base font-medium text-[var(--color-text-1)]">
            {chatInfo.name}
          </div>
        </div>
      </div>

      {/* 聊天内容区域 */}
      <div className="flex-1 bg-[var(--color-background-body)] overflow-hidden">
        <Flex vertical style={{ height: '100%', padding: '16px 0 16px 8px' }}>
          <div
            style={{
              flex: 1,
              overflow: 'auto',
              paddingBottom: '8px',
              paddingRight: '8px',
            }}
            className="custom-scrollbar"
          >
            <Bubble.List
              roles={roles}
              style={{
                width: '100%',
              }}
              className="w-full"
              items={messages.map(({ id, message, status }) => {
                const isAIMessage = status !== 'local' && status !== 'loading';
                return {
                  key: id,
                  loading: status === 'loading',
                  role: status === 'local' ? 'local' : 'ai',
                  content: message,
                  ...(isAIMessage && {
                    footer: (
                      <Actions
                        items={actionItems}
                        onClick={({ keyPath }) =>
                          handleActionClick(keyPath[0], message)
                        }
                      />
                    ),
                  }),
                };
              })}
            />
          </div>

          {/* 发送器 */}
          <div
            className="mt-4 mr-2 bg-[var(--color-bg)] rounded-2xl sender-container"
            style={{ boxShadow: '0 2px 8px rgba(0, 0, 0, 0.08)' }}
          >
            <style
              dangerouslySetInnerHTML={{
                __html: `
                  .sender-container .ant-sender-input{
                    font-size: 16px !important;
                  }
                  .ant-bubble-footer {
                    margin-top: 0 !important;
                  }
                  .ant-bubble-content {
                    font-size: 16px !important;
                  }
                `,
              }}
            />
            <Sender
              loading={agent.isRequesting()}
              value={content}
              onChange={setContent}
              onSubmit={(nextContent) => {
                onRequest(nextContent);
                setContent('');
              }}
              placeholder="输入消息..."
              style={{
                border: 'none',
                borderRadius: '20px',
                backgroundColor: 'transparent',
                width: '100%',
              }}
            />
          </div>
        </Flex>
      </div>
    </div>
  );
}
