import useApiClient from '@/utils/request';

const useApiController = () => {
  const { get } = useApiClient();

  // 获取控制器列表
  const getControllerList = async ({
    name,
    search,
    os,
    page,
    page_size,
  }: {
    name?: string;
    search?: string;
    os?: string;
    page?: number;
    page_size?: number;
  }) => {
    return await get('/node_mgmt/api/controller/', {
      params: { search, os, name, page, page_size },
    });
  };

  return {
    getControllerList,
  };
};

export default useApiController;
