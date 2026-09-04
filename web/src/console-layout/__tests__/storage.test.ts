import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  CONSOLE_CHROME_LAYOUT_STORAGE_KEY,
  CONSOLE_SIDE_NAV_STORAGE_KEY,
  normalizeConsoleChromeLayout,
  normalizeConsoleSideNavMode,
  persistConsoleChromeLayout,
  persistConsoleSideNavMode,
  readStoredConsoleChromeLayout,
  readStoredConsoleSideNavMode,
} from '../storage';

describe('console chrome layout storage', () => {
  afterEach(() => {
    window.localStorage.removeItem(CONSOLE_CHROME_LAYOUT_STORAGE_KEY);
    window.localStorage.removeItem(CONSOLE_SIDE_NAV_STORAGE_KEY);
  });

  it('defaults the side nav to expanded and only accepts collapsed as the other mode', () => {
    expect(readStoredConsoleSideNavMode()).toBe('expanded');
    window.localStorage.setItem(CONSOLE_SIDE_NAV_STORAGE_KEY, 'hidden');
    expect(readStoredConsoleSideNavMode()).toBe('expanded');
    persistConsoleSideNavMode('collapsed');
    expect(window.localStorage.getItem(CONSOLE_SIDE_NAV_STORAGE_KEY)).toBe('collapsed');
    expect(readStoredConsoleSideNavMode()).toBe('collapsed');
    expect(normalizeConsoleSideNavMode('collapsed')).toBe('collapsed');
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
