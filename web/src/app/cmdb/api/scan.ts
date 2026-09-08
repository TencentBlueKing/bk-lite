import { useCallback } from 'react';
import useApiClient from '@/utils/request';

export const useScanApi = () => {
  const { get, post, put, del } = useApiClient();

  const getScanList = useCallback(
    (params?: Record<string, unknown>) => get('/cmdb/api/scan/', { params }),
    [get]
  );

  const getScanDetail = useCallback(
    (scanId: number | string) => get(`/cmdb/api/scan/${scanId}/`),
    [get]
  );

  const createScan = useCallback(
    (params: Record<string, unknown>) => post('/cmdb/api/scan/', params),
    [post]
  );

  const updateScan = useCallback(
    (scanId: number | string, params: Record<string, unknown>) =>
      put(`/cmdb/api/scan/${scanId}/`, params),
    [put]
  );

  const deleteScan = useCallback(
    (scanId: number | string) => del(`/cmdb/api/scan/${scanId}/`),
    [del]
  );

  const executeScan = useCallback(
    (scanId: number | string) => post(`/cmdb/api/scan/${scanId}/exec/`),
    [post]
  );

  const getScanExecution = useCallback(
    (executionId: number | string) => get(`/cmdb/api/scan/executions/${executionId}/`),
    [get]
  );

  const getScanHits = useCallback(
    (executionId: number | string, params?: Record<string, unknown>) =>
      get(`/cmdb/api/scan/executions/${executionId}/hits/`, { params }),
    [get]
  );

  const writeCmdb = useCallback(
    (executionId: number | string, hitIds: number[]) =>
      post(`/cmdb/api/scan/executions/${executionId}/write_cmdb/`, {
        hit_ids: hitIds,
      }),
    [post]
  );

  const writeCmdbAndGenerateCollect = useCallback(
    (executionId: number | string, hitIds: number[]) =>
      post(`/cmdb/api/scan/executions/${executionId}/write_cmdb_and_generate_collect/`, {
        hit_ids: hitIds,
      }),
    [post]
  );

  const generateCollect = useCallback(
    (executionId: number | string, hitIds: number[]) =>
      post(`/cmdb/api/scan/executions/${executionId}/generate_collect/`, {
        hit_ids: hitIds,
      }),
    [post]
  );

  const pushMonitor = useCallback(
    (executionId: number | string, hitIds: number[]) =>
      post(`/cmdb/api/scan/executions/${executionId}/push_monitor/`, {
        hit_ids: hitIds,
      }),
    [post]
  );

  const classifyHits = useCallback(
    (executionId: number | string, hitIds: number[], cmdbModelId: string) =>
      post(`/cmdb/api/scan/executions/${executionId}/classify_hits/`, {
        hit_ids: hitIds,
        cmdb_model_id: cmdbModelId,
      }),
    [post]
  );

  const rematchSoid = useCallback(
    (executionId: number | string, soid: string, hitIds?: number[]) =>
      post(`/cmdb/api/scan/executions/${executionId}/rematch_soid/`, {
        soid,
        ...(hitIds?.length ? { hit_ids: hitIds } : {}),
      }),
    [post]
  );

  return {
    getScanList,
    getScanDetail,
    createScan,
    updateScan,
    deleteScan,
    executeScan,
    getScanExecution,
    getScanHits,
    writeCmdb,
    writeCmdbAndGenerateCollect,
    generateCollect,
    pushMonitor,
    classifyHits,
    rematchSoid,
  };
};
