import { ChartData } from '@/app/monitor/types';
import { BaseMetricConfig } from '../../shared/types';

export type { MetricUnit, TrendLegendItem } from '../../shared/types';

export interface PostgresqlMetricConfig extends BaseMetricConfig {
  groupId?: number | string;
}

export interface MetricSeries extends PostgresqlMetricConfig {
  viewData: ChartData[];
  loadState: 'success' | 'error';
}
