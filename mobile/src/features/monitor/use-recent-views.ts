'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useAuth } from '@/context/auth';
import { listMonitorObjects, resolveRecentViews } from '@/features/monitor/adapter';
import type { ResolvedMonitorRecentView } from '@/features/monitor/model';
import { readRecentViews } from '@/features/monitor/recent-views-storage';
import { getCurrentTeamCookie } from '@/utils/teamCookie';

export type RecentViewsStatus = 'loading' | 'ready' | 'error';

export function useRecentViews() {
  const { userInfo } = useAuth();
  const userId = userInfo?.id || 0;
  const teamId = getCurrentTeamCookie() || 'none';
  const [entries, setEntries] = useState<ResolvedMonitorRecentView[]>([]);
  const [status, setStatus] = useState<RecentViewsStatus>('loading');
  const requestId = useRef(0);

  const reload = useCallback(async (signal?: AbortSignal, preserveContent = false) => {
    const current = ++requestId.current;
    if (!preserveContent) setStatus('loading');
    try {
      const config = readRecentViews(userId, teamId);
      const objects = await listMonitorObjects(signal);
      const resolved = await resolveRecentViews(config, objects, signal);
      if (current !== requestId.current || signal?.aborted) return;
      setEntries(resolved);
      setStatus('ready');
    } catch (error) {
      if (current !== requestId.current || signal?.aborted) return;
      if (!preserveContent) setStatus('error');
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
