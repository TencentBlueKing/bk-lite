'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { buildPresetQuery, mergePage, selectHighestLevel, type AlertLevel, type TodoAlert, type TodoViewKey } from './model';
import { listAlertLevels, listAlerts } from './adapter';

export interface FeedState {
  items: TodoAlert[];
  count: number;
  page: number;
  status: 'idle' | 'loading' | 'ready' | 'error';
}

export interface AlertFeedViewState {
  activeView: TodoViewKey;
  feeds: Record<TodoViewKey, FeedState>;
  levels: AlertLevel[];
  levelStatus: 'loading' | 'ready' | 'error';
}

const EMPTY_FEED: FeedState = { items: [], count: 0, page: 0, status: 'idle' };

function initialFeeds(): Record<TodoViewKey, FeedState> {
  return { mine: { ...EMPTY_FEED }, open: { ...EMPTY_FEED }, high: { ...EMPTY_FEED } };
}

export function useAlertFeed(initialState?: AlertFeedViewState) {
  const [activeView, setActiveView] = useState<TodoViewKey>(initialState?.activeView || 'mine');
  const [feeds, setFeeds] = useState<Record<TodoViewKey, FeedState>>(initialState?.feeds || initialFeeds);
  const [levels, setLevels] = useState<AlertLevel[]>(initialState?.levels || []);
  const [levelStatus, setLevelStatus] = useState<'loading' | 'ready' | 'error'>(initialState?.levelStatus || 'loading');
  const requestIds = useRef<Record<TodoViewKey, number>>({ mine: 0, open: 0, high: 0 });
  const levelRequestId = useRef(0);
  const feedsRef = useRef(feeds);
  const levelStatusRef = useRef(levelStatus);
  feedsRef.current = feeds;
  levelStatusRef.current = levelStatus;
  const highestLevel = useMemo(() => selectHighestLevel(levels), [levels]);

  const loadLevels = useCallback(async () => {
    const requestId = ++levelRequestId.current;
    setLevelStatus('loading');
    try {
      const next = await listAlertLevels();
      if (requestId !== levelRequestId.current) return;
      setLevels(next);
      setLevelStatus('ready');
    } catch (error) {
      if (requestId !== levelRequestId.current) return;
      setLevels([]);
      setLevelStatus('error');
      throw error;
    }
  }, []);

  const load = useCallback(async (view: TodoViewKey, page: number, preserveContent = false) => {
    const query = buildPresetQuery(view, page, highestLevel?.levelId);
    if (!query) {
      if (view === 'high' && levelStatus === 'ready') {
        setFeeds((current) => ({ ...current, high: { ...EMPTY_FEED, status: 'ready' } }));
      }
      return;
    }
    const requestId = ++requestIds.current[view];
    if (!preserveContent) {
      setFeeds((current) => ({ ...current, [view]: { ...current[view], status: 'loading' } }));
    }
    try {
      const result = await listAlerts(query);
      if (requestId !== requestIds.current[view]) return;
      setFeeds((current) => ({
        ...current,
        [view]: {
          items: page === 1 ? result.items : mergePage(current[view].items, result.items, (item) => item.id),
          count: result.count,
          page,
          status: 'ready',
        },
      }));
    } catch (error) {
      if (requestId !== requestIds.current[view]) return;
      setFeeds((current) => ({
        ...current,
        [view]: { ...current[view], status: preserveContent ? 'ready' : 'error' },
      }));
      throw error;
    }
  }, [highestLevel?.levelId, levelStatus]);

  useEffect(() => {
    if (initialState?.levelStatus !== 'ready') void loadLevels().catch(() => undefined);
    return () => {
      levelRequestId.current += 1;
      for (const view of ['mine', 'open', 'high'] as const) requestIds.current[view] += 1;
    };
  }, [initialState?.levelStatus, loadLevels]);

  useEffect(() => {
    for (const view of ['mine', 'open', 'high'] as const) {
      if (feeds[view].status !== 'idle') continue;
      if (view === 'high' && levelStatus !== 'ready') continue;
      void load(view, 1).catch(() => undefined);
    }
  }, [feeds, levelStatus, load]);

  const refresh = useCallback(() => load(activeView, 1, true), [activeView, load]);
  const revalidate = useCallback(async () => {
    const currentFeeds = feedsRef.current;
    const currentLevelStatus = levelStatusRef.current;
    const views = (['mine', 'open', 'high'] as const).filter((view) => {
      if (currentFeeds[view].status === 'idle') return false;
      if (view === 'high' && currentLevelStatus !== 'ready') return false;
      return true;
    });
    if (views.length === 0) return true;
    const results = await Promise.allSettled(views.map((view) => load(view, 1, true)));
    return results.some((result) => result.status === 'fulfilled');
  }, [load]);
  const retry = useCallback(() => (
    activeView === 'high' && levelStatus === 'error' ? loadLevels() : load(activeView, 1)
  ), [activeView, levelStatus, load, loadLevels]);
  const loadMore = useCallback(
    () => load(activeView, feeds[activeView].page + 1, true),
    [activeView, feeds, load],
  );

  const viewState = useMemo<AlertFeedViewState>(() => ({
    activeView,
    feeds,
    levels,
    levelStatus,
  }), [activeView, feeds, levels, levelStatus]);

  return {
    activeView,
    setActiveView,
    feed: feeds[activeView],
    feeds,
    levels,
    levelStatus,
    refresh,
    revalidate,
    retry,
    loadMore,
    viewState,
  };
}
