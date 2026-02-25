import useApiClient from '@/utils/request';
import {
  Model,
  ModelGroup,
  ModelGroupPayload,
  GroupOrderPayload,
} from '../types/provider';

export const useProviderApi = () => {
  const { get, post, put, del } = useApiClient();

  const fetchModels = async (type: string): Promise<Model[]> => {
    return get(`/opspilot/model_provider_mgmt/${type}/`);
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

  const deleteProvider = async (type: string, id: number): Promise<void> => {
    await del(`/opspilot/model_provider_mgmt/${type}/${id}/`);
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
    deleteProvider,
    fetchModelGroups,
    createModelGroup,
    updateModelGroup,
    deleteModelGroup,
    updateGroupOrder,
  };
};
