import useApiClient from '@/utils/request';

export const useArchitectureApi = () => {
  const { get, put, post, del } = useApiClient();

  const getArchitectureDetail = async (id: string | number) => {
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

  return {
    getArchitectureDetail,
    saveArchitecture,
    createArchitecture,
    deleteArchitecture,
  };
};
