'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { SpinLoading } from 'antd-mobile';
import { initSecureStorage, getToken } from '@/utils/secureStorage';

// localStorage key 用于存储用户最后打开的对话页
const LAST_CONVERSATION_KEY = 'bk_lite_last_conversation';

interface LastConversation {
  botId: string;
  sessionId: string;
}

export default function Home() {
  const router = useRouter();

  useEffect(() => {
    const checkAuth = async () => {
      try {
        // 初始化安全存储
        await initSecureStorage();

        // 从安全存储获取 token
        const token = await getToken();

        if (token) {
          // 已登录，尝试获取最后打开的对话页
          let targetUrl = '/conversation'; // 默认跳转

          try {
            const lastConversationStr = localStorage.getItem(LAST_CONVERSATION_KEY);
            if (lastConversationStr) {
              const lastConversation: LastConversation = JSON.parse(lastConversationStr);
              if (lastConversation.botId) {
                // 构建跳转 URL，包含 botId 和 sessionId
                targetUrl = `/conversation?bot_id=${lastConversation.botId}`;
                if (lastConversation.sessionId) {
                  targetUrl += `&session_id=${lastConversation.sessionId}`;
                }
              }
            }
          } catch (e) {
            console.warn('get last conversation failed:', e);
          }

          router.replace(targetUrl);
        } else {
          // 未登录，跳转到登录页
          router.replace('/login');
        }
      } catch (error) {
        console.error('Auth check failed:', error);
        router.replace('/login');
      }
    };

    checkAuth();
  }, [router]);

  return (
    <div className="flex flex-col items-center justify-center h-full gap-3">
      <SpinLoading color="primary" style={{ '--size': '32px' }} />
    </div>
  );
}
