import useApiClient from '@/utils/request';
import type {
  CreateIncidentIMGroupParams,
  IncidentIMGroup,
  IncidentIMGroupOptions,
  IncidentIMMemberList,
  IncidentIMMemberListParams,
  UpdateIncidentIMGroupParams,
} from '@/app/alarm/types/incidents';

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

  const getIncidentIMGroup = async (incidentPk: string): Promise<IncidentIMGroup | null> => {
    return get<IncidentIMGroup | null>(`/alerts/api/incident/${incidentPk}/im-group/`);
  };

  const getIncidentIMGroupOptions = async (
    incidentPk: string,
    channelId?: number,
  ): Promise<IncidentIMGroupOptions> => {
    return get<IncidentIMGroupOptions>(`/alerts/api/incident/${incidentPk}/im-group/options/`, {
      params: channelId === undefined ? undefined : { channel_id: channelId },
    });
  };

  const createIncidentIMGroup = async (
    incidentPk: string,
    data: CreateIncidentIMGroupParams,
  ): Promise<IncidentIMGroup> => {
    return post<IncidentIMGroup>(`/alerts/api/incident/${incidentPk}/im-group/`, data);
  };

  const updateIncidentIMGroup = async (
    incidentPk: string,
    data: UpdateIncidentIMGroupParams,
  ): Promise<IncidentIMGroup> => {
    return patch<IncidentIMGroup>(`/alerts/api/incident/${incidentPk}/im-group/`, data);
  };

  const getIncidentIMMembers = async (
    incidentPk: string,
    params: IncidentIMMemberListParams,
  ): Promise<IncidentIMMemberList> => {
    return get<IncidentIMMemberList>(`/alerts/api/incident/${incidentPk}/im-group/members/`, { params });
  };

  const retryIncidentIMGroup = async (incidentPk: string): Promise<IncidentIMGroup> => {
    return post<IncidentIMGroup>(`/alerts/api/incident/${incidentPk}/im-group/retry/`);
  };

  const pauseIncidentIMGroup = async (incidentPk: string): Promise<IncidentIMGroup> => {
    return post<IncidentIMGroup>(`/alerts/api/incident/${incidentPk}/im-group/pause/`);
  };

  const resumeIncidentIMGroup = async (incidentPk: string): Promise<IncidentIMGroup> => {
    return post<IncidentIMGroup>(`/alerts/api/incident/${incidentPk}/im-group/resume/`);
  };

  const unlinkIncidentIMGroup = async (incidentPk: string, groupName: string): Promise<void> => {
    return del<void>(`/alerts/api/incident/${incidentPk}/im-group/`, {
      data: { group_name: groupName },
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
    getIncidentIMGroup,
    getIncidentIMGroupOptions,
    createIncidentIMGroup,
    updateIncidentIMGroup,
    getIncidentIMMembers,
    retryIncidentIMGroup,
    pauseIncidentIMGroup,
    resumeIncidentIMGroup,
    unlinkIncidentIMGroup,
  };
};
