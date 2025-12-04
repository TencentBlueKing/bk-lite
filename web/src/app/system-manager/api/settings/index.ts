import useApiClient from '@/utils/request';

export const useSettingsApi = () => {
  const { get, post, del } = useApiClient();

  /**
   * Fetches user API secrets.
   */
  const fetchUserApiSecrets = async (): Promise<any[]> => {
    return get('/base/user_api_secret/');
  };

  /**
   * Fetches teams/groups.
   */
  const fetchTeams = async (): Promise<any[]> => {
    return get('/opspilot/knowledge_mgmt/knowledge_base/get_teams/');
  };

  /**
   * Deletes a user API secret by ID.
   * @param id - Secret ID.
   */
  const deleteUserApiSecret = async (id: number): Promise<void> => {
    await del(`/base/user_api_secret/${id}/`);
  };

  /**
   * Creates a new user API secret.
   */
  const createUserApiSecret = async (): Promise<void> => {
    await post('/base/user_api_secret/');
  };

  return {
    fetchUserApiSecrets,
    fetchTeams,
    deleteUserApiSecret,
    createUserApiSecret,
  };
};