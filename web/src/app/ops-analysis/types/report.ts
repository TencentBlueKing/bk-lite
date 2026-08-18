import type { DirItem } from './index';
import type { FilterValue, UnifiedFilterDefinition, WidgetConfig } from './dashBoard';

export interface ReportSection {
  id: string;
  valueConfig: WidgetConfig;
}

export interface ReportViewSets {
  schema_version: 1;
  filters: UnifiedFilterDefinition[];
  sections: ReportSection[];
}

export interface ReportProps {
  selectedReport?: DirItem | null;
  shareMode?: boolean;
  renderMode?: boolean;
  renderFilterValues?: Record<string, FilterValue>;
  renderDataSourceIds?: number[];
  getReportDetailOverride?: (id: string | number) => Promise<ReportDetail>;
}

export interface ReportDetail {
  id: number | string;
  name: string;
  desc?: string | null;
  updated_at?: string;
  refresh_interval?: number;
  view_sets: unknown;
}

export interface SaveReportViewSetsInput {
  view_sets: ReportViewSets;
  expected_updated_at: string;
}
