import type {
  ScreenBackgroundConfig,
  ScreenDecorationsConfig,
  ScreenDisplayAdapter,
  ScreenFitAdapter,
  ScreenItem,
  ScreenTextStyleConfig,
  ScreenViewportConfig,
  ScreenViewSets,
} from '@/app/ops-analysis/types/screen';
import { normalizeStoredFilterDefinitions } from '@/app/ops-analysis/utils/unifiedFilterState';
import {
  DEFAULT_SCREEN_THEME_ID,
  resolveScreenThemeId,
} from './screenTheme';
import {
  createScreenClockItem,
  createScreenTitleFrameItem,
  DEFAULT_SCREEN_CLOCK_FORMAT,
  LEGACY_CLOCK_ID,
  LEGACY_TITLE_FRAME_ID,
} from './screenItems';
import {
  defaultWallpaperKeyForTheme,
  isScreenImageBackgroundSrc,
} from './screenBackground';

export interface ScreenViewportPreset {
  key: string;
  label: string;
  width: number;
  height: number;
}

export const DEFAULT_SCREEN_VIEWPORT: ScreenViewportConfig = {
  width: 1920,
  height: 1080,
  background: { type: 'preset', key: 'dark-glow' },
  theme: DEFAULT_SCREEN_THEME_ID,
  adapter: 'fill',
};

export const DEFAULT_SCREEN_DECORATIONS: ScreenDecorationsConfig = {
  showTitle: false,
  showClock: false,
  title: '',
};

const cloneBackground = (
  background?: ScreenBackgroundConfig,
): ScreenBackgroundConfig | undefined => {
  if (!background) return undefined;
  if (background.type === 'color') {
    return { type: 'color', color: background.color };
  }
  if (background.type === 'image' && isScreenImageBackgroundSrc(background.src)) {
    return { type: 'image', src: background.src };
  }
  if (background.type === 'preset' && background.key) {
    return { type: 'preset', key: background.key };
  }
  return undefined;
};

const cloneViewport = (
  viewport: ScreenViewportConfig,
): ScreenViewportConfig => ({
  ...viewport,
  background: cloneBackground(viewport.background),
});

export const SCREEN_VIEWPORT_PRESETS: ScreenViewportPreset[] = [
  { key: '1920x1080', label: '1920 × 1080', width: 1920, height: 1080 },
  { key: '1366x768', label: '1366 × 768', width: 1366, height: 768 },
  { key: '3840x2160', label: '3840 × 2160', width: 3840, height: 2160 },
];

export const isValidViewportSize = (value: unknown): value is number =>
  typeof value === 'number' &&
  Number.isInteger(value) &&
  Number.isFinite(value) &&
  value > 0;

export const resolveScreenFitAdapter = (
  value: unknown,
): ScreenFitAdapter =>
  value === 'fitWidth' || value === 'fitHeight' ? value : 'fill';

/** 查看和编辑始终等比留边。显示方式只作用于放大和分享。PDF 固定留边。 */
export const resolveScreenDisplayAdapter = ({
  adapter,
  fullscreen = false,
  shareMode = false,
  forceContain = false,
}: {
  adapter: unknown;
  editMode?: boolean;
  fullscreen?: boolean;
  shareMode?: boolean;
  forceContain?: boolean;
}): ScreenDisplayAdapter => {
  if (forceContain || (!fullscreen && !shareMode)) {
    return 'contain';
  }
  return resolveScreenFitAdapter(adapter);
};

const scaleAxis = (value: number, ratio: number, minimum = 0) =>
  Math.max(minimum, Math.round(value * ratio));

const scaleTextStyle = (
  textStyle: ScreenTextStyleConfig | undefined,
  fontScale: number,
): ScreenTextStyleConfig | undefined => {
  if (typeof textStyle?.fontSize !== 'number') {
    return textStyle;
  }
  return {
    ...textStyle,
    fontSize: Math.max(8, Math.round(textStyle.fontSize * fontScale)),
  };
};

