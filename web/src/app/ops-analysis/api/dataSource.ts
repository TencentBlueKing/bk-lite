import useApiClient from '@/utils/request';
import { buildRequestDedupKey, dedupeInFlightRequest } from './requestDedup';

export const useDataSourceApi = () => {
  const { get, post, put, del } = useApiClient();

  const getDataSourceList = async (params?: any) => {
    return get('/operation_analysis/api/data_source/', { params });
  };

  const createDataSource = async (data: any) => {
    return post('/operation_analysis/api/data_source/', data);
  };

  const updateDataSource = async (id: number, data: any) => {
    return put(`/operation_analysis/api/data_source/${id}/`, data);
  };

  const deleteDataSource = async (id: number) => {
    return del(`/operation_analysis/api/data_source/${id}/`);
  };

  const getDataSourceDetail = async (id: number) => {
    return get(`/operation_analysis/api/data_source/${id}/`);
  };

  const getSourceDataByApiId = async (id: number, params?: any) => {
    const dedupKey = buildRequestDedupKey(id, params);
    return dedupeInFlightRequest(dedupKey, () =>
      post(`/operation_analysis/api/data_source/get_source_data/${id}/`, params),
    );
  };

  return {
    getDataSourceList,
    createDataSource,
    updateDataSource,
    deleteDataSource,
    getDataSourceDetail,
    getSourceDataByApiId
  };
};
