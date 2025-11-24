import useApiClient from '@/utils/request';
import type {
  ConfigParams,
  ConfigListParams,
} from '@/app/node-manager/types/cloudregion';

/**
 * 配置管理API Hook
 * 职责：处理采集器配置的增删改查和应用操作
 */
const useConfigApi = () => {
  const { get, post, del, patch } = useApiClient();

  // 获取配置文件列表
  const getConfiglist = async (params: ConfigListParams) => {
    return await post('/node_mgmt/api/configuration/config_node_asso/', params);
  };

  // 查询节点信息以及关联的配置
  const getAssoNodes = async (params: ConfigListParams) => {
    return await post('/node_mgmt/api/configuration/config_node_asso/', params);
  };

  // 获取子配置文件列表
  const getChildConfig = async (params: {
    collector_config_id: string;
    search?: string;
    page?: number;
    page_size?: number;
  }) => {
    return await get('/node_mgmt/api/child_config', { params });
  };

  // 创建一个配置文件
  const createConfig = async (data: ConfigParams) => {
    return await post('/node_mgmt/api/configuration/', data);
  };

  // 创建一个子配置文件
  const createChildConfig = async (data: {
    collect_type: string;
    config_type: string;
    content: string;
    collector_config: string;
  }) => {
    return await post('/node_mgmt/api/child_config', data);
  };

  // 更新子配置内容
  const updateChildConfig = async (
    id: string,
    data: {
      collect_type: string;
      config_type: string;
      content: string;
      collector_config: string;
    }
  ) => {
    return await patch(`/node_mgmt/api/child_config/${id}`, data);
  };

  // 部分更新采集器
  const updateCollector = async (id: string, data: ConfigParams) => {
    return await patch(`/node_mgmt/api/configuration/${id}/`, data);
  };

  // 删除采集器配置
  const deleteCollector = async (id: string) => {
    return await del(`/node_mgmt/api/configuration/${id}/`);
  };

  // 应用指定采集器配置文件到指定节点
  const applyConfig = async (
    data: {
      node_id?: string;
      collector_configuration_id?: string;
    }[]
  ) => {
    return await post(
      '/node_mgmt/api/configuration/apply_to_node/',
      JSON.stringify(data)
    );
  };

  // 解绑应用
  const cancelApply = async (data: {
    node_id?: string;
    collector_configuration_id?: string;
  }) => {
    return await post(
      '/node_mgmt/api/configuration/cancel_apply_to_node/',
      data
    );
  };

  // 批量删除采集器配置
  const batchDeleteCollector = async (data: { ids: string[] }) => {
    return await post('/node_mgmt/api/configuration/bulk_delete/', data);
  };

  return {
    getConfiglist,
    getAssoNodes,
    getChildConfig,
    createConfig,
    createChildConfig,
    updateChildConfig,
    updateCollector,
    deleteCollector,
    applyConfig,
    cancelApply,
    batchDeleteCollector,
  };
};

export default useConfigApi;
