import useApiClient from '@/utils/request';
import type {
  updateConfigReq,
  ControllerInstallFields,
  NodeItem,
  ConfigParams,
  ConfigListParams,
} from '@/app/node-manager/types/cloudregion';

const useApiCloudRegion = () => {
  const { get, post, del, patch } = useApiClient();

  //获取云区域列表
  const getcloudlist = async () => {
    return await get('/node_mgmt/api/cloud_region/');
  };

  //更新云区域的介绍
  const updatecloudintro = async (
    id: string,
    data: { introduction: string }
  ) => {
    return await patch(`/node_mgmt/api/cloud_region/${id}/`, data);
  };

  //节点的模块
  //获取节点列表
  const getnodelist = async (params: {
    cloud_region_id?: number;
    name?: string;
    operating_system?: string;
  }) => {
    return await get('/node_mgmt/api/node/', {
      params,
    });
  };

  // 获取包列表
  const getPackages = async (params: {
    os?: string;
    object?: string;
    operating_system?: string;
  }) => {
    return await get('/node_mgmt/api/package/', {
      params,
    });
  };

  // 获取手动安装控制器指令
  const getInstallCommand = async (params: {
    os?: string;
    package_name?: string;
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

  // 获控制器节点信息
  const getControllerNodes = async (params: { taskId: number }) => {
    return await post(
      `/node_mgmt/api/installer/controller/task/${params.taskId}/nodes/`
    );
  };

  // 获采集器节点信息
  const getCollectorNodes = async (params: { taskId: number }) => {
    return await post(
      `/node_mgmt/api/installer/collector/install/${params.taskId}/nodes/`
    );
  };

  //获取sidecar的安装步骤
  const getsidecarstep = async (
    ip: string,
    operating_system: string,
    group: string
  ) => {
    return await get('/node_mgmt/api/sidecar/install_guide/', {
      params: {
        ip,
        operating_system,
        group,
      },
    });
  };

  //批量绑定或更新节点的采集器配置
  const batchbindcollector = async (data: updateConfigReq) => {
    return await post('/node_mgmt/api/node/batch_binding_configuration/', data);
  };

  //批量操作节点的采集器（启动、停止、重启）
  const batchoperationcollector = async (data: {
    node_ids?: string[];
    collector_id?: string;
    operation?: string;
  }) => {
    return await post('/node_mgmt/api/node/batch_operate_collector/', data);
  };

  //获取节点管理的状态枚举值
  const getnodstateenum = async () => {
    return await get('/node_mgmt/api/node/enum/');
  };

  //配置文件的模块
  //获取配置文件列表
  const getconfiglist = async (params: ConfigListParams) => {
    return await post('/node_mgmt/api/configuration/config_node_asso/', params);
  };

  //配置文件的模块
  //查询节点信息以及关联的配置
  const getAssoNodes = async (params: ConfigListParams) => {
    return await post('/node_mgmt/api/configuration/config_node_asso/', params);
  };

  // 获取子配置文件列表
  const getchildconfig = async (
    collector_config_id: string,
    search?: string
  ) => {
    return await get('/node_mgmt/api/child_config', {
      params: {
        collector_config_id,
        search,
      },
    });
  };

  //创建一个配置文件
  const createconfig = async (data: ConfigParams) => {
    return await post('/node_mgmt/api/configuration/', data);
  };

  // 创建一个子配置文件
  const createchildconfig = async (data: {
    collect_type: string;
    config_type: string;
    content: string;
    collector_config: string;
  }) => {
    return await post('/node_mgmt/api/child_config', data);
  };

  // 更新子配置内容
  const updatechildconfig = async (
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

  //部分更新采集器
  const updatecollector = async (id: string, data: ConfigParams) => {
    return await patch(`/node_mgmt/api/configuration/${id}/`, data);
  };

  //删除采集器配置
  const deletecollector = async (id: string) => {
    return await del(`/node_mgmt/api/configuration/${id}/`);
  };

  //应用指定采集器配置文件到指定节点
  const applyconfig = async (
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

  //批量删除采集器配置
  const batchdeletecollector = async (data: { ids: string[] }) => {
    return await post('/node_mgmt/api/configuration/bulk_delete/', data);
  };

  //变量的模块
  //获取变量列表
  const getvariablelist = async (cloud_region_id: number, search?: string) => {
    return await get('/node_mgmt/api/sidecar_env/', {
      params: { cloud_region_id, search },
    });
  };

  //创建环境变量
  const createvariable = async (data: {
    key: string;
    value: string;
    description?: string;
    cloud_region_id: number;
  }) => {
    return await post('/node_mgmt/api/sidecar_env/', data);
  };

  //部分更新环境变量
  const updatevariable = async (
    id: number,
    data: {
      key: string;
      value: string;
      description?: string;
    }
  ) => {
    return await patch(`/node_mgmt/api/sidecar_env/${id}/`, data);
  };

  //删除环境变量
  const deletevariable = async (id: string) => {
    return await del(`/node_mgmt/api/sidecar_env/${id}/`);
  };
  return {
    getcloudlist,
    updatecloudintro,
    getnodelist,
    getsidecarstep,
    getconfiglist,
    createconfig,
    updatecollector,
    deletecollector,
    applyconfig,
    batchdeletecollector,
    getvariablelist,
    createvariable,
    updatevariable,
    deletevariable,
    batchbindcollector,
    batchoperationcollector,
    getnodstateenum,
    getPackages,
    installController,
    getControllerNodes,
    uninstallController,
    getchildconfig,
    createchildconfig,
    updatechildconfig,
    installCollector,
    getCollectorNodes,
    getInstallCommand,
    getAssoNodes,
    cancelApply,
  };
};
export default useApiCloudRegion;
