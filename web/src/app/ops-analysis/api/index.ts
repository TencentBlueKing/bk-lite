import useApiClient from '@/utils/request';
import { DirectoryType } from '@/app/ops-analysis/types';

const API_ENDPOINTS = {
  directory: '/operation_analysis/api/directory/',
  dashboard: '/operation_analysis/api/dashboard/',
  topology: '/operation_analysis/api/topology/',
  architecture: '/operation_analysis/api/architecture/',
} as const;

export const useDirectoryApi = () => {
  const { get, post, put, del } = useApiClient();

  const getDirectoryTree = async (params?: any) => {
    return get('/operation_analysis/api/directory/tree/', { params });
  };

  const createItem = async (type: DirectoryType, data: any) => {
    const endpoint = API_ENDPOINTS[type as keyof typeof API_ENDPOINTS];
    return post(endpoint, data);
  };

  const updateItem = async (type: DirectoryType, id: number | string, data: any) => {
    const endpoint = API_ENDPOINTS[type as keyof typeof API_ENDPOINTS];
    return put(`${endpoint}${id}/`, data);
  };

  const deleteItem = async (type: DirectoryType, id: number | string) => {
    const endpoint = API_ENDPOINTS[type as keyof typeof API_ENDPOINTS];
    return del(`${endpoint}${id}/`);
  };

  return {
    getDirectoryTree,
    createItem,
    updateItem,
    deleteItem,
  };
};
