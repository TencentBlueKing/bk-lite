import type { DirItem } from './index';
import type { ValueConfig } from './dashBoard';

export interface ReportSection {
  id: string;
  title: string;
  description?: string;
  valueConfig?: ValueConfig;
}

export interface ReportViewSets {
  time_range?: string | number | null;
  sections: ReportSection[];
}

export interface ReportProps {
  selectedReport?: DirItem | null;
}
