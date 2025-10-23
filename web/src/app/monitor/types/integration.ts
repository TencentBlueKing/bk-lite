import { MetricItem } from '@/app/monitor/types';

export interface OrderParam {
  id: number;
  sort_order: number;
  [key: string]: any;
}

export interface IntegrationMonitoredObject {
  key?: string;
  node_ids?: string | string[] | null;
  instance_name?: string | null;
  group_ids?: string[];
  url?: string | null;
  urls?: string | string[] | null;
  ip?: string | null;
  instance_id?: string;
  instance_type?: string;
  endpoint?: string | null;
  server?: string | null;
  host?: string | null;
  port?: string | null;
  jmx_url?: string | null;
  ENV_PORT?: string | null;
  ENV_HOST?: string | null;
  [key: string]: any;
}

export interface NodeConfigParam {
  configs?: any;
  collect_type?: string;
  monitor_object_id?: number;
  instances?: Omit<IntegrationMonitoredObject, 'key'>[];
}

export interface MetricInfo {
  type?: string;
  name?: string;
  display_name?: string;
  metric_group?: number;
  monitor_object?: number;
  instance_id_keys?: string[];
  id?: number;
  query?: string;
  data_type?: string;
  unit?: string;
  description?: string;
  dimensions?: string[];
}

export interface FilterItem {
  name: string | null;
  method: string | null;
  value: string;
}

export interface GroupingRules {
  type?: string;
  metric_id?: number;
  filter?: FilterItem[];
}

export interface RuleInfo {
  type?: string;
  name?: string;
  rule?: GroupingRules;
  organizations?: string[];
  monitor_object?: number;
  metric?: number;
  id?: number;
}

export interface InstanceInfo {
  organizations?: (string | number)[];
  organization?: (string | number)[];
  instance_name?: string;
  instance_id?: string;
  name?: string;
  keys?: React.Key[];
}

export interface ObjectInstItem {
  instance_id: string;
  agent_id: string;
  organizations: string[];
  time: string;
  [key: string]: unknown;
}

export interface MetricListItem {
  id: string;
  name: string;
  child: MetricItem[];
  display_name?: string;
  isOpen?: boolean;
  is_pre: boolean;
}

export interface DimensionItem {
  name: string;
  [key: string]: unknown;
}

export interface EnumItem {
  name: string | null;
  id: number | null;
  [key: string]: unknown;
}

export interface IntegrationAccessProps {
  showInterval?: boolean;
}

export interface InstNameConfig {
  index: number;
  field: string;
  dataIndex?: string;
}
