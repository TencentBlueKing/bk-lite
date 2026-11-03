import useApiClient from '@/utils/request';

export interface ProcessFingerprintItem {
  id: number | string;
  target_type: string;
  linux_process: string;
  windows_image: string;
  built_in: boolean;
  enabled: boolean;
  permission?: string[];
  [key: string]: unknown;
}

export const useProcessFingerprintApi = () => {
  const { get, post, del, patch } = useApiClient();

  const getProcessFingerprintList = (params?: Record<string, unknown>) =>
    get('/cmdb/api/process_fingerprint/', { params });

  const createProcessFingerprint = (params: {
    target_type: string;
    linux_process?: string;
    windows_image?: string;
  }) => post('/cmdb/api/process_fingerprint/', params);

  const updateProcessFingerprint = (id: number | string, params: { enabled: boolean }) =>
    patch(`/cmdb/api/process_fingerprint/${id}/`, params);

  const deleteProcessFingerprint = (id: number | string) =>
    del(`/cmdb/api/process_fingerprint/${id}/`);

  return {
    getProcessFingerprintList,
    createProcessFingerprint,
    updateProcessFingerprint,
    deleteProcessFingerprint,
  };
};
