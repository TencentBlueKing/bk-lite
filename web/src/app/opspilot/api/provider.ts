import useApiClient from '@/utils/request';

export const useProviderApi = () => {
  const { get, post, put, del } = useApiClient();

  /**
   * Fetches models by type.
   * @param type - The type of models to fetch.
   */
  const fetchModels = async (type: string): Promise<any[]> => {
    return get(`/opspilot/model_provider_mgmt/${type}/`);
  };


  /**
   * Fetches models detail by type.
   * @param type - The type of models to fetch.
   * @param id - The ID of the model to fetch.
   */
  const fetchModelDetail = async (type: string, id: number): Promise<any> => {
    return get(`/opspilot/model_provider_mgmt/${type}/${id}/`);
  };

  /**
   * Adds a new provider.
   * @param type - The type of the provider.
   * @param payload - Data for the new provider.
   */
  const addProvider = async (type: string, payload: any): Promise<any> => {
    return post(`/opspilot/model_provider_mgmt/${type}/`, payload);
  };

  /**
   * Updates a provider.
   * @param type - The type of the provider.
   * @param id - The ID of the provider.
   * @param payload - Updated data for the provider.
   */
  const updateProvider = async (type: string, id: number, payload: any): Promise<any> => {
    return put(`/opspilot/model_provider_mgmt/${type}/${id}/`, payload);
  };

  /**
   * Deletes a provider.
   * @param type - The type of the provider.
   * @param id - The ID of the provider.
   */
  const deleteProvider = async (type: string, id: number): Promise<void> => {
    await del(`/opspilot/model_provider_mgmt/${type}/${id}/`);
  };

  // 新增分组管理相关API
  /**
   * Fetches model groups by type.
   * @param type - The type of model groups to fetch.
   * @param provider_type - The provider type filter (llm, embed, ocr, rerank).
   */
  const fetchModelGroups = async (type: string, provider_type?: string): Promise<any[]> => {
    const params = provider_type ? { provider_type } : {};
    return get(`/opspilot/model_provider_mgmt/model_type/`, { params });
  };

  /**
   * Creates a new model group.
   * @param type - The type of the model group.
   * @param payload - Data for the new group.
   */
  const createModelGroup = async (type: string, payload: any): Promise<any> => {
    return post(`/opspilot/model_provider_mgmt/model_type/`, payload);
  };

  /**
   * Updates a model group.
   * @param type - The type of the model group.
   * @param groupId - The ID of the group.
   * @param payload - Updated data for the group.
   */
  const updateModelGroup = async (type: string, groupId: string, payload: any): Promise<any> => {
    return put(`/opspilot/model_provider_mgmt/model_type/${groupId}/`, payload);
  };

  /**
   * Deletes a model group.
   * @param type - The type of the model group.
   * @param groupId - The ID of the group.
   */
  const deleteModelGroup = async (type: string, groupId: string): Promise<void> => {
    await del(`/opspilot/model_provider_mgmt/model_type/${groupId}/`);
  };

  /**
   * Updates the order of model groups.
   * @param type - The type of model groups.
   * @param payload - Group with updated index.
   */
  const updateGroupOrder = async (type: string, payload: { id: number; index: number }): Promise<any> => {
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
