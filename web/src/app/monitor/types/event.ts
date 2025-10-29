import { ThresholdField, FilterItem } from '@/app/monitor/types';

export interface PluginItem {
  id: number;
  name: string;
  description: string;
  display_name?: string;
  monitor_object: number[];
  display_description?: string;
  [key: string]: unknown;
}

export interface SourceFeild {
  type: string;
  values: Array<string | number>;
}

export interface StrategyFields {
  name?: string;
  organizations?: string[];
  source?: SourceFeild;
  collect_type?: number;
  schedule?: {
    type: string;
    value: number;
  };
  period?: {
    type: string;
    value: number;
  };
  algorithm?: string;
  threshold: ThresholdField[];
  recovery_condition?: number;
  no_data_period?: {
    type: string;
    value: number;
  };
  no_data_recovery_period?: {
    type: string;
    value: number;
  };
  no_data_level?: string;
  notice?: boolean;
  notice_type?: string;
  notice_type_id?: number;
  notice_users?: string[];
  monitor_object?: number;
  id?: number;
  group_by?: string[];
  enable_alerts?: string[];
  query_condition?: {
    type: string;
    query?: string;
    metric_id?: number;
    filter?: FilterItem[];
  };
  [key: string]: unknown;
}

export interface FiltersConfig {
  level: string[];
  state: string[];
}

export interface UnitMap {
  [key: string]: number;
}

export interface ChannelItem {
  channel_type: string;
  id: number;
  name: string;
}
