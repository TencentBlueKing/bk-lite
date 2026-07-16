import { useCallback, useEffect, useRef, useState } from 'react';
import type { NetworkTopologyRuntime } from '@/app/ops-analysis/types/networkTopology';
import { useTranslation } from '@/utils/i18n';

/**
 * 运行态轮询 hook(design.md §8, scenario "Runtime refresh has a request boundary"):
 * - 固定 60s 自动轮询(可由调用方覆盖)
 * - 手动刷新 vs 自动刷新并发时只允许一个 in-flight
 * - 整体失败时保留上一份 runtime,标记 stale
 */

export interface WeopsErrorPayload {
  /** 401/403 等致命错误(WeOps Token 失效)。 */
  fatal?: boolean;
  message?: string;
  code?: string;
}

export interface UseNetworkRefreshParams {
  canvasId: string | number | undefined;
  /** 拉取运行态的函数;抛错时整体失败。 */
  fetcher: (canvasId: string | number) => Promise<NetworkTopologyRuntime>;
  /** 自动刷新间隔；P0 默认 60s，传 0 可关闭。 */
  refreshIntervalMs?: number;
}

export interface UseNetworkRefreshReturn {
  runtime: NetworkTopologyRuntime | null;
  loading: boolean;
  refreshing: boolean;
  stale: boolean;
  fatalMessage: string | null;
  lastRefreshAt: string | null;
  refresh: () => Promise<void>;
}

const formatClockTime = (date: Date): string => {
  const h = String(date.getHours()).padStart(2, '0');
  const m = String(date.getMinutes()).padStart(2, '0');
  const s = String(date.getSeconds()).padStart(2, '0');
  return `${h}:${m}:${s}`;
};

const isFatalError = (error: unknown): WeopsErrorPayload | null => {
  if (!error) return null;
  if (error instanceof Error && /token|401|403|weops_token_invalid/i.test(error.message)) {
    return { fatal: true, message: error.message };
  }
  const maybe = error as WeopsErrorPayload;
  if (maybe && typeof maybe === 'object' && (maybe.fatal || maybe.code)) {
    return maybe;
  }
  return null;
};

export const useNetworkRefresh = ({
  canvasId,
  fetcher,
  refreshIntervalMs = 60_000,
}: UseNetworkRefreshParams): UseNetworkRefreshReturn => {
  const { t } = useTranslation();
  const [runtime, setRuntime] = useState<NetworkTopologyRuntime | null>(null);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [stale, setStale] = useState(false);
  const [fatalMessage, setFatalMessage] = useState<string | null>(null);
  const [lastRefreshAt, setLastRefreshAt] = useState<string | null>(null);
  const inFlightRef = useRef<Promise<void> | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const fetcherRef = useRef(fetcher);
  const runtimeRef = useRef<NetworkTopologyRuntime | null>(runtime);

  useEffect(() => {
    fetcherRef.current = fetcher;
  }, [fetcher]);

  useEffect(() => {
    runtimeRef.current = runtime;
  }, [runtime]);

  const refresh = useCallback(async () => {
    if (canvasId === undefined || canvasId === null || canvasId === '') return;
    if (inFlightRef.current) {
      // 并发请求回收:返回当前 in-flight,不发起第二次(design.md §8 边界场景)。
      return inFlightRef.current;
    }
    const task = (async () => {
      const isFirst = runtimeRef.current === null;
      if (isFirst) setLoading(true);
      else setRefreshing(true);
      try {
        const data = await fetcherRef.current(canvasId);
        setRuntime(data);
        setStale(false);
        setFatalMessage(null);
        setLastRefreshAt(formatClockTime(new Date()));
      } catch (err) {
        const fatal = isFatalError(err);
        if (fatal) {
          setFatalMessage(fatal.message ?? t('opsAnalysis.networkTopology.errors.tokenInvalid'));
          setStale(false);
          setRuntime(null);
          return;
        }
        // 非致命错误保留上一份运行态，避免 WeOps 单次超时把整张画布清空。
        setStale(runtimeRef.current !== null);
      } finally {
        setLoading(false);
        setRefreshing(false);
        inFlightRef.current = null;
      }
    })();
    inFlightRef.current = task;
    return task;
  }, [canvasId]);

  useEffect(() => {
    if (canvasId === undefined || canvasId === null || canvasId === '') {
      return undefined;
    }
    // 进入画布时主动拉一次,随后按 P0 需求默认 60s 自动刷新。
    void refresh();
    if (refreshIntervalMs > 0) {
      timerRef.current = setInterval(() => {
        void refresh();
      }, refreshIntervalMs);
    }
    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
    // 故意忽略 refresh(由 fetcherRef 维护),避免每次 refresh 引用变化
    // 重新挂 effect 触发额外请求。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canvasId, refreshIntervalMs]);

  return {
    runtime,
    loading,
    refreshing,
    stale,
    fatalMessage,
    lastRefreshAt,
    refresh,
  };
};
