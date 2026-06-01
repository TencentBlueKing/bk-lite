import { ChartData } from '@/app/monitor/types';
import { BaseMetricConfig } from '../../shared/types';

export type { MetricUnit, TrendLegendItem } from '../../shared/types';

export interface MssqlMetricConfig extends BaseMetricConfig {
  groupId?: number | string;
}

export interface MetricSeries extends MssqlMetricConfig {
  viewData: ChartData[];
  loadState: 'success' | 'error';
}
