import useApiClient from '@/utils/request';
import { DirectoryType } from '@/app/ops-analysis/types';
import { CANVAS_TYPE_REGISTRY } from '@/app/ops-analysis/constants/canvasTypes';

const API_ENDPOINTS = {
  directory: '/operation_analysis/api/directory/',
  ...Object.fromEntries(
    Object.entries(CANVAS_TYPE_REGISTRY).map(([type, meta]) => [
      type,
      meta.endpoint,
    ])
  ),
} as const;

const getEndpoint = (type: DirectoryType) => {
  const endpoint = API_ENDPOINTS[type as keyof typeof API_ENDPOINTS];
  if (!endpoint) {
    throw new Error(`Unsupported ops-analysis directory type: ${type}`);
  }
  return endpoint;
};

export const useDirectoryApi = () => {
  const { get, post, patch, del } = useApiClient();

  const getDirectoryTree = async (params?: any) => {
    return get('/operation_analysis/api/directory/tree/', { params });
  };

  const createItem = async (type: DirectoryType, data: any) => {
    const endpoint = getEndpoint(type);
    return post(endpoint, data);
  };

  const updateItem = async (type: DirectoryType, id: number | string, data: any) => {
    const endpoint = getEndpoint(type);
    return patch(`${endpoint}${id}/`, data);
  };

  const deleteItem = async (type: DirectoryType, id: number | string) => {
    const endpoint = getEndpoint(type);
    return del(`${endpoint}${id}/`);
  };

  return {
    getDirectoryTree,
    createItem,
    updateItem,
    deleteItem,
  };
};
