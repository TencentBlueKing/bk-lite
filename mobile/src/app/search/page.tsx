'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { SearchBar, Avatar, List, SpinLoading } from 'antd-mobile';
import { LeftOutline, FrownOutline, SearchOutline } from 'antd-mobile-icons';
import { mockChatData, mockChatMessages, ChatMessageRecord, ChatItem } from '@/constants/mockData';
import Image from 'next/image';
import { useTranslation } from '@/utils/i18n';
import { getApplication } from '@/api/bot';
import { getAvatar } from '@/utils/avatar';

type SearchType = 'ConversationList' | 'WorkbenchPage' | 'ChatHistory';

export default function SearchPage() {
    const { t } = useTranslation();
    const router = useRouter();
    const searchParams = useSearchParams();
    const searchType = (searchParams?.get('type') || 'ConversationList') as SearchType;
    const botId = searchParams?.get('bot_id') || '';

    const [searchValue, setSearchValue] = useState('');
    const [workbenchResults, setWorkbenchResults] = useState<any[]>([]);
    const [loading, setLoading] = useState(false);

    // 用于取消请求的 AbortController
    const abortControllerRef = useRef<AbortController | null>(null);

    // 搜索工作台应用
    const searchWorkbenchApps = useCallback(async (keyword: string) => {
        if (!keyword.trim()) {
            setWorkbenchResults([]);
            return;
        }

        // 取消上一个请求
        if (abortControllerRef.current) {
            abortControllerRef.current.abort();
        }

        // 创建新的 AbortController
        const controller = new AbortController();
        abortControllerRef.current = controller;

        setLoading(true);

        try {
            const response = await getApplication({
                app_name: keyword.trim(),
                page: 1,
                page_size: 20,
            }, { signal: controller.signal });

            // 检查请求是否被取消
            if (controller.signal.aborted) {
                return;
            }
            if (!response.result) {
                setWorkbenchResults([]);
                return;
            }
            setWorkbenchResults(response?.data.items || []);
        } catch (error: any) {
            // 忽略取消的请求错误
            if (error?.name === 'AbortError') {
                return;
            }
            console.error('Failed to search applications:', error);
            setWorkbenchResults([]);
        } finally {
            if (!controller.signal.aborted) {
                setLoading(false);
            }
        }
    }, []);

    // 防抖搜索
    useEffect(() => {
        if (searchType !== 'WorkbenchPage') return;

        const timer = setTimeout(() => {
            searchWorkbenchApps(searchValue);
        }, 300);

        return () => {
            clearTimeout(timer);
            if (abortControllerRef.current) {
                abortControllerRef.current.abort();
            }
        };
    }, [searchValue, searchType, searchWorkbenchApps]);

    // 获取非工作台的搜索结果
    const getOtherSearchResults = useCallback(() => {
        if (!searchValue.trim()) return [];

        const keyword = searchValue.trim().toLowerCase();

        if (searchType === 'ConversationList') {
            // 搜索对话列表
            return mockChatData.filter(
                (chat) =>
                    chat.name.toLowerCase().includes(keyword)
            );
        } else if (searchType === 'ChatHistory') {
            // 搜索聊天记录
            const filtered = mockChatMessages.filter((message) => message.chatId === botId)?.filter(
                (message) =>
                    message.content.toLowerCase().includes(keyword)
            );
            // 按时间倒序排序（最新的在前面）
            return filtered.sort((a, b) => b.timestamp - a.timestamp);
        }

        return [];
    }, [searchValue, searchType, botId]);

    // 获取搜索结果
    const searchResults = searchType === 'WorkbenchPage' ? workbenchResults : getOtherSearchResults();

    // app_tags 映射
    const appTagsMap: { [key: string]: string } = {
        'routine_ops': t('workbench.routineOps'),
        'monitor_alarm': t('workbench.monitorAlarm'),
        'automation': t('workbench.automation'),
        'security_audit': t('workbench.securityAudit'),
        'performance_analysis': t('workbench.performanceAnalysis'),
        'ops_plan': t('workbench.opsPlan'),
    };

    const appTagColors: { [key: string]: { bg: string; text: string } } = {
        'routine_ops': { bg: '#E5F4FF', text: '#4A9EFF' },
        'monitor_alarm': { bg: '#FFE5E5', text: '#FF6B9D' },
        'automation': { bg: '#FFF4E5', text: '#FFB84D' },
        'security_audit': { bg: '#E5FFE5', text: '#52C41A' },
        'performance_analysis': { bg: '#F0E5FF', text: '#9B59B6' },
        'ops_plan': { bg: '#E5F0FF', text: '#3498DB' },
    };

    // 通用渲染函数 - 对话列表项和聊天记录项
    const renderListItem = (item: ChatItem | ChatMessageRecord, type: 'conversation' | 'message') => {
        const isConversation = type === 'conversation';
        const chatItem = item as ChatItem;
        const messageItem = item as ChatMessageRecord;

        return (
            <List.Item
                key={isConversation ? chatItem.id : messageItem.messageId}
                arrowIcon={false}
                prefix={
                    <Avatar
                        src={isConversation ? chatItem.avatar : messageItem.chatAvatar}
                        style={{ '--size': '48px' }}
                        className="ml-1 mr-1"
                    />
                }
                description={
                    <div className="mt-1">
                        <span className="text-sm text-[var(--color-text-3)] line-clamp-1">
                            {isConversation ? chatItem.lastMessage : messageItem.content}
                        </span>
                    </div>
                }
                extra={
                    <div className="flex flex-col items-end space-y-1">
                        <span className="text-xs text-[var(--color-text-4)]">
                            {isConversation ? chatItem.time : formatMessageTime(messageItem.timestamp)}
                        </span>
                        {isConversation && chatItem.unread && chatItem.unread > 0 && (
                            <span className="flex items-center justify-center min-w-[18px] h-[18px] px-1.5 bg-red-500 text-white text-xs rounded-full">
                                {chatItem.unread}
                            </span>
                        )}
                    </div>
                }
                onClick={() => {
                    if (isConversation) {
                        router.push(`/conversation?id=${chatItem.id}`);
                    } else {
                        router.push(`/conversation?id=${messageItem.chatId}`);
                    }
                }}
            >
                <div className="flex items-center justify-between">
                    <span className="text-base font-medium text-[var(--color-text-1)]">
                        {isConversation ? chatItem.name : messageItem.chatName}
                    </span>
                    {isConversation && chatItem.website && (
                        <span className="text-xs text-[var(--color-text-4)] ml-2">
                            {chatItem.website}
                        </span>
                    )}
                </div>
            </List.Item>
        );
    };

    // 渲染对话列表项
    const renderConversationItem = (chat: any) => renderListItem(chat, 'conversation');

    // 渲染工作台列表项
    const renderWorkbenchItem = (item: any) => (
        <div
            key={item.id}
            className="bg-[var(--color-bg)] mx-3 mt-3 rounded-lg shadow-sm border border-[var(--color-border)] p-4 active:bg-[var(--color-bg-hover)] cursor-pointer relative overflow-hidden"
            onClick={() => {
                router.push(`/workbench/detail?bot_id=${item.bot}`);
            }}
        >
            {/* 右上角状态 - 默认在线 */}
            <div
                className="absolute top-0 right-0 w-6 h-6"
                style={{
                    clipPath: 'polygon(100% 0, 100% 100%, 0 0)',
                    backgroundColor: '#52C41A',
                }}
            ></div>

            <div className="flex items-start space-x-3">
                {/* 缩略图 */}
                <div className="flex-shrink-0 relative">
                    <div className="w-16 h-16 bg-gradient-to-br from-blue-400 to-blue-600 rounded-full overflow-hidden">
                        <Image
                            src={getAvatar(item.id)}
                            alt={item.app_name}
                            width={64}
                            height={64}
                            className="w-full h-full object-cover"
                        />
                    </div>
                </div>

                {/* 内容区域 */}
                <div className="flex-1 min-w-0">
                    {/* 名称 */}
                    <div className="flex items-center justify-between mb-1.5">
                        <h3 className="text-base font-medium text-[var(--color-text-1)]">
                            {item.app_name}
                        </h3>
                    </div>

                    {/* 描述文本 */}
                    <p className="text-xs text-[var(--color-text-2)] mb-3 leading-relaxed truncate">
                        {item.app_description || t('workbench.noIntroduction')}
                    </p>

                    {/* 标签按钮 */}
                    {item.app_tags && item.app_tags.length > 0 && (
                        <div className="flex flex-wrap gap-1 justify-end">
                            {item.app_tags.map((tag: string) => (
                                <span
                                    key={tag}
                                    className="px-2 py-0.5 text-xs font-medium rounded"
                                    style={{
                                        backgroundColor: appTagColors[tag]?.bg || '#F0F0F0',
                                        color: appTagColors[tag]?.text || '#666666',
                                    }}
                                >
                                    {appTagsMap[tag] || tag}
                                </span>
                            ))}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );

    // 格式化时间戳
    const formatMessageTime = (timestamp: number) => {
        const date = new Date(timestamp);
        const now = new Date();
        const diff = now.getTime() - timestamp;

        // 今天
        if (date.toDateString() === now.toDateString()) {
            return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
        }

        // 昨天
        const yesterday = new Date(now);
        yesterday.setDate(yesterday.getDate() - 1);
        if (date.toDateString() === yesterday.toDateString()) {
            return t('search.yesterday');
        }

        // 一周内
        if (diff < 7 * 24 * 60 * 60 * 1000) {
            const days = ['日', '一', '二', '三', '四', '五', '六'];
            return `周${days[date.getDay()]}`;
        }

        // 今年
        if (date.getFullYear() === now.getFullYear()) {
            return `${date.getMonth() + 1}月${date.getDate()}日`;
        }

        // 更早
        return `${date.getFullYear()}年${date.getMonth() + 1}月${date.getDate()}日`;
    };

    // 渲染聊天记录项
    const renderChatMessageItem = (message: ChatMessageRecord) => renderListItem(message, 'message');


    // 获取占位符文本
    const getPlaceholder = () => {
        switch (searchType) {
            case 'ConversationList':
                return t('search.searchConversation');
            case 'WorkbenchPage':
                return t('search.searchApp');
            case 'ChatHistory':
                return t('search.searchChatHistory');
            default:
                return t('search.enterKeyword');
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
                        <SearchOutline className='text-7xl mb-4' />
                        <p className="text-sm">{t('search.searchHint')}</p>
                    </div>
                ) : loading && searchType === 'WorkbenchPage' ? (
                    // 加载状态
                    <div className="h-full flex flex-col items-center justify-center">
                        <SpinLoading color="primary" />
                    </div>
                ) : searchResults.length === 0 ? (
                    // 空状态 - 无搜索结果
                    <div className="h-full flex flex-col items-center justify-center h-64 text-[var(--color-text-3)]">
                        <FrownOutline className='text-7xl mb-4' />
                        <p className="text-sm">{t('search.noResults')}</p>
                        <p className="text-xs mt-1">{t('search.tryOtherKeywords')}</p>
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
                        ) : searchType === 'ChatHistory' ? (
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
                                {searchResults.map((item) => renderChatMessageItem(item as ChatMessageRecord))}
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