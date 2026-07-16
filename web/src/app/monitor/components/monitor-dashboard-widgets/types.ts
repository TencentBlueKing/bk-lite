import type React from 'react';

export interface GapInterval {
  start: number;
  end: number;
  duration?: number;
  series?: Array<{
    metric?: Record<string, string>;
    missing_points?: number;
  }>;
}

export interface ChartData {
  time: number;
  value1?: number;
  value2?: number;
  gapIntervals?: GapInterval[];
  seriesMetrics?: Record<string, Record<string, string>>;
  details?: Record<string, Array<{ name: string; label: string; value: string }>>;
  [key: string]: unknown;
}

export interface Dimension {
  name: string;
  description?: string;
  [key: string]: unknown;
}

export interface InterfaceTableItem {
  [key: string]: unknown;
}

export interface MetricItem {
  id: number;
  metric_group: number;
  metric_object: number;
  name: string;
  type: string;
  display_name?: string;
  display_description?: string;
  instance_id_keys?: string[];
  dimensions: Dimension[];
  query?: string;
  unit?: string;
  displayType?: string;
  description?: string;
  viewData?: ChartData[] | InterfaceTableItem[];
  displayUnit?: string;
  style?: {
    width: string;
    height: string;
  };
  [key: string]: unknown;
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

export type ProfessionalDashboardComponent = React.ComponentType;

export interface ProfessionalDashboardRegistryItem {
  key: string;
  aliases?: string[];
  groupKey: string;
  objectName: string;
  objectDisplayName?: string;
  inheritedPermissionPath?: string;
  component: ProfessionalDashboardComponent;
}
