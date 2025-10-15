import useApiClient from '@/utils/request';
import { SourceFeild } from '@/app/monitor/types/event';

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
    } = {}
  ) => {
    return await get(`/monitor/api/monitor_policy/${id}`, {
      params,
    });
  };

  const getPolicyTemplate = async (params: {
    monitor_object_name?: string | null;
  }) => {
    return await post('/monitor/api/monitor_policy/template/', params);
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

  const deleteMonitorPolicy = async (id: number | string) => {
    return await del(`/monitor/api/monitor_policy/${id}/`);
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
    return await get(
      `/monitor/api/monitor_alert_metric_snapshot/query/${id}/`,
      {
        params: rest,
      }
    );
  };

  return {
    getMonitorEventDetail,
    getEventRaw,
    getMonitorPolicy,
    getPolicyTemplate,
    getSystemChannelList,
    patchMonitorPolicy,
    deleteMonitorPolicy,
    getTemplateObjects,
    getSnapshot,
  };
};

export default useEventApi;
