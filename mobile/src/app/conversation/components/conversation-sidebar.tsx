import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Avatar, InfiniteScroll, SearchBar, SpinLoading } from 'antd-mobile';
import {
    AppstoreOutline,
    LeftOutline,
    MoreOutline,
    SearchOutline,
    SetOutline,
} from 'antd-mobile-icons';
import { useRouter } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import { useLocale } from '@/context/locale';
import { SessionItem } from '@/types/conversation';
import { getMobileSessions } from '@/api/bot';
import { useAuth } from '@/context/auth';
import { useSessionDeletion } from '@/app/conversation/hooks';
import { buildConversationHref } from '@/utils/conversationRoute';
import MobilePullToRefresh from '@/components/mobile-pull-to-refresh';
import { formatSessionActivity } from '@/app/conversations/session-time';
import {
    hasMoreSessions,
    mergeSessionItems,
    MOBILE_SESSION_PAGE_SIZE,
    shouldShowSessionPagination,
} from '@/utils/sessionPagination';

interface ConversationSidebarProps {
    visible: boolean;
    onClose: () => void;
    currentBotId?: string;
    currentNodeId?: string;
    currentAppName?: string;
    currentAppAvatar?: string;
    currentSessionId?: string;
    needRefresh?: boolean;
    onRefreshComplete?: () => void;
    sessions: SessionItem[];
    onSessionsUpdate: (sessions: SessionItem[]) => void;
    loading: boolean;
    onLoadingChange: (loading: boolean) => void;
    scrollPosition: number;
    onScrollPositionChange: (position: number) => void;
    hasFetched: boolean;
    cacheInitialized: boolean;
}

