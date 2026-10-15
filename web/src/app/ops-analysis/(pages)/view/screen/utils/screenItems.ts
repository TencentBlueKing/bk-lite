import { v4 as uuidv4 } from 'uuid';
import type {
  ScreenClockFormatId,
  ScreenClockItem,
  ScreenDecorationItem,
  ScreenDecorationPresetId,
  ScreenDecorationType,
  ScreenDividerPresetId,
  ScreenItem,
  ScreenItemGeometry,
  ScreenPanelFramePresetId,
  ScreenShapeItem,
  ScreenShapeKind,
  ScreenTextItem,
  ScreenTitleFrameItem,
  ScreenTitleFramePresetId,
  ScreenWidgetItem,
} from '@/app/ops-analysis/types/screen';
import {
  DEFAULT_SCREEN_SHAPE_STYLE,
  SCREEN_SHAPE_KINDS,
  resolveScreenShapeKind,
} from './screenShape';

const DEFAULT_INSERT_X = 48;
const DEFAULT_INSERT_Y = 96;

const nextZIndex = (items: ScreenItem[]) =>
  items.reduce((max, item) => Math.max(max, item.zIndex || 0), 0) + 1;

const geometry = (
  items: ScreenItem[],
  overrides?: Partial<ScreenItemGeometry>,
): ScreenItemGeometry => ({
  id: overrides?.id || uuidv4(),
  x: overrides?.x ?? DEFAULT_INSERT_X,
  y: overrides?.y ?? DEFAULT_INSERT_Y,
  w: overrides?.w ?? 320,
  h: overrides?.h ?? 80,
  zIndex: overrides?.zIndex ?? nextZIndex(items),
});

export const isScreenWidgetItem = (item: ScreenItem): item is ScreenWidgetItem =>
  (item as ScreenWidgetItem).type === 'widget' &&
  (item.kind === 'widget' || item.kind === undefined);

export const isScreenTextItem = (item: ScreenItem): item is ScreenTextItem =>
  item.kind === 'text';

export const isScreenClockItem = (item: ScreenItem): item is ScreenClockItem =>
  item.kind === 'clock';

export const isScreenTitleFrameItem = (
  item: ScreenItem,
): item is ScreenTitleFrameItem => item.kind === 'titleFrame';

export const isScreenDecorationItem = (
  item: ScreenItem,
): item is ScreenDecorationItem => item.kind === 'decoration';

export const isScreenShapeItem = (item: ScreenItem): item is ScreenShapeItem =>
  item.kind === 'shape';

export const isScreenChromeItem = (item: ScreenItem) => !isScreenWidgetItem(item);

export const SCREEN_CLOCK_FORMATS: ScreenClockFormatId[] = [
  'HH:mm:ss',
  'YYYY-MM-DD',
  'YYYY-MM-DD HH:mm:ss',
  'YYYY年M月D日',
  'M月D日 HH:mm',
  'dddd HH:mm:ss',
];

export const DEFAULT_SCREEN_CLOCK_FORMAT: ScreenClockFormatId =
  'YYYY-MM-DD HH:mm:ss';

export const createScreenTextItem = (
  items: ScreenItem[],
  overrides?: Partial<ScreenTextItem>,
): ScreenTextItem => ({
  kind: 'text',
  content: overrides?.content ?? '',
  textStyle: overrides?.textStyle ?? {
    fontSize: 20,
    fontWeight: 600,
    color: 'canvas',
    align: 'left',
  },
  ...geometry(items, { w: 360, h: 72, ...overrides }),
});

export const createScreenClockItem = (
  items: ScreenItem[],
  overrides?: Partial<ScreenClockItem>,
): ScreenClockItem => ({
  kind: 'clock',
  format: overrides?.format ?? DEFAULT_SCREEN_CLOCK_FORMAT,
  textStyle: overrides?.textStyle ?? {
    fontSize: 20,
    fontWeight: 600,
    color: 'canvas',
  },
  ...geometry(items, { w: 360, h: 56, ...overrides }),
});

const TITLE_FRAME_DEFAULTS: Record<
  ScreenTitleFramePresetId,
  { w: number; h: number; content: string }
