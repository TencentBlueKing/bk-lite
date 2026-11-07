import useApiClient from '@/utils/request';
import type { RetentionJob, RetentionPolicy } from '@/app/cmdb/(pages)/assetManage/systemSettings/RetentionPolicyForm';

export const useRetentionApi = () => {
  const { get, put } = useApiClient();
  const getRetention = () =>
    get('/cmdb/api/change_record_retention/') as Promise<{ policy: RetentionPolicy; job: RetentionJob }>;
  const saveRetention = (policy: RetentionPolicy) =>
    put('/cmdb/api/change_record_retention/', policy) as Promise<{ policy: RetentionPolicy; job: RetentionJob }>;
  return { getRetention, saveRetention };
};
