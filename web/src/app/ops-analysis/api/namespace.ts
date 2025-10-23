import useApiClient from '@/utils/request';

export const useNamespaceApi = () => {
  const { get, post, put, del } = useApiClient();

  const getNamespaceList = async (params?: any) => {
    return get('/operation_analysis/api/namespace/', { params });
  };

  const getTagList = async (params?: any) => {
    return get('/operation_analysis/api/tag/', { params });
  };

  const createNamespace = async (data: {
    name: string;
    account: string;
    password: string;
    domain: string;
    describe?: string;
  }) => {
    return post('/operation_analysis/api/namespace/', data);
  };

  const updateNamespace = async (id: number, data: {
    name: string;
    account: string;
    password: string;
    domain: string;
    describe?: string;
  }) => {
    return put(`/operation_analysis/api/namespace/${id}/`, data);
  };

  const deleteNamespace = async (id: number) => {
    return del(`/operation_analysis/api/namespace/${id}/`);
  };

  const getNamespaceDetail = async (id: number) => {
    return get(`/operation_analysis/api/namespace/${id}/`);
  };

  const toggleNamespaceStatus = async (id: number, is_active: boolean) => {
    return put(`/operation_analysis/api/namespace/${id}/`, { is_active });
  };

  return {
    getNamespaceList,
    getTagList,
    createNamespace,
    updateNamespace,
    deleteNamespace,
    getNamespaceDetail,
    toggleNamespaceStatus
  };
};
