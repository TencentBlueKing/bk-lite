export interface ListItem {
  title?: string;
  label?: string;
  name?: string;
  display_name?: string;
  id?: string | number;
  value?: string | number;
  color?: string;
}

export interface TableDataItem {
  id?: number | string;
  [key: string]: any;
}

export interface ThresholdField {
  level: string;
  method: string;
  value: number | null;
}

export type {
  ChartData,
  Dimension,
  GapInterval,
  MetricItem,
} from '@/app/monitor/components/monitor-dashboard-widgets/types';
