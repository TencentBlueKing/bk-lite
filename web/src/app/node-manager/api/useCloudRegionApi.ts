import useApiClient from '@/utils/request';
import type { DeployCloudRegionParams } from '@/app/node-manager/types/cloudregion';

/**
 * 云区域管理API Hook
 * 职责：处理云区域的CRUD操作
 */
const useCloudRegionApi = () => {
  const { get, post, del, patch, put } = useApiClient();

  // 获取云区域列表
  const getCloudList = async () => {
    return await get('/node_mgmt/api/cloud_region/');
  };

  // 创建云区域
  const createCloudRegion = async (data: {
    name?: string;
    introduction?: string;
    proxy_address?: string;
  }) => {
    return await post('/node_mgmt/api/cloud_region/', data);
  };

  // 删除云区域
  const deleteCloudRegion = async (id: string | number) => {
    return await del(`/node_mgmt/api/cloud_region/${id}`);
  };

  // 更新云区域
  const updateCloudIntro = async (
    id: string,
    data: {
      name?: string;
      introduction?: string;
      proxy_address?: string;
    }
  ) => {
    return await put(`/node_mgmt/api/cloud_region/${id}/`, data);
  };

  // 更新部分云区域
  const updatePartCloudIntro = async (
    id: string,
    data: {
      name?: string;
      introduction?: string;
      proxy_address?: string;
    }
  ) => {
    return await patch(`/node_mgmt/api/cloud_region/${id}/`, data);
  };

  // 部署云区域服务
  const deployCloudRegion = async (data: DeployCloudRegionParams) => {
    return await post('/node_mgmt/api/cloud_region/deploy_services/', data);
  };

  // 获取云区域详情
  const getCloudRegionDetail = async (id: string | number) => {
    return await get(`/node_mgmt/api/cloud_region/${id}/`);
  };

  // 获取部署指令
  const getDeployCommand = async (data = {}) => {
    return await post(`/node_mgmt/api/cloud_region/deploy_command/`, data);
  };

  return {
    getCloudList,
    createCloudRegion,
    deleteCloudRegion,
    updateCloudIntro,
    updatePartCloudIntro,
    deployCloudRegion,
    getCloudRegionDetail,
    getDeployCommand,
  };
};

export default useCloudRegionApi;