/** 画布改尺寸时，元素按新旧宽高比缩放，构图保持在新画布内。 */
export const scaleScreenItemsToViewport = (
  items: ScreenItem[],
  fromWidth: number,
  fromHeight: number,
  toWidth: number,
  toHeight: number,
): ScreenItem[] => {
  if (
    fromWidth === toWidth &&
    fromHeight === toHeight
  ) {
    return items;
  }
  if (fromWidth <= 0 || fromHeight <= 0 || toWidth <= 0 || toHeight <= 0) {
    return items;
  }
  const scaleX = toWidth / fromWidth;
  const scaleY = toHeight / fromHeight;
  const fontScale = Math.min(scaleX, scaleY);
  return items.map((item) => {
    const next = {
      ...item,
      x: scaleAxis(item.x, scaleX),
      y: scaleAxis(item.y, scaleY),
      w: scaleAxis(item.w, scaleX, 1),
      h: scaleAxis(item.h, scaleY, 1),
    };
    if (
      next.kind === 'text' ||
      next.kind === 'titleFrame' ||
      next.kind === 'clock'
    ) {
      return { ...next, textStyle: scaleTextStyle(next.textStyle, fontScale) };
    }
    return next;
  });
};

const resolveBackground = (
  value: unknown,
  theme?: ScreenViewportConfig['theme'],
): ScreenBackgroundConfig => {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    const source = value as Record<string, unknown>;
    if (source.type === 'color' && typeof source.color === 'string' && source.color.trim()) {
      return { type: 'color', color: source.color };
    }
    if (source.type === 'image' && isScreenImageBackgroundSrc(source.src)) {
      return { type: 'image', src: source.src };
    }
    if (
      (source.type === 'preset' || source.type === 'builtIn') &&
      typeof source.key === 'string' &&
      source.key.trim()
    ) {
      const key =
        source.key === 'tech-grid'
          ? defaultWallpaperKeyForTheme(theme)
          : source.key;
      return { type: 'preset', key };
    }
  }
  return {
    type: 'preset',
    key: defaultWallpaperKeyForTheme(theme),
  };
};

export const buildDefaultScreenViewSets = (): ScreenViewSets => ({
  viewport: cloneViewport(DEFAULT_SCREEN_VIEWPORT),
  items: [],
  decorations: { ...DEFAULT_SCREEN_DECORATIONS },
  filters: [],
});

const nextLegacyZ = (items: ScreenViewSets['items'], fallback: number) =>
  Math.max(
    fallback,
    items.reduce((max, item) => Math.max(max, item.zIndex || 0), 0) + 1,
  );

/**
 * 旧顶栏（screen-canvas-header）在设计坐标、ui-scale=1 时的尺寸：
 * 标题 top:14、高 46、字号 24 / 800、最宽 600、水平居中；
 * 时钟右内边距 94、字号 14 / 700、min-width 230。
 * 迁移改用 hero-5 皮肤，所以在旧比例上略放宽宽高，避免新皮肤显得又扁又小。
 */
const LEGACY_CHROME_BASE_WIDTH = 1920;
const LEGACY_TITLE_TOP = 14;
const LEGACY_TITLE_HEIGHT = 46;
const LEGACY_TITLE_FONT_SIZE = 24;
const LEGACY_TITLE_FONT_WEIGHT = 800;
const LEGACY_TITLE_MAX_WIDTH = 600;
const LEGACY_HEADER_PAD_X = 94;
const LEGACY_CLOCK_TOP = 18;
const LEGACY_CLOCK_FONT_SIZE = 14;
const LEGACY_CLOCK_FONT_WEIGHT = 700;
const LEGACY_CLOCK_MIN_WIDTH = 230;
const LEGACY_CLOCK_HEIGHT = 34;

const legacyChromeScale = (width: number) =>
  Math.max(width / LEGACY_CHROME_BASE_WIDTH, 0.5);

const scaleLegacyPx = (value: number, width: number) =>
  Math.max(1, Math.round(value * legacyChromeScale(width)));

const buildLegacyTitleFrame = (
  items: ScreenViewSets['items'],
  width: number,
  content: string,
) => {
  // hero-5 目录默认宽 800；比旧 max 600 稍宽，居中仍贴近旧顶栏
  const titleWidth = Math.min(
    scaleLegacyPx(Math.max(LEGACY_TITLE_MAX_WIDTH, 800), width),
    Math.max(1, width - scaleLegacyPx(LEGACY_HEADER_PAD_X * 2, width)),
  );
  // 旧高 46；hero-5 素材略抬高，避免字贴边
  const titleHeight = scaleLegacyPx(
    Math.max(LEGACY_TITLE_HEIGHT, 56),
    width,
  );
  return createScreenTitleFrameItem(items, {
    id: LEGACY_TITLE_FRAME_ID,
    preset: 'hero-5',
    content,
    x: Math.max(0, Math.round((width - titleWidth) / 2)),
    y: scaleLegacyPx(LEGACY_TITLE_TOP, width),
    w: titleWidth,
    h: titleHeight,
    zIndex: nextLegacyZ(items, 1000),
    textStyle: {
      fontSize: scaleLegacyPx(LEGACY_TITLE_FONT_SIZE, width),
      fontWeight: LEGACY_TITLE_FONT_WEIGHT,
      color: 'canvas',
      align: 'center',
    },
  });
};

