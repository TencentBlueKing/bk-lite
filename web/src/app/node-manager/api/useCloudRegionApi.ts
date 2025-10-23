import useApiClient from '@/utils/request';

/**
 * 云区域管理API Hook
 * 职责：处理云区域的CRUD操作
 */
const useCloudRegionApi = () => {
  const { get, post, del, patch } = useApiClient();

  // 获取云区域列表
  const getCloudList = async () => {
    return await get('/node_mgmt/api/cloud_region/');
  };

  // 创建云区域
  const createCloudRegion = async (data: {
    name: string;
    introduction: string;
  }) => {
    return await post('/node_mgmt/api/cloud_region/', data);
  };

  // 删除云区域
  const deleteCloudRegion = async (id: string | number) => {
    return await del(`/node_mgmt/api/cloud_region/${id}`);
  };

  // 更新云区域的介绍
  const updateCloudIntro = async (
    id: string,
    data: {
      name?: string;
      introduction: string;
    }
  ) => {
    return await patch(`/node_mgmt/api/cloud_region/${id}/`, data);
  };

  return {
    getCloudList,
    createCloudRegion,
    deleteCloudRegion,
    updateCloudIntro,
  };
};

export default useCloudRegionApi;
