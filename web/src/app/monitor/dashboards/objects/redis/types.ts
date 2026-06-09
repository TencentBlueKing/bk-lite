import { ChartData } from '@/app/monitor/types';

export type MetricUnit =
  | 'counts'
  | 'percent'
  | 'cps'
  | 's'
  | 'bytes'
  | 'byteps'
  | 'ms'
  | 'none';

export interface RedisMetricConfig {
  name: string;
  display_name: string;
  description: string;
  unit: MetricUnit;
  query: string;
  color: string;
  dimensions?: Array<{ name: string; description: string }>;
  groupId?: number | string;
}

export interface MetricSeries extends RedisMetricConfig {
  viewData: ChartData[];
  loadState: 'success' | 'error';
}

export interface MetricSection {
  key: string;
  title: string;
  metrics: MetricSeries[];
}

export interface TrendLegendItem {
  label: string;
  color: string;
  primary?: boolean;
  dashed?: boolean;
}
