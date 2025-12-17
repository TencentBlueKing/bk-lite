import useApiClient from '@/utils/request';
import {
  ManualInstallController,
  RetryInstallParams,
} from '../types/controller';

/**
 * 控制器管理API Hook
 * 职责：处理控制器相关操作
 */
const useControllerApi = () => {
  const { get, post } = useApiClient();

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

  // 控制器安装重试
  const retryInstallController = async (params: RetryInstallParams) => {
    return await post('/node_mgmt/api/installer/controller/retry/', params);
  };

  // 控制器手动安装
  const manualInstallController = async (params: ManualInstallController) => {
    return await post(
      '/node_mgmt/api/installer/controller/manual_install/',
      params
    );
  };

  // 控制器手动安装的节点状态查询

  const getManualInstallStatus = async (params: { node_ids: React.Key[] }) => {
    return await post(
      '/node_mgmt/api/installer/controller/manual_install_status/',
      params
    );
  };

  // 获取手动安装控制器指令
  const getInstallCommand = async (params: {
    package_id?: string;
    cloud_region_id?: number;
    os?: string;
  }) => {
    return await post('/node_mgmt/api/installer/get_install_command/', params);
  };

  return {
    getControllerList,
    retryInstallController,
    manualInstallController,
    getManualInstallStatus,
    getInstallCommand,
  };
};

export default useControllerApi;
