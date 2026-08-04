import {
  ChartProps,
  MetricItem,
  ObjectItem,
  TableDataItem,
  TimeSelectorDefaultValue,
  TimeValuesProps
} from '@/app/monitor/types';
import { Dayjs } from 'dayjs';

export interface ViewPluginOption {
  label: string;
  value: string;
}

export interface ViewColumnPreference {
  field_keys: string[];
  fixed_field_keys?: string[];
}

export interface ViewModalProps {
  monitorObject: React.Key;
  monitorName: string;
  plugins: ViewPluginOption[];
  form?: ChartProps;
  metrics?: MetricItem[];
  objects?: ObjectItem[];
}

export interface ViewListProps {
  objectId: React.Key;
  objects: ObjectItem[];
  showTab?: boolean;
  updateTree?: () => void;
}

export interface NodeThresholdColor {
  value: number;
  color: string;
}

export interface ChartDataConfig {
  data: TableDataItem;
  metricsData: MetricItem[];
  hexColor: NodeThresholdColor[];
  queryMetric: string;
}

export interface InterfaceTableItem {
  id: string;
  [key: string]: string;
}

export interface ViewDetailProps {
  monitorObjectId: React.Key;
  instanceId: string;
  monitorObjectName: string;
  idValues: string[];
  instanceName: string;
  /**
   * 查询标签键覆盖。例如主机全量指标下钻进程时，只用 instance_id
   * 过滤，避免把 process_name 拼进 __$labels__。
   */
  queryInstanceIdKeys?: string[];
  externalTimeValues?: TimeValuesProps;
  externalTimeDefaultValue?: TimeSelectorDefaultValue;
  externalFrequence?: number;
  externalRefreshSignal?: number;
  collectionInterval?: number;
  hideTimeSelector?: boolean;
  onExternalXRangeChange?: (range: [Dayjs, Dayjs]) => void;
}

export interface ViewInstanceSearchProps {
  monitor_object_id: React.Key;
  instance_id: string;
  metric_id: React.Key;
  auto_convert: boolean;
  limit?: number;
  mode?: 'top' | 'bottom' | 'limited' | string;
}

export interface TooltipMetricDataItem {
  metric: Record<string, string>;
  value: [number, string];
}

export interface TooltipDimensionDataItem {
  label: string;
  value: string;
}

export interface MetricInfo {
  metricItem: MetricItem;
  metricUnit: string;
}

export interface MetricDimensionTooltipProps {
  instanceId: string;
  monitorObjectId: React.Key;
  metricInfo: MetricInfo;
}
