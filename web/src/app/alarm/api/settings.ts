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

  // Alarm Strategy API (告警策略)
  const getAlarmStrategyList = (params: any) =>
    get('/alerts/api/alarm_strategy/', { params });

  const createAlarmStrategy = (params: any) =>
    post('/alerts/api/alarm_strategy/', params);

  const updateAlarmStrategy = (id: string | number, params: any) =>
    put(`/alerts/api/alarm_strategy/${id}/`, params);

  const deleteAlarmStrategy = (id: string | number) =>
    del(`/alerts/api/alarm_strategy/${id}/`);

  // Legacy aliases for backward compatibility (映射到新API)
  const getCorrelationRuleList = (params: any) =>
    getAlarmStrategyList(params);

  const createCorrelationRule = (params: any) =>
    createAlarmStrategy(params);

  const updateCorrelationRule = (id: string | number, params: any) =>
    updateAlarmStrategy(id, params);

  const deleteCorrelationRule = (id: string | number) =>
    deleteAlarmStrategy(id);

  const getGlobalConfig = (key: any) =>
    get(`/alerts/api/settings/get_setting_key/${key}/`);

  const getLevelList = (params?: any) => get('/alerts/api/level/', { params });

  const createLevel = (params: any) => post('/alerts/api/level/', params);

  const updateLevel = (id: string | number, params: any) =>
    put(`/alerts/api/level/${id}/`, params);

  const deleteLevel = (id: string | number) => del(`/alerts/api/level/${id}/`);

  const updateGlobalConfig = (id: any, params: any) =>
    put(`/alerts/api/settings/${id}/`, params);

  const toggleGlobalConfig = (id: any, params: any) =>
    patch(`/alerts/api/settings/${id}/`, params);

  const getLogList = (params: any) => get('/alerts/api/log/', { params });

  const getChannelList = (params: any) =>
    get('/alerts/api/settings/get_channel_list/', { params });

  const getEnrichmentList = (params: any) =>
    get('/alerts/api/enrichment/', { params });

  const getEnrichment = (id: string | number) =>
    get(`/alerts/api/enrichment/${id}/`);

  const createEnrichment = (params: any) =>
    post('/alerts/api/enrichment/', params);

  const updateEnrichment = (id: string | number, params: any) =>
    put(`/alerts/api/enrichment/${id}/`, params);

  const deleteEnrichment = (id: string | number) =>
    del(`/alerts/api/enrichment/${id}/`);

  const patchEnrichment = (id: string | number, params: any) =>
    patch(`/alerts/api/enrichment/${id}/`, params);

  const getEnrichmentMetrics = () =>
    get('/alerts/api/enrichment/metrics/');

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
    getAlarmStrategyList,
    createAlarmStrategy,
    updateAlarmStrategy,
    deleteAlarmStrategy,
    getCorrelationRuleList,
    createCorrelationRule,
    updateCorrelationRule,
    deleteCorrelationRule,
    getLevelList,
    createLevel,
    updateLevel,
    deleteLevel,
    getGlobalConfig,
    updateGlobalConfig,
    toggleGlobalConfig,
    getLogList,
    getChannelList,
    getEnrichmentList,
    getEnrichment,
    createEnrichment,
    updateEnrichment,
    deleteEnrichment,
    patchEnrichment,
    getEnrichmentMetrics,
  };
};
