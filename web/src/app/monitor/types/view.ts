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
