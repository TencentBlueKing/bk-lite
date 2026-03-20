import useApiClient from '@/utils/request';
import type {
  PageResult,
  SubscriptionListParams,
  SubscriptionRule,
  SubscriptionRuleCreate,
  SubscriptionRuleUpdate,
} from '../types/subscription';

export const useSubscriptionApi = () => {
  const { get, post, patch, del } = useApiClient();

  const getSubscriptionRules = async (
    params?: SubscriptionListParams
  ): Promise<PageResult<SubscriptionRule>> => {
    return get('/cmdb/api/subscription/', { params });
  };

  const getSubscriptionRule = async (id: number): Promise<SubscriptionRule> => {
    return get(`/cmdb/api/subscription/${id}/`);
  };

  const createSubscriptionRule = async (
    data: SubscriptionRuleCreate
  ): Promise<SubscriptionRule> => {
    return post('/cmdb/api/subscription/', data);
  };

  const updateSubscriptionRule = async (
    id: number,
    data: SubscriptionRuleUpdate
  ): Promise<SubscriptionRule> => {
    return patch(`/cmdb/api/subscription/${id}/`, data);
  };

  const deleteSubscriptionRule = async (id: number): Promise<void> => {
    await del(`/cmdb/api/subscription/${id}/`);
  };

  const toggleSubscriptionRule = async (id: number): Promise<SubscriptionRule> => {
    return post(`/cmdb/api/subscription/${id}/toggle/`);
  };

  return {
    getSubscriptionRules,
    getSubscriptionRule,
    createSubscriptionRule,
    updateSubscriptionRule,
    deleteSubscriptionRule,
    toggleSubscriptionRule,
  };
};
