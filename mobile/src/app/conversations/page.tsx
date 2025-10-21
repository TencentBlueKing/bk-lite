'use client';

import React, { useState, useEffect } from 'react';
import BottomTabBar from '@/components/bottom-tab-bar';
import { useRouter } from 'next/navigation';
import { SearchBar, Avatar, List } from 'antd-mobile';
import { ChatItem, mockChatData } from '@/constants/mockData';
import { useTranslation } from '@/utils/i18n';
import {
  SearchOutline,
  ScanningOutline,
  AddCircleOutline,
} from 'antd-mobile-icons';

export default function ConversationList() {
  const { t } = useTranslation();
  const router = useRouter();
  const [searchValue, setSearchValue] = useState('');
  const [chatList, setChatList] = useState<ChatItem[]>([]);

  useEffect(() => {
    // 模拟API请求
    const fetchChatList = async () => {
      await new Promise((resolve) => setTimeout(resolve, 500));
      setChatList(mockChatData);
    };

    fetchChatList();
  }, []);

  const filteredChats = chatList.filter(
    (chat) =>
      chat.name.toLowerCase().includes(searchValue.toLowerCase()) ||
      chat.lastMessage.toLowerCase().includes(searchValue.toLowerCase())
  );

  return (
    <div className="flex flex-col h-full bg-[var(--color-background-body)]">
      {/* 顶部导航栏 */}
      <div className="flex items-center justify-between px-4 py-3 bg-[var(--color-bg)]">
        <ScanningOutline fontSize={24} className="text-[var(--color-text-2)]" />
        <h1 className="text-lg font-medium text-[var(--color-text-1)]">
          {t('navigation.conversations')}
        </h1>
        <div className="flex items-center space-x-3">
          <SearchOutline fontSize={24} className="text-[var(--color-text-2)]" />
          <AddCircleOutline
            fontSize={24}
            className="text-[var(--color-primary)]"
          />
        </div>
      </div>

      {/* 搜索框 */}
      <div className="px-4 py-3 bg-[var(--color-bg)]">
        <SearchBar
          placeholder={t('common.search')}
          value={searchValue}
          onChange={setSearchValue}
          style={
            {
              '--background': 'var(--color-fill-2)',
              '--border-radius': '8px',
              '--height': '38px',
              '--font-size': '15px',
            } as React.CSSProperties
          }
        />
      </div>

      {/* 聊天列表 */}
      <div className="flex-1 overflow-y-auto">
        <List>
          <style
            dangerouslySetInnerHTML={{
              __html: `
                .adm-list-item-content-extra {
                position: absolute;
                right: 5px;
                }
              `,
            }}
          />
          {filteredChats.map((chat) => (
            <List.Item
              key={chat.id}
              arrowIcon={false}
              prefix={
                <Avatar
                  src={chat.avatar}
                  style={{ '--size': '48px' }}
                  className="ml-1 mr-1"
                />
              }
              description={
                <div className="flex items-center justify-between mt-1">
                  <span className="text-sm text-[var(--color-text-3)] flex-1 truncate">
                    {chat.lastMessage}
                  </span>
                </div>
              }
              extra={
                <div className="flex flex-col items-end space-y-1">
                  <span className="text-xs text-[var(--color-text-4)]">
                    {chat.time}
                  </span>
                  {chat.unread && chat.unread > 0 && (
                    <span className="flex items-center justify-center min-w-[18px] h-[18px] px-1.5 bg-red-500 text-white text-xs rounded-full">
                      {chat.unread}
                    </span>
                  )}
                </div>
              }
              onClick={() => {
                router.push(`/conversation?id=${chat.id}`);
              }}
            >
              <div className="flex items-center justify-between">
                <span className="text-base font-medium text-[var(--color-text-1)]">
                  {chat.name}
                </span>
                {chat.website && (
                  <span className="text-xs text-[var(--color-text-4)] ml-2">
                    {chat.website}
                  </span>
                )}
              </div>
            </List.Item>
          ))}
        </List>
      </div>

      {/* 底部导航 */}
      <BottomTabBar />
    </div>
  );
}
