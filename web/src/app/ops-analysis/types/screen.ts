import type { DirItem } from './index';

export interface ScreenViewportConfig {
  width: number;
  height: number;
  background?: {
    type?: string;
    key?: string;
  };
  theme?: string;
}

export type ScreenItem = Record<string, unknown>;

export interface ScreenDecorationsConfig {
  showTitle?: boolean;
  showClock?: boolean;
  title?: string;
}

export interface ScreenViewSets {
  viewport: ScreenViewportConfig;
  items: ScreenItem[];
  decorations: ScreenDecorationsConfig;
}

export interface ScreenProps {
  selectedScreen?: DirItem | null;
}
