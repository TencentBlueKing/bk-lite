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
  list: ObectItem[];
  name?: string;
  [key: string]: unknown;
}

export interface ObectItem {
  id: number;
  name: string;
  type: string;
  plugin_name?: string;
  plugin_id?: number;
  display_description?: string;
  description: string;
  display_name?: string;
  display_type?: string;
  options?: ObectItem[];
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

export interface MetricItem {
  id: number;
  metric_group: number;
  metric_object: number;
  name: string;
  type: string;
  display_name?: string;
  display_description?: string;
  instance_id_keys?: string[];
  dimensions: any[];
  query?: string;
  unit?: string;
  displayType?: string;
  description?: string;
  viewData?: any[];
  style?: {
    width: string;
    height: string;
  };
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

export interface TableDataItem {
  metric: Record<string, string>;
  value: string;
  index: number;
  [key: string]: any;
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
  notify: string[];
  monitor_objects: string[];
}
export interface ThresholdField {
  level: string;
  method: string;
  value: number | null;
}

export interface AlertProps {
  objects: ObectItem[];
  metrics: MetricItem[];
  groupObjects?: ObectItem[];
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
  critical: string;
  error: string;
  warning: string;
  [key: string]: unknown;
}

export interface StateMap {
  new: string;
  recovered: string;
  closed: string;
  [key: string]: any;
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
  metrics?: MetricItem[];
  objects?: ObectItem[];
}

export interface ViewListProps {
  objectId: React.Key;
  objects: ObectItem[];
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
}

export interface MetricListItem {
  id: string;
  name: string;
  child: MetricItem[];
  display_name?: string;
  isOpen?: boolean;
  is_pre: boolean;
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
  value: number,
  color: string
}

export interface ChartDataConfig {
  data: TableDataItem,
  metricsData: MetricItem[],
  hexColor: NodeThresholdColor[],
  queryMetric: string
}