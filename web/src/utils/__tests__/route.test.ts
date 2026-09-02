import { describe, expect, it } from 'vitest';

import {
  getClientIdFromRoute,
  isAppClientMenuRoute,
  isWaitingForClientMenus,
  PORTAL_HOME_PATH,
} from '@/utils/route';

describe('app client route', () => {
  it('exposes the portal landing path', () => {
    expect(PORTAL_HOME_PATH).toBe('/ops-console/home');
  });

  it('reads the first path segment as the client id', () => {
    expect(getClientIdFromRoute('/system-manager/user')).toBe('system-manager');
    expect(getClientIdFromRoute('/cmdb/assetOverview')).toBe('cmdb');
    expect(getClientIdFromRoute('/auth/signin')).toBe('ops-console');
    expect(getClientIdFromRoute('/')).toBe('ops-console');
  });

  it('only reloads app menus on real app routes', () => {
    expect(isAppClientMenuRoute('/system-manager/user')).toBe(true);
    expect(isAppClientMenuRoute('/cmdb/assetOverview')).toBe(true);
    expect(isAppClientMenuRoute('/no-permission')).toBe(false);
    expect(isAppClientMenuRoute('/no-found')).toBe(false);
    expect(isAppClientMenuRoute('/auth/signin')).toBe(false);
    expect(isAppClientMenuRoute('/')).toBe(false);
    expect(isAppClientMenuRoute(null)).toBe(false);
  });

  it('waits for menus when the same-tab app client changes', () => {
    expect(isWaitingForClientMenus('/system-manager/user', 'cmdb')).toBe(true);
    expect(isWaitingForClientMenus('/system-manager/user', 'system-manager')).toBe(false);
    expect(isWaitingForClientMenus('/system-manager/user', null)).toBe(true);
    expect(isWaitingForClientMenus('/no-permission', 'cmdb')).toBe(false);
  });
});
