import type { FilterItem } from '@/app/cmdb/store';

export type FilterType = 'condition' | 'instances';
export type TriggerType = 'attribute_change' | 'relation_change' | 'expiration';

export interface ConditionFilter {
  query_list: FilterItem[];
}

export interface InstancesFilter {
  instance_ids: number[];
}

export interface AttributeChangeConfig {
  fields: string[];
}

export interface RelationChangeConfig {
  related_model: string;
  fields?: string[];
}

export interface ExpirationConfig {
  time_field: string;
  days_before: number;
}

export interface TriggerConfig {
  attribute_change?: AttributeChangeConfig;
  relation_change?: RelationChangeConfig;
  expiration?: ExpirationConfig;
}

export interface Recipients {
  users: number[];
}

export interface SubscriptionRule {
  id: number;
  name: string;
  organization: number;
  model_id: string;
  filter_type: FilterType;
  instance_filter: ConditionFilter | InstancesFilter;
  trigger_types: TriggerType[];
  trigger_config: TriggerConfig;
  recipients: Recipients;
  channel_ids: number[];
  is_enabled: boolean;
  last_triggered_at: string | null;
  last_check_time: string | null;
  created_by: string;
  created_at: string;
  updated_by: string;
  updated_at: string;
  can_manage: boolean;
}

export interface SubscriptionRuleCreate {
  name: string;
  organization: number;
  model_id: string;
  filter_type: FilterType;
  instance_filter: ConditionFilter | InstancesFilter;
  trigger_types: TriggerType[];
  trigger_config: TriggerConfig;
  recipients: Recipients;
  channel_ids: number[];
  is_enabled?: boolean;
}

export type SubscriptionRuleUpdate = Partial<SubscriptionRuleCreate>;

export interface SubscriptionListParams {
  name?: string;
  page?: number;
  page_size?: number;
}

export type QuickSubscribeSource =
  | 'list_selection'
  | 'list_filter'
  | 'detail'
  | 'drawer';

export interface QuickSubscribeDefaults {
  source: QuickSubscribeSource;
  model_id: string;
  model_name: string;
  filter_type: FilterType;
  instance_filter: ConditionFilter | InstancesFilter;
  name: string;
  organization: number;
  recipients: Recipients;
}

export interface PageResult<T> {
  count: number;
  next?: string | null;
  previous?: string | null;
  results: T[];
}
