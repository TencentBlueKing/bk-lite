import type { ThemeMode } from './contract';

export const THEME_MODE_STORAGE_KEY = 'theme';

export const normalizeThemeMode = (value: unknown): ThemeMode => (
  value === 'dark' ? 'dark' : 'light'
);

export const readStoredThemeMode = (): ThemeMode => {
  if (typeof window === 'undefined') {
    return 'light';
  }
  try {
    return normalizeThemeMode(window.localStorage.getItem(THEME_MODE_STORAGE_KEY));
  } catch {
    return 'light';
  }
};

export const persistThemeMode = (mode: ThemeMode) => {
  try {
    window.localStorage.setItem(THEME_MODE_STORAGE_KEY, mode);
  } catch {
    // Storage may be unavailable in hardened/private browser contexts.
  }
};
