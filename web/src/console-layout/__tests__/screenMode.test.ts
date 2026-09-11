import { describe, expect, it } from 'vitest';

import {
  applyScreenAwareHref,
  isScreenModeEnabled,
  resolveSameOriginNavigation,
  syncScreenModePersistence,
  withScreenQuery,
} from '../screenMode';

const memoryStorage = (initial: Record<string, string> = {}) => {
  const store = { ...initial };
  return {
    getItem: (key: string) => (key in store ? store[key] : null),
    setItem: (key: string, value: string) => {
      store[key] = value;
    },
    removeItem: (key: string) => {
      delete store[key];
    },
  };
};

describe('screen mode query contract', () => {
  it('enables screen mode only for true or 1, case-insensitive', () => {
    expect(isScreenModeEnabled('?screen=true')).toBe(true);
    expect(isScreenModeEnabled('?screen=TRUE')).toBe(true);
    expect(isScreenModeEnabled('?screen=1')).toBe(true);
    expect(isScreenModeEnabled(new URLSearchParams('screen=True'))).toBe(true);
    expect(isScreenModeEnabled('?screen=false')).toBe(false);
    expect(isScreenModeEnabled('?screen=yes')).toBe(false);
    expect(isScreenModeEnabled('?embed=true')).toBe(false);
    expect(isScreenModeEnabled('')).toBe(false);
    expect(isScreenModeEnabled(null)).toBe(false);
  });

  it('adds screen=true to same-tab hrefs and leaves other queries intact', () => {
    expect(withScreenQuery('/ops-analysis/view', true)).toBe('/ops-analysis/view?screen=true');
    expect(withScreenQuery('/ops-analysis/view?type=dashboard&id=7', true)).toBe(
      '/ops-analysis/view?type=dashboard&id=7&screen=true',
    );
    expect(withScreenQuery('/cmdb/assetOverview?screen=true', true)).toBe(
      '/cmdb/assetOverview?screen=true',
    );
    expect(withScreenQuery('/cmdb#panel', true)).toBe('/cmdb?screen=true#panel');
    expect(withScreenQuery('/cmdb', false)).toBe('/cmdb');
    expect(withScreenQuery('https://mail.example/qmail', true)).toBe('https://mail.example/qmail');
    expect(withScreenQuery('https://lite.example/cmdb?x=1', true, 'https://lite.example')).toBe(
      '/cmdb?x=1&screen=true',
    );
    expect(withScreenQuery('https://mail.example/qmail', true, 'https://lite.example')).toBe(
      'https://mail.example/qmail',
    );
  });

  it('restores screen after login drops the query, but not as a lasting preference', () => {
    const storage = memoryStorage();

    expect(syncScreenModePersistence({
      pathname: '/ops-analysis/view',
      search: '?screen=true',
      isAuthRoute: false,
      storage,
    }).restoreHref).toBeNull();

    expect(syncScreenModePersistence({
      pathname: '/auth/signin',
      search: '?callbackUrl=%2Fops-analysis%2Fview',
      isAuthRoute: true,
      storage,
    }).restoreHref).toBeNull();

    expect(syncScreenModePersistence({
      pathname: '/ops-analysis/view',
      search: '?type=dashboard&id=7',
      isAuthRoute: false,
      storage,
    }).restoreHref).toBe('/ops-analysis/view?type=dashboard&id=7&screen=true');

    expect(syncScreenModePersistence({
      pathname: '/cmdb/assetOverview',
      search: '',
      isAuthRoute: false,
      storage,
    }).restoreHref).toBeNull();

    expect(syncScreenModePersistence({
      pathname: '/auth/signin',
      search: '',
      isAuthRoute: true,
      storage,
    }).restoreHref).toBeNull();

    expect(syncScreenModePersistence({
      pathname: '/cmdb/assetOverview',
      search: '',
      isAuthRoute: false,
      storage,
    }).restoreHref).toBeNull();
  });

  it('restores screen when login itself started with screen=true', () => {
    const storage = memoryStorage();

    expect(syncScreenModePersistence({
      pathname: '/auth/signin',
      search: '?screen=true',
      isAuthRoute: true,
      storage,
    }).restoreHref).toBeNull();

    expect(syncScreenModePersistence({
      pathname: '/ops-console/home',
      search: '',
      isAuthRoute: false,
      storage,
    }).restoreHref).toBe('/ops-console/home?screen=true');

    expect(syncScreenModePersistence({
      pathname: '/ops-console/home',
      search: '?screen=true',
      isAuthRoute: false,
      storage,
    }).restoreHref).toBeNull();

    expect(syncScreenModePersistence({
      pathname: '/cmdb/assetOverview',
      search: '',
      isAuthRoute: false,
      storage,
    }).restoreHref).toBeNull();
  });
});

describe('screen-aware navigation', () => {
  it('keeps rebuilt query hrefs in screen mode and leaves ordinary hrefs alone', () => {
    expect(applyScreenAwareHref('/monitor/view/detail?id=9', '?screen=true')).toBe(
      '/monitor/view/detail?id=9&screen=true',
    );
    expect(applyScreenAwareHref('/cmdb/assetData?modelId=host', '?type=dashboard&screen=1')).toBe(
      '/cmdb/assetData?modelId=host&screen=true',
    );
    expect(applyScreenAwareHref('/log/integration/list', '')).toBe('/log/integration/list');
    expect(applyScreenAwareHref('/cmdb/assetData?screen=true', '?screen=true')).toBe(
      '/cmdb/assetData?screen=true',
    );
  });

  it('keeps same-origin current-page jumps in the frame and adds screen', () => {
    expect(resolveSameOriginNavigation('/monitor/view/dashboard/host?objId=1', {
      currentSearch: '?screen=true',
    })).toEqual({
      href: '/monitor/view/dashboard/host?objId=1&screen=true',
      mode: 'sameFrame',
    });
    expect(resolveSameOriginNavigation('/cmdb/assetOverview', {
      currentSearch: '',
    })).toEqual({
      href: '/cmdb/assetOverview',
      mode: 'sameFrame',
    });
  });

  it('converts implicit new-tab same-origin jumps to the current frame while screen is on', () => {
    expect(resolveSameOriginNavigation('/cmdb/assetData/detail/baseInfo?model_id=host', {
      currentSearch: '?screen=true',
      preferNewTab: true,
    })).toEqual({
      href: '/cmdb/assetData/detail/baseInfo?model_id=host&screen=true',
      mode: 'sameFrame',
    });
    expect(resolveSameOriginNavigation('/cmdb/assetData/detail/baseInfo?model_id=host', {
      currentSearch: '',
      preferNewTab: true,
    })).toEqual({
      href: '/cmdb/assetData/detail/baseInfo?model_id=host',
      mode: 'newTab',
    });
  });

  it('does not force screen onto an explicit new-window product action', () => {
    expect(resolveSameOriginNavigation('/monitor/view?id=3', {
      currentSearch: '?screen=true',
      explicitNewWindow: true,
    })).toEqual({
      href: '/monitor/view?id=3',
      mode: 'newTab',
    });
  });
});
