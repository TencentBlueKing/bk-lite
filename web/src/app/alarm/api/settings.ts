import useApiClient from '@/utils/request';

export const useSettingApi = () => {
  const { get, post, del, put, patch } = useApiClient();

  const getAssignmentList = (params: any) =>
    get('/alerts/api/assignment/', { params });

  const getAssignment = (id: string | number) =>
    get(`/alerts/api/assignment/${id}/`);

  const createAssignment = (params: any) =>
    post('/alerts/api/assignment/', params);

  const updateAssignment = (id: string | number, params: any) =>
    put(`/alerts/api/assignment/${id}/`, params);

  const deleteAssignment = (id: string | number) =>
    del(`/alerts/api/assignment/${id}/`);

  const patchAssignment = (id: string | number, params: any) =>
    patch(`/alerts/api/assignment/${id}/`, params);

  const getShieldList = (params: any) => get('/alerts/api/shield/', { params });

  const getShield = (id: string | number) => get(`/alerts/api/shield/${id}/`);

  const createShield = (params: any) => post('/alerts/api/shield/', params);

  const updateShield = (id: string | number, params: any) =>
    put(`/alerts/api/shield/${id}/`, params);

  const deleteShield = (id: string | number) =>
    del(`/alerts/api/shield/${id}/`);

  const patchShield = (id: string | number, params: any) =>
    patch(`/alerts/api/shield/${id}/`, params);

  const getAggregationRule = (params: any) =>
    get(`/alerts/api/aggregation_rule/`, { params });

  const getCorrelationRuleList = (params: any) =>
    get(`/alerts/api/correlation_rule/`, { params });

  const createCorrelationRule = (params: any) =>
    post('/alerts/api/correlation_rule/', params);

  const updateCorrelationRule = (id: string | number, params: any) =>
    put(`/alerts/api/correlation_rule/${id}/`, params);

  const deleteCorrelationRule = (id: string | number) =>
    del(`/alerts/api/correlation_rule/${id}/`);

  const getGlobalConfig = (key: any) =>
    get(`/alerts/api/settings/get_setting_key/${key}/`);

  const updateGlobalConfig = (id: any, params: any) =>
    put(`/alerts/api/settings/${id}/`, params);

  const toggleGlobalConfig = (id: any, params: any) =>
    patch(`/alerts/api/settings/${id}/`, params);

  const getLogList = (params: any) => get('/alerts/api/log/', { params });

  const getChannelList = (params: any) =>
    get('/alerts/api/settings/get_channel_list/', { params });

  return {
    getAssignmentList,
    getAssignment,
    createAssignment,
    updateAssignment,
    deleteAssignment,
    patchAssignment,
    getShieldList,
    getShield,
    createShield,
    updateShield,
    deleteShield,
    patchShield,
    getAggregationRule,
    getCorrelationRuleList,
    createCorrelationRule,
    updateCorrelationRule,
    deleteCorrelationRule,
    getGlobalConfig,
    updateGlobalConfig,
    toggleGlobalConfig,
    getLogList,
    getChannelList
  };
};
