'use client';

import React, { useState, useEffect, useMemo } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { SearchBar, Avatar, List } from 'antd-mobile';
import { LeftOutline } from 'antd-mobile-icons';
import { mockChatData, mockWorkbenchData } from '@/constants/mockData';
import Image from 'next/image';

type SearchType = 'ConversationList' | 'WorkbenchPage';

export default function SearchPage() {
    const router = useRouter();
    const searchParams = useSearchParams();
    const searchType = (searchParams?.get('type') || 'ConversationList') as SearchType;

    const [searchValue, setSearchValue] = useState('');

    // 根据类型获取搜索结果
    const searchResults = useMemo(() => {
        if (!searchValue.trim()) return [];

        const keyword = searchValue.trim().toLowerCase();

        if (searchType === 'ConversationList') {
            // 搜索对话列表
            return mockChatData.filter(
                (chat) =>
                    chat.name.toLowerCase().includes(keyword)
            );
        } else if (searchType === 'WorkbenchPage') {
            // 搜索工作台
            return mockWorkbenchData.data.items.filter(
                (bot) =>
                    bot.name.toLowerCase().includes(keyword)
            );
        }

        return [];
    }, [searchValue, searchType]);

    // bot_type 映射
    const botTypeMap: { [key: number]: string } = {
        1: 'Pilot',
        2: 'LobeChat',
        3: 'Chatflow',
    };

    // 渲染对话列表项
    const renderConversationItem = (chat: any) => (
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
    );

    // 渲染工作台列表项
    const renderWorkbenchItem = (item: any) => (
        <div
            key={item.id}
            className="bg-[var(--color-bg)] mx-3 mt-3 rounded-lg shadow-sm border border-[var(--color-border)] p-4 active:bg-[var(--color-bg-hover)] cursor-pointer"
            onClick={() => {
                sessionStorage.setItem('currentBot', JSON.stringify(item));
                router.push(`/workbench/detail?id=${item.id}`);
            }}
        >
            <div className="flex items-start space-x-3">
                {/* 缩略图 */}
                <div className="flex-shrink-0 relative">
                    <div className="w-16 h-16 bg-gradient-to-br from-blue-400 to-blue-600 rounded-full overflow-hidden">
                        <Image
                            src="/avatars/04.svg"
                            alt={item.name}
                            width={64}
                            height={64}
                            className="w-full h-full object-cover"
                        />
                    </div>
                </div>

                {/* 内容区域 */}
                <div className="flex-1 min-w-0">
                    {/* 名称和状态 */}
                    <div className="flex items-center justify-between mb-1.5">
                        <h3 className="text-base font-medium text-[var(--color-text-1)]">
                            {item.name}
                        </h3>
                        <div className="flex items-center space-x-1.5">
                            <div
                                className={`w-2 h-2 rounded-full ${item.online ? 'bg-blue-500' : 'bg-gray-400'
                                    }`}
                            ></div>
                            <span
                                className={`text-xs ${item.online ? 'text-blue-500' : 'text-gray-400'
                                    }`}
                            >
                                {item.online ? '在线' : '下线'}
                            </span>
                        </div>
                    </div>

                    {/* 描述文本 */}
                    <p className="text-xs text-[var(--color-text-2)] mb-3 leading-relaxed overflow-hidden"
                        style={{
                            whiteSpace: 'nowrap',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis'
                        }}
                    >
                        {item.introduction || '暂无简介'}
                    </p>

                    {/* 标签按钮 */}
                    {item.bot_type && (
                        <span className="float-right px-3 py-1 text-xs font-medium text-gray-800 bg-gray-200 rounded">
                            {botTypeMap[item.bot_type] || '未知类型'}
                        </span>
                    )}
                </div>
            </div>
        </div>
    );


    // 获取占位符文本
    const getPlaceholder = () => {
        switch (searchType) {
            case 'ConversationList':
                return '搜索对话名称';
            case 'WorkbenchPage':
                return '搜索应用名称';
            default:
                return '请输入搜索关键词';
        }
    };

    return (
        <div className="flex flex-col h-full bg-[var(--color-background-body)]">
            {/* 顶部搜索栏 */}
            <div className="bg-[var(--color-bg)] border-b border-[var(--color-border)]">
                <div className="flex items-center px-2 py-2 space-x-2">
                    <button
                        onClick={() => router.back()}
                        className="flex items-center justify-center w-8 h-8"
                    >
                        <LeftOutline fontSize={24} className="text-[var(--color-text-1)]" />
                    </button>
                    <div className="flex-1">
                        <SearchBar
                            placeholder={getPlaceholder()}
                            value={searchValue}
                            onChange={setSearchValue}
                            onClear={() => setSearchValue('')}
                            style={{
                                '--border-radius': '18px',
                                '--background': 'var(--color-fill-2)',
                                '--height': '36px',
                            }}
                        />
                    </div>
                </div>
            </div>

            {/* 搜索结果 */}
            <div className="flex-1 overflow-y-auto">
                {!searchValue.trim() ? (
                    // 空状态 - 未输入搜索词
                    <div className="h-full flex flex-col items-center justify-center h-64 text-[var(--color-text-3)]">
                        <svg
                            className="w-16 h-16 mb-4 opacity-40"
                            fill="none"
                            stroke="currentColor"
                            viewBox="0 0 24 24"
                        >
                            <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                strokeWidth={2}
                                d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
                            />
                        </svg>
                        <p className="text-sm">请输入关键词进行搜索</p>
                    </div>
                ) : searchResults.length === 0 ? (
                    // 空状态 - 无搜索结果
                    <div className="h-full flex flex-col items-center justify-center h-64 text-[var(--color-text-3)]">
                        <svg
                            className="w-16 h-16 mb-4 opacity-40"
                            fill="none"
                            stroke="currentColor"
                            viewBox="0 0 24 24"
                        >
                            <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                strokeWidth={2}
                                d="M9.172 16.172a4 4 0 015.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                            />
                        </svg>
                        <p className="text-sm">未找到相关结果</p>
                        <p className="text-xs mt-1">试试其他关键词</p>
                    </div>
                ) : (
                    // 渲染搜索结果
                    <div>
                        {searchType === 'ConversationList' ? (
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
                                {searchResults.map((item) => renderConversationItem(item))}
                            </List>
                        ) : (
                            searchResults.map((item) => renderWorkbenchItem(item))
                        )}
                    </div>
                )}
            </div>
        </div>
    );
}
