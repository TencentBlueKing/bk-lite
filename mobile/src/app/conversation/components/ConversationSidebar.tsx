import React, { useEffect, useCallback } from 'react';
import { SpinLoading, Mask } from 'antd-mobile';
import { CloseOutline, SetOutline, SearchOutline, AppstoreOutline, RightOutline } from 'antd-mobile-icons';
import { useAuth } from '@/context/auth';
import { useRouter } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import { sessionsItem } from '@/types/conversation';
import { getSessions } from '@/api/bot';
import { useRunningSessionIds } from '@/context/conversation';

interface ConversationSidebarProps {
    visible: boolean;
    onClose: () => void;
    currentBotId?: string;
    currentSessionId?: string;
    needRefresh?: boolean;
    onRefreshComplete?: () => void;
    sessions: sessionsItem[];
    onSessionsUpdate: (sessions: sessionsItem[]) => void;
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
    const router = useRouter();
    const { userInfo } = useAuth();
    const scrollContainerRef = React.useRef<HTMLDivElement>(null);

    // 获取正在运行 AI 响应的会话 ID 列表
    const runningSessionIds = useRunningSessionIds();

    useEffect(() => {
        // 等待缓存初始化完成
        if (!cacheInitialized) return;

        // 只在以下情况获取数据：
        // 1. 侧边栏打开 且 从未获取过数据（首次加载）
        // 2. 侧边栏打开 且 需要刷新（新对话产生）
        if (visible && (!hasFetched || needRefresh)) {
            fetchSessions();
        }
    }, [visible, needRefresh, hasFetched, cacheInitialized]);

    // 恢复滚动位置
    useEffect(() => {
        if (visible && scrollContainerRef.current && scrollPosition > 0) {
            // 使用 setTimeout 确保 DOM 渲染完成
            setTimeout(() => {
                if (scrollContainerRef.current) {
                    scrollContainerRef.current.scrollTop = scrollPosition;
                }
            }, 0);
        }
    }, [visible, scrollPosition]);

    // 监听滚动事件，保存滚动位置（使用 useRef 缓存回调，避免重新创建）
    const scrollHandlerRef = React.useRef(onScrollPositionChange);

    // 同步最新的回调函数
    useEffect(() => {
        scrollHandlerRef.current = onScrollPositionChange;
    }, [onScrollPositionChange]);

    const handleScroll = useCallback((e: React.UIEvent<HTMLDivElement>) => {
        const target = e.currentTarget;
        scrollHandlerRef.current(target.scrollTop);
    }, []);

    const fetchSessions = async () => {
        onLoadingChange(true);
        try {
            const response = await getSessions();
            if (!response.result) {
                throw new Error(response.message || 'Failed to fetch sessions');
            }
            onSessionsUpdate(response.data || []);
            // 通知父组件刷新完成
            onRefreshComplete?.();
        } catch (error) {
            console.error('getSessions error:', error);
        } finally {
            onLoadingChange(false);
        }
    };

    const handleSessionClick = (session: sessionsItem) => {
        if (session.bot_id === Number(currentBotId) && session.session_id === currentSessionId) {
            // 已经在当前会话，只关闭侧边栏
            onClose();
            return;
        }
        // 跳转到指定对话
        router.push(`/conversation?bot_id=${session.bot_id}&session_id=${session.session_id}`);
        onClose();
    };

    const renderContent = () => {
        if (loading) {
            return (
                <div className="h-full flex flex-col items-center justify-center">
                    <SpinLoading color="primary" />
                </div>
            );
        }

        if (sessions.length === 0) {
            return (
                <div className="h-full flex flex-col items-center justify-center text-[var(--color-text-3)]">
                    {t('chat.noConversations')}
                </div>
            );
        }

        return (
            <div>
                {sessions.map((session) => {
                    const isActive = session.bot_id === Number(currentBotId) && session.session_id === currentSessionId;
                    const isRunning = runningSessionIds.includes(session.session_id);
                    return (
                        <div
                            key={session.session_id}
                            onClick={() => handleSessionClick(session)}
                            className={`cursor-pointer text-base ${isActive ? 'bg-[var(--color-fill-2)] font-semibold' : ''} m-2 p-3 rounded-lg`}
                        >
                            <div className="flex items-center gap-2">
                                <div className="flex-1 truncate text-[var(--color-text-1)]">
                                    {session.title}
                                </div>
                                {isRunning && (
                                    <SpinLoading style={{ '--size': '16px' }} color="primary" />
                                )}
                            </div>
                        </div>
                    );
                })}
            </div>
        );
    };

