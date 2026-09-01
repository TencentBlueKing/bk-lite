import { describe, expect, it } from 'vitest';

import type { MenuItem } from '@/types/index';
import {
  buildAppTopSideNavGroups,
  countVisibleAppSlots,
  findActiveApp,
  isConsoleChromeException,
  isDetailChromeContext,
  resolveAppNavigation,
  resolveEffectiveChromeLayout,
  shouldOpenAppInNewTab,
  shouldShowAppTopSideNav,
  shouldShowClassicSegmentedNav,
  splitOverflowApps,
} from '../resolve';
import { normalizeConsoleChromeLayout } from '../storage';

const menu = (item: Partial<MenuItem> & Pick<MenuItem, 'name' | 'url'>): MenuItem => ({
  title: item.title || item.name,
  icon: '',
  operation: [],
  ...item,
});

const opspilotMenus: MenuItem[] = [
  menu({
    title: '工作台',
    url: '/opspilot/studio',
    name: 'bot_list',
    hasDetail: true,
    children: [
      menu({ title: '设置', url: '/opspilot/studio/detail/settings', name: 'bot_settings' }),
      menu({ title: '日志', url: '/opspilot/studio/detail/logInfo', name: 'bot_conversation_log' }),
    ],
  }),
  menu({
    title: '智能体',
    url: '/opspilot/skill',
    name: 'skill_list',
    hasDetail: true,
  }),
];

const jobMenus: MenuItem[] = [
  menu({ title: '首页', url: '/job/home', name: 'home' }),
  menu({
    title: '作业执行',
    url: '/job/execution',
    name: 'execution',
    children: [
      menu({ title: '快速执行', url: '/job/execution/quick-exec', name: 'quick_exec' }),
      menu({ title: '文件分发', url: '/job/execution/file-dist', name: 'file_dist' }),
      menu({ title: '创建定时任务', url: '/job/execution/cron-task/create', name: 'cron_task_create', isNotMenuItem: true }),
    ],
  }),
];

