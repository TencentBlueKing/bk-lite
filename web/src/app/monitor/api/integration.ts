import useApiClient from '@/utils/request';
import { TreeSortData } from '@/app/monitor/types';
import {
  OrderParam,
  NodeConfigParam,
  InstanceInfo,
} from '@/app/monitor/types/integration';

const useIntegrationApi = () => {
  const { get, post, del } = useApiClient();

  const getInstanceGroupRule = async (
    params: {
      monitor_object_id?: React.Key;
    } = {}
  ) => {
    return await get(`/monitor/api/organization_rule/`, {
      params,
    });
  };

  const getInstanceChildConfig = async (data: {
    instance_id?: string | number;
    instance_type?: string;
  }) => {
    return await post(`/monitor/api/node_mgmt/get_instance_asso_config/`, data);
  };

  const getMonitorNodeList = async (data: {
    cloud_region_id?: number;
    page?: number;
    page_size?: number;
    is_active?: boolean;
  }) => {
    return await post('/monitor/api/node_mgmt/nodes/', data);
  };

  const updateMonitorObject = async (data: TreeSortData[]) => {
    return await post(`/monitor/api/monitor_object/order/`, data);
  };

  const importMonitorPlugin = async (data: any) => {
    return await post(`/monitor/api/monitor_plugin/import/`, data);
  };

  const updateMetricsGroup = async (data: OrderParam[]) => {
    return await post('/monitor/api/metrics_group/set_order/', data);
  };

  const updateMonitorMetrics = async (data: OrderParam[]) => {
    return await post('/monitor/api/metrics/set_order/', data);
  };

  const updateNodeChildConfig = async (data: NodeConfigParam) => {
    return await post(
      '/monitor/api/node_mgmt/batch_setting_node_child_config/',
      data
    );
  };

  const checkMonitorInstance = async (
    id: string,
    data: {
      instance_id: string | number;
      instance_name: string;
    }
  ) => {
    return await post(
      `/monitor/api/monitor_instance/${id}/check_monitor_instance/`,
      data
    );
  };

  const deleteInstanceGroupRule = async (
    id: number | string,
    params: {
      del_instance_org: boolean;
    }
  ) => {
    return await del(`/monitor/api/organization_rule/${id}/`, { params });
  };

  const deleteMonitorInstance = async (data: {
    instance_ids: any;
    clean_child_config: boolean;
  }) => {
    return await post(
      `/monitor/api/monitor_instance/remove_monitor_instance/`,
      data
    );
  };

  const deleteMonitorMetrics = async (id: string | number) => {
    return await del(`/monitor/api/metrics/${id}/`);
  };

  const deleteMetricsGroup = async (id: string | number) => {
    return await del(`/monitor/api/metrics_group/${id}/`);
  };

  const getConfigContent = async (data: { ids: string[] }) => {
    return await post('/monitor/api/node_mgmt/get_config_content/', data);
  };

  const updateMonitorInstance = async (data: InstanceInfo) => {
    return await post(
      '/monitor/api/monitor_instance/update_monitor_instance/',
      data
    );
  };

  const setInstancesGroup = async (data: {
    instance_ids: React.Key[];
    organizations: React.Key[];
  }) => {
    return await post(
      `/monitor/api/monitor_instance/set_instances_organizations/`,
      data
    );
  };

  return {
    getInstanceGroupRule,
    getInstanceChildConfig,
    getMonitorNodeList,
    updateMonitorObject,
    importMonitorPlugin,
    updateMetricsGroup,
    updateMonitorMetrics,
    updateNodeChildConfig,
    checkMonitorInstance,
    deleteInstanceGroupRule,
    deleteMonitorInstance,
    deleteMonitorMetrics,
    deleteMetricsGroup,
    getConfigContent,
    updateMonitorInstance,
    setInstancesGroup,
  };
};

export default useIntegrationApi;
