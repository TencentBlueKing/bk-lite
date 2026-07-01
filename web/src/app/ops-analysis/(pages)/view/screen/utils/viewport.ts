import type {
  ScreenDecorationsConfig,
  ScreenViewportConfig,
  ScreenViewSets,
} from '@/app/ops-analysis/types/screen';
import { normalizeStoredFilterDefinitions } from '@/app/ops-analysis/utils/unifiedFilterState';

export interface ScreenViewportPreset {
  key: string;
  label: string;
  width: number;
  height: number;
}

export const DEFAULT_SCREEN_VIEWPORT: ScreenViewportConfig = {
  width: 1920,
  height: 1080,
  background: { type: 'builtIn', key: 'tech-grid' },
  theme: 'screen-tech-blue',
};

export const DEFAULT_SCREEN_DECORATIONS: ScreenDecorationsConfig = {
  showTitle: false,
  showClock: false,
  title: '',
};

const cloneViewport = (
  viewport: ScreenViewportConfig,
): ScreenViewportConfig => ({
  ...viewport,
  background: viewport.background ? { ...viewport.background } : undefined,
});

export const DEFAULT_SCREEN_VIEW_SETS: ScreenViewSets = {
  viewport: cloneViewport(DEFAULT_SCREEN_VIEWPORT),
  items: [],
  decorations: { ...DEFAULT_SCREEN_DECORATIONS },
  filters: [],
};

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

export const buildDefaultScreenViewSets = (): ScreenViewSets => ({
  viewport: cloneViewport(DEFAULT_SCREEN_VIEWPORT),
  items: [],
  decorations: { ...DEFAULT_SCREEN_DECORATIONS },
  filters: [],
});

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
  const decorations =
    source.decorations &&
    typeof source.decorations === 'object' &&
    !Array.isArray(source.decorations)
      ? {
        ...DEFAULT_SCREEN_DECORATIONS,
        ...source.decorations,
      }
      : { ...DEFAULT_SCREEN_DECORATIONS };

  return {
    viewport: {
      width,
      height,
      background: DEFAULT_SCREEN_VIEWPORT.background
        ? { ...DEFAULT_SCREEN_VIEWPORT.background }
        : undefined,
      theme: DEFAULT_SCREEN_VIEWPORT.theme,
    },
    items: Array.isArray(source.items) ? source.items : [],
    decorations,
    filters: normalizeStoredFilterDefinitions(source.filters),
  };
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
  },
  items: [...viewSets.items],
  decorations: { ...viewSets.decorations },
  filters: [...(viewSets.filters ?? [])],
});
