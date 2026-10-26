import { useCallback } from 'react';
import useApiClient from '@/utils/request';
import { useShareCanvasDetailOverride } from '@/app/ops-analysis/context/shareCanvasDetail';

export interface ArchitectureResourceSearchParams {
  keyword: string;
  model_id: string;
  page: number;
  page_size: number;
  case_sensitive: boolean;
}

export const useArchitectureApi = () => {
  const { get, put, post, del } = useApiClient();
  const shareDetailOverride = useShareCanvasDetailOverride();

  const getArchitectureDetail = async (id: string | number) => {
    if (shareDetailOverride) {
      return shareDetailOverride();
    }
    return get(`/operation_analysis/api/architecture/${id}/`);
  };

  const saveArchitecture = async (id: string | number, data: any) => {
    return put(`/operation_analysis/api/architecture/${id}/`, data);
  };

  const createArchitecture = async (data: any) => {
    return post('/operation_analysis/api/architecture/', data);
  };

  const deleteArchitecture = async (id: string | number) => {
    return del(`/operation_analysis/api/architecture/${id}/`);
  };

  const queryNodeStatus = async (instUuids: string[]) => {
    return post('/operation_analysis/api/architecture/node_status/', {
      inst_uuids: instUuids,
    });
  };

  const getArchitectureModels = useCallback(
    () => get('/operation_analysis/api/architecture/models/'),
    [get],
  );

  const searchArchitectureResources = useCallback(
    (params: ArchitectureResourceSearchParams) =>
      post('/operation_analysis/api/architecture/resource_search/', params),
    [post],
  );

  const queryDisplayMetrics = async (instUuids: string[]) => {
    return post('/operation_analysis/api/architecture/display_metrics/', {
      inst_uuids: instUuids,
    });
  };

  const getMonitorLink = useCallback(
    (monitorId: string) =>
      get('/operation_analysis/api/architecture/monitor_link/', {
        params: { monitor_id: monitorId },
      }),
    [get],
  );

  return {
    getArchitectureDetail,
    saveArchitecture,
    createArchitecture,
    deleteArchitecture,
    queryNodeStatus,
    getArchitectureModels,
    searchArchitectureResources,
    queryDisplayMetrics,
    getMonitorLink,
  };
};
