import type { DirItem } from './index';
import type { UnifiedFilterDefinition, WidgetConfig } from './dashBoard';

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
}

export interface ReportDetail {
  id: number | string;
  name: string;
  desc?: string | null;
  updated_at: string;
  view_sets: unknown;
}

export interface SaveReportViewSetsInput {
  view_sets: ReportViewSets;
  expected_updated_at: string;
}
