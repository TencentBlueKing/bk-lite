'use client';

import React, { useState, useEffect } from 'react';
import { Flex, type GetProp } from 'antd';
import { NavBar, Avatar, Toast } from 'antd-mobile';
import { LeftOutline } from 'antd-mobile-icons';
import { useRouter, useSearchParams } from 'next/navigation';
import { Bubble, Sender, useXAgent, useXChat } from '@ant-design/x';
import { UserOutlined } from '@ant-design/icons';
import { mockChatData } from '@/constants/mockData';
import { ChatInfo } from '@/types/conversation';

const sleep = (ms: number = 1000) =>
  new Promise((resolve) => setTimeout(resolve, ms));

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
      maxWidth: '70%',
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
      color: '#ffffff',
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
  const getAIReply = (userMessage: string): string => {
    const message = userMessage.toLowerCase();

    if (message.includes('产品') || message.includes('功能')) {
      return '我们的产品具有以下核心功能：\n\n• 🚀 智能运维自动化\n• 📊 实时监控告警\n• 🔧 故障快速定位\n• 💡 AI 智能分析\n\n您想了解哪个功能的详细信息？';
    } else if (message.includes('技术') || message.includes('支持')) {
      return '我很乐意为您提供技术支持！请告诉我您遇到的具体问题：\n\n• 🔍 系统配置问题\n• 🐛 故障排查\n• 📋 使用指南\n• 🔗 集成对接\n\n我会尽快为您解答。';
    } else if (message.includes('谢谢') || message.includes('感谢')) {
      return '不客气！😊 很高兴能帮助到您。如果还有其他问题，随时可以问我！';
    } else if (message.includes('帮助') || message.includes('help')) {
      return '我是您的AI助手，可以帮您：\n\n🔹 产品功能咨询\n🔹 技术问题解答\n🔹 使用指导\n🔹 故障排查\n\n请告诉我您需要什么帮助？';
    } else {
      const responses = [
        '我理解您的问题，让我为您详细解答...',
        '这是一个很好的问题！根据我的了解...',
        '关于这个问题，我建议您...',
        '我来帮您分析一下这个情况...',
      ];
      return responses[Math.floor(Math.random() * responses.length)];
    }
  };

  const [agent] = useXAgent<string, { message: string }, string>({
    request: async ({ message }, { onSuccess, onError }) => {
      await sleep(1500);
      try {
        const aiReply = getAIReply(message);
        onSuccess([aiReply]);
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
      <div className="flex items-center justify-center h-screen">
        <div className="text-[var(--color-text-3)]">加载中...</div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-screen bg-[var(--color-bg)]">
      {/* 顶部导航栏 */}
      <NavBar onBack={() => router.back()} backIcon={<LeftOutline />}>
        <div className="flex items-center">
          <Avatar
            src={chatInfo.avatar}
            style={{ '--size': '32px' }}
            className="mr-3"
          />
          <div className="flex flex-col">
            <div className="text-sm font-medium text-[var(--color-text-1)] leading-tight">
              {chatInfo.name}
            </div>
            <div className="text-xs text-[var(--color-text-3)] mt-0.5">
              {chatInfo.status === 'online' ? '在线' : '离线'}
            </div>
          </div>
        </div>
      </NavBar>

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
              items={messages.map(({ id, message, status }) => ({
                key: id,
                loading: status === 'loading',
                role: status === 'local' ? 'local' : 'ai',
                content: message,
              }))}
            />
          </div>

          {/* 发送器 */}
          <div
            className="mt-4 mr-2 bg-[var(--color-bg)] rounded-2xl"
            style={{ boxShadow: '0 2px 8px rgba(0, 0, 0, 0.08)' }}
          >
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
