import { useCallback, useMemo, useRef, useState } from 'react';
import { message } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useSubscriptionApi } from '../api/subscription';
import type {
  FilterType,
  QuickSubscribeDefaults,
  QuickSubscribeSource,
  SubscriptionListParams,
  SubscriptionRule,
  SubscriptionRuleCreate,
  SubscriptionRuleUpdate,
} from '../types/subscription';

export function useSubscriptionList() {
  const api = useSubscriptionApi();
  const [rules, setRules] = useState<SubscriptionRule[]>([]);
  const [loading, setLoading] = useState(false);
  const [pagination, setPagination] = useState({
    current: 1,
    pageSize: 10,
    total: 0,
  });
  
  const paginationRef = useRef(pagination);
  paginationRef.current = pagination;
  
  const lastSearchRef = useRef<string>('');

  const fetchRules = useCallback(
    async (params?: SubscriptionListParams) => {
      setLoading(true);
      try {
        const page = params?.page || paginationRef.current.current;
        const pageSize = params?.page_size || paginationRef.current.pageSize;
        const search = params?.name ?? lastSearchRef.current;
        lastSearchRef.current = search;
        const data = await api.getSubscriptionRules({
          page,
          page_size: pageSize,
          name: search || undefined,
        });
        setRules(data.results || []);
        setPagination({ current: page, pageSize, total: data.count || 0 });
      } finally {
        setLoading(false);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    []
  );

  const refresh = useCallback(async () => {
    await fetchRules({ 
      page: paginationRef.current.current, 
      page_size: paginationRef.current.pageSize,
      name: lastSearchRef.current,
    });
  }, [fetchRules]);

  return { rules, loading, pagination, fetchRules, refresh };
}

export function useSubscriptionMutation() {
  const { t } = useTranslation();
  const api = useSubscriptionApi();
  const [submitting, setSubmitting] = useState(false);

  const withSubmit = useCallback(async <T,>(fn: () => Promise<T>) => {
    setSubmitting(true);
    try {
      return await fn();
    } finally {
      setSubmitting(false);
    }
  }, []);

  const createRule = useCallback(
    async (data: SubscriptionRuleCreate) => {
      const res = await withSubmit(() => api.createSubscriptionRule(data));
      message.success(t('successfullyAdded'));
      return res;
    },
    [api, withSubmit, t]
  );

  const updateRule = useCallback(
    async (id: number, data: SubscriptionRuleUpdate) => {
      const res = await withSubmit(() => api.updateSubscriptionRule(id, data));
      message.success(t('successfullyModified'));
      return res;
    },
    [api, withSubmit, t]
  );

  const deleteRule = useCallback(
    async (id: number) => {
      await withSubmit(() => api.deleteSubscriptionRule(id));
      message.success(t('successfullyDeleted'));
    },
    [api, withSubmit, t]
  );

  const toggleRule = useCallback(
    async (id: number) => {
      const res = await withSubmit(() => api.toggleSubscriptionRule(id));
      message.success(t('subscription.operateSuccess'));
      return res;
    },
    [api, withSubmit, t]
  );

  return { submitting, createRule, updateRule, deleteRule, toggleRule };
}

export function useQuickSubscribeDefaults(
  source: QuickSubscribeSource,
  context: {
    model_id: string;
    model_name: string;
    selectedInstanceIds?: number[];
    queryList?: any[];
    currentInstanceId?: number;
    currentInstanceName?: string;
    currentUser: number;
    currentOrganization: number;
  }
): QuickSubscribeDefaults {
  const selectedInstanceIdsKey = JSON.stringify(context.selectedInstanceIds || []);
  const queryListKey = JSON.stringify(context.queryList || []);

  return useMemo(() => {
    const timestamp = new Date().toISOString().slice(0, 16).replace(/[-:T]/g, '');

    switch (source) {
      case 'list_selection':
        return {
          source,
          model_id: context.model_id,
          model_name: context.model_name,
          filter_type: 'instances' as FilterType,
          instance_filter: { instance_ids: context.selectedInstanceIds || [] },
          name: `${context.model_name}${timestamp}`,
          organization: context.currentOrganization,
          recipients: { users: [context.currentUser] },
        };
      case 'list_filter':
        return {
          source,
          model_id: context.model_id,
          model_name: context.model_name,
          filter_type: 'condition' as FilterType,
          instance_filter: { query_list: context.queryList || [] },
          name: `${context.model_name}${timestamp}`,
          organization: context.currentOrganization,
          recipients: { users: [context.currentUser] },
        };
      case 'detail':
        return {
          source,
          model_id: context.model_id,
          model_name: context.model_name,
          filter_type: 'instances' as FilterType,
          instance_filter: {
            instance_ids: context.currentInstanceId ? [context.currentInstanceId] : [],
          },
          name: `${context.currentInstanceName || context.model_name}${timestamp}`,
          organization: context.currentOrganization,
          recipients: { users: [context.currentUser] },
        };
      default:
        return {
          source,
          model_id: context.model_id,
          model_name: context.model_name,
          filter_type: 'instances' as FilterType,
          instance_filter: { instance_ids: [] },
          name: '',
          organization: context.currentOrganization,
          recipients: { users: [context.currentUser] },
        };
    }
  }, [
    source,
    context.model_id,
    context.model_name,
    context.currentInstanceId,
    context.currentInstanceName,
    context.currentUser,
    context.currentOrganization,
    selectedInstanceIdsKey,
    queryListKey,
  ]);
}
