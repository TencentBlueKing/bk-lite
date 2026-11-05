import { useCallback } from 'react';
import useApiClient from '@/utils/request';
import { useShareCanvasDetailOverride } from '@/app/ops-analysis/context/shareCanvasDetail';
import { loadPlaybackCanvasDetail, usePlaybackInitialDetail } from '@/app/ops-analysis/context/playbackInitialDetail';

export const useTopologyApi = () => {
  const { get, post, put, del } = useApiClient();
  const shareDetailOverride = useShareCanvasDetailOverride();
  const playbackDetail = usePlaybackInitialDetail();

  const getTopologyDetail = useCallback(async (id: string | number) => {
    if (shareDetailOverride) {
      return shareDetailOverride();
    }
    return loadPlaybackCanvasDetail(playbackDetail, 'topology', id, () => (
      get(`/operation_analysis/api/topology/${id}/`)
    ));
  }, [get, playbackDetail, shareDetailOverride]);

  const saveTopology = useCallback(async (id: string | number, data: any) => {
    return put(`/operation_analysis/api/topology/${id}/`, data);
  }, [put]);

  const createTopology = useCallback(async (data: any) => {
    return post('/operation_analysis/api/topology/', data);
  }, [post]);

  const deleteTopology = useCallback(async (id: string | number) => {
    return del(`/operation_analysis/api/topology/${id}/`);
  }, [del]);

  return {
    getTopologyDetail,
    saveTopology,
    createTopology,
    deleteTopology,
  };
};
