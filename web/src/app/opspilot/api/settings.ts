import useApiClient from '@/utils/request';
import {
  QuotaRuleParams,
  QuotaRuleResponse,
  QuotaRulePayload,
  GroupUser,
  MyQuotaResponse,
} from '../types/settings';

export const useQuotaApi = () => {
  const { get, post, put, del } = useApiClient();

  const fetchQuotaRules = async (params: QuotaRuleParams): Promise<QuotaRuleResponse> => {
    return get('/opspilot/quota_rule_mgmt/quota_rule/', { params });
  };

  const fetchGroupUsers = async (): Promise<GroupUser[]> => {
    return get('/opspilot/quota_rule_mgmt/quota_rule/get_group_user/');
  };

  const fetchModelsByGroup = async (groupId: string): Promise<unknown[]> => {
    return post('/opspilot/model_provider_mgmt/llm_model/search_by_groups/', { group_id: groupId });
  };

  const deleteQuotaRule = async (id: number): Promise<void> => {
    await del(`/opspilot/quota_rule_mgmt/quota_rule/${id}/`);
  };

  const saveQuotaRule = async (mode: 'add' | 'edit', id: number | undefined, payload: QuotaRulePayload): Promise<void> => {
    if (mode === 'add') {
      await post('/opspilot/quota_rule_mgmt/quota_rule/', payload);
    } else if (mode === 'edit' && id) {
      await put(`/opspilot/quota_rule_mgmt/quota_rule/${id}/`, payload);
    }
  };

  const fetchMyQuota = async (): Promise<MyQuotaResponse> => {
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
