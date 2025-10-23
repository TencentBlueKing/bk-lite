import { ListItem } from '@/app/log/types';
import { FilterItem } from './integration';

export interface UnitMap {
  [key: string]: number;
}

export interface ObjectItem {
  id: number;
  name: string;
  type: string;
  plugin_name?: string;
  plugin_id?: number;
  display_description?: string;
  description: string;
  display_name?: string;
  display_type?: string;
  collector: string;
  options?: ObjectItem[];
  label?: string;
  value?: string;
  [key: string]: unknown;
}

export interface TreeSortData {
  type: string;
  name_list: string[];
}

export interface StrategyFields {
  name?: string;
  alert_name?: string;
  alert_level?: string;
  log_groups?: string[];
  organizations?: string[];
  collect_type?: number;
  schedule?: {
    type: string;
    value: number;
  };
  period?: {
    type: string;
    value: number;
  };
  notice?: boolean;
  notice_type?: string;
  notice_type_id?: number;
  notice_users?: string[];
  id?: number;
  group_by?: string[];
  query?: string;
  alert_type?: string;
  enable?: boolean;
  alert_condition?: {
    group_by?: string[];
    query?: string;
    rule?: {
      mode: string;
      conditions: FilterItem[];
    };
  };
  show_fields?: string[];
  [key: string]: unknown;
}

export interface ChannelItem {
  channel_type: string;
  id: number;
  name: string;
}

export interface SelectCardsProps {
  data: ListItem[];
  value?: string;
  onChange?: (value: string) => void;
}

export interface ConditionFilterProps {
  data: FilterItem[];
  fields: string[];
  onChange?: (data: FilterItem[]) => void;
}

export interface FiltersConfig {
  level: string[];
  state: string[];
}

export interface LogAlertParams {
  id?: React.Key;
  status?: string;
  level?: string;
  collect_type?: string;
  policy_name?: string;
  step?: string;
  page?: number;
  page_size?: number;
  start_event_time?: string;
  end_event_time?: string;
}
