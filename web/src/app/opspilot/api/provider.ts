import useApiClient from '@/utils/request';
import {
  Model,
  ModelVendor,
  ModelVendorPayload,
  ModelGroup,
  ModelGroupPayload,
  GroupOrderPayload,
} from '../types/provider';

export const useProviderApi = () => {
  const { get, post, put, del, patch } = useApiClient();

  interface TestVendorConnectionPayload {
    api_base: string;
    api_key?: string;
    password_changed?: boolean;
    original_id?: number;
  }

  const fetchModels = async (type: string, params?: Record<string, unknown>): Promise<Model[]> => {
    return get(`/opspilot/model_provider_mgmt/${type}/`, params ? { params } : undefined);
  };

  const fetchModelDetail = async (type: string, id: number): Promise<Model> => {
    return get(`/opspilot/model_provider_mgmt/${type}/${id}/`);
  };

  const addProvider = async (type: string, payload: Record<string, unknown>): Promise<Model> => {
    return post(`/opspilot/model_provider_mgmt/${type}/`, payload);
  };

  const updateProvider = async (type: string, id: number, payload: Record<string, unknown>): Promise<Model> => {
    return put(`/opspilot/model_provider_mgmt/${type}/${id}/`, payload);
  };

  const patchProvider = async (type: string, id: number, payload: Record<string, unknown>): Promise<Model> => {
    return patch(`/opspilot/model_provider_mgmt/${type}/${id}/`, payload);
  };

  const deleteProvider = async (type: string, id: number): Promise<void> => {
    await del(`/opspilot/model_provider_mgmt/${type}/${id}/`);
  };

  const fetchVendors = async (params?: Record<string, unknown>): Promise<ModelVendor[]> => {
    return get('/opspilot/model_provider_mgmt/model_vendor/', params ? { params } : undefined);
  };

  const fetchVendorDetail = async (id: number): Promise<ModelVendor> => {
    return get(`/opspilot/model_provider_mgmt/model_vendor/${id}/`);
  };

  const createVendor = async (payload: ModelVendorPayload): Promise<ModelVendor> => {
    return post('/opspilot/model_provider_mgmt/model_vendor/', payload);
  };

  const updateVendor = async (id: number, payload: Partial<ModelVendorPayload>): Promise<ModelVendor> => {
    return put(`/opspilot/model_provider_mgmt/model_vendor/${id}/`, payload);
  };

  const patchVendor = async (id: number, payload: Partial<ModelVendorPayload>): Promise<ModelVendor> => {
    return patch(`/opspilot/model_provider_mgmt/model_vendor/${id}/`, payload);
  };

  const deleteVendor = async (id: number): Promise<void> => {
    await del(`/opspilot/model_provider_mgmt/model_vendor/${id}/`);
  };

  const testVendorConnection = async (payload: TestVendorConnectionPayload): Promise<{ success: boolean }> => {
    await post('/opspilot/model_provider_mgmt/model_vendor/test_connection/', payload);
    return { success: true };
  };

  const fetchModelGroups = async (_type: string, provider_type?: string): Promise<ModelGroup[]> => {
    const params = provider_type ? { provider_type } : {};
    return get(`/opspilot/model_provider_mgmt/model_type/`, { params });
  };

  const createModelGroup = async (_type: string, payload: ModelGroupPayload): Promise<ModelGroup> => {
    return post(`/opspilot/model_provider_mgmt/model_type/`, payload);
  };

  const updateModelGroup = async (_type: string, groupId: string, payload: Partial<ModelGroupPayload>): Promise<ModelGroup> => {
    return put(`/opspilot/model_provider_mgmt/model_type/${groupId}/`, payload);
  };

  const deleteModelGroup = async (_type: string, groupId: string): Promise<void> => {
    await del(`/opspilot/model_provider_mgmt/model_type/${groupId}/`);
  };

  const updateGroupOrder = async (_type: string, payload: GroupOrderPayload): Promise<ModelGroup> => {
    return put(`/opspilot/model_provider_mgmt/model_type/change_index/`, payload);
  };

  return {
    fetchModels,
    fetchModelDetail,
    addProvider,
    updateProvider,
    patchProvider,
    deleteProvider,
    fetchVendors,
    fetchVendorDetail,
    createVendor,
    updateVendor,
    patchVendor,
    deleteVendor,
    testVendorConnection,
    fetchModelGroups,
    createModelGroup,
    updateModelGroup,
    deleteModelGroup,
    updateGroupOrder,
  };
};
