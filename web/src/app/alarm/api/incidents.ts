import useApiClient from '@/utils/request';

export const useIncidentsApi = () => {
  const { get, post, patch, del } = useApiClient();

  const getIncidentList = async (params: any) => {
    return get('/alerts/api/incident/', { params });
  };

  const getIncidentDetail = async (id: string) => {
    return get(`/alerts/api/incident/${id}/`);
  };

  const createIncidentDetail = async (params: any) => {
    return post(`/alerts/api/incident/`, params);
  };

  const modifyIncidentDetail = async (id: string, params: any) => {
    return patch(`/alerts/api/incident/${id}/`, params);
  };

  const incidentActionOperate = async (actionType: string, params: any) => {
    return post(`/alerts/api/incident/operator/${actionType}/`, params);
  };

  const getIncidentUpdates = async (incidentPk: string, params?: any) => {
    return get(`/alerts/api/incident/${incidentPk}/updates/`, { params });
  };

  const createIncidentUpdate = async (incidentPk: string, data: any) => {
    return post(`/alerts/api/incident/${incidentPk}/updates/`, data);
  };

  const editIncidentUpdate = async (incidentPk: string, updateId: number, data: any) => {
    return patch(`/alerts/api/incident/${incidentPk}/updates/${updateId}/`, data);
  };

  const deleteIncidentUpdate = async (incidentPk: string, updateId: number) => {
    return del(`/alerts/api/incident/${incidentPk}/updates/${updateId}/`);
  };

  const toggleKeyInfo = async (incidentPk: string, updateId: number) => {
    return post(`/alerts/api/incident/${incidentPk}/updates/${updateId}/key_info/`);
  };

  const getDiagnosis = async (incidentPk: string) => {
    return get(`/alerts/api/incident/${incidentPk}/updates/diagnosis/`);
  };

  const addAlertsToIncident = async (incidentId: string, alertIds: number[]) => {
    return post(`/alerts/api/incident/${incidentId}/alerts/add/`, {
      alert: alertIds,
    });
  };

  const removeAlertsFromIncident = async (incidentId: string, alertIds: number[]) => {
    return post(`/alerts/api/incident/${incidentId}/alerts/remove/`, {
      alert: alertIds,
    });
  };

  return {
    getIncidentList,
    getIncidentDetail,
    createIncidentDetail,
    modifyIncidentDetail,
    incidentActionOperate,
    getIncidentUpdates,
    createIncidentUpdate,
    editIncidentUpdate,
    deleteIncidentUpdate,
    toggleKeyInfo,
    getDiagnosis,
    addAlertsToIncident,
    removeAlertsFromIncident,
  };
};
