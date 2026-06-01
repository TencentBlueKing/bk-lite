import { ComponentType } from 'react';
import { ChartData } from '@/app/monitor/types';

export type ProfessionalDashboardComponent = ComponentType;

export interface ProfessionalDashboardRegistryItem {
  key: string;
  aliases?: string[];
  objectName: string;
  objectDisplayName?: string;
  inheritedPermissionPath?: string;
  component: ProfessionalDashboardComponent;
}

export type MetricUnit =
  | 'counts'
  | 'percent'
  | 'cps'
  | 's'
  | 'bytes'
  | 'byteps'
  | 'kibibytes'
  | 'mebibytes'
  | 'ms'
  | 'ops'
  | 'permin'
  | 'ns'
  | 'msps'
  | 'none'
  | 'short'
  | string;

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

export interface TrendLegendItem {
  label: string;
  color: string;
  primary?: boolean;
  dashed?: boolean;
}
