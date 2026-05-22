import useApiClient from '@/utils/request';
import { K8sRenderParams, SnmpTrapNodeListResponse, TeamSecretsResponse, TeamSecretResponse } from '@/app/alarm/types/integration';

export const useSourceApi = () => {
  const { get, post } = useApiClient();

  const getAlertSources = async () => get('/alerts/api/alert_source/');

  const getAlertSourcesDetail = async (id: number | string) =>
    get(`/alerts/api/alert_source/${id}`);

  const getK8sMeta = async () => get('/alerts/api/alert_source/k8s_meta/');

  const getAlertSnmpTrapNodeList = async (data: {
    cloud_region_id?: number;
    page?: number;
    page_size?: number;
    is_active?: boolean;
    is_container?: boolean;
  }): Promise<SnmpTrapNodeListResponse> => post('/alerts/api/alert_source/snmp_trap_nodes/', data);

  const downloadK8sFile = async (fileKey: string, params: K8sRenderParams) =>
    post(`/alerts/api/alert_source/k8s_download/${fileKey}/`, params, {
      responseType: 'blob',
    });

  const listTeamSecrets = async (sourceId: number | string): Promise<TeamSecretsResponse> =>
    get(`/alerts/api/alert_source/${sourceId}/team_secrets/`);

  const addTeamSecret = async (sourceId: number | string, teamId: string): Promise<TeamSecretResponse> =>
    post(`/alerts/api/alert_source/${sourceId}/team_secrets/add/`, { team_id: teamId });

  const regenerateTeamSecret = async (sourceId: number | string, teamId: string): Promise<TeamSecretResponse> =>
    post(`/alerts/api/alert_source/${sourceId}/team_secrets/regenerate/`, { team_id: teamId });

  const removeTeamSecret = async (sourceId: number | string, teamId: string): Promise<void> =>
    post(`/alerts/api/alert_source/${sourceId}/team_secrets/remove/`, { team_id: teamId });

  return {
    getAlertSources,
    getAlertSourcesDetail,
    getK8sMeta,
    getAlertSnmpTrapNodeList,
    downloadK8sFile,
    listTeamSecrets,
    addTeamSecret,
    regenerateTeamSecret,
    removeTeamSecret,
  };
};
