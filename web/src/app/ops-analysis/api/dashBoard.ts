import { useCallback } from 'react';
import useApiClient from '@/utils/request';

export const useDashBoardApi = () => {
  const { get, put } = useApiClient();

  const getDashboardDetail = useCallback(async (id: string | number) => {
    return get(`/operation_analysis/api/dashboard/${id}/`);
  }, [get]);

  const saveDashboard = useCallback(async (id: string | number, data: any) => {
    return put(`/operation_analysis/api/dashboard/${id}/`, data);
  }, [put]);

  return {
    getDashboardDetail,
    saveDashboard,
  };
};
