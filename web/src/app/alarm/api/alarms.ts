import useApiClient from '@/utils/request';

export const useAlarmApi = () => {
  const { get, post } = useApiClient();

  const getAlarmList = async (params: any) => {
    return get('/alerts/api/alerts/', { params });
  };

  const getEventList = async (params: any) => {
    return get('/alerts/api/events/', { params });
  };

  const getRelatedAlerts = async (
    alertId: number,
    params?: { time_window?: number; limit?: number }
  ) => {
    return get(`/alerts/api/alerts/${alertId}/related/`, { params });
  };

  const alertActionOperate = async (actionType: string, params: any) => {
    return post(`/alerts/api/alerts/operator/${actionType}/`, params);
  };

  return { getAlarmList, getEventList, getRelatedAlerts, alertActionOperate };
};