    return (
        <>
            {/* 遮罩层 */}
            <Mask
                visible={visible}
                onMaskClick={onClose}
                opacity={0.4}
                className="z-[999]"
            />

            {/* 侧边栏 */}
            <div
                className={`fixed top-0 left-0 h-full w-80 bg-[var(--color-bg)] z-[1000] transition-transform duration-300 ease-out flex flex-col ${visible ? 'translate-x-0' : '-translate-x-full'}`} >
                {/* 侧边栏头部 */}
                <div className="flex gap-2 items-center justify-between px-4 py-3 flex-shrink-0">
                    <div className='flex-1 px-2 py-1 bg-[var(--color-background-body)] rounded-xl flex gap-2 items-center text-[var(--color-text-2)]' onClick={() => router.push('/search?type=ConversationList')}>
                        <SearchOutline className='text-xl' />
                        <span className='text-base'>{t('common.search')}</span>
                    </div>
                    <button
                        onClick={onClose}
                        className="flex-shrink-0"
                    >
                        <CloseOutline fontSize={20} className="text-[var(--color-text-1)]" />
                    </button>
                </div>

                {/* 侧边栏内容 */}
                <div
                    ref={scrollContainerRef}
                    onScroll={handleScroll}
                    className="flex-1 overflow-y-auto scrollbar-hide"
                >
                    <div className='flex justify-between items-center border-b border-[var(--color-border)]'
                        onClick={() => { router.push('/workbench'); onClose(); }}>
                        <div className="flex items-center gap-2 px-4 py-3 text-[var(--color-text-1)]">
                            <AppstoreOutline className='text-2xl' />
                            <span className='text-base'>{t('common.allApps')}</span>
                        </div>
                        <RightOutline className='text-base text-[var(--color-text-2)] mr-3' />
                    </div>
                    {renderContent()}
                </div>

                {/* 用户信息区域 */}
                <div className="border-t border-[var(--color-border)] bg-[var(--color-bg)] flex-shrink-0">
                    <div className="flex items-center justify-between p-4">
                        {/* 左侧：用户信息 */}
                        <div
                            className="flex items-center gap-2 flex-1 min-w-0 cursor-pointer "
                            onClick={() => {
                                router.push('/profile');
                                onClose();
                            }}
                        >
                            <div
                                className="flex items-center justify-center flex-shrink-0 rounded-full"
                                style={{
                                    width: '30px',
                                    height: '30px',
                                    backgroundColor: 'var(--color-primary)',
                                    color: 'white',
                                    fontSize: '16px',
                                    fontWeight: '500'
                                }}
                            >
                                {userInfo?.display_name?.charAt(0)?.toUpperCase() || userInfo?.username?.charAt(0)?.toUpperCase() || 'U'}
                            </div>
                            <div className="flex-1 min-w-0 overflow-hidden">
                                <div className="text-base text-[var(--color-text-1)] truncate">
                                    {userInfo?.display_name || userInfo?.username || '用户'}
                                </div>
                            </div>
                        </div>

                        {/* 右侧：设置图标 */}
                        <button
                            onClick={() => {
                                router.push('/profile');
                                onClose();
                            }}
                            className="p-2 hover:bg-[var(--color-fill-2)] rounded-lg transition-colors"
                        >
                            <SetOutline fontSize={22} className="text-[var(--color-text-2)]" />
                        </button>
                    </div>
                </div>
            </div>
        </>
    );
};
