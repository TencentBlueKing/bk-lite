import { ComponentType } from 'react';
import { ChartData } from '@/app/monitor/types';

export type ProfessionalDashboardComponent = ComponentType;

export interface ProfessionalDashboardRegistryItem {
  key: string;
  aliases?: string[];
  groupKey: string;
  objectName: string;
  objectDisplayName?: string;
  inheritedPermissionPath?: string;
  component: ProfessionalDashboardComponent;
}

export type MetricUnit =
  | 'none'
  | 'percent'
  | 'counts'
  | 'thousand'
  | 'million'
  | 'billion'
  | 'trillion'
  | 'quadrillion'
  | 'quintillion'
  | 'sextillion'
  | 'septillion'
  | 'bits'
  | 'kilobits'
  | 'megabits'
  | 'gigabits'
  | 'terabits'
  | 'petabits'
  | 'bytes'
  | 'kibibytes'
  | 'mebibytes'
  | 'gibibytes'
  | 'tebibytes'
  | 'pebibytes'
  | 'bitps'
  | 'kbitps'
  | 'mbitps'
  | 'gbitps'
  | 'tbitps'
  | 'pbitps'
  | 'byteps'
  | 'kibyteps'
  | 'mibyteps'
  | 'gibyteps'
  | 'tibyteps'
  | 'pibyteps'
  | 'ns'
  | 'µs'
  | 'us'
  | 'ms'
  | 's'
  | 'm'
  | 'h'
  | 'd'
  | 'cps'
  | 'hertz'
  | 'kilohertz'
  | 'megahertz'
  | 'msps'
  | 'celsius'
  | 'fahrenheit'
  | 'kelvin'
  | 'watts'
  | 'volts';

export interface BaseMetricConfig {
  name: string;
  display_name: string;
  description: string;
  unit: MetricUnit;
  query: string;
  color: string;
  dimensions?: Array<{ name: string; description?: string; [key: string]: unknown }>;
}

export interface MetricSeriesBase extends BaseMetricConfig {
  viewData: ChartData[];
  loadState: 'success' | 'error';
}

export interface GuideItem {
  label: string;
  detail: string;
}

export interface CollectionStatusResult {
  label: string;
  tagColor?: 'success' | 'warning' | 'error';
  accentColor?: string;
  summary?: string;
  detail: string;
}

export interface PeriodCompare {
  direction: 'up' | 'down' | 'flat';
  value: string;
}

export type CompareFavorableDirection = 'up' | 'down';

export interface EnumMetricOption {
  label: string;
  color?: string;
}

export type MetricEnumMap = Record<number, EnumMetricOption>;

export interface TrendLegendItem {
  label: string;
  color: string;
  primary?: boolean;
  dashed?: boolean;
}
