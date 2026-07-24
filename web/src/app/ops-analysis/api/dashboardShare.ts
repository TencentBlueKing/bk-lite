import { useCallback } from 'react';
import useApiClient from '@/utils/request';

export const useDashboardShareApi = () => {
  const { get, post, del } = useApiClient();

  const createOrUpdateShare = useCallback(
    (dashboardId: string | number, data: { permanent: boolean; duration_seconds?: number }) =>
      post(`/operation_analysis/api/dashboard/${dashboardId}/share/`, data),
    [post],
  );

  const listShares = useCallback(
    (dashboardId: string | number) =>
      get(`/operation_analysis/api/dashboard/${dashboardId}/share/`),
    [get],
  );

  const revokeShare = useCallback(
    (dashboardId: string | number, shareId: number) =>
      del(`/operation_analysis/api/dashboard/${dashboardId}/share/${shareId}/`),
    [del],
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
    createOrUpdateShare,
    listShares,
    revokeShare,
    exchangeShare,
    getSharedDashboard,
    querySharedDataSource,
    getSharedDataSources,
  };
};
