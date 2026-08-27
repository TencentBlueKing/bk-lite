import useApiClient from '@/utils/request';
import { SourceFeild } from '@/app/monitor/types/event';
import { AxiosRequestConfig } from 'axios';

const useEventApi = () => {
  const { get, post, patch, del } = useApiClient();

  const getMonitorEventDetail = async (
    id?: string | number,
    params: {
      page?: number;
      page_size?: number;
    } = {}
  ) => {
    return await get(`/monitor/api/monitor_event/query/${id}/`, {
      params,
    });
  };

  const getEventRaw = async (id?: string | number) => {
    return await get(`/monitor/api/monitor_event/raw_data/${id}/`);
  };

  const getMonitorPolicy = async (
    id?: any,
    params: {
      name?: string;
      page?: number;
      page_size?: number;
      monitor_object_id?: React.Key;
    } = {},
    config?: AxiosRequestConfig
  ) => {
    return await get(`/monitor/api/monitor_policy/${id}`, {
      params,
      ...config,
    });
  };

  const getPolicyTemplate = async (
    params: {
      monitor_object_name?: string | null;
      plugin_id?: string | number;
    },
    config?: AxiosRequestConfig
  ) => {
    return await post('/monitor/api/monitor_policy/template/', params, config);
  };

  const bulkCreatePoliciesFromTemplates = async (data: Record<string, unknown>) => {
    return await post('/monitor/api/monitor_policy/bulk_create_from_templates/', data);
  };

  const savePolicyTemplate = async (data: Record<string, unknown>) =>
    post('/monitor/api/monitor_policy/template/save/', data);

  const importPolicyTemplates = async (file: File, overwrite = false) => {
    const data = new FormData();
    data.append('file', file);
    data.append('overwrite', String(overwrite));
    return post('/monitor/api/monitor_policy/template/import/', data, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  };

  const exportPolicyTemplates = async (keys: string[]) =>
    post('/monitor/api/monitor_policy/template/export/', { keys }, { responseType: 'blob' });

  const bulkDeletePolicyTemplates = async (keys: string[]) =>
    post('/monitor/api/monitor_policy/template/bulk_delete/', { keys });

  const previewMonitorPolicy = async (
    data: Record<string, unknown>,
    config?: AxiosRequestConfig
  ) => {
    return await post('/monitor/api/monitor_policy/preview/', data, config);
  };

  const getSystemChannelList = async () => {
    return await get('/monitor/api/system_mgmt/search_channel_list/');
  };

  const patchMonitorPolicy = async (
    id: number,
    data: {
      enable?: boolean;
      source?: SourceFeild;
    }
  ) => {
    return await patch(`/monitor/api/monitor_policy/${id}/`, data);
  };

  const deleteMonitorPolicy = async (id: React.Key) => {
    return await del(`/monitor/api/monitor_policy/${String(id)}/`);
  };

  const getTemplateObjects = async () => {
    return await get('/monitor/api/monitor_policy/template/monitor_object/');
  };

  const getSnapshot = async (
    params: {
      id?: React.Key;
      page?: number;
      page_size?: number;
    } = {}
  ) => {
    const { id, ...rest } = params;
    return await get(`/monitor/api/monitor_alert/snapshots/${String(id)}/`, {
      params: rest,
    });
  };

  const getUnitList = async () => {
    return await get(`/monitor/api/unit/list/`);
  };

  return {
    getMonitorEventDetail,
    getEventRaw,
    getMonitorPolicy,
    getPolicyTemplate,
    bulkCreatePoliciesFromTemplates,
    savePolicyTemplate,
    importPolicyTemplates,
    exportPolicyTemplates,
    bulkDeletePolicyTemplates,
    previewMonitorPolicy,
    getSystemChannelList,
    patchMonitorPolicy,
    deleteMonitorPolicy,
    getTemplateObjects,
    getSnapshot,
    getUnitList,
  };
};

export default useEventApi;
