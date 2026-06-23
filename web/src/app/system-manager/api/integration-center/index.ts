import useApiClient from '@/utils/request';
import type {
  AvailableInstance,
  CreateIntegrationInstancePayload,
  IntegrationInstance,
  ProviderManifest,
  TestConnectionResult,
  UpdateIntegrationInstancePayload,
} from '@/app/system-manager/types/integration-center';

interface PaginatedResponse<T> {
  count: number;
  items: T[];
}

export const useIntegrationCenterApi = () => {
  const { get, post, put, del } = useApiClient();

  async function getProviders(): Promise<ProviderManifest[]> {
    return await get('/system_mgmt/integration_instance/providers/');
  }

  async function getInstances(params?: Record<string, unknown>): Promise<IntegrationInstance[]> {
    const response = await get<PaginatedResponse<IntegrationInstance> | IntegrationInstance[]>(
      '/system_mgmt/integration_instance/',
      { params }
    );
    if (Array.isArray(response)) return response;
    return (response as PaginatedResponse<IntegrationInstance>).items ?? [];
  }

  async function getInstance(id: number): Promise<IntegrationInstance> {
    return await get(`/system_mgmt/integration_instance/${id}/`);
  }

  async function createInstance(params: CreateIntegrationInstancePayload): Promise<IntegrationInstance> {
    return await post('/system_mgmt/integration_instance/', params);
  }

  async function updateInstance(id: number, params: UpdateIntegrationInstancePayload): Promise<IntegrationInstance> {
    return await put(`/system_mgmt/integration_instance/${id}/`, params);
  }

  async function deleteInstance(id: number): Promise<void> {
    return await del(`/system_mgmt/integration_instance/${id}/`);
  }

  async function testConnection(id: number, capability_key?: string): Promise<TestConnectionResult> {
    return await post(`/system_mgmt/integration_instance/${id}/test_connection/`, capability_key ? { capability_key } : {});
  }

  async function getAvailableInstances(capability: string): Promise<AvailableInstance[]> {
    return await get('/system_mgmt/integration_instance/available_instances/', {
      params: { capability },
    });
  }

  return {
    getProviders,
    getInstances,
    getInstance,
    createInstance,
    updateInstance,
    deleteInstance,
    testConnection,
    getAvailableInstances,
  };
};
