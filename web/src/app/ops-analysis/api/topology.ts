import { useCallback } from 'react';
import useApiClient from '@/utils/request';
import { useShareCanvasDetailOverride } from '@/app/ops-analysis/context/shareCanvasDetail';

export const useTopologyApi = () => {
  const { get, post, put, del } = useApiClient();
  const shareDetailOverride = useShareCanvasDetailOverride();

  const getTopologyDetail = useCallback(async (id: string | number) => {
    if (shareDetailOverride) {
      return shareDetailOverride();
    }
    return get(`/operation_analysis/api/topology/${id}/`);
  }, [get, shareDetailOverride]);

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