export const ConversationSidebar: React.FC<ConversationSidebarProps> = ({
    visible,
    onClose,
    currentBotId,
    currentNodeId,
    currentAppName,
    currentAppAvatar,
    currentSessionId,
    needRefresh = false,
    onRefreshComplete,
    sessions,
    onSessionsUpdate,
    loading,
    onLoadingChange,
    scrollPosition,
    onScrollPositionChange,
    hasFetched,
    cacheInitialized,
}) => {
    const { t } = useTranslation();
    const { locale } = useLocale();
    const router = useRouter();
    const { userInfo } = useAuth();
    const scrollContainerRef = React.useRef<HTMLDivElement>(null);
    const scrollHandlerRef = React.useRef(onScrollPositionChange);
    const fetchingRef = React.useRef(false);
    const requestGenerationRef = React.useRef(0);
    const requestAbortRef = React.useRef<AbortController | null>(null);
    const [searchValue, setSearchValue] = useState('');
    const [loadFailed, setLoadFailed] = useState(false);
    const [sessionCount, setSessionCount] = useState<number | null>(null);
    const [nextPage, setNextPage] = useState(1);

    const fetchSessions = useCallback(async ({
        append = false,
        page = 1,
        preserveContent = false,
    } = {}) => {
        if (!currentBotId || !currentNodeId || fetchingRef.current) return;

        const requestGeneration = requestGenerationRef.current + 1;
        requestGenerationRef.current = requestGeneration;
        const abortController = new AbortController();
        requestAbortRef.current = abortController;
        fetchingRef.current = true;
        if (!preserveContent) {
            onLoadingChange(true);
            setLoadFailed(false);
        }
        try {
            const response = await getMobileSessions({
                bot_id: Number(currentBotId),
                node_id: currentNodeId,
                page,
                page_size: MOBILE_SESSION_PAGE_SIZE,
            }, { signal: abortController.signal });
            if (abortController.signal.aborted || requestGeneration !== requestGenerationRef.current) return;
            const items = response.data?.items;
            if (!response.result || !items) {
                throw new Error(response.message || 'Failed to fetch sessions');
            }
            onSessionsUpdate(append ? mergeSessionItems(sessions, items) : items);
            setSessionCount(response.data?.count ?? items.length);
            setNextPage(page + 1);
            setLoadFailed(false);
            onRefreshComplete?.();
        } catch (error) {
            if (abortController.signal.aborted || (error instanceof Error && error.name === 'AbortError')) {
                return;
            }
            console.error('getMobileSessions error:', error);
            if (preserveContent) {
                throw error;
            }
            setLoadFailed(true);
        } finally {
            if (requestGeneration === requestGenerationRef.current) {
                fetchingRef.current = false;
                requestAbortRef.current = null;
                if (!preserveContent) {
                    onLoadingChange(false);
                }
            }
        }
    }, [currentBotId, currentNodeId, onLoadingChange, onRefreshComplete, onSessionsUpdate, sessions]);

    useEffect(() => () => {
        requestGenerationRef.current += 1;
        requestAbortRef.current?.abort();
        requestAbortRef.current = null;
        fetchingRef.current = false;
        onLoadingChange(false);
    }, [currentBotId, currentNodeId, onLoadingChange]);

    useEffect(() => {
        if (!cacheInitialized || !currentNodeId) return;
        if (visible && (!hasFetched || needRefresh)) {
            void fetchSessions({ preserveContent: sessions.length > 0 });
        }
    }, [visible, needRefresh, hasFetched, cacheInitialized, currentNodeId, fetchSessions, sessions.length]);

    useEffect(() => {
        if (visible && scrollContainerRef.current && scrollPosition > 0) {
            requestAnimationFrame(() => {
                if (scrollContainerRef.current) {
                    scrollContainerRef.current.scrollTop = scrollPosition;
                }
            });
        }
    }, [visible, scrollPosition]);

    useEffect(() => {
        scrollHandlerRef.current = onScrollPositionChange;
    }, [onScrollPositionChange]);

    const handleScroll = useCallback((event: React.UIEvent<HTMLDivElement>) => {
        scrollHandlerRef.current(event.currentTarget.scrollTop);
    }, []);

    const filteredSessions = useMemo(() => {
        const keyword = searchValue.trim().toLocaleLowerCase();
        if (!keyword) return sessions;
        return sessions.filter((session) => (
            (session.title || t('conversations.untitled')).toLocaleLowerCase().includes(keyword)
        ));
    }, [searchValue, sessions, t]);

    const handleSessionClick = (session: SessionItem) => {
        if (session.bot_id === Number(currentBotId) && session.session_id === currentSessionId) {
            onClose();
            return;
        }
        router.push(buildConversationHref({
            botId: session.bot_id,
            sessionId: session.session_id,
            nodeId: session.node_id || currentNodeId,
        }));
        onClose();
    };

    const handleSessionDeleted = useCallback(async (session: SessionItem) => {
        if (session.session_id === currentSessionId && currentBotId) {
            onClose();
            router.replace(buildConversationHref({
                botId: currentBotId,
                nodeId: currentNodeId,
            }));
        }

        await fetchSessions();
    }, [currentBotId, currentNodeId, currentSessionId, fetchSessions, onClose, router]);
    const { deletingSessionId, isSessionRunning, openSessionActions } = useSessionDeletion({
        fallbackNodeId: currentNodeId,
        onDeleted: handleSessionDeleted,
    });
    const loadMoreSessions = useCallback(() => fetchSessions({
        append: true,
        page: nextPage,
        preserveContent: true,
    }), [fetchSessions, nextPage]);
    const hasMore = sessionCount === null
        ? sessions.length >= MOBILE_SESSION_PAGE_SIZE
        : hasMoreSessions(sessions, sessionCount);
    const showPagination = shouldShowSessionPagination(sessionCount, sessions.length);

    const renderContent = () => {
        if (loading) {
            return (
                <div className="flex min-h-40 items-center justify-center">
                    <SpinLoading color="primary" />
                </div>
            );
        }

        if (loadFailed) {
            return (
                <div className="flex min-h-40 flex-col items-center justify-center gap-3 px-6 text-center text-[var(--color-text-3)]">
                    <span>{t('conversations.loadFailed')}</span>
                    <button
                        type="button"
                        className="min-h-11 rounded-lg px-4 text-[var(--color-primary)] active:bg-[var(--color-fill-2)]"
                        onClick={() => void fetchSessions()}
                    >
                        {t('common.retry')}
                    </button>
                </div>
            );
        }

        if (sessions.length === 0) {
            return (
                <div className="flex min-h-40 items-center justify-center px-6 text-center text-[var(--color-text-3)]">
                    {t('chat.noConversations')}
                </div>
            );
        }

        if (filteredSessions.length === 0) {
            return (
                <div className="flex min-h-40 flex-col items-center justify-center gap-2 px-6 text-center text-[var(--color-text-3)]">
                    <SearchOutline className="text-3xl" aria-hidden="true" />
                    <span>{t('search.noResults')}</span>
                    <span className="text-sm">{t('search.tryOtherKeywords')}</span>
                    {showPagination && (
                        <InfiniteScroll loadMore={loadMoreSessions} hasMore={hasMore} />
                    )}
                </div>
            );
        }

        return (
            <div className="px-2 pb-4">
                {filteredSessions.map((session) => {
                    const isActive = session.bot_id === Number(currentBotId) && session.session_id === currentSessionId;
                    const isRunning = isSessionRunning(session.session_id);
                    const isDeleting = deletingSessionId === session.session_id;
                    const activityTime = session.updated_at || session.created_at;

                    return (
                        <div
                            key={session.session_id}
                            className={`group my-1 flex min-h-12 items-center rounded-lg ${isActive ? 'bg-[var(--color-fill-2)]' : 'active:bg-[var(--color-fill-1)]'}`}
                        >
                            <button
                                type="button"
                                className="flex min-w-0 flex-1 items-center gap-2 px-3 py-3 text-left leading-6"
                                aria-current={isActive ? 'page' : undefined}
                                onClick={() => handleSessionClick(session)}
                            >
                                <span className={`min-w-0 flex-1 truncate text-[17px] leading-6 text-[var(--color-text-1)] ${isActive ? 'font-semibold' : ''}`}>
                                    {session.title || t('conversations.untitled')}
                                </span>
                                {activityTime && (
                                    <time
                                        className="flex-shrink-0 whitespace-nowrap text-xs font-normal leading-none tabular-nums text-[var(--color-text-4)]"
                                        dateTime={activityTime}
                                    >
                                        {formatSessionActivity(activityTime, locale, t('common.yesterday'))}
                                    </time>
                                )}
                            </button>
                            {isRunning && (
                                <span className="flex min-h-11 min-w-11 items-center justify-center" aria-label={t('chat.executing')}>
                                    <SpinLoading style={{ '--size': '16px' }} color="primary" />
                                </span>
                            )}
                            <button
                                type="button"
                                className="flex min-h-11 min-w-11 items-center justify-center rounded-lg text-[var(--color-text-2)] active:bg-[var(--color-fill-2)]"
                                aria-label={t('chat.conversationActions')}
                                disabled={isDeleting}
                                onClick={() => openSessionActions(session)}
                            >
                                {isDeleting
                                    ? <SpinLoading style={{ '--size': '16px' }} color="primary" />
                                    : <MoreOutline fontSize={20} aria-hidden="true" />}
                            </button>
                        </div>
                    );
                })}
                {showPagination && (
                    <InfiniteScroll loadMore={loadMoreSessions} hasMore={hasMore} />
                )}
            </div>
        );
    };

    return (
            <aside
                id="conversation-history-drawer"
                tabIndex={-1}
                aria-hidden={!visible}
                aria-label={t('navigation.conversations')}
                className="flex h-full max-h-full w-full flex-col overflow-hidden bg-[var(--color-bg)] focus:outline-none"
            >
                <div className="flex flex-shrink-0 items-center px-2 pb-1 pt-[max(8px,env(safe-area-inset-top))]">
                    <button
                        type="button"
                        className="flex min-h-11 min-w-0 flex-1 items-center gap-1 rounded-lg px-2 text-left text-[var(--color-text-1)] active:bg-[var(--color-fill-1)]"
                        onClick={() => {
                            router.push('/workbench');
                            onClose();
                        }}
                    >
                        <LeftOutline className="flex-shrink-0 text-lg" aria-hidden="true" />
                        <span className="truncate text-base font-medium">{t('chat.backToAppList')}</span>
                    </button>
                </div>

                <div className="flex flex-shrink-0 items-center gap-3 px-4 pb-3 pt-2">
                    {currentAppAvatar ? (
                        <Avatar
                            src={currentAppAvatar}
                            style={{ '--size': '32px', '--border-radius': '10px' }}
                            className="flex-shrink-0"
                        />
                    ) : (
                        <span className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-[10px] bg-[var(--color-fill-2)] text-[var(--color-text-2)]">
                            <AppstoreOutline fontSize={18} aria-hidden="true" />
                        </span>
                    )}
                    <h2 className="min-w-0 flex-1 truncate text-base font-semibold text-[var(--color-text-1)]">
                        {currentAppName || t('navigation.apps')}
                    </h2>
                </div>

                <div className="px-3 pb-3" role="search">
                    <SearchBar
                        aria-label={t('common.search')}
                        placeholder={t('common.search')}
                        value={searchValue}
                        onChange={setSearchValue}
                        onClear={() => setSearchValue('')}
                        style={{
                            '--border-radius': '12px',
                            '--background': 'var(--color-background-body)',
                            '--height': '44px',
                        }}
                    />
                </div>

                <div
                    ref={scrollContainerRef}
                    onScroll={handleScroll}
                    className="min-h-0 flex-1 overflow-y-auto overscroll-contain scrollbar-hide"
                >
                    <MobilePullToRefresh
                        disabled={!currentBotId || !currentNodeId}
                        onRefresh={() => fetchSessions({ preserveContent: true })}
                    >
                        <div className="min-h-full">
                            {renderContent()}
                        </div>
                    </MobilePullToRefresh>
                </div>

                <button
                    type="button"
                    className="flex min-h-14 flex-shrink-0 items-center gap-3 border-t border-[var(--color-border)] px-4 pb-[max(8px,env(safe-area-inset-bottom))] pt-2 text-left active:bg-[var(--color-fill-1)]"
                    onClick={() => {
                        router.push('/profile');
                        onClose();
                    }}
                >
                    <span className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-[var(--color-primary)] text-sm font-medium text-[var(--color-text-on-primary)]">
                        {userInfo?.display_name?.charAt(0)?.toUpperCase()
                            || userInfo?.username?.charAt(0)?.toUpperCase()
                            || 'U'}
                    </span>
                    <span className="min-w-0 flex-1 truncate text-base text-[var(--color-text-1)]">
                        {userInfo?.display_name || userInfo?.username || t('account.user')}
                    </span>
                    <SetOutline fontSize={20} className="text-[var(--color-text-3)]" aria-hidden="true" />
                </button>
            </aside>
    );
};
