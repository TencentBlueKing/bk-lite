'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useArchitectureApi } from '@/app/ops-analysis/api/architecture';
import {
  ARCHITECTURE_METRIC_BATCH_SIZE,
  combineMetricBatches,
  type DisplayMetricItem,
  type MetricObjectColumns,
} from './displayMetrics';
import { chunkBoundUuids, shouldPauseArchitectureStatusRefresh } from './status';

export function useArchitectureDisplayMetrics(options: {
  enabled: boolean;
  uuids: string[];
  intervalMs: number;
  refreshOnVisible?: boolean;
}) {
  const { queryDisplayMetrics } = useArchitectureApi();
  const queryRef = useRef(queryDisplayMetrics);
  queryRef.current = queryDisplayMetrics;
  const [byUuid, setByUuid] = useState<Record<string, DisplayMetricItem>>({});
  const [objects, setObjects] = useState<Record<string, MetricObjectColumns>>({});
  const [phase, setPhase] = useState<'idle' | 'ready' | 'failed'>('idle');
  const [reloadKey, setReloadKey] = useState(0);
  const cacheRef = useRef<Record<string, DisplayMetricItem>>({});
  const signature = options.uuids.join('\n');
  const refreshOnVisible = options.refreshOnVisible !== false;

  useEffect(() => {
    if (!options.enabled) return undefined;
    const requested = signature ? signature.split('\n') : [];
    if (!requested.length) {
      setByUuid({});
      setPhase('ready');
      return undefined;
    }
    const kept: Record<string, DisplayMetricItem> = {};
    for (const uuid of requested) {
      const row = cacheRef.current[uuid];
      if (row) kept[uuid] = row;
    }
    setByUuid(kept);
    setPhase(Object.keys(kept).length ? 'ready' : 'idle');

    let cancelled = false;
    let timer = 0;
    let retryTimer = 0;
    let seq = 0;
    const apply = (settled: Array<{ uuids: string[]; ok: boolean; data?: unknown }>, current: number) => {
      if (cancelled || current !== seq) return;
      const combined = combineMetricBatches(settled, cacheRef.current);
      cacheRef.current = { ...cacheRef.current, ...combined.byUuid };
      for (const uuid of requested) {
        if (!combined.byUuid[uuid]) delete cacheRef.current[uuid];
      }
      setByUuid(combined.byUuid);
      if (Object.keys(combined.objects).length) {
        setObjects((currentObjects) => ({ ...currentObjects, ...combined.objects }));
      }
      setPhase(combined.failed ? 'failed' : 'ready');
    };
    const requestBatches = () => {
      const batches = chunkBoundUuids(requested, ARCHITECTURE_METRIC_BATCH_SIZE);
      return Promise.all(batches.map(async (uuids) => {
        try {
          const data = await queryRef.current(uuids);
          return { uuids, ok: true, data };
        } catch {
          return { uuids, ok: false };
        }
      }));
    };
    const run = () => {
      if (shouldPauseArchitectureStatusRefresh(typeof document !== 'undefined' && document.hidden)) {
        return;
      }
      const current = ++seq;
      requestBatches().then((settled) => {
        if (cancelled || current !== seq) return;
        if (settled.some((batch) => !batch.ok)) {
          retryTimer = window.setTimeout(() => {
            if (cancelled || current !== seq) return;
            requestBatches().then((retried) => apply(retried, current));
          }, 500);
          return;
        }
        apply(settled, current);
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
      window.clearTimeout(retryTimer);
      if (refreshOnVisible) {
        document.removeEventListener('visibilitychange', onVisibility);
      }
    };
  }, [options.enabled, options.intervalMs, refreshOnVisible, reloadKey, signature]);

  const reload = useCallback(() => setReloadKey((current) => current + 1), []);

  return { byUuid, objects, phase, reload };
}