describe('console chrome layout resolve', () => {
  it('defaults unknown storage values to classic', () => {
    expect(normalizeConsoleChromeLayout('app-top')).toBe('app-top');
    expect(normalizeConsoleChromeLayout('classic')).toBe('classic');
    expect(normalizeConsoleChromeLayout('side')).toBe('classic');
    expect(normalizeConsoleChromeLayout(null)).toBe('classic');
  });

  it('forces classic chrome on exception routes', () => {
    expect(isConsoleChromeException('/ops-console/home')).toBe(true);
    expect(isConsoleChromeException('/opspilot/studio/chat')).toBe(true);
    expect(isConsoleChromeException('/ops-analysis/share/abc')).toBe(true);
    expect(isConsoleChromeException('/ops-analysis/render/execution/7')).toBe(true);
    expect(isConsoleChromeException('/monitor/view/dashboard/1')).toBe(true);
    expect(isConsoleChromeException('/auth/signin')).toBe(true);
    expect(isConsoleChromeException('/no-permission')).toBe(true);
    expect(isConsoleChromeException('/cmdb/assetOverview')).toBe(false);
    expect(resolveEffectiveChromeLayout('app-top', '/ops-console')).toBe('classic');
    expect(resolveEffectiveChromeLayout('app-top', '/cmdb/assetOverview')).toBe('app-top');
  });

  it('keeps the global app side nav on detail pages so first-layer items stay reachable', () => {
    expect(isDetailChromeContext('/opspilot/studio', opspilotMenus)).toBe(false);
    expect(isDetailChromeContext('/opspilot/studio/detail/settings', opspilotMenus)).toBe(true);
    expect(shouldShowAppTopSideNav('app-top', '/opspilot/studio', opspilotMenus)).toBe(true);
    expect(shouldShowAppTopSideNav('app-top', '/opspilot/studio/detail/settings', opspilotMenus)).toBe(true);
    expect(shouldShowAppTopSideNav('classic', '/opspilot/studio', opspilotMenus)).toBe(false);
    expect(shouldShowAppTopSideNav('app-top', '/ops-console/home', opspilotMenus)).toBe(false);
    expect(shouldShowAppTopSideNav('app-top', '/no-permission', opspilotMenus)).toBe(false);
  });

  it('keeps first-layer items flat and leaves children to the original in-page side menu', () => {
    const groups = buildAppTopSideNavGroups(jobMenus, '/job/execution/quick-exec');
    expect(groups.map((group) => group.item.name)).toEqual(['home', 'execution']);
    expect(groups[0].children).toEqual([]);
    expect(groups[1].children).toEqual([]);
  });

  it('does not inline detail children under a hasDetail first-layer item', () => {
    const groups = buildAppTopSideNavGroups(opspilotMenus, '/opspilot/studio');
    expect(groups[0].children).toEqual([]);
    expect(groups[1].children).toEqual([]);
  });

  it('keeps classic segmented nav only when classic chrome is effective', () => {
    expect(shouldShowClassicSegmentedNav('classic', '/job/execution', jobMenus, true)).toBe(true);
    expect(shouldShowClassicSegmentedNav('app-top', '/job/execution', jobMenus, true)).toBe(false);
    expect(shouldShowClassicSegmentedNav('classic', '/job/execution', jobMenus, false)).toBe(false);
  });

  it('opens custom or cross-origin apps in a new tab and same-origin builtins in-page', () => {
    const origin = 'https://lite.example';
    expect(shouldOpenAppInNewTab({ url: '/cmdb', is_build_in: true }, origin)).toBe(false);
    expect(shouldOpenAppInNewTab({ url: 'https://lite.example/monitor', is_build_in: true }, origin)).toBe(false);
    expect(shouldOpenAppInNewTab({ url: 'https://mail.example/qmail', is_build_in: true }, origin)).toBe(true);
    expect(shouldOpenAppInNewTab({ url: '/custom', is_build_in: false }, origin)).toBe(true);
    expect(resolveAppNavigation({ url: 'https://lite.example/cmdb?x=1', is_build_in: true }, origin)).toEqual({
      mode: 'same-tab',
      href: '/cmdb?x=1',
    });
    expect(resolveAppNavigation({ url: 'https://mail.example/qmail', is_build_in: false }, origin)).toEqual({
      mode: 'new-tab',
      href: 'https://mail.example/qmail',
    });
  });

  it('picks the longest matching same-origin app as active', () => {
    const origin = 'https://lite.example';
    const apps = [
      { url: '/ops', name: 'ops' },
      { url: '/ops-analysis', name: 'ops-analysis' },
      { url: '/cmdb', name: 'cmdb' },
    ];
    expect(findActiveApp(apps, '/ops-analysis/view', origin)?.name).toBe('ops-analysis');
    expect(findActiveApp(apps, '/cmdb/assetData', origin)?.name).toBe('cmdb');
  });

  it('keeps an app active on sibling pages of its landing url', () => {
    const origin = 'https://lite.example';
    const apps = [
      { url: '/cmdb/assetSearch', name: 'cmdb' },
      { url: '/monitor/view', name: 'monitor' },
      { url: '/node-manager/cloudregion', name: 'node' },
    ];
    expect(findActiveApp(apps, '/cmdb/assetOverview', origin)?.name).toBe('cmdb');
    expect(findActiveApp(apps, '/cmdb/assetSearch', origin)?.name).toBe('cmdb');
    expect(findActiveApp(apps, '/node-manager/cloudregion', origin)?.name).toBe('node');
    expect(findActiveApp(apps, '/monitor/view', origin)?.name).toBe('monitor');
  });

  it('keeps the active app visible when splitting overflow', () => {
    const apps = [
      { url: '/a' },
      { url: '/b' },
      { url: '/c' },
      { url: '/d' },
    ];
    const split = splitOverflowApps(apps, 2, '/d');
    expect(split.visible.map((app) => app.url)).toEqual(['/a', '/d']);
    expect(split.overflow.map((app) => app.url)).toEqual(['/b', '/c']);
    expect(splitOverflowApps(apps, 8, '/d').overflow).toEqual([]);
    expect(countVisibleAppSlots(500, 3)).toBe(3);
    expect(countVisibleAppSlots(400, 3)).toBe(2);
    expect(countVisibleAppSlots(200, 8)).toBe(1);
  });
});
