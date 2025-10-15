import {
  IntegrationItem,
  ChartProps,
  MetricItem,
  ObjectItem,
  TableDataItem,
} from '@/app/monitor/types';

export interface ViewModalProps {
  monitorObject: React.Key;
  monitorName: string;
  plugins: IntegrationItem[];
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
}
