import {
  DEFAULT_CONSOLE_CHROME_LAYOUT,
  type ConsoleChromeLayout,
} from './contract';

export const CONSOLE_CHROME_LAYOUT_STORAGE_KEY = 'console-chrome-layout';

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
