import { useCallback } from 'react';
import useApiClient from '@/utils/request';
import { loadPlaybackCanvasDetail, usePlaybackInitialDetail } from '@/app/ops-analysis/context/playbackInitialDetail';

export const useDashBoardApi = () => {
  const { get, put } = useApiClient();
  const playbackDetail = usePlaybackInitialDetail();

  const getDashboardDetail = useCallback(async (id: string | number) => {
    return loadPlaybackCanvasDetail(playbackDetail, 'dashboard', id, () => (
      get(`/operation_analysis/api/dashboard/${id}/`)
    ));
  }, [get, playbackDetail]);

  const saveDashboard = useCallback(async (id: string | number, data: any) => {
    return put(`/operation_analysis/api/dashboard/${id}/`, data);
  }, [put]);

  return {
    getDashboardDetail,
    saveDashboard,
  };
};
