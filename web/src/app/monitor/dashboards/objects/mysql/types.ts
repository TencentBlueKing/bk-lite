import { ChartData } from '@/app/monitor/types';
import { BaseMetricConfig } from '../../shared/types';

export type { MetricUnit, TrendLegendItem } from '../../shared/types';

export interface MysqlMetricConfig extends BaseMetricConfig {
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
