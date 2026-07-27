import { useCallback } from 'react';
import useApiClient from '@/utils/request';
import type { DashboardShareLinkDto } from '@/app/ops-analysis/types/dashboardShare';

export const useDashboardShareApi = () => {
  const { get, post } = useApiClient();

  const createShare = useCallback(
    (dashboardId: string | number): Promise<DashboardShareLinkDto> =>
      post(`/operation_analysis/api/dashboard/${dashboardId}/share/`, {}),
    [post],
  );

  const exchangeShare = useCallback(
    (token: string) =>
      post('/operation_analysis/api/dashboard_share/exchange/', { token }),
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
