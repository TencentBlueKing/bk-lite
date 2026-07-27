import type { CmdbAttrField, CmdbUserSummary } from '@/app/cmdb/components/cmdb-shared';
import type {
  SubscriptionListParams,
  SubscriptionRule,
  SubscriptionRuleCreate,
  SubscriptionRuleUpdate,
} from './types';

export interface CmdbSubscriptionModelSummary {
  model_id: string;
  model_name: string;
}

export interface CmdbSubscriptionCloudOption {
  proxy_id: string;
  proxy_name: string;
}

export interface SubscriptionListController {
  rules: SubscriptionRule[];
  loading: boolean;
  pagination: { current: number; pageSize: number; total: number };
  fetchRules: (params?: SubscriptionListParams) => Promise<void> | void;
  refresh: () => Promise<void> | void;
}

export interface SubscriptionMutationController {
  submitting: boolean;
  createRule: (payload: SubscriptionRuleCreate) => Promise<unknown>;
  updateRule: (id: number, payload: SubscriptionRuleUpdate) => Promise<unknown>;
  deleteRule: (id: number) => Promise<unknown>;
  toggleRule: (id: number) => Promise<unknown>;
}

export interface SubscriptionRuleFormRuntime {
  userList: CmdbUserSummary[];
  modelList: CmdbSubscriptionModelSummary[];
  cloudOptions: CmdbSubscriptionCloudOption[];
  searchInstances: (params: {
    query_list: unknown[];
    page: number;
    page_size: number;
    order: string;
    model_id: string;
    role: string;
    case_sensitive: boolean;
  }) => Promise<{
    insts?: Array<{
      _id?: string | number;
      inst_name?: string;
      name?: string;
      ip_addr?: string;
    }>;
  }>;
  getModelAttrGroupsFullInfo: (modelId: string) => Promise<{
    groups?: Array<{ attrs?: CmdbAttrField[] }>;
  } | unknown>;
  getModelAssociations: (modelId: string) => Promise<unknown>;
  loadChannelOptions: () => Promise<Array<{ label: string; value: number }>>;
}
