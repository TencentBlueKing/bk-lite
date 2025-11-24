import useApiClient from '@/utils/request';

/**
 * 环境变量管理API Hook
 * 职责：处理云区域环境变量的CRUD操作
 */
const useVariableApi = () => {
  const { get, post, del, patch } = useApiClient();

  // 获取变量列表
  const getVariableList = async (params: {
    cloud_region_id: number;
    search?: string;
    page?: number;
    page_size?: number;
  }) => {
    return await get('/node_mgmt/api/sidecar_env/', { params });
  };

  // 创建环境变量
  const createVariable = async (data: {
    key: string;
    value?: string;
    description?: string;
    cloud_region_id: number;
    type?: string;
  }) => {
    return await post('/node_mgmt/api/sidecar_env/', data);
  };

  // 部分更新环境变量
  const updateVariable = async (
    id: number,
    data: {
      key: string;
      value?: string;
      description?: string;
      type?: string;
    }
  ) => {
    return await patch(`/node_mgmt/api/sidecar_env/${id}/`, data);
  };

  // 删除环境变量
  const deleteVariable = async (id: string) => {
    return await del(`/node_mgmt/api/sidecar_env/${id}/`);
  };

  return {
    getVariableList,
    createVariable,
    updateVariable,
    deleteVariable,
  };
};

export default useVariableApi;