const buildLegacyClock = (
  items: ScreenViewSets['items'],
  width: number,
) => {
  const clockWidth = scaleLegacyPx(
    Math.max(LEGACY_CLOCK_MIN_WIDTH, 300),
    width,
  );
  const clockHeight = scaleLegacyPx(
    Math.max(LEGACY_CLOCK_HEIGHT, 40),
    width,
  );
  const rightPad = scaleLegacyPx(LEGACY_HEADER_PAD_X, width);
  return createScreenClockItem(items, {
    id: LEGACY_CLOCK_ID,
    format: DEFAULT_SCREEN_CLOCK_FORMAT,
    x: Math.max(0, width - rightPad - clockWidth),
    y: scaleLegacyPx(LEGACY_CLOCK_TOP, width),
    w: clockWidth,
    h: clockHeight,
    zIndex: nextLegacyZ(items, 1001),
    textStyle: {
      fontSize: scaleLegacyPx(
        Math.max(LEGACY_CLOCK_FONT_SIZE, 16),
        width,
      ),
      fontWeight: LEGACY_CLOCK_FONT_WEIGHT,
      color: 'canvas',
    },
  });
};

const migrateLegacyChrome = (viewSets: ScreenViewSets): ScreenViewSets => {
  const decorations = { ...viewSets.decorations };
  const items = [...viewSets.items];
  const width = viewSets.viewport.width;
  const title = decorations.title?.trim() || '';

  if (decorations.showTitle && title) {
    const exists = items.some((item) => item.id === LEGACY_TITLE_FRAME_ID);
    if (!exists) {
      items.push(buildLegacyTitleFrame(items, width, title));
    }
  }
  decorations.showTitle = false;

  if (decorations.showClock) {
    const exists = items.some((item) => item.id === LEGACY_CLOCK_ID);
    if (!exists) {
      items.push(buildLegacyClock(items, width));
    }
  }
  decorations.showClock = false;

  return {
    ...viewSets,
    items,
    decorations,
  };
};

export const normalizeScreenViewSets = (value: unknown): ScreenViewSets => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return buildDefaultScreenViewSets();
  }

  const source = value as Partial<ScreenViewSets>;
  const viewport: Partial<ScreenViewportConfig> =
    source.viewport &&
    typeof source.viewport === 'object' &&
    !Array.isArray(source.viewport)
      ? source.viewport
      : {};
  const width = isValidViewportSize(viewport.width)
    ? viewport.width
    : DEFAULT_SCREEN_VIEWPORT.width;
  const height = isValidViewportSize(viewport.height)
    ? viewport.height
    : DEFAULT_SCREEN_VIEWPORT.height;
  const theme = resolveScreenThemeId(viewport.theme);
  const decorations =
    source.decorations &&
    typeof source.decorations === 'object' &&
    !Array.isArray(source.decorations)
      ? {
        ...DEFAULT_SCREEN_DECORATIONS,
        ...source.decorations,
      }
      : { ...DEFAULT_SCREEN_DECORATIONS };

  const normalized: ScreenViewSets = {
    viewport: {
      width,
      height,
      background: resolveBackground(viewport.background, theme),
      theme,
      adapter: resolveScreenFitAdapter(viewport.adapter),
    },
    items: Array.isArray(source.items) ? [...source.items] : [],
    decorations,
    filters: normalizeStoredFilterDefinitions(source.filters),
  };

  return migrateLegacyChrome(normalized);
};

export const updateScreenViewport = (
  viewSets: ScreenViewSets,
  viewport: ScreenViewportConfig,
): ScreenViewSets => ({
  ...viewSets,
  viewport: {
    ...viewSets.viewport,
    width: viewport.width,
    height: viewport.height,
    theme: resolveScreenThemeId(viewport.theme ?? viewSets.viewport.theme),
    adapter: resolveScreenFitAdapter(
      viewport.adapter ?? viewSets.viewport.adapter,
    ),
    background: cloneBackground(
      viewport.background ?? viewSets.viewport.background,
    ),
  },
  items: scaleScreenItemsToViewport(
    viewSets.items,
    viewSets.viewport.width,
    viewSets.viewport.height,
    viewport.width,
    viewport.height,
  ),
  decorations: { ...viewSets.decorations },
  filters: [...(viewSets.filters ?? [])],
});
