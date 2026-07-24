'use client';

import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { SearchBar, Avatar, ErrorBlock, InfiniteScroll, List, SpinLoading } from 'antd-mobile';
import { LeftOutline, FrownOutline, MessageOutline, SearchOutline } from 'antd-mobile-icons';
import { mockChatMessages, ChatMessageRecord } from '@/constants/mockData';
import Image from 'next/image';
import { useTranslation } from '@/utils/i18n';
import {
    ChatApplicationItem,
    getApplication,
    getApplicationItems,
    getMobileSessions,
} from '@/api/bot';
import { SessionItem } from '@/types/conversation';
import { getAvatar } from '@/utils/avatar';
import { withBasePath } from '@/utils/basePath';
import { getAppTagColor, getAppTagLabel } from '@/constants/workbenchTags';
import { buildConversationHref } from '@/utils/conversationRoute';
import MobileSafeHeader from '@/components/mobile-safe-header';
import { useMobileBack } from '@/navigation/mobile-back';
import {
    hasMoreSessions,
    mergeSessionItems,
    MOBILE_SESSION_PAGE_SIZE,
    shouldShowSessionPagination,
} from '@/utils/sessionPagination';

type SearchType = 'ConversationList' | 'WorkbenchPage' | 'ChatHistory';

export default function SearchPage() {
    const { t } = useTranslation();
    const router = useRouter();
    const searchParams = useSearchParams();
    const searchType = (searchParams?.get('type') || 'ConversationList') as SearchType;
    const botId = searchParams?.get('bot_id') || '';
    const nodeId = searchParams?.get('node_id');
    const fallbackHref = useMemo(() => {
        if (searchType === 'WorkbenchPage') return '/workbench';
        if (searchType !== 'ChatHistory' || !botId) return '/conversations';

        const params = new URLSearchParams({ bot_id: botId });
        if (nodeId) params.set('node_id', nodeId);
        return `/workbench/detail?${params.toString()}`;
    }, [botId, nodeId, searchType]);
    const handleBack = useMobileBack({ fallbackHref });

    const [searchValue, setSearchValue] = useState('');
    const [workbenchResults, setWorkbenchResults] = useState<ChatApplicationItem[]>([]);
    const [conversationSessions, setConversationSessions] = useState<SessionItem[]>([]);
    const [loading, setLoading] = useState(false);
    const [loadFailed, setLoadFailed] = useState(false);
    const [conversationReloadVersion, setConversationReloadVersion] = useState(0);
    const [conversationCount, setConversationCount] = useState(0);
    const [nextConversationPage, setNextConversationPage] = useState(1);

    // 用于取消请求的 AbortController
    const abortControllerRef = useRef<AbortController | null>(null);
    const conversationAbortControllerRef = useRef<AbortController | null>(null);
    const conversationRequestRef = useRef(false);

    // 搜索工作台应用
    const searchWorkbenchApps = useCallback(async (keyword: string) => {
        if (!keyword.trim()) {
            setWorkbenchResults([]);
            setLoadFailed(false);
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
        setLoadFailed(false);

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
                throw new Error(response.message || 'Failed to search applications');
            }
            setWorkbenchResults(getApplicationItems(response));
        } catch (error: unknown) {
            // 忽略取消的请求错误
            if (error instanceof DOMException && error.name === 'AbortError') {
                return;
            }
            console.error('Failed to search applications:', error);
            setWorkbenchResults([]);
            setLoadFailed(true);
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

    const loadConversationSessions = useCallback(async ({ append = false, page = 1 } = {}) => {
        if (conversationRequestRef.current) return;
        const controller = new AbortController();
        conversationAbortControllerRef.current = controller;
        conversationRequestRef.current = true;
        if (!append) {
            setLoading(true);
            setLoadFailed(false);
        }
        try {
            const response = await getMobileSessions({
                page,
                page_size: MOBILE_SESSION_PAGE_SIZE,
            }, { signal: controller.signal });
            const items = response.data?.items;
            if (!response.result || !items) {
                throw new Error(response.message || 'Failed to load conversations');
            }
            setConversationSessions((currentSessions) => (
                append ? mergeSessionItems(currentSessions, items) : items
            ));
            setConversationCount(response.data?.count ?? items.length);
            setNextConversationPage(page + 1);
        } catch (error: unknown) {
            if (!(error instanceof DOMException && error.name === 'AbortError')) {
                console.error('Failed to load conversations:', error);
                if (!append) {
                    setConversationSessions([]);
                    setLoadFailed(true);
                }
            }
        } finally {
            conversationRequestRef.current = false;
            if (!controller.signal.aborted && !append) {
                setLoading(false);
            }
        }
    }, []);

    useEffect(() => {
        if (searchType !== 'ConversationList') return;

        void loadConversationSessions();
        return () => conversationAbortControllerRef.current?.abort();
    }, [conversationReloadVersion, loadConversationSessions, searchType]);

    const loadMoreConversationSessions = useCallback(() => loadConversationSessions({
        append: true,
        page: nextConversationPage,
    }), [loadConversationSessions, nextConversationPage]);
    const hasMoreConversationSessions = hasMoreSessions(conversationSessions, conversationCount);
    const showConversationPagination = shouldShowSessionPagination(
        conversationCount,
        conversationSessions.length,
    );

    // 获取非工作台的搜索结果
    const getOtherSearchResults = useCallback(() => {
        if (!searchValue.trim()) return [];

        const keyword = searchValue.trim().toLowerCase();

        if (searchType === 'ConversationList') {
            return conversationSessions.filter(
                (session) =>
                    (session.title || t('conversations.untitled')).toLowerCase().includes(keyword)
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
    }, [searchValue, searchType, botId, conversationSessions, t]);

    // 获取搜索结果
    const searchResults = searchType === 'WorkbenchPage' ? workbenchResults : getOtherSearchResults();

    const renderChatMessageItem = (messageItem: ChatMessageRecord) => {
        return (
            <List.Item
                key={messageItem.messageId}
                arrowIcon={false}
                prefix={
                    <Avatar
                        src={withBasePath(messageItem.chatAvatar)}
                        style={{ '--size': '48px' }}
                        className="ml-1 mr-1"
                    />
                }
                description={
                    <div className="mt-1">
                        <span className="text-sm text-[var(--color-text-3)] line-clamp-1">
                            {messageItem.content}
                        </span>
                    </div>
                }
                extra={
                    <div className="flex flex-col items-end space-y-1">
                        <span className="text-xs text-[var(--color-text-4)]">
                            {formatMessageTime(messageItem.timestamp)}
                        </span>
                    </div>
                }
                onClick={nodeId ? () => router.push(buildConversationHref({
                    botId: messageItem.chatId,
                    nodeId,
                })) : undefined}
            >
                <div className="flex items-center justify-between">
                    <span className="text-base font-medium text-[var(--color-text-1)]">
                        {messageItem.chatName}
                    </span>
                </div>
            </List.Item>
        );
    };

    const renderConversationItem = (session: SessionItem) => (
        <List.Item
            key={session.session_id}
            arrowIcon={false}
            prefix={
                <span className="flex h-12 w-12 items-center justify-center rounded-full bg-[var(--color-fill-2)] text-[var(--color-text-2)]">
                    <MessageOutline fontSize={24} aria-hidden="true" />
                </span>
            }
            description={t('conversations.sessionHint')}
            onClick={() => router.push(buildConversationHref({
                botId: session.bot_id,
                sessionId: session.session_id,
                nodeId: session.node_id,
            }))}
        >
            <span className="line-clamp-1 text-base font-medium text-[var(--color-text-1)]">
                {session.title || t('conversations.untitled')}
            </span>
        </List.Item>
    );

    // 渲染工作台列表项
    const renderWorkbenchItem = (item: ChatApplicationItem) => (
        <button
            type="button"
            key={item.id}
            className="block w-[calc(100%_-_1.5rem)] bg-[var(--color-bg)] mx-3 mt-3 rounded-lg shadow-sm border border-[var(--color-border)] p-4 text-left active:bg-[var(--color-bg-hover)] cursor-pointer relative overflow-hidden"
            onClick={() => {
                router.push(buildConversationHref({ botId: item.bot, nodeId: item.node_id }));
            }}
        >
            {/* 右上角状态 - 默认在线 */}
            <span
                aria-hidden="true"
                className="absolute top-0 right-0 w-6 h-6"
                style={{
                    clipPath: 'polygon(100% 0, 100% 100%, 0 0)',
                    backgroundColor: 'var(--color-success)',
                }}
            />

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
                            {item.app_tags.map((tag: string) => {
                                const tagColor = getAppTagColor(tag);
                                return (
                                    <span
                                        key={tag}
                                        className="px-2 py-0.5 text-xs font-medium rounded"
                                        style={{
                                            backgroundColor: tagColor.bg,
                                            color: tagColor.text,
                                        }}
                                    >
                                        {getAppTagLabel(tag, t)}
                                    </span>
                                );
                            })}
                        </div>
                    )}
                </div>
            </div>
        </button>
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
            <MobileSafeHeader contentClassName="flex items-center gap-2 px-2 py-1.5">
                <button
                    type="button"
                    aria-label={t('common.back')}
                    onClick={handleBack}
                    className="flex min-h-11 min-w-11 items-center justify-center rounded-lg active:bg-[var(--color-fill-2)]"
                >
                    <LeftOutline fontSize={24} className="text-[var(--color-text-1)]" aria-hidden="true" />
                </button>
                <div className="min-w-0 flex-1">
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
            </MobileSafeHeader>

            {/* 搜索结果 */}
            <div className="flex-1 overflow-y-auto">
                {!searchValue.trim() ? (
                    // 空状态 - 未输入搜索词
                    <div className="h-full flex flex-col items-center justify-center h-64 text-[var(--color-text-3)]">
                        <SearchOutline className='text-7xl mb-4' />
                        <p className="text-sm">{t('search.searchHint')}</p>
                    </div>
                ) : loading && (searchType === 'WorkbenchPage' || searchType === 'ConversationList') ? (
                    // 加载状态
                    <div className="h-full flex flex-col items-center justify-center">
                        <SpinLoading color="primary" />
                    </div>
                ) : loadFailed && (searchType === 'WorkbenchPage' || searchType === 'ConversationList') ? (
                    <div className="flex h-full flex-col items-center justify-center px-6 text-center">
                        <ErrorBlock
                            status="disconnected"
                            title={t('search.loadFailed')}
                            description={t('search.loadFailedDescription')}
                        >
                            <button
                                type="button"
                                className="min-h-11 rounded-lg px-4 text-[var(--color-primary)] active:bg-[var(--color-fill-2)]"
                                onClick={() => {
                                    if (searchType === 'WorkbenchPage') {
                                        void searchWorkbenchApps(searchValue);
                                    } else {
                                        setConversationReloadVersion((version) => version + 1);
                                    }
                                }}
                            >
                                {t('common.retry')}
                            </button>
                        </ErrorBlock>
                    </div>
                ) : searchResults.length === 0 ? (
                    // 空状态 - 无搜索结果
                    <div className="h-full flex flex-col items-center justify-center h-64 text-[var(--color-text-3)]">
                        <FrownOutline className='text-7xl mb-4' />
                        <p className="text-sm">{t('search.noResults')}</p>
                        <p className="text-xs mt-1">{t('search.tryOtherKeywords')}</p>
                        {searchType === 'ConversationList' && showConversationPagination && (
                            <InfiniteScroll
                                loadMore={loadMoreConversationSessions}
                                hasMore={hasMoreConversationSessions}
                            />
                        )}
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
                                {searchResults.map((item) => renderConversationItem(item as SessionItem))}
                                {showConversationPagination && (
                                    <InfiniteScroll
                                        loadMore={loadMoreConversationSessions}
                                        hasMore={hasMoreConversationSessions}
                                    />
                                )}
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
                            searchResults.map((item) => renderWorkbenchItem(item as ChatApplicationItem))
                        )}
                    </div>
                )}
            </div>
        </div>
    );
}
