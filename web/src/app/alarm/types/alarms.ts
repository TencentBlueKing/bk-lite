import type { Pagination, TableDataItem } from '@/app/alarm/types/types';
export interface GroupInfo {
  name?: string;
  description?: string;
  id?: number;
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

export interface AlarmTableDataItem {
  id: number;
  event_count: number;
  source_names: string;
  duration: string;
  operator_user: string;
  operator: string[];
  created_at: string;
  updated_at: string;
  alert_id: string;
  status: string;
  level: keyof LevelMap;
  title: string;
  content: string;
  first_event_time: string | null;
  last_event_time: string | null;
  item: string;
  resource_id: string;
  resource_name: string;
  resource_type: string;
  operate: string | null;
  notification_status: string;
  [key: string]: any;
}
export interface RuleInfo {
  type?: string;
  name?: string;
  grouping_rules?: GroupingRules;
  organizations?: string[];
  monitor_object?: number;
  id?: number;
}

export interface NodeConfigInfo {
  content?: string;
  id?: number;
  [key: string]: unknown;
}

export interface GroupingRules {
  query?: string;
  instances?: string[];
}

export interface ObjectInstItem {
  instance_id: string;
  agent_id: string;
  organizations: string[];
  time: string;
  [key: string]: unknown;
}

export interface IntergrationItem {
  label: string;
  value: string;
  list: ObjectItem[];
  name?: string;
  [key: string]: unknown;
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
  options?: ObjectItem[];
  label?: string;
  value?: string;
  [key: string]: unknown;
}

export interface PluginItem {
  id: number;
  name: string;
  description: string;
  display_name?: string;
  monitor_object: number[];
  display_description?: string;
  [key: string]: unknown;
}

export interface CollectionTargetField {
  monitor_instance_name: string;
  monitor_object_id?: number;
  interval: number;
  monitor_url?: string;
  unit?: string;
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

export interface IndexViewItem {
  name?: string;
  display_name?: string;
  id: number;
  isLoading?: boolean;
  child?: any[];
}
export interface ChartDataItem {
  metric: Record<string, string>;
  values: [number, string][];
  [key: string]: any;
}

export interface InterfaceTableItem {
  id: string;
  [key: string]: string;
}

export interface ConditionItem {
  label: string | null;
  condition: string | null;
  value: string;
}

export interface FilterItem {
  name: string | null;
  method: string | null;
  value: string;
}

export interface SearchParams {
  time?: number;
  end?: number;
  start?: number;
  step?: number;
  query: string;
}

export interface FiltersConfig {
  level: string[];
  state: string[];
  alarm_source: string[];
}
export interface ThresholdField {
  level: string;
  method: string;
  value: number | null;
}

export interface AlertProps {
  objects: ObjectItem[];
  groupObjects?: ObjectItem[];
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
  query_condition?: {
    type: string;
    query?: string;
    metric_id?: number;
    filter?: FilterItem[];
  };
  [key: string]: unknown;
}

export interface LevelMap {
  fatal: string;
  severity: string;
  warning: string;
  [key: string]: unknown;
}

export interface StateMap {
  new: string;
  closed: string;
  pending: string;
  processing: string;
  unassigned: string;
  resolved: string;
}

export interface UnitMap {
  [key: string]: number;
}

export interface MonitorGroupMap {
  [key: string]: {
    list: string[];
    default: string[];
  };
}

export interface ObjectIconMap {
  [key: string]: string;
}

export interface ConfigTypeMap {
  [key: string]: string[];
}

export interface ViewDetailProps {
  monitorObjectId: React.Key;
  instanceId: string;
  monitorObjectName: string;
  idValues: string[];
  instanceName: string;
}

export interface ChartProps {
  instance_id?: string;
  showInstName?: boolean;
  instance_id_keys: string[];
  instance_id_values: string[];
  instance_name: string;
  title: string;
  dimensions: any[];
  [key: string]: unknown;
}

export interface ViewModalProps {
  monitorObject: React.Key;
  monitorName: string;
  plugins: IntergrationItem[];
  form?: ChartProps;
  objects?: ObjectItem[];
}

export interface ViewListProps {
  objectId: React.Key;
  objects: ObjectItem[];
  showTab?: boolean;
}

export interface IntergrationMonitoredObject {
  key: string;
  node_ids: string | string[] | null;
  instance_name?: string | null;
  group_ids: string[];
  url?: string | null;
  ip?: string | null;
  instance_id?: string;
  instance_type?: string;
  endpoint?: string | null;
  server?: string | null;
  host?: string | null;
  port?: string | null;
  jmx_url?: string | null;
}

export interface TreeSortData {
  type: string;
  name_list: string[];
}

export interface ChannelItem {
  channel_type: string;
  id: number;
  name: string;
}
export interface NodeWorkload {
  created_by_kind: string;
  created_by_name: string;
}

export interface NodeThresholdColor {
  value: number;
  color: string;
}

export interface ChartDataConfig {
  data: TableDataItem;
  hexColor: NodeThresholdColor[];
  queryMetric: string;
}

export interface AlarmActionProps {
  rowData: TableDataItem[];
  btnSize?: 'small' | 'middle' | 'large';
  showAll?: boolean;
  displayMode?: 'inline' | 'dropdown';
  from?: 'alarm' | 'incident';
  onAction: () => void;
}

export interface AlarmTableProps {
  dataSource: TableDataItem[];
  pagination?: Pagination;
  loading: boolean;
  tableScrollY: string;
  selectedRowKeys: React.Key[];
  onChange: (pag: any) => void;
  onRefresh: () => void;
  onSelectionChange: (keys: React.Key[]) => void;
  extraActions?: (record: TableDataItem) => React.ReactNode;
  readonly?: boolean;
}
export interface EventRawData {
  item: string;
  level: string;
  title: string;
  value: number;
  labels: Record<string, string>;
  status: string;
  start_time: string;
  end_time: string;
  annotations: {
    summary: string;
    severity: string;
    alertname: string;
  };
  description: string;
  external_id: string;
  resource_id: number;
  resource_name: string;
  resource_type: string;
}

export interface EventItem {
  id: number;
  start_time: string;
  end_time: string;
  source_name: string;
  raw_data: EventRawData;
  received_at: string;
  title: string;
  description: string;
  level: string;
  action: string;
  rule_id: number | null;
  event_id: string;
  external_id: string;
  item: string;
  resource_id: string;
  resource_type: string;
  resource_name: string;
  status: string;
  assignee: any[];
  note: string | null;
  value: number;
  source: number;
}

export interface SearchFilterCondition {
  field: string;
  type: string;
  value: any;
}
export interface SearchFilterProps {
  onSearch: (condition: SearchFilterCondition, rawValue?: any) => void;
  attrList: Array<{
    attr_id: string;
    attr_name: string;
    attr_type: string;
    is_required?: boolean;
    editable?: boolean;
    option?: any[];
  }>;
}

export type ActionType =
  | 'close'
  | 'assign'
  | 'reassign'
  | 'acknowledge'
  | 'reopen';
