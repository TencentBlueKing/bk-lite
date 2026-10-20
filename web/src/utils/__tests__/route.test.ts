import { describe, expect, it } from 'vitest';

import {
  getClientIdFromRoute,
  isAppClientMenuRoute,
  isModuleLinkRoute,
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
    expect(getClientIdFromRoute('/module-link/cmdb-monitor/tasks/abc')).toBe('cmdb');
    expect(getClientIdFromRoute('/module-link/monitor-cmdb/tasks/abc')).toBe('monitor');
    expect(getClientIdFromRoute('/auth/signin')).toBe('ops-console');
    expect(getClientIdFromRoute('/')).toBe('ops-console');
  });

  it('only reloads app menus on real app routes', () => {
    expect(isAppClientMenuRoute('/system-manager/user')).toBe(true);
    expect(isAppClientMenuRoute('/cmdb/assetOverview')).toBe(true);
    expect(isAppClientMenuRoute('/no-permission')).toBe(false);
    expect(isAppClientMenuRoute('/no-found')).toBe(false);
    expect(isAppClientMenuRoute('/auth/signin')).toBe(false);
    expect(isAppClientMenuRoute('/module-link/cmdb-monitor/tasks/abc')).toBe(false);
    expect(isAppClientMenuRoute('/')).toBe(false);
    expect(isAppClientMenuRoute(null)).toBe(false);
  });

  it('treats glue task pages as internal module-link routes', () => {
    expect(isModuleLinkRoute('/module-link')).toBe(true);
    expect(isModuleLinkRoute('/module-link/cmdb-monitor/tasks/abc')).toBe(true);
    expect(isModuleLinkRoute('/cmdb/assetData')).toBe(false);
    expect(isModuleLinkRoute(null)).toBe(false);
  });

  it('waits for menus when the same-tab app client changes', () => {
    expect(isWaitingForClientMenus('/system-manager/user', 'cmdb')).toBe(true);
    expect(isWaitingForClientMenus('/system-manager/user', 'system-manager')).toBe(false);
    expect(isWaitingForClientMenus('/system-manager/user', null)).toBe(true);
    expect(isWaitingForClientMenus('/no-permission', 'cmdb')).toBe(false);
    expect(isWaitingForClientMenus('/module-link/cmdb-monitor/tasks/abc', 'cmdb')).toBe(false);
  });
});
