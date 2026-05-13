import { ChartData } from '@/app/monitor/types';

export type MetricUnit =
  | 'counts'
  | 'percent'
  | 'cps'
  | 's'
  | 'bytes'
  | 'byteps'
  | 'ms'
  | 'ops'
  | 'permin';

export interface MysqlMetricConfig {
  name: string;
  display_name: string;
  description: string;
  unit: MetricUnit;
  query: string;
  color: string;
  dimensions?: Array<{ name: string; description: string }>;
  groupId?: number | string;
}

export interface MetricOriginMeta {
  kind: 'raw' | 'derived';
  sources: string[];
  queryHint: string;
}

export interface MetricSeries extends MysqlMetricConfig {
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
