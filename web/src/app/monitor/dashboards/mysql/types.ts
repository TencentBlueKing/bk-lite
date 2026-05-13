import { ChartData } from '@/app/monitor/types';

export type MetricUnit =
  | 'counts'
  | 'percent'
  | 'cps'
  | 'bytes'
  | 'byteps'
  | 'ms'
  | 'ops'
  | 'permin';

export type MysqlMetricConfig = {
  name: string;
  display_name: string;
  description: string;
  unit: MetricUnit;
  query: string;
  color: string;
  dimensions?: Array<{ name: string; description: string }>;
  groupId?: number | string;
};

export type MetricOriginMeta = {
  kind: 'raw' | 'derived';
  sources: string[];
  queryHint: string;
};

export type MetricSeries = MysqlMetricConfig & {
  viewData: ChartData[];
  loadState: 'success' | 'error';
};

export type MetricSection = {
  key: string;
  title: string;
  metrics: MetricSeries[];
};

export type TrendLegendItem = {
  label: string;
  color: string;
  primary?: boolean;
};
