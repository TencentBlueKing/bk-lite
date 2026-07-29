import { useState, useEffect, useCallback, useRef } from 'react';
import { SessionItem } from '@/types/conversation';
import {
    CONVERSATION_SESSION_CACHE_KEYS,
    scopedConversationCacheKey,
} from '@/utils/conversationCache';

const SESSIONS_CACHE_SCHEMA_VERSION = 2;

interface SessionsCache {
    version?: number;
    sessions: SessionItem[];
    timestamp: number; // 缓存时间戳
}

/**
 * 自定义 Hook：管理对话列表缓存
 * 使用 sessionStorage 存储，关闭标签页后自动清空
 */
export const useSessionsCache = (scope = 'all') => {
    const [cachedSessions, setCachedSessions] = useState<SessionItem[]>([]);
    const [scrollPosition, setScrollPosition] = useState<number>(0);
    const [isInitialized, setIsInitialized] = useState(false);
    const [hasFetched, setHasFetched] = useState(false);
    const [needRefresh, setNeedRefresh] = useState(false);

    // 从 sessionStorage 加载缓存
    useEffect(() => {
        const sessionsCacheKey = scopedConversationCacheKey(CONVERSATION_SESSION_CACHE_KEYS.sessions, scope);
        const scrollPositionKey = scopedConversationCacheKey(CONVERSATION_SESSION_CACHE_KEYS.scrollPosition, scope);
        const hasFetchedKey = scopedConversationCacheKey(CONVERSATION_SESSION_CACHE_KEYS.hasFetched, scope);
        const needRefreshKey = scopedConversationCacheKey(CONVERSATION_SESSION_CACHE_KEYS.needRefresh, scope);

        setCachedSessions([]);
        setScrollPosition(0);
        setHasFetched(false);
        setNeedRefresh(false);
        setIsInitialized(false);

        try {
            // 加载对话列表缓存
            const cached = sessionStorage.getItem(sessionsCacheKey);
            if (cached) {
                const data: SessionsCache = JSON.parse(cached);
                // 检查缓存是否过期（可选：设置60分钟过期）
                const now = Date.now();
                const CACHE_EXPIRE_TIME = 60 * 60 * 1000; // 60分钟
                if (
                    data.version === SESSIONS_CACHE_SCHEMA_VERSION
                    && now - data.timestamp < CACHE_EXPIRE_TIME
                ) {
                    setCachedSessions(data.sessions);
                } else {
                    // 缓存过期或结构升级，重新获取完整会话信息。
                    sessionStorage.removeItem(sessionsCacheKey);
                    sessionStorage.removeItem(hasFetchedKey);
                }
            }

            // 加载滚动位置
            const savedScrollPosition = sessionStorage.getItem(scrollPositionKey);
            if (savedScrollPosition) {
                setScrollPosition(Number(savedScrollPosition));
            }

            // 加载获取状态标记
            const fetchedFlag = sessionStorage.getItem(hasFetchedKey);
            if (fetchedFlag === 'true') {
                setHasFetched(true);
            }

            // 加载需要刷新标记
            const refreshFlag = sessionStorage.getItem(needRefreshKey);
            if (refreshFlag === 'true') {
                setNeedRefresh(true);
            }

            setIsInitialized(true);
        } catch (error) {
            console.error('Failed to load conversation cache:', error);
            setIsInitialized(true);
        }
    }, [scope]);

    // 更新会话列表缓存
    const updateSessionsCache = useCallback((sessions: SessionItem[]) => {
        // 内存状态是界面的主路径，sessionStorage 只做 best-effort 恢复。
        setCachedSessions(sessions);
        setHasFetched(true);
        try {
            const cacheData: SessionsCache = {
                version: SESSIONS_CACHE_SCHEMA_VERSION,
                sessions,
                timestamp: Date.now(),
            };
            sessionStorage.setItem(
                scopedConversationCacheKey(CONVERSATION_SESSION_CACHE_KEYS.sessions, scope),
                JSON.stringify(cacheData),
            );
            sessionStorage.setItem(
                scopedConversationCacheKey(CONVERSATION_SESSION_CACHE_KEYS.hasFetched, scope),
                'true',
            );
        } catch (error) {
            console.error('Failed to update sessions cache:', error);
        }
    }, [scope]);

    // 更新滚动位置（使用 ref 来避免频繁的状态更新）
    const scrollPositionRef = useRef<number>(scrollPosition);
    const scrollTimerRef = useRef<NodeJS.Timeout | null>(null);

    useEffect(() => () => {
        if (scrollTimerRef.current) {
            clearTimeout(scrollTimerRef.current);
        }
    }, [scope]);

    // 同步 ref 和 state
    useEffect(() => {
        scrollPositionRef.current = scrollPosition;
    }, [scrollPosition]);

    const updateScrollPosition = useCallback((position: number) => {
        try {
            // 立即更新 ref，避免状态更新导致的重渲染
            scrollPositionRef.current = position;

            // 使用防抖，只在停止滚动后保存到 sessionStorage
            if (scrollTimerRef.current) {
                clearTimeout(scrollTimerRef.current);
            }

            scrollTimerRef.current = setTimeout(() => {
                sessionStorage.setItem(
                    scopedConversationCacheKey(CONVERSATION_SESSION_CACHE_KEYS.scrollPosition, scope),
                    position.toString(),
                );
                setScrollPosition(position);
            }, 150); // 150ms 防抖延迟
        } catch (error) {
            console.error('Failed to update scroll position:', error);
        }
    }, [scope]);

    // 更新需要刷新标记
    const updateNeedRefresh = useCallback((refresh: boolean) => {
        setNeedRefresh(refresh);
        try {
            if (refresh) {
                sessionStorage.setItem(
                    scopedConversationCacheKey(CONVERSATION_SESSION_CACHE_KEYS.needRefresh, scope),
                    'true',
                );
            } else {
                sessionStorage.removeItem(
                    scopedConversationCacheKey(CONVERSATION_SESSION_CACHE_KEYS.needRefresh, scope),
                );
            }
        } catch (error) {
            console.error('Failed to update need refresh flag:', error);
        }
    }, [scope]);

    return {
        cachedSessions,
        scrollPosition,
        isInitialized,
        hasFetched,
        needRefresh,
        updateSessionsCache,
        updateScrollPosition,
        updateNeedRefresh,
    };
};
