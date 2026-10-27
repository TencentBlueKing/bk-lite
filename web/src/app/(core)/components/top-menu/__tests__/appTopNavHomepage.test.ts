import { describe, expect, it } from 'vitest';
import {
  findAppTopNavActiveApp,
  isAppTopNavActive,
  shouldStayOnAppTopNavClick,
} from '../appTopNavHomepage';

const origin = 'http://localhost:3000';
const apps = [
  { name: 'ops-console', url: '/ops-console/home' },
  { name: 'ops-analysis', url: '/ops-analysis' },
  { name: 'cmdb', url: '/cmdb' },
];

describe('isAppTopNavActive', () => {
  it('highlights neither console nor ops-analysis on dashboard shell under console home', () => {
    expect(isAppTopNavActive(apps[0], '/ops-console/home', origin, '?dashboard_id=105')).toBe(false);
    expect(isAppTopNavActive(apps[1], '/ops-console/home', origin, '?dashboard_id=105')).toBe(false);
    expect(isAppTopNavActive(apps[2], '/ops-console/home', origin, '?dashboard_id=105')).toBe(false);
  });

  it('keeps highlighting console on bare workbench home', () => {
    expect(isAppTopNavActive(apps[0], '/ops-console/home', origin, '')).toBe(true);
    expect(isAppTopNavActive(apps[1], '/ops-console/home', origin, '')).toBe(false);
  });

  it('highlights ops-analysis only on real ops-analysis routes', () => {
    expect(isAppTopNavActive(apps[1], '/ops-analysis', origin, '')).toBe(true);
    expect(isAppTopNavActive(apps[1], '/ops-analysis/view', origin, '')).toBe(true);
    expect(isAppTopNavActive(apps[0], '/ops-analysis/view', origin, '')).toBe(false);
  });

  it('keeps normal app active matching for other routes', () => {
    expect(isAppTopNavActive(apps[2], '/cmdb/assetOverview', origin, '')).toBe(true);
    expect(isAppTopNavActive(apps[0], '/cmdb/assetOverview', origin, '')).toBe(false);
  });
});

describe('shouldStayOnAppTopNavClick', () => {
  it('does not stay when console is inactive (dashboard shell case)', () => {
    expect(shouldStayOnAppTopNavClick(
      false,
      { mode: 'same-tab', href: '/ops-console/home' },
    )).toBe(false);
  });

  it('still stays when already on bare console', () => {
    expect(shouldStayOnAppTopNavClick(
      true,
      { mode: 'same-tab', href: '/ops-console/home' },
    )).toBe(true);
  });

  it('still stays for other active apps', () => {
    expect(shouldStayOnAppTopNavClick(
      true,
      { mode: 'same-tab', href: '/cmdb/assetSearch' },
    )).toBe(true);
  });
});

describe('findAppTopNavActiveApp', () => {
  it('returns no active app on dashboard shell', () => {
    expect(findAppTopNavActiveApp(apps, '/ops-console/home', origin, 'dashboard_id=105'))
      .toBeUndefined();
  });

  it('returns console on bare home', () => {
    expect(findAppTopNavActiveApp(apps, '/ops-console/home', origin, '')?.name)
      .toBe('ops-console');
  });

  it('returns ops-analysis on real ops-analysis route', () => {
    expect(findAppTopNavActiveApp(apps, '/ops-analysis/view', origin, '')?.name)
      .toBe('ops-analysis');
  });
});
