import { useCallback } from 'react';
import useApiClient from '@/utils/request';
import type { DashboardShareLinkDto } from '@/app/ops-analysis/types/dashboardShare';

/** 未登录也可调用：不走 Bearer 拦截器，避免永久 token 进入登录 callbackUrl 前无法 prepare。 */
export async function prepareShareToken(token: string): Promise<{ state: string }> {
  const response = await fetch(
    '/api/proxy/operation_analysis/api/dashboard_share/prepare/',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token }),
      // 携带/写入 prepare nonce Cookie，供登录后 exchange 绑定发起方
      credentials: 'include',
    },
  );
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || payload?.result === false) {
    throw new Error(payload?.message || 'prepare share failed');
  }
  return (payload?.data ?? payload) as { state: string };
}

export const useDashboardShareApi = () => {
  const { get, post } = useApiClient();

  const createShare = useCallback(
    (dashboardId: string | number): Promise<DashboardShareLinkDto> =>
      post(`/operation_analysis/api/dashboard/${dashboardId}/share/`, {}),
    [post],
  );

  const exchangeShare = useCallback(
    (payload: { token?: string; state?: string }) =>
      post('/operation_analysis/api/dashboard_share/exchange/', payload),
    [post],
  );

  const getSharedDashboard = useCallback(
    (sessionId: string) =>
      get(`/operation_analysis/api/dashboard_share/session/${sessionId}/`),
    [get],
  );

  const querySharedDataSource = useCallback(
    (sessionId: string, dataSourceId: number, params?: unknown) =>
      post(
        `/operation_analysis/api/dashboard_share/session/${sessionId}/query/${dataSourceId}/`,
        params,
      ),
    [post],
  );

  const getSharedDataSources = useCallback(
    (sessionId: string) =>
      get(`/operation_analysis/api/dashboard_share/session/${sessionId}/data_sources/`),
    [get],
  );

  return {
    createShare,
    exchangeShare,
    getSharedDashboard,
    querySharedDataSource,
    getSharedDataSources,
  };
};
