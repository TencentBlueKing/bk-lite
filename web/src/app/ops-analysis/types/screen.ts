import type { DirItem } from './index';
import type { UnifiedFilterDefinition, ValueConfig } from './dashBoard';

export type ScreenWidgetChartType =
  | 'single'
  | 'gauge'
  | 'line'
  | 'bar'
  | 'pie'
  | 'table'
  | 'topN'
  | 'eventTable'
  | 'networkStatusTopology';

export interface ScreenViewportConfig {
  width: number;
  height: number;
  background?: {
    type?: string;
    key?: string;
  };
  theme?: 'screen-tech-blue';
}

export interface ScreenDecorationsConfig {
  showTitle?: boolean;
  showClock?: boolean;
  title?: string;
}

export interface ScreenWidgetItem {
  id: string;
  type: 'widget';
  chartType: ScreenWidgetChartType;
  title: string;
  x: number;
  y: number;
  w: number;
  h: number;
  zIndex: number;
  valueConfig: ValueConfig;
}

export type ScreenItem = ScreenWidgetItem;

export interface ScreenViewSets {
  viewport: ScreenViewportConfig;
  items: ScreenItem[];
  decorations: ScreenDecorationsConfig;
  filters?: UnifiedFilterDefinition[];
}

export interface ScreenProps {
  selectedScreen?: DirItem | null;
}
