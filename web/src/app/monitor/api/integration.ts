import useApiClient from '@/utils/request';
import { useMemo } from 'react';
import { TreeSortData } from '@/app/monitor/types';
import {
  OrderParam,
  NodeConfigParam,
  InstanceInfo,
  FlowAssetPayload,
  FlowDetectParams,
  FlowGuideParams,
  FlowIntegrationApi,
  SnmpCollectTemplateDoc,
} from '@/app/monitor/types/integration';
import { AxiosRequestConfig } from 'axios';

const useIntegrationApi = () => {
  const { get, post, del, put } = useApiClient();
  return useMemo(
    () => ({
      getInstanceGroupRule: async (
        params: {
          monitor_object_id?: React.Key;
        } = {},
        config?: AxiosRequestConfig
      ) => {
        return await get(`/monitor/api/organization_rule/`, {
          params,
          ...config,
        });
      },
      getCloudRegionList: async (params = {}) => {
        return await get(`/monitor/api/manual_collect/cloud_region_list/`, {
          params,
        });
      },
      getInstanceChildConfig: async (data: {
        instance_id?: string | number;
        instance_type?: string;
        collect_type?: string;
        collector?: string;
        monitor_plugin_id?: string | number;
      }) => {
        return await post(`/monitor/api/node_mgmt/get_instance_asso_config/`, data);
      },
      getMonitorNodeList: async (data: {
        cloud_region_id?: number;
        page?: number;
        page_size?: number;
        is_active?: boolean;
        monitor_plugin_id?: string | number;
      }) => {
        return await post('/monitor/api/node_mgmt/nodes/', data);
      },
      updateMonitorObject: async (data: TreeSortData[]) => {
        return await post(`/monitor/api/monitor_object/order/`, data);
      },
      importMonitorPlugin: async (data: any) => {
        return await post(`/monitor/api/monitor_plugin/import/`, data);
      },
      updateMetricsGroup: async (data: OrderParam[]) => {
        return await post('/monitor/api/metrics_group/set_order/', data);
      },
      updateMonitorMetrics: async (data: OrderParam[]) => {
        return await post('/monitor/api/metrics/set_order/', data);
      },
      updateNodeChildConfig: async (data: NodeConfigParam) => {
        return await post(
          '/monitor/api/node_mgmt/batch_setting_node_child_config/',
          data
        );
      },
      checkMonitorInstance: async (
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
      },
      deleteInstanceGroupRule: async (
        id: number | string,
        params: {
          del_instance_org: boolean;
        }
      ) => {
        return await del(`/monitor/api/organization_rule/${id}/`, { params });
      },
      deleteMonitorInstance: async (data: {
        instance_ids: any;
        clean_child_config: boolean;
      }) => {
        return await post(
          `/monitor/api/monitor_instance/remove_monitor_instance/`,
          data
        );
      },
      deleteMonitorMetrics: async (id: string | number) => {
        return await del(`/monitor/api/metrics/${id}/`);
      },
      deleteMetricsGroup: async (id: string | number) => {
        return await del(`/monitor/api/metrics_group/${id}/`);
      },
      getConfigContent: async (data: { ids: string[] }) => {
        return await post('/monitor/api/node_mgmt/get_config_content/', data);
      },
      updateMonitorInstance: async (data: InstanceInfo) => {
        return await post(
          '/monitor/api/monitor_instance/update_monitor_instance/',
          data
        );
      },
      setInstancesGroup: async (data: {
        instance_ids: React.Key[];
        organizations: React.Key[];
      }) => {
        return await post(
          `/monitor/api/monitor_instance/set_instances_organizations/`,
          data
        );
      },
      getUiTemplate: async (data: { id: React.Key }) => {
        return await get(`/monitor/api/monitor_plugin/${data.id}/ui_template/`);
      },
      getTemplateAccessGuide: async (
        id: React.Key,
        params: { organization_id: React.Key; cloud_region_id: React.Key }
      ) => {
        return await get(`/monitor/api/monitor_plugin/${id}/access_guide/`, {
          params,
        });
      },
      createCustomTemplate: async (data: Record<string, any>) => {
        return await post(`/monitor/api/monitor_plugin/`, data);
      },
      updateCustomTemplate: async (id: React.Key, data: Record<string, any>) => {
        return await put(`/monitor/api/monitor_plugin/${id}/`, data);
      },
      deleteCustomTemplate: async (id: React.Key) => {
        return await del(`/monitor/api/monitor_plugin/${id}/`);
      },
      getUiTemplateByParams: async (params: {
        collector: string;
        collect_type: string;
        monitor_object_id: string;
      }) => {
        return await get(`/monitor/api/monitor_plugin/ui_template_by_params/`, {
          params,
        });
      },
      getUiTemplateByPlugin: async (pluginId: React.Key) => {
        return await get(`/monitor/api/monitor_plugin/${pluginId}/ui_template/`);
      },
      getSnmpCollectTemplate: async (
        pluginId: React.Key
      ): Promise<SnmpCollectTemplateDoc> => {
        return await get(`/monitor/api/monitor_plugin/${pluginId}/collect_template/`);
      },
      updateSnmpCollectTemplate: async (
        pluginId: React.Key,
        data: { content: string }
      ): Promise<SnmpCollectTemplateDoc> => {
        return await put(`/monitor/api/monitor_plugin/${pluginId}/collect_template/`, data);
      },
      getInstanceListByPrimaryObject: async (
        params: {
          id?: React.Key;
          page?: number;
          page_size?: number;
          name?: string;
        } = {},
        config?: AxiosRequestConfig
      ) => {
        const { id, ...rest } = params;
        return await post(
          `/monitor/api/monitor_instance/${id}/list_by_primary_object/`,
          rest,
          config
        );
      },
      createK8sInstance: async (
        params: {
          organizations?: React.Key[];
          id?: string;
          name?: string;
          monitor_object_id?: React.Key;
        } = {}
      ) => {
        return await post(
          `/monitor/api/manual_collect/create_manual_instance/`,
          params
        );
      },
      getK8sCommand: async (
        params: {
          instance_id?: string;
          cloud_region_id?: React.Key;
          interval?: number;
        } = {}
      ) => {
        return await post(
          `/monitor/api/manual_collect/generate_install_command`,
          params
        );
      },
      checkCollectStatus: async (
        params: {
          instance_id?: string;
          monitor_object_id?: React.Key;
        } = {}
      ) => {
        return await post(
          `/monitor/api/manual_collect/check_collect_status/`,
          params
        );
      },
      createFlowAsset: async (data: FlowAssetPayload) => {
        return await post('/monitor/api/manual_collect/flow_asset/', data);
      },
      updateFlowAsset: async (
        data: Partial<FlowAssetPayload> & { instance_id: string }
      ) => {
        return await post('/monitor/api/manual_collect/flow_asset/update/', data);
      },
      getFlowGuide: async (params: FlowGuideParams) => {
        return await post('/monitor/api/manual_collect/flow_access_guide/', params);
      },
      detectFlowStatus: async (data: FlowDetectParams) => {
        return await post('/monitor/api/manual_collect/flow_detect_status/', data);
      },
    } satisfies FlowIntegrationApi),
    [del, get, post, put]
  );
};

export default useIntegrationApi;
