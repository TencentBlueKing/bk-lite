import { useCallback } from 'react';
import useApiClient from '@/utils/request';

interface NamespaceBasePayload {
  name: string;
  account: string;
  password?: string;
  domain: string;
  namespace: string;
  enable_tls: boolean;
  desc: string;
}

export const useNamespaceApi = () => {
  const { get, post, patch, del } = useApiClient();
  const getNamespaceList = useCallback(async (params?: any) => {
    return get('/operation_analysis/api/namespace/', { params });
  }, [get]);
  const getTagList = useCallback(async (params?: any) => {
    return get('/operation_analysis/api/tag/', { params });
  }, [get]);
  const createNamespace = useCallback(async (data: NamespaceBasePayload) => {
    return post('/operation_analysis/api/namespace/', data);
  }, [post]);
  const updateNamespace = useCallback(async (id: number, data: NamespaceBasePayload) => {
    return patch(`/operation_analysis/api/namespace/${id}/`, data);
  }, [patch]);
  const deleteNamespace = useCallback(async (id: number) => {
    return del(`/operation_analysis/api/namespace/${id}/`);
  }, [del]);
  const getNamespaceDetail = useCallback(async (id: number) => {
    return get(`/operation_analysis/api/namespace/${id}/`);
  }, [get]);
  // [内部预留] toggleNamespaceStatus 已废弃，is_active 字段仅后端/导入导出链路使用
  // const toggleNamespaceStatus = async (id: number, is_active: boolean) => {
  //   return put(`/operation_analysis/api/namespace/${id}/`, { is_active });
  // };
  return {
    getNamespaceList,
    getTagList,
    createNamespace,
    updateNamespace,
    deleteNamespace,
    getNamespaceDetail,
  };
};