> = {
  'hero-1': { w: 750, h: 70, content: 'Operations screen' },
  'hero-2': { w: 750, h: 70, content: 'Operations screen' },
  'hero-3': { w: 720, h: 72, content: 'Operations screen' },
  'hero-4': { w: 720, h: 68, content: 'Operations screen' },
  'hero-5': { w: 800, h: 48, content: 'Operations screen' },
  'hero-6': { w: 720, h: 156, content: 'Operations screen' },
  'section-1': { w: 400, h: 36, content: 'Overview' },
  'section-2': { w: 400, h: 36, content: 'Overview' },
  'section-3': { w: 400, h: 36, content: 'Overview' },
  'section-4': { w: 480, h: 40, content: 'Overview' },
};

export const createScreenTitleFrameItem = (
  items: ScreenItem[],
  overrides?: Partial<ScreenTitleFrameItem>,
): ScreenTitleFrameItem => {
  const preset = overrides?.preset ?? 'hero-1';
  const defaults = TITLE_FRAME_DEFAULTS[preset];
  return {
    kind: 'titleFrame',
    preset,
    content: overrides?.content ?? defaults.content,
    textStyle: overrides?.textStyle,
    ...geometry(items, { w: defaults.w, h: defaults.h, ...overrides }),
  };
};

export const SCREEN_PANEL_FRAME_PRESETS: ScreenPanelFramePresetId[] = [
  'border-21',
  'border-22',
  'border-23',
  'border-25',
  'border-1',
  'tech',
  'border-16',
  'border-20',
  'border-24',
];

export const SCREEN_DIVIDER_PRESETS: ScreenDividerPresetId[] = [
  'line-1',
  'line-2',
  'line-3',
  'line-dec',
  'line-4',
];

const PANEL_FRAME_PRESET_SET = new Set<string>(SCREEN_PANEL_FRAME_PRESETS);
const DIVIDER_PRESET_SET = new Set<string>(SCREEN_DIVIDER_PRESETS);

export const resolvePanelFramePreset = (
  preset: string | undefined,
): ScreenPanelFramePresetId => {
  if (preset === 'b') return 'tech';
  if (preset && PANEL_FRAME_PRESET_SET.has(preset)) {
    return preset as ScreenPanelFramePresetId;
  }
  return 'border-21';
};

export const resolveDividerPreset = (
  preset: string | undefined,
): ScreenDividerPresetId => {
  if (preset === 'b') return 'line-dec';
  if (preset && DIVIDER_PRESET_SET.has(preset)) {
    return preset as ScreenDividerPresetId;
  }
  return 'line-1';
};

export const createScreenDecorationItem = (
  items: ScreenItem[],
  decorationType: ScreenDecorationType,
  preset?: ScreenDecorationPresetId,
  overrides?: Partial<ScreenItemGeometry>,
): ScreenDecorationItem => {
  const resolved =
    preset ??
    (decorationType === 'divider'
      ? 'line-1'
      : decorationType === 'panelFrame'
        ? 'border-21'
        : 'a');
  const size =
    decorationType === 'divider'
      ? { w: 480, h: resolved === 'line-2' || resolved === 'line-4' ? 32 : 16 }
      : decorationType === 'corner'
        ? { w: 120, h: 120 }
        : { w: 640, h: 360 };
  return {
    kind: 'decoration',
    decorationType,
    preset: resolved,
    ...geometry(items, { ...size, ...overrides }),
  };
};

const SHAPE_SIZE: Record<ScreenShapeKind, { w: number; h: number }> = {
  rect: { w: 320, h: 180 },
  roundedRect: { w: 320, h: 180 },
  circle: { w: 200, h: 200 },
};

export const createScreenShapeItem = (
  items: ScreenItem[],
  shape: ScreenShapeKind = 'rect',
  overrides?: Partial<ScreenShapeItem>,
): ScreenShapeItem => {
  const resolved = resolveScreenShapeKind(overrides?.shape ?? shape);
  return {
    kind: 'shape',
    shape: resolved,
    shapeStyle: overrides?.shapeStyle ?? { ...DEFAULT_SCREEN_SHAPE_STYLE },
    ...geometry(items, { ...SHAPE_SIZE[resolved], ...overrides }),
  };
};

