import useApiClient from '@/utils/request';

export const useDashBoardApi = () => {
  const { get, put } = useApiClient();

  const getDashboardDetail = async (id: string | number) => {
    return get(`/operation_analysis/api/dashboard/${id}/`);
  };

  const saveDashboard = async (id: string | number, data: any) => {
    return put(`/operation_analysis/api/dashboard/${id}/`, data);
  };

  return {
    getDashboardDetail,
    saveDashboard,
  };
};
