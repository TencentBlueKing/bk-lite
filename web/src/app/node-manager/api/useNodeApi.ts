import useApiClient from '@/utils/request';
import type {
  ControllerInstallFields,
  NodeItem,
  UpdateConfigReq,
} from '../types/cloudregion';
import { SearchFilters } from '../types/node';

/**
 * 节点管理API Hook
 * 职责：处理节点相关的所有操作，包括节点管理、控制器和采集器安装等
 */
const useNodeApi = () => {
  const { get, post, del } = useApiClient();

  // 获取节点列表
  const getNodeList = async (params: {
    cloud_region_id?: number;
    filters?: SearchFilters;
  }) => {
    return await post('/node_mgmt/api/node/search/', params);
  };

  // 删除节点
  const delNode = async (id: React.Key) => {
    return await del(`/node_mgmt/api/node/${id}/`);
  };

  // 获取节点管理的状态枚举值
  const getNodeStateEnum = async () => {
    return await get('/node_mgmt/api/node/enum/');
  };

  // 获取包列表
  const getPackages = async (params: {
    os?: string;
    object?: string;
    operating_system?: string;
  }) => {
    return await get('/node_mgmt/api/package/', { params });
  };

  // 获取手动安装控制器指令
  const getInstallCommand = async (params: {
    os?: string;
    package_name?: string;
    cloud_region_id?: number;
  }) => {
    return await post('/node_mgmt/api/installer/get_install_command/', params);
  };

  // 卸载控制器
  const uninstallController = async (params: {
    cloud_region_id?: number;
    work_node?: number;
    nodes?: NodeItem[];
  }) => {
    return await post('/node_mgmt/api/installer/controller/uninstall/', params);
  };

  // 安装控制器
  const installController = async (params: ControllerInstallFields) => {
    return await post('/node_mgmt/api/installer/controller/install/', params);
  };

  // 安装采集器
  const installCollector = async (params: {
    collector_package: number;
    nodes: string[];
  }) => {
    return await post('/node_mgmt/api/installer/collector/install/', params);
  };

  // 获取控制器节点信息
  const getControllerNodes = async (params: { taskId: number }) => {
    return await post(
      `/node_mgmt/api/installer/controller/task/${params.taskId}/nodes/`
    );
  };

  // 获取采集器节点信息
  const getCollectorNodes = async (params: { taskId: number }) => {
    return await post(
      `/node_mgmt/api/installer/collector/install/${params.taskId}/nodes/`
    );
  };

  // 批量绑定或更新节点的采集器配置
  const batchBindCollector = async (data: UpdateConfigReq) => {
    return await post('/node_mgmt/api/node/batch_binding_configuration/', data);
  };

  // 批量操作节点的采集器（启动、停止、重启）
  const batchOperationCollector = async (data: {
    node_ids?: string[];
    collector_id?: string;
    operation?: string;
  }) => {
    return await post('/node_mgmt/api/node/batch_operate_collector/', data);
  };

  return {
    getNodeList,
    delNode,
    getNodeStateEnum,
    getPackages,
    getInstallCommand,
    uninstallController,
    installController,
    installCollector,
    getControllerNodes,
    getCollectorNodes,
    batchBindCollector,
    batchOperationCollector,
  };
};

export default useNodeApi;
