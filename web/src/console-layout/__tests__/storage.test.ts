import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  CONSOLE_CHROME_LAYOUT_STORAGE_KEY,
  normalizeConsoleChromeLayout,
  persistConsoleChromeLayout,
  readStoredConsoleChromeLayout,
} from '../storage';

describe('console chrome layout storage', () => {
  afterEach(() => {
    window.localStorage.removeItem(CONSOLE_CHROME_LAYOUT_STORAGE_KEY);
  });

  it('reads classic when storage is empty or invalid', () => {
    expect(readStoredConsoleChromeLayout()).toBe('classic');
    window.localStorage.setItem(CONSOLE_CHROME_LAYOUT_STORAGE_KEY, 'side');
    expect(readStoredConsoleChromeLayout()).toBe('classic');
  });

  it('persists and reads app-top', () => {
    persistConsoleChromeLayout('app-top');
    expect(window.localStorage.getItem(CONSOLE_CHROME_LAYOUT_STORAGE_KEY)).toBe('app-top');
    expect(readStoredConsoleChromeLayout()).toBe('app-top');
    expect(normalizeConsoleChromeLayout('app-top')).toBe('app-top');
  });
});
