import type { ScreenItem } from '@/app/ops-analysis/types/screen';
import {
  isScreenClockItem,
  isScreenDecorationItem,
  isScreenShapeItem,
  isScreenTextItem,
  isScreenTitleFrameItem,
  isScreenWidgetItem,
  resolveDividerPreset,
  resolvePanelFramePreset,
} from './screenItems';

export interface ScreenElementListLabels {
  text?: string;
  title?: string;
  clock?: string;
  corner?: string;
  divider?: string;
  panelFrame?: string;
  panelFramePreset?: (preset: string) => string;
  dividerPreset?: (preset: string) => string;
  shapeRect?: string;
  shapeCircle?: string;
  shapeRoundedRect?: string;
}

export interface ScreenElementListEntry {
  id: string;
  label: string;
  zIndex: number;
}

const TEXT_LABEL_LIMIT = 12;

const truncate = (value: string) => {
  const trimmed = value.trim();
  if (trimmed.length <= TEXT_LABEL_LIMIT) return trimmed;
  return `${trimmed.slice(0, TEXT_LABEL_LIMIT)}…`;
};

const compactLabel = (value: string) => value.replace(/\s+/g, '');

export const getScreenItemBaseLabel = (
  item: ScreenItem,
  labels: ScreenElementListLabels = {},
): string => {
  if (isScreenWidgetItem(item)) {
    return item.title.trim() || item.chartType;
  }
  if (isScreenTextItem(item)) {
    return truncate(item.content) || labels.text || 'Text';
  }
  if (isScreenTitleFrameItem(item)) {
    return truncate(item.content) || labels.title || 'Title';
  }
  if (isScreenClockItem(item)) {
    return labels.clock || 'Clock';
  }
  if (isScreenDecorationItem(item)) {
    if (item.decorationType === 'corner') return labels.corner || 'Corner';
    if (item.decorationType === 'divider') {
      const preset = resolveDividerPreset(item.preset);
      return compactLabel(
        labels.dividerPreset?.(preset) || labels.divider || 'Divider',
      );
    }
    const preset = resolvePanelFramePreset(item.preset);
    return compactLabel(
      labels.panelFramePreset?.(preset) || labels.panelFrame || 'Frame',
    );
  }
  if (isScreenShapeItem(item)) {
    if (item.shape === 'circle') return labels.shapeCircle || 'Circle';
    if (item.shape === 'roundedRect') return labels.shapeRoundedRect || 'Rounded rectangle';
    return labels.shapeRect || 'Rectangle';
  }
  return (item as ScreenItem).id;
};

export const buildScreenElementList = (
  items: ScreenItem[],
  labels: ScreenElementListLabels = {},
): ScreenElementListEntry[] => {
  const ordered = [...items].sort((left, right) => {
    const zDiff = (right.zIndex || 0) - (left.zIndex || 0);
    if (zDiff !== 0) return zDiff;
    return left.id.localeCompare(right.id);
  });
  const seen = new Map<string, number>();

  return ordered.map((item) => {
    const base = getScreenItemBaseLabel(item, labels);
    const count = (seen.get(base) || 0) + 1;
    seen.set(base, count);
    return {
      id: item.id,
      zIndex: item.zIndex,
      label: count === 1 ? base : `${base}-${count - 1}`,
    };
  });
};
