import useApiClient from '@/utils/request';

const useLogApi = () => {
  const { get } = useApiClient();

  const getAllUsers = async (organizationIds?: Array<string | number>) => {
    const params =
      organizationIds && organizationIds.length
        ? { organization_ids: organizationIds.join(',') }
        : undefined;
    return await get(`/log/system_mgmt/user_all/`, { params });
  };

  return {
    getAllUsers,
  };
};

export default useLogApi;
