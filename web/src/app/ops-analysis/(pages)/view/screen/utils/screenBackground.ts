import type { CSSProperties } from 'react';
import type {
  ScreenBackgroundConfig,
  ScreenThemeId,
} from '@/app/ops-analysis/types/screen';

export const SCREEN_BACKGROUND_IMAGE_MAX_BYTES = 2 * 1024 * 1024;

export const SCREEN_BACKGROUND_IMAGE_MIME_TYPES = [
  'image/png',
  'image/jpeg',
  'image/webp',
] as const;

const IMAGE_SRC_PATTERN = new RegExp(
  `^data:image/(${SCREEN_BACKGROUND_IMAGE_MIME_TYPES.map((type) => type.slice('image/'.length)).join('|')});base64,[A-Za-z0-9+/]+={0,2}$`,
);

export const isScreenImageBackgroundSrc = (value: unknown): value is string =>
  typeof value === 'string' && IMAGE_SRC_PATTERN.test(value);

export const screenBackgroundImageRejection = (file: {
  type: string;
  size: number;
}): 'type' | 'size' | null => {
  if (!(SCREEN_BACKGROUND_IMAGE_MIME_TYPES as readonly string[]).includes(file.type)) {
    return 'type';
  }
  if (file.size > SCREEN_BACKGROUND_IMAGE_MAX_BYTES) {
    return 'size';
  }
  return null;
};

export interface ScreenWallpaperPreset {
  key: string;
  theme: ScreenThemeId;
  background: string;
}

export const SCREEN_WALLPAPER_PRESETS: ScreenWallpaperPreset[] = [
  {
    key: 'dark-glow',
    theme: 'screen-dark',
    background:
      'radial-gradient(ellipse 80% 42% at 78% 118%, rgba(0,168,255,0.28), transparent 58%), radial-gradient(ellipse 70% 36% at 18% 122%, rgba(32,92,176,0.22), transparent 54%), radial-gradient(circle at 50% 0%, rgba(0,229,255,0.16), transparent 34%), linear-gradient(180deg, #071422 0%, #0a1c33 42%, #061018 100%)',
  },
  {
    key: 'dark-grid',
    theme: 'screen-dark',
    background:
      'linear-gradient(rgba(0,229,255,0.06) 1px, transparent 1px), linear-gradient(90deg, rgba(0,229,255,0.06) 1px, transparent 1px), radial-gradient(circle at 50% 0%, rgba(0,168,255,0.18), transparent 36%), linear-gradient(180deg, #07182b 0%, #050e1a 100%)',
  },
  {
    key: 'dark-mesh',
    theme: 'screen-dark',
    background:
      'radial-gradient(circle at 12% 18%, rgba(0,168,255,0.2), transparent 28%), radial-gradient(circle at 88% 78%, rgba(58,90,180,0.18), transparent 26%), linear-gradient(180deg, #081526 0%, #050d18 100%)',
  },
  {
    key: 'dark-horizon',
    theme: 'screen-dark',
    background:
      'linear-gradient(180deg, #0a2038 0%, #071422 52%, #03080f 100%), radial-gradient(ellipse 90% 28% at 50% 100%, rgba(0,168,255,0.22), transparent 70%)',
  },
  {
    key: 'light-mist',
    theme: 'screen-light',
    background: 'linear-gradient(135deg, #ffffff 0%, #e8edf4 100%)',
  },
  {
    key: 'light-grid',
    theme: 'screen-light',
    background:
      'linear-gradient(rgba(15,76,129,0.06) 1px, transparent 1px), linear-gradient(90deg, rgba(15,76,129,0.06) 1px, transparent 1px), linear-gradient(180deg, #f7f9fc 0%, #e7edf5 100%)',
  },
  {
    key: 'light-paper',
    theme: 'screen-light',
    background: 'linear-gradient(180deg, #fbfcfe 0%, #eef2f7 100%)',
  },
  {
    key: 'light-studio',
    theme: 'screen-light',
    background:
      'radial-gradient(circle at 80% 0%, rgba(59,130,246,0.12), transparent 32%), linear-gradient(180deg, #f4f7fb 0%, #e6edf6 100%)',
  },
];

export const getScreenWallpaperPreset = (key?: string) =>
  SCREEN_WALLPAPER_PRESETS.find((item) => item.key === key);

export const defaultWallpaperKeyForTheme = (theme?: ScreenThemeId) =>
  theme === 'screen-light' ? 'light-mist' : 'dark-glow';

export const resolveScreenCanvasBackgroundStyle = (
  background?: ScreenBackgroundConfig,
  theme?: ScreenThemeId,
): CSSProperties => {
  if (background?.type === 'image' && isScreenImageBackgroundSrc(background.src)) {
    return {
      backgroundImage: `url("${background.src}")`,
      backgroundSize: 'cover',
      backgroundPosition: 'center',
      backgroundRepeat: 'no-repeat',
    };
  }
  if (background?.type === 'color' && background.color) {
    return { background: background.color };
  }
  const key =
    background?.type === 'preset'
      ? background.key
      : defaultWallpaperKeyForTheme(theme);
  const preset =
    getScreenWallpaperPreset(key) ||
    getScreenWallpaperPreset(defaultWallpaperKeyForTheme(theme));
  const isGrid = preset?.key === 'dark-grid' || preset?.key === 'light-grid';
  return {
    backgroundImage: preset?.background,
    backgroundSize: isGrid
      ? '40px 40px, 40px 40px, cover, auto'
      : 'cover',
    backgroundPosition: 'center',
    backgroundRepeat: isGrid ? 'repeat, repeat, no-repeat, no-repeat' : 'no-repeat',
  };
};
