import { useCallback } from 'react';
import useApiClient from '@/utils/request';
import { useShareCanvasDetailOverride } from '@/app/ops-analysis/context/shareCanvasDetail';

export const useReportApi = () => {
  const { get, put, post, del } = useApiClient();
  const shareDetailOverride = useShareCanvasDetailOverride();

  const getReportDetail = useCallback(async (id: string | number) => {
    if (shareDetailOverride) {
      return shareDetailOverride();
    }
    return get(`/operation_analysis/api/report/${id}/`);
  }, [get, shareDetailOverride]);

  const saveReport = useCallback(async (id: string | number, data: any) => {
    return put(`/operation_analysis/api/report/${id}/`, data);
  }, [put]);

  const createReport = useCallback(async (data: any) => {
    return post('/operation_analysis/api/report/', data);
  }, [post]);

  const deleteReport = useCallback(async (id: string | number) => {
    return del(`/operation_analysis/api/report/${id}/`);
  }, [del]);

  return {
    getReportDetail,
    saveReport,
    createReport,
    deleteReport,
  };
};
