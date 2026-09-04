import {
  DEFAULT_CONSOLE_CHROME_LAYOUT,
  DEFAULT_CONSOLE_SIDE_NAV_MODE,
  type ConsoleChromeLayout,
  type ConsoleSideNavMode,
} from './contract';

export const CONSOLE_CHROME_LAYOUT_STORAGE_KEY = 'console-chrome-layout';
export const CONSOLE_SIDE_NAV_STORAGE_KEY = 'console-side-nav';

export const normalizeConsoleSideNavMode = (value: unknown): ConsoleSideNavMode => (
  value === 'collapsed' ? 'collapsed' : DEFAULT_CONSOLE_SIDE_NAV_MODE
);

export const readStoredConsoleSideNavMode = (): ConsoleSideNavMode => {
  if (typeof window === 'undefined') {
    return DEFAULT_CONSOLE_SIDE_NAV_MODE;
  }
  try {
    return normalizeConsoleSideNavMode(
      window.localStorage.getItem(CONSOLE_SIDE_NAV_STORAGE_KEY),
    );
  } catch {
    return DEFAULT_CONSOLE_SIDE_NAV_MODE;
  }
};

export const persistConsoleSideNavMode = (mode: ConsoleSideNavMode) => {
  try {
    window.localStorage.setItem(CONSOLE_SIDE_NAV_STORAGE_KEY, mode);
  } catch {
    // Storage may be unavailable in hardened/private browser contexts.
  }
};

export const normalizeConsoleChromeLayout = (value: unknown): ConsoleChromeLayout => (
  value === 'app-top' ? 'app-top' : DEFAULT_CONSOLE_CHROME_LAYOUT
);

export const readStoredConsoleChromeLayout = (): ConsoleChromeLayout => {
  if (typeof window === 'undefined') {
    return DEFAULT_CONSOLE_CHROME_LAYOUT;
  }
  try {
    return normalizeConsoleChromeLayout(
      window.localStorage.getItem(CONSOLE_CHROME_LAYOUT_STORAGE_KEY),
    );
  } catch {
    return DEFAULT_CONSOLE_CHROME_LAYOUT;
  }
};

export const persistConsoleChromeLayout = (layout: ConsoleChromeLayout) => {
  try {
    window.localStorage.setItem(CONSOLE_CHROME_LAYOUT_STORAGE_KEY, layout);
  } catch {
    // Storage may be unavailable in hardened/private browser contexts.
  }
};
