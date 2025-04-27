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

export const useQuotaApi = () => {
  const { get, post, put, del } = useApiClient();

  const fetchQuotaRules = async (params: any): Promise<{ items: any[]; count: number }> => {
    return get('/opspilot/quota_rule_mgmt/quota_rule/', { params });
  };

  const fetchGroupUsers = async (): Promise<any[]> => {
    return get('/opspilot/quota_rule_mgmt/quota_rule/get_group_user/');
  };

  const fetchModelsByGroup = async (groupId: string): Promise<any[]> => {
    return post('/opspilot/model_provider_mgmt/llm_model/search_by_groups/', { group_id: groupId });
  };

  const deleteQuotaRule = async (id: number): Promise<void> => {
    await del(`/opspilot/quota_rule_mgmt/quota_rule/${id}/`);
  };

  const saveQuotaRule = async (mode: 'add' | 'edit', id: number | undefined, payload: any): Promise<void> => {
    if (mode === 'add') {
      await post('/opspilot/quota_rule_mgmt/quota_rule/', payload);
    } else if (mode === 'edit' && id) {
      await put(`/opspilot/quota_rule_mgmt/quota_rule/${id}/`, payload);
    }
  };

  const fetchMyQuota = async (): Promise<any> => {
    return get('/opspilot/quota_rule_mgmt/quota_rule/my_quota/');
  };

  return {
    fetchQuotaRules,
    fetchGroupUsers,
    fetchModelsByGroup,
    deleteQuotaRule,
    saveQuotaRule,
    fetchMyQuota,
  };
};
