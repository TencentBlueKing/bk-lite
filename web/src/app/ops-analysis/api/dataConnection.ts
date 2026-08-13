import { useCallback } from 'react';
import useApiClient from '@/utils/request';

export const useDataConnectionApi = () => {
  const { get, post, patch, del } = useApiClient();

  const getDataConnectionList = useCallback(
    async (params?: any) => get('/operation_analysis/api/data_connection/', { params }),
    [get],
  );

  const createDataConnection = useCallback(
    async (data: any) => post('/operation_analysis/api/data_connection/', data),
    [post],
  );

  const updateDataConnection = useCallback(
    async (id: number, data: any) =>
      patch(`/operation_analysis/api/data_connection/${id}/`, data),
    [patch],
  );

  const deleteDataConnection = useCallback(
    async (id: number) => del(`/operation_analysis/api/data_connection/${id}/`),
    [del],
  );

  const getDataConnectionDetail = useCallback(
    async (id: number) => get(`/operation_analysis/api/data_connection/${id}/`),
    [get],
  );

  const getDataConnectionReferences = useCallback(
    async (id: number) =>
      get(`/operation_analysis/api/data_connection/${id}/references/`),
    [get],
  );

  const testDataConnection = useCallback(
    async (id: number, config?: any) =>
      post(
        `/operation_analysis/api/data_connection/${id}/test_connection/`,
        {},
        config,
      ),
    [post],
  );

  return {
    getDataConnectionList,
    createDataConnection,
    updateDataConnection,
    deleteDataConnection,
    getDataConnectionDetail,
    getDataConnectionReferences,
    testDataConnection,
  };
};
