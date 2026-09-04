import useApiClient from '@/utils/request';

export interface PortFingerprintItem {
  id: number | string;
  port: number;
  protocol: string;
  target_type: string;
  built_in: boolean;
  permission?: string[];
  [key: string]: any;
}

export const usePortFingerprintApi = () => {
  const { get, post, del } = useApiClient();

  // 获取端口指纹列表
  const getPortFingerprintList = (params?: any) =>
    get('/cmdb/api/port_fingerprint/', { params });

  // 创建端口指纹
  const createPortFingerprint = (params: {
    port: number;
    target_type: string;
    protocol?: string;
  }) => post('/cmdb/api/port_fingerprint/', params);

  // 删除端口指纹
  const deletePortFingerprint = (id: number | string) =>
    del(`/cmdb/api/port_fingerprint/${id}/`);

  return {
    getPortFingerprintList,
    createPortFingerprint,
    deletePortFingerprint,
  };
};
