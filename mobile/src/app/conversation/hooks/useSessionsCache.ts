import { useState, useEffect, useCallback, useRef } from 'react';
import { sessionsItem } from '@/types/conversation';

const SESSIONS_CACHE_KEY = 'bk_lite_sessions_cache';
const SCROLL_POSITION_KEY = 'bk_lite_sidebar_scroll_position';
const HAS_FETCHED_KEY = 'bk_lite_sessions_has_fetched';
const NEED_REFRESH_KEY = 'bk_lite_sessions_need_refresh';

interface SessionsCache {
    sessions: sessionsItem[];
    timestamp: number; // 缓存时间戳
}

/**
 * 自定义 Hook：管理对话列表缓存
 * 使用 sessionStorage 存储，关闭标签页后自动清空
 */
export const useSessionsCache = () => {
    const [cachedSessions, setCachedSessions] = useState<sessionsItem[]>([]);
    const [scrollPosition, setScrollPosition] = useState<number>(0);
    const [isInitialized, setIsInitialized] = useState(false);
    const [hasFetched, setHasFetched] = useState(false);
    const [needRefresh, setNeedRefresh] = useState(false);

    // 从 sessionStorage 加载缓存
    useEffect(() => {
        try {
            // 加载对话列表缓存
            const cached = sessionStorage.getItem(SESSIONS_CACHE_KEY);
            if (cached) {
                const data: SessionsCache = JSON.parse(cached);
                // 检查缓存是否过期（可选：设置60分钟过期）
                const now = Date.now();
                const CACHE_EXPIRE_TIME = 60 * 60 * 1000; // 60分钟
                if (now - data.timestamp < CACHE_EXPIRE_TIME) {
                    setCachedSessions(data.sessions);
                } else {
                    // 缓存过期，清除所有相关数据
                    sessionStorage.removeItem(SESSIONS_CACHE_KEY);
                    sessionStorage.removeItem(HAS_FETCHED_KEY);
                }
            }

            // 加载滚动位置
            const savedScrollPosition = sessionStorage.getItem(SCROLL_POSITION_KEY);
            if (savedScrollPosition) {
                setScrollPosition(Number(savedScrollPosition));
            }

            // 加载获取状态标记
            const fetchedFlag = sessionStorage.getItem(HAS_FETCHED_KEY);
            if (fetchedFlag === 'true') {
                setHasFetched(true);
            }

            // 加载需要刷新标记
            const refreshFlag = sessionStorage.getItem(NEED_REFRESH_KEY);
            if (refreshFlag === 'true') {
                setNeedRefresh(true);
            }

            setIsInitialized(true);
        } catch (error) {
            console.error('Failed to load conversation cache:', error);
            setIsInitialized(true);
        }
    }, []);

    // 更新会话列表缓存
    const updateSessionsCache = useCallback((sessions: sessionsItem[]) => {
        try {
            const cacheData: SessionsCache = {
                sessions,
                timestamp: Date.now(),
            };
            sessionStorage.setItem(SESSIONS_CACHE_KEY, JSON.stringify(cacheData));
            sessionStorage.setItem(HAS_FETCHED_KEY, 'true');
            setCachedSessions(sessions);
            setHasFetched(true);
        } catch (error) {
            console.error('Failed to update sessions cache:', error);
        }
    }, []);

    // 更新滚动位置（使用 ref 来避免频繁的状态更新）
    const scrollPositionRef = useRef<number>(scrollPosition);
    const scrollTimerRef = useRef<NodeJS.Timeout | null>(null);

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
                sessionStorage.setItem(SCROLL_POSITION_KEY, position.toString());
                setScrollPosition(position);
            }, 150); // 150ms 防抖延迟
        } catch (error) {
            console.error('Failed to update scroll position:', error);
        }
    }, []);

    // 更新需要刷新标记
    const updateNeedRefresh = useCallback((refresh: boolean) => {
        try {
            if (refresh) {
                sessionStorage.setItem(NEED_REFRESH_KEY, 'true');
            } else {
                sessionStorage.removeItem(NEED_REFRESH_KEY);
            }
            setNeedRefresh(refresh);
        } catch (error) {
            console.error('Failed to update need refresh flag:', error);
        }
    }, []);

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
