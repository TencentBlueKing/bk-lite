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

  return {
    fetchModels,
    addProvider,
    updateProvider,
    deleteProvider,
  };
};
