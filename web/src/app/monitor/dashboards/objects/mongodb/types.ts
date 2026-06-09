import { ChartData } from '@/app/monitor/types';

export type MetricUnit =
  | 'counts'
  | 'percent'
  | 'cps'
  | 's'
  | 'bytes'
  | 'byteps'
  | 'ms'
  | 'none'
  | 'ns'
  | 'mebibytes';

export interface MongoMetricConfig {
  name: string;
  display_name: string;
  description: string;
  unit: MetricUnit;
  query: string;
  color: string;
  dimensions?: Array<{ name: string; description: string }>;
  groupId?: number | string;
}

export interface MetricSeries extends MongoMetricConfig {
  viewData: ChartData[];
  loadState: 'success' | 'error';
}

export interface TrendLegendItem {
  label: string;
  color: string;
  primary?: boolean;
  dashed?: boolean;
}