export const placeScreenItemAtPoint = <T extends ScreenItem>(
  item: T,
  point: { x: number; y: number },
  bounds: { width: number; height: number },
): T => {
  const maxX = Math.max(0, bounds.width - item.w);
  const maxY = Math.max(0, bounds.height - item.h);
  return {
    ...item,
    x: Math.min(Math.max(Math.round(point.x - item.w / 2), 0), maxX),
    y: Math.min(Math.max(Math.round(point.y - item.h / 2), 0), maxY),
  };
};

export const SCREEN_CHROME_DRAG_MIME = 'application/x-bk-screen-chrome';

export type ScreenChromeDragPayload =
  | { kind: 'text' }
  | { kind: 'clock' }
  | { kind: 'titleFrame'; preset: ScreenTitleFramePresetId }
  | {
      kind: 'decoration';
      decorationType: 'panelFrame' | 'divider';
      preset: ScreenDecorationPresetId;
    }
  | { kind: 'shape'; shape: ScreenShapeKind };

const isScreenChromeDragPayload = (
  value: unknown,
): value is ScreenChromeDragPayload => {
  if (!value || typeof value !== 'object') return false;
  const payload = value as {
    kind?: string;
    preset?: string;
    decorationType?: string;
    shape?: string;
  };
  if (payload.kind === 'text' || payload.kind === 'clock') return true;
  if (payload.kind === 'shape') {
    return SCREEN_SHAPE_KINDS.includes(payload.shape as ScreenShapeKind);
  }
  if (payload.kind === 'titleFrame') {
    return TITLE_FRAME_PRESETS.includes(payload.preset as ScreenTitleFramePresetId);
  }
  if (payload.kind !== 'decoration') return false;
  if (payload.decorationType === 'panelFrame') {
    return PANEL_FRAME_PRESET_SET.has(payload.preset || '');
  }
  if (payload.decorationType === 'divider') {
    return DIVIDER_PRESET_SET.has(payload.preset || '');
  }
  return false;
};

export const writeScreenChromeDrag = (
  dataTransfer: DataTransfer,
  payload: ScreenChromeDragPayload,
) => {
  const raw = JSON.stringify(payload);
  dataTransfer.setData(SCREEN_CHROME_DRAG_MIME, raw);
  dataTransfer.setData('text/plain', raw);
  dataTransfer.effectAllowed = 'copy';
};

export const readScreenChromeDrag = (
  dataTransfer: DataTransfer,
): ScreenChromeDragPayload | null => {
  const raw =
    dataTransfer.getData(SCREEN_CHROME_DRAG_MIME) ||
    dataTransfer.getData('text/plain');
  if (!raw) return null;
  try {
    const parsed: unknown = JSON.parse(raw);
    return isScreenChromeDragPayload(parsed) ? parsed : null;
  } catch {
    return null;
  }
};

export const createScreenChromeFromDrag = (
  items: ScreenItem[],
  payload: ScreenChromeDragPayload,
): ScreenItem => {
  if (payload.kind === 'text') return createScreenTextItem(items);
  if (payload.kind === 'clock') return createScreenClockItem(items);
  if (payload.kind === 'titleFrame') {
    return createScreenTitleFrameItem(items, { preset: payload.preset });
  }
  if (payload.kind === 'shape') {
    return createScreenShapeItem(items, payload.shape);
  }
  return createScreenDecorationItem(
    items,
    payload.decorationType,
    payload.preset,
  );
};

export const LEGACY_TITLE_FRAME_ID = 'legacy-title-frame';
export const LEGACY_CLOCK_ID = 'legacy-clock';

export const TITLE_FRAME_PRESETS: ScreenTitleFramePresetId[] = [
  'hero-1',
  'hero-2',
  'hero-3',
  'hero-4',
  'hero-5',
  'hero-6',
  'section-1',
  'section-2',
  'section-3',
  'section-4',
];
