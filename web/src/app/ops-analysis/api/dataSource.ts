import { useCallback } from 'react';
import useApiClient from '@/utils/request';
import { useSharedDataSourceQuery } from '@/app/ops-analysis/context/shareDataSource';

export const useDataSourceApi = () => {
  const { get, post, put, del } = useApiClient();
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

  const deleteDataSource = useCallback(async (id: number) => {
    return del(`/operation_analysis/api/data_source/${id}/`);
  }, [del]);

  const getDataSourceDetail = useCallback(async (id: number) => {
    return get(`/operation_analysis/api/data_source/${id}/`);
  }, [get]);

  const getSourceDataByApiId = useCallback(async (id: number, params?: any) => {
    if (sharedAccess) {
      return sharedAccess.queryDataSource(id, params);
    }
    return post(`/operation_analysis/api/data_source/get_source_data/${id}/`, params);
  }, [post, sharedAccess]);

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

  return {
    getDataSourceList,
    getDataSourceBriefList,
    getDataSourceDetails,
    createDataSource,
    updateDataSource,
    deleteDataSource,
    getDataSourceDetail,
    getSourceDataByApiId,
    previewDataSourceConfig,
    previewDataSource
  };
};
