'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useArchitectureApi } from '@/app/ops-analysis/api/architecture';
import type { ArchitectureNodeStatusItem } from './model';
import {
  chunkBoundUuids,
  combineStatusBatches,
  keptStatusForRequest,
  shouldPauseArchitectureStatusRefresh,
} from './status';

export function useArchitectureNodeStatus(options: {
  enabled: boolean;
  uuids: string[];
  intervalMs: number;
  refreshOnVisible?: boolean;
}) {
  const { queryNodeStatus } = useArchitectureApi();
  const queryRef = useRef(queryNodeStatus);
  queryRef.current = queryNodeStatus;
  const [byUuid, setByUuid] = useState<Record<string, ArchitectureNodeStatusItem>>({});
  const [phase, setPhase] = useState<'idle' | 'ready' | 'failed'>('idle');
  const [reloadKey, setReloadKey] = useState(0);
  const cacheRef = useRef<Record<string, ArchitectureNodeStatusItem>>({});
  const signature = options.uuids.join('\n');
  const refreshOnVisible = options.refreshOnVisible !== false;

  useEffect(() => {
    // Keep the last names while edit mode pauses polling, so cancel does not
    // flash Untitled before the next response.
    if (!options.enabled) return undefined;
    const requested = signature ? signature.split('\n') : [];
    if (!requested.length) {
      setByUuid({});
      setPhase('ready');
      return undefined;
    }
    const kept = keptStatusForRequest(cacheRef.current, requested);
    setByUuid(kept);
    setPhase(Object.keys(kept).length ? 'ready' : 'idle');

    let cancelled = false;
    let timer = 0;
    let seq = 0;
    const apply = (
      next: Record<string, ArchitectureNodeStatusItem>,
      nextPhase: 'ready' | 'failed',
      current: number,
    ) => {
      if (cancelled || current !== seq) return;
      cacheRef.current = { ...cacheRef.current, ...next };
      setByUuid(next);
      setPhase(nextPhase);
    };
    const run = () => {
      if (shouldPauseArchitectureStatusRefresh(typeof document !== 'undefined' && document.hidden)) {
        return;
      }
      const current = ++seq;
      const batches = chunkBoundUuids(requested);
      Promise.all(batches.map(async (uuids) => {
        try {
          const data = await queryRef.current(uuids);
          return {
            uuids,
            ok: true,
            items: Array.isArray(data?.items) ? data.items : [],
          };
        } catch {
          return { uuids, ok: false };
        }
      })).then((settled) => {
        const combined = combineStatusBatches(settled, cacheRef.current);
        apply(combined.byUuid, combined.failed ? 'failed' : 'ready', current);
      });
    };

    run();
    if (options.intervalMs > 0) {
      const arm = () => {
        timer = window.setTimeout(() => {
          run();
          if (!cancelled) arm();
        }, options.intervalMs);
      };
      arm();
    }
    const onVisibility = () => {
      if (!document.hidden) run();
    };
    if (refreshOnVisible) {
      document.addEventListener('visibilitychange', onVisibility);
    }
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
      if (refreshOnVisible) {
        document.removeEventListener('visibilitychange', onVisibility);
      }
    };
  }, [options.enabled, options.intervalMs, refreshOnVisible, reloadKey, signature]);

  const reload = useCallback(() => setReloadKey((current) => current + 1), []);

  return { byUuid, phase, reload };
}
