import { afterEach, describe, expect, it } from 'vitest';

import { getStoredLocale } from '../userPreferences';

describe('getStoredLocale', () => {
  afterEach(() => {
    window.localStorage.clear();
    window.history.pushState({}, '', '/');
  });

  it('uses the locale query and remembers it for the next page', () => {
    window.localStorage.setItem('locale', 'en');
    window.history.pushState({}, '', '/ops-analysis/display/t/token?locale=zh-Hans');

    expect(getStoredLocale()).toBe('zh-Hans');
    expect(window.localStorage.getItem('locale')).toBe('zh-Hans');
  });

  it('keeps the stored locale when the link has no locale', () => {
    window.localStorage.setItem('locale', 'zh-Hans');
    window.history.pushState({}, '', '/ops-analysis/display/view');

    expect(getStoredLocale()).toBe('zh-Hans');
  });
});
