import useApiClient from '@/utils/request';

/**
 * 控制器管理API Hook
 * 职责：处理控制器相关操作
 */
const useControllerApi = () => {
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

export default useControllerApi;
