import { ChartData } from '@/app/monitor/types';
import { BaseMetricConfig } from '../../shared/types';

export type { MetricUnit, TrendLegendItem } from '../../shared/types';

export interface NginxMetricConfig extends BaseMetricConfig {
  groupId?: number | string;
}

export interface MetricSeries extends NginxMetricConfig {
  viewData: ChartData[];
  loadState: 'success' | 'error';
}
