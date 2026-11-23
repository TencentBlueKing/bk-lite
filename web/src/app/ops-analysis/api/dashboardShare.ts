import { useCallback } from 'react';
import useApiClient from '@/utils/request';
import { CANVAS_TYPE_REGISTRY } from '@/app/ops-analysis/constants/canvasTypes';
import type {
  CanvasShareLinkDto,
  CanvasShareResourceType,
  SharedCanvasDto,
} from '@/app/ops-analysis/types/dashboardShare';

const shareInflight = new Map<string, Promise<unknown>>();
const SHARE_RESULT_RETAIN_MS = 2000;

/** 重叠调用共用一次请求。成功结果只留短暂窗口，盖住完成后才挂上的第二次 effect。 */
export function shareSingleFlight<T>(key: string, run: () => Promise<T>): Promise<T> {
  const existing = shareInflight.get(key) as Promise<T> | undefined;
  if (existing) return existing;
  const promise = run().then(
    (value) => {
      setTimeout(() => {
        if (shareInflight.get(key) === promise) shareInflight.delete(key);
      }, SHARE_RESULT_RETAIN_MS);
      return value;
    },
    (error: unknown) => {
      if (shareInflight.get(key) === promise) shareInflight.delete(key);
      throw error;
    },
  );
  shareInflight.set(key, promise);
  return promise;
}

export function resetShareSingleFlightForTests() {
  shareInflight.clear();
}

/** 未登录也可调用：不走 Bearer 拦截器，避免永久 token 进入登录 callbackUrl 前无法 prepare。 */
export function prepareShareToken(token: string): Promise<{ state: string }> {
  return shareSingleFlight(`prepare:${token}`, async () => {
    const response = await fetch(
      '/api/proxy/operation_analysis/api/dashboard_share/prepare/',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token }),
        credentials: 'include',
      },
    );
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || payload?.result === false) {
      throw new Error(payload?.message || 'prepare share failed');
    }
    return (payload?.data ?? payload) as { state: string };
  });
}

export const useCanvasShareApi = () => {
  const { get, post } = useApiClient();

  const createShare = useCallback(
    (
      resourceType: CanvasShareResourceType,
      resourceId: string | number,
    ): Promise<CanvasShareLinkDto> => {
      const endpoint = CANVAS_TYPE_REGISTRY[resourceType].endpoint.replace(/\/$/, '');
      return post(`${endpoint}/${resourceId}/share/`, {});
    },
    [post],
  );

  const exchangeShare = useCallback(
    (payload: { token?: string; state?: string }) =>
      shareSingleFlight(
        `exchange:${payload.state || payload.token || ''}`,
        () => post('/operation_analysis/api/dashboard_share/exchange/', payload),
      ),
    [post],
  );

  const getSharedCanvas = useCallback(
    (sessionId: string): Promise<SharedCanvasDto> =>
      get(`/operation_analysis/api/dashboard_share/session/${sessionId}/`),
    [get],
  );

  const querySharedDataSource = useCallback(
    (
      sessionId: string,
      dataSourceId: number,
      params?: unknown,
      options?: { suppressErrorNotification?: boolean },
    ) =>
      post(
        `/operation_analysis/api/dashboard_share/session/${sessionId}/query/${dataSourceId}/`,
        params,
        options?.suppressErrorNotification
          ? { suppressErrorNotification: true }
          : undefined,
      ),
    [post],
  );

  const getSharedDataSources = useCallback(
    (sessionId: string) =>
      get(`/operation_analysis/api/dashboard_share/session/${sessionId}/data_sources/`),
    [get],
  );

  const resolveSharedOptionSource = useCallback(
    (
      sessionId: string,
      body: { sourceId?: number; builtinKey?: string; sourceRef?: string },
    ) =>
      post(
        `/operation_analysis/api/dashboard_share/session/${sessionId}/resolve_option_source/`,
        {
          sourceId: body.sourceId,
          builtinKey: body.builtinKey,
          sourceRef: body.sourceRef
            ? { type: 'rest_api', value: body.sourceRef }
            : undefined,
        },
        { suppressErrorNotification: true },
      ) as Promise<{ status?: string; id?: number }>,
    [post],
  );

  const getSharedNetworkTopologyMetricValues = useCallback(
    (
      sessionId: string,
      items: Array<{
        request_id: string;
        node_ref: Record<string, unknown>;
        metric_ref: { metric_field: string; result_table_id: string };
        dimensions?: Record<string, string>;
        condition_filter?: Array<{ dimension_id: string; value: string[] }>;
        display_mode?: 'aggregate' | 'dimension';
        aggregate_type?: 'sum' | 'max' | 'min' | 'mean' | 'last';
      }>,
    ) =>
      post(
        `/operation_analysis/api/dashboard_share/session/${sessionId}/network_topology/metric_values/`,
        { items },
      ),
    [post],
  );

  const getSharedNetworkTopologyLinkRuntime = useCallback(
    (
      sessionId: string,
      payload: {
        link: unknown;
        nodes?: unknown;
      },
    ) =>
      post(
        `/operation_analysis/api/dashboard_share/session/${sessionId}/network_topology/link_runtime/`,
        payload,
      ),
    [post],
  );

  return {
    createShare,
    exchangeShare,
    getSharedCanvas,
    querySharedDataSource,
    getSharedDataSources,
    resolveSharedOptionSource,
    getSharedNetworkTopologyMetricValues,
    getSharedNetworkTopologyLinkRuntime,
  };
};

/** @deprecated Prefer useCanvasShareApi */
export const useDashboardShareApi = () => {
  const api = useCanvasShareApi();
  return {
    createShare: (dashboardId: string | number) => api.createShare('dashboard', dashboardId),
    exchangeShare: api.exchangeShare,
    getSharedDashboard: api.getSharedCanvas,
    querySharedDataSource: api.querySharedDataSource,
    getSharedDataSources: api.getSharedDataSources,
  };
};
