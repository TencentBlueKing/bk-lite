import type { DirItem } from './index';
import type { UnifiedFilterDefinition, ValueConfig } from './dashBoard';

export type ScreenWidgetChartType =
  | 'single'
  | 'multiValue'
  | 'gauge'
  | 'line'
  | 'bar'
  | 'pie'
  | 'table'
  | 'topN'
  | 'eventTable'
  | 'eventTimeline'
  | 'cardList'
  | 'radar'
  | 'nodeGraph'
  | 'topologyMap'
  | 'room3D'
  | 'networkStatusTopology'
  | 'application3D'
  | 'relatedTopology';

export type ScreenFitAdapter = 'fill' | 'fitWidth' | 'fitHeight';

/** 编辑画布和 PDF 使用的等比留边，不写入 viewport。 */
export type ScreenDisplayAdapter = ScreenFitAdapter | 'contain';

export type ScreenBackgroundConfig =
  | { type: 'color'; color: string }
  | { type: 'preset'; key: string };

export interface ScreenViewportConfig {
  width: number;
  height: number;
  background?: ScreenBackgroundConfig;
  theme?: ScreenThemeId;
  adapter?: ScreenFitAdapter;
}

export type ScreenThemeId = 'screen-dark' | 'screen-light';

export interface ScreenDecorationsConfig {
  showTitle?: boolean;
  showClock?: boolean;
  title?: string;
}

export type ScreenClockFormatId =
  | 'HH:mm:ss'
  | 'YYYY-MM-DD'
  | 'YYYY-MM-DD HH:mm:ss'
  | 'YYYY年M月D日'
  | 'M月D日 HH:mm'
  | 'dddd HH:mm:ss';

export type ScreenTextColorToken = 'canvas' | 'muted' | 'accent';
export type ScreenTextAlign = 'left' | 'center' | 'right';

export interface ScreenTextStyleConfig {
  fontSize?: number;
  fontWeight?: number;
  color?: ScreenTextColorToken;
  align?: ScreenTextAlign;
}

export type ScreenTitleFramePresetId =
  | 'hero-1'
  | 'hero-2'
  | 'hero-3'
  | 'hero-4'
  | 'hero-5'
  | 'hero-6'
  | 'section-1'
  | 'section-2'
  | 'section-3'
  | 'section-4';

export type ScreenDecorationType = 'corner' | 'divider' | 'panelFrame';

/** 空心边框。`a`/`b` 只用于读旧数据。 */
export type ScreenPanelFramePresetId =
  | 'border-21'
  | 'border-22'
  | 'border-23'
  | 'border-25'
  | 'border-1'
  | 'tech'
  | 'border-16'
  | 'border-20'
  | 'border-24';

/** 分隔线。`a`/`b` 只用于读旧数据。 */
export type ScreenDividerPresetId =
  | 'line-1'
  | 'line-2'
  | 'line-3'
  | 'line-dec'
  | 'line-4';

export type ScreenDecorationPresetId =
  | 'a'
  | 'b'
  | ScreenPanelFramePresetId
  | ScreenDividerPresetId;

export interface ScreenItemGeometry {
  id: string;
  x: number;
  y: number;
  w: number;
  h: number;
  zIndex: number;
}

export interface ScreenWidgetItem extends ScreenItemGeometry {
  kind?: 'widget';
  type: 'widget';
  chartType: ScreenWidgetChartType;
  title: string;
  valueConfig: ValueConfig;
}

export interface ScreenTextItem extends ScreenItemGeometry {
  kind: 'text';
  content: string;
  textStyle?: ScreenTextStyleConfig;
}

export interface ScreenClockItem extends ScreenItemGeometry {
  kind: 'clock';
  format: ScreenClockFormatId;
  textStyle?: ScreenTextStyleConfig;
}

export interface ScreenTitleFrameItem extends ScreenItemGeometry {
  kind: 'titleFrame';
  preset: ScreenTitleFramePresetId;
  content: string;
  textStyle?: ScreenTextStyleConfig;
}

export interface ScreenDecorationItem extends ScreenItemGeometry {
  kind: 'decoration';
  decorationType: ScreenDecorationType;
  preset: ScreenDecorationPresetId;
}

export type ScreenShapeKind = 'rect' | 'circle' | 'roundedRect';

export type ScreenShapeGradientDirection = 'vertical' | 'horizontal';

export interface ScreenShapeStyle {
  backgroundColor: string;
  hideBackground: boolean;
  borderColor: string;
  borderWidth: number;
  hideBorder: boolean;
  shadow: number;
  gradient: boolean;
  gradientDirection: ScreenShapeGradientDirection;
  gradientStart: string;
  gradientEnd: string;
}

export interface ScreenShapeItem extends ScreenItemGeometry {
  kind: 'shape';
  shape: ScreenShapeKind;
  shapeStyle: ScreenShapeStyle;
}

export type ScreenItem =
  | ScreenWidgetItem
  | ScreenTextItem
  | ScreenClockItem
  | ScreenTitleFrameItem
  | ScreenDecorationItem
  | ScreenShapeItem;

export interface ScreenViewSets {
  viewport: ScreenViewportConfig;
  items: ScreenItem[];
  decorations: ScreenDecorationsConfig;
  filters?: UnifiedFilterDefinition[];
}

export interface ScreenProps {
  selectedScreen?: DirItem | null;
  shareMode?: boolean;
}
