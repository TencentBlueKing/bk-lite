import { useCallback } from 'react';
import useApiClient from '@/utils/request';
import { useSharedDataSourceQuery } from '@/app/ops-analysis/context/shareDataSource';
import {
  parseSourceDataResponse,
  type SourceDataResult,
} from '@/app/ops-analysis/utils/sourceDataResponse';

export interface SourceDataRequestOptions {
  suppressErrorNotification?: boolean;
}

export const withRuntimeSourceDataErrorSuppression = (
  getSourceDataByApiId: (
    id: number,
    params?: unknown,
    options?: SourceDataRequestOptions,
  ) => Promise<SourceDataResult>,
) => (id: number, params?: unknown) =>
  getSourceDataByApiId(id, params, { suppressErrorNotification: true });

export const useDataSourceApi = () => {
  const { get, post, put, del, patch } = useApiClient();
  const sharedAccess = useSharedDataSourceQuery();

  const getDataSourceList = useCallback(async (params?: any) => {
    return get('/operation_analysis/api/data_source/', { params });
  }, [get]);

  const getDataSourceBriefList = useCallback(async (params?: any) => {
    return get('/operation_analysis/api/data_source/', {
      params: { ...params, mode: 'brief' },
    });
  }, [get]);

  const getDataSourceDetails = useCallback(async (ids: Array<number | string>) => {
    const normalizedIds = Array.from(
      new Set(
        ids
          .map((id) => (typeof id === 'string' ? parseInt(id, 10) : id))
          .filter((id) => Number.isFinite(id))
      )
    ) as number[];

    if (normalizedIds.length === 0) {
      return [];
    }
    if (sharedAccess) {
      const response = await sharedAccess.getDataSourceDetails(normalizedIds);
      const items = Array.isArray(response) ? response : [];
      return items.filter((item: { id: number }) => normalizedIds.includes(item.id));
    }

    return get('/operation_analysis/api/data_source/', {
      params: {
        mode: 'detail',
        ids: normalizedIds.join(','),
      },
    });
  }, [get, sharedAccess]);

  const createDataSource = useCallback(async (data: any) => {
    return post('/operation_analysis/api/data_source/', data);
  }, [post]);

  const updateDataSource = useCallback(async (id: number, data: any) => {
    return put(`/operation_analysis/api/data_source/${id}/`, data);
  }, [put]);

  const patchDataSource = useCallback(async (id: number, data: any) => {
    return patch(`/operation_analysis/api/data_source/${id}/`, data);
  }, [patch]);

  const deleteDataSource = useCallback(async (id: number, config?: any) => {
    return del(`/operation_analysis/api/data_source/${id}/`, config);
  }, [del]);

  const getDataSourceDetail = useCallback(async (id: number) => {
    return get(`/operation_analysis/api/data_source/${id}/`);
  }, [get]);

  const getSourceDataByApiId = useCallback(async (
    id: number,
    params?: unknown,
    options?: SourceDataRequestOptions,
  ): Promise<SourceDataResult> => {
    const requestConfig = options?.suppressErrorNotification
      ? { suppressErrorNotification: true as const }
      : undefined;
    const raw = sharedAccess
      ? await sharedAccess.queryDataSource(id, params, options)
      : await post(
        `/operation_analysis/api/data_source/get_source_data/${id}/`,
        params,
        requestConfig,
      );
    return parseSourceDataResponse(raw);
  }, [post, sharedAccess]);

  const testDataSourceConnectionConfig = useCallback(async (data: any) => {
    return post('/operation_analysis/api/data_source/test_connection/', data);
  }, [post]);

  const testDataSourceConnection = useCallback(async (id: number, data?: any) => {
    return post(`/operation_analysis/api/data_source/${id}/test_connection/`, data || {});
  }, [post]);

  const extractDataSourceConnection = useCallback(async (id: number, data?: any) => {
    return post(`/operation_analysis/api/data_source/${id}/extract_connection/`, data || {});
  }, [post]);

  const previewDataSourceConfig = useCallback(async (data: any) => {
    const isFormData =
      typeof FormData !== 'undefined' && data instanceof FormData;
    return post(
      '/operation_analysis/api/data_source/preview/',
      data,
      isFormData ? { headers: { 'Content-Type': 'multipart/form-data' } } : undefined
    );
  }, [post]);

  const previewDataSource = useCallback(async (id: number, data?: any) => {
    return post(`/operation_analysis/api/data_source/${id}/preview/`, data);
  }, [post]);

  const submitExcelMaterialization = useCallback(async (id: number, data: FormData) => {
    return post(
      `/operation_analysis/api/data_source/${id}/submit_excel/`,
      data,
      { headers: { 'Content-Type': 'multipart/form-data' } },
    );
  }, [post]);

  const retryExcelMaterialization = useCallback(async (id: number, data?: any) => {
    return post(`/operation_analysis/api/data_source/${id}/retry_excel_materialization/`, data || {});
  }, [post]);

  return {
    getDataSourceList,
    getDataSourceBriefList,
    getDataSourceDetails,
    createDataSource,
    updateDataSource,
    patchDataSource,
    deleteDataSource,
    getDataSourceDetail,
    getSourceDataByApiId,
    previewDataSourceConfig,
    previewDataSource,
    submitExcelMaterialization,
    retryExcelMaterialization,
    testDataSourceConnectionConfig,
    testDataSourceConnection,
    extractDataSourceConnection,
  };
};
