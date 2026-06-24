import useApiClient from '@/utils/request';
import type {
  AvailableInstance,
  IMNotificationChannel,
  IMNotificationChannelPayload,
  IMNotificationSyncRun,
  IMNotificationUserMapping,
} from '@/app/system-manager/types/im-notification';

interface PaginatedResponse<T> {
  count: number;
  items: T[];
}

export const useImNotificationApi = () => {
  const { get, post, put, del } = useApiClient();

  async function getChannels(params: Record<string, unknown>): Promise<PaginatedResponse<IMNotificationChannel>> {
    return await get('/system_mgmt/im_notification_channel/', { params })
  };

  async function createChannel(data: IMNotificationChannelPayload): Promise<IMNotificationChannel> {
    return await post('/system_mgmt/im_notification_channel/', data);
  }

  async function updateChannel(
    id: number,
    data: Partial<IMNotificationChannelPayload>
  ): Promise<IMNotificationChannel> {
    return await put(`/system_mgmt/im_notification_channel/${id}/`, data);
  }

  async function deleteChannel(id: number): Promise<void> {
    return await del(`/system_mgmt/im_notification_channel/${id}/`);
  }

  async function getAvailableInstances(): Promise<AvailableInstance[]> {
    return await get('/system_mgmt/integration_instance/available_instances/', {
      params: { capability: 'im_notification' },
    });
  }

  async function syncMappings(id: number): Promise<{ run_id?: number }> {
    return await post(`/system_mgmt/im_notification_channel/${id}/sync_mappings/`);
  }

  async function getMappings(id: number, params: Record<string, unknown>): Promise<PaginatedResponse<IMNotificationUserMapping>> {
    return await get(`/system_mgmt/im_notification_channel/${id}/mappings/`, { params });
  }

  async function getRecords(id: number, params: Record<string, unknown>): Promise<PaginatedResponse<IMNotificationSyncRun>> {
    return await get(`/system_mgmt/im_notification_channel/${id}/records/`, { params });
  }

  async function testSend(
    id: number,
    payload: { title: string; content: string; receivers: string[] }
  ): Promise<Record<string, unknown> | undefined> {
    return await post(`/system_mgmt/im_notification_channel/${id}/test_send/`, payload);
  }

  async function sendNotification(payload: {
    channel_id: number;
    user_ids: number[];
    title: string;
    content: string;
  }): Promise<Record<string, unknown> | undefined> {
    return await post('/system_mgmt/im_notification_channel/send/', payload);
  }

  return {
    getChannels,
    createChannel,
    updateChannel,
    deleteChannel,
    getAvailableInstances,
    syncMappings,
    getMappings,
    getRecords,
    testSend,
    sendNotification,
  };
};
