import useApiClient from '@/utils/request';
import { K8sRenderParams } from '@/app/alarm/types/integration';

export const useSourceApi = () => {
  const { get, post } = useApiClient();

  const getAlertSources = async () => get('/alerts/api/alert_source/');

  const getAlertSourcesDetail = async (id: number | string) =>
    get(`/alerts/api/alert_source/${id}`);

  const getK8sMeta = async () => get('/alerts/api/alert_source/k8s_meta/');

  const downloadK8sFile = async (fileKey: string, params: K8sRenderParams) =>
    post(`/alerts/api/alert_source/k8s_download/${fileKey}/`, params, {
      responseType: 'blob',
    });

  return { getAlertSources, getAlertSourcesDetail, getK8sMeta, downloadK8sFile };
};
