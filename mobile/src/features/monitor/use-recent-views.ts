'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useAuth } from '@/context/auth';
import { listMonitorObjects, resolveRecentViews } from '@/features/monitor/adapter';
import type { ResolvedMonitorRecentView } from '@/features/monitor/model';
import { monitorRecentViewsResolutionStatus } from '@/features/monitor/model';
import { readRecentViews } from '@/features/monitor/recent-views-storage';
import { getCurrentTeamCookie } from '@/utils/teamCookie';

export type RecentViewsStatus = 'loading' | 'ready' | 'empty' | 'partial' | 'unavailable' | 'refresh-error' | 'error';

export function useRecentViews() {
  const { userInfo } = useAuth();
  const userId = userInfo?.id || 0;
  const teamId = getCurrentTeamCookie() || 'none';
  const [entries, setEntries] = useState<ResolvedMonitorRecentView[]>([]);
  const entriesRef = useRef<ResolvedMonitorRecentView[]>([]);
  const [status, setStatus] = useState<RecentViewsStatus>('loading');
  const requestId = useRef(0);

  const reload = useCallback(async (signal?: AbortSignal, preserveContent = false) => {
    const current = ++requestId.current;
    if (!preserveContent) setStatus('loading');
    try {
      const config = readRecentViews(userId, teamId);
      const objects = await listMonitorObjects(signal);
      const resolution = await resolveRecentViews(config, objects, signal);
      if (current !== requestId.current || signal?.aborted) return;
      const nextStatus = monitorRecentViewsResolutionStatus(
        resolution,
        preserveContent && entriesRef.current.length > 0,
      );
      if (nextStatus !== 'refresh-error') {
        entriesRef.current = resolution.entries;
        setEntries(resolution.entries);
      }
      setStatus(nextStatus);
    } catch (error) {
      if (current !== requestId.current || signal?.aborted) return;
      setStatus(preserveContent && entriesRef.current.length > 0 ? 'refresh-error' : 'error');
      throw error;
    }
  }, [teamId, userId]);

  useEffect(() => {
    const controller = new AbortController();
    void reload(controller.signal).catch(() => undefined);
    return () => {
      requestId.current += 1;
      controller.abort();
    };
  }, [reload]);

  return { entries, status, reload };
}
