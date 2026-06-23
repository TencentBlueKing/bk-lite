import useApiClient from '@/utils/request';
import type {
  AvailableInstance,
  PreviewResult,
  UserSyncDepartmentOptions,
  UserSyncRun,
  UserSyncSource,
} from '@/app/system-manager/types/user-sync';
import { normalizeUserSyncList } from '@/app/system-manager/utils/userSyncUtils';

export const useUserSyncApi = () => {
  const { get, post, put, del } = useApiClient();

  async function getSyncSources(): Promise<UserSyncSource[]> {
    const response = await get<UserSyncSource[] | { count: number; items: UserSyncSource[] }>(
      '/system_mgmt/user_sync_source/'
    );
    return normalizeUserSyncList(response);
  }

  async function createSyncSource(data: Partial<UserSyncSource>): Promise<UserSyncSource> {
    return await post('/system_mgmt/user_sync_source/', data);
  }

  async function updateSyncSource(id: number, data: Partial<UserSyncSource>): Promise<UserSyncSource> {
    return await put(`/system_mgmt/user_sync_source/${id}/`, data);
  }

  async function deleteSyncSource(id: number): Promise<void> {
    return await del(`/system_mgmt/user_sync_source/${id}/`);
  }

  async function getAvailableInstances(): Promise<AvailableInstance[]> {
    return await get('/system_mgmt/integration_instance/available_instances/', {
      params: { capability: 'user_sync' },
    });
  }

  async function getDepartmentOptions(params: {
    integration_instance: number;
    current_root_department_id?: string;
    department_id_type?: string;
  }): Promise<UserSyncDepartmentOptions> {
    return await get('/system_mgmt/user_sync_source/department_options/', { params });
  }

  async function syncNow(id: number): Promise<void> {
    await post(`/system_mgmt/user_sync_source/${id}/sync_now/`);
  }

  async function getRecords(id: number): Promise<UserSyncRun[]> {
    return await get(`/system_mgmt/user_sync_source/${id}/records/`);
  }

  async function getPagedRecords(
    params: { page: number; page_size: number }
  ): Promise<{ count: number; items: Array<UserSyncRun & { source_name: string }> }> {
    return await get('/system_mgmt/user_sync_source/records/', { params });
  }

  async function previewSyncSource(payload: Record<string, unknown>): Promise<PreviewResult> {
    return await post('/system_mgmt/user_sync_source/preview/', payload);
  }

  return {
    getSyncSources,
    createSyncSource,
    updateSyncSource,
    deleteSyncSource,
    getAvailableInstances,
    getDepartmentOptions,
    syncNow,
    getRecords,
    getPagedRecords,
    previewSyncSource,
  };
};
