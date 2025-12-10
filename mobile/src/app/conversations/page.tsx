'use client';

import React, { useState, useEffect } from 'react';
import BottomTabBar from '@/components/bottom-tab-bar';
import { useRouter } from 'next/navigation';
import { List, SpinLoading } from 'antd-mobile';
import { useTranslation } from '@/utils/i18n';
import { sessionsItem } from '@/types/conversation';
import {
  SearchOutline,
  ScanningOutline,
  AddCircleOutline,
} from 'antd-mobile-icons';
import { getSessions } from '@/api/bot';

export default function ConversationList() {
  const { t } = useTranslation();
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [sessions, setSessions] = useState<sessionsItem[]>([]);

  useEffect(() => {
    // 模拟API请求
    const fetchChatList = async () => {
      setLoading(true);
      try {
        const response = await getSessions();
        if (!response.result) {
          throw new Error(response.message || 'Failed to fetch sessions');
        }
        setSessions(response.data || []);
      } catch (error) {
        console.error('getSessions error:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchChatList();
  }, []);

  const renderContent = () => {
    if (loading) {
      return (
        <div className="h-full flex flex-col items-center justify-center">
          <SpinLoading color="primary" />
        </div>)
    }
    if (sessions.length > 0) {
      return (
        <List>
          {sessions.map((chat) => (
            <List.Item
              key={chat.session_id}>
              <div
                className="flex items-center gap-3"
                onClick={() => router.push(`/conversation?bot_id=${chat.bot_id}&session_id=${chat.session_id}`)}
              >
                {chat.title}
              </div>
            </List.Item>
          ))}
        </List>
      );
    }
  }


  return (
    <div className="flex flex-col h-full bg-[var(--color-background-body)]">
      {/* 顶部导航栏 */}
      <div className="flex items-center justify-center px-4 py-3 bg-[var(--color-bg)]">
        <ScanningOutline fontSize={24} className="absolute left-4 text-[var(--color-text-2)]" />
        <h1 className="text-lg font-medium text-[var(--color-text-1)]">
          {t('navigation.conversations')}
        </h1>
        <div className="flex items-center space-x-3 absolute right-4">
          <AddCircleOutline
            fontSize={24}
            className="text-[var(--color-primary)]"
          />
        </div>
      </div>

      <div className="px-4 py-3 bg-[var(--color-background-body)]">
        <div className='py-2 bg-[var(--color-bg)] rounded-xl flex gap-2 items-center justify-center text-[var(--color-text-2)] text-sm' onClick={() => router.push('/search?type=ConversationList')}>
          <SearchOutline />
          <span>{t('common.search')}</span>
        </div>
      </div>

      {/* 聊天列表 */}
      <div className="flex-1 overflow-y-auto">
        {renderContent()}
      </div>

      {/* 底部导航 */}
      <BottomTabBar />
    </div>
  );
}