import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import en from '@/locales/en.json';
import zh from '@/locales/zh.json';
import {
  canShowDashboardSettingsLink,
  followGlobalDescription,
  homepageParentLabelKey,
  homepageParentRightLabel,
  homepageRadioChecked,
  hrefAfterFollowGlobal,
  hrefAfterPinWorkbench,
  menuGrantsOpsAnalysisView,
  personalDashboardCaption,
} from '../homepageMenu';

const userInfoDir = path.resolve(
  process.cwd(),
  'src/app/(core)/components/top-menu/user-info',
);
const indexSource = readFileSync(path.join(userInfoDir, 'index.tsx'), 'utf8');
const switcherSource = readFileSync(path.join(userInfoDir, 'homepageSwitcher.tsx'), 'utf8');

describe('homepage menu copy', () => {
  const keys = [
    'homepage',
    'homepagePanelTitle',
    'homepageFollowGlobal',
    'homepageFollowGlobalHint',
    'homepageFollowGlobalCurrent',
    'homepageFollowGlobalSuccess',
    'homepagePinWorkbench',
    'homepagePinWorkbenchHint',
    'homepagePinWorkbenchSuccess',
    'homepageDashboardSettings',
    'homepageDashboardSettingsHint',
    'homepageCurrentHomepage',
    'homepagePersonalDashboardFallback',
  ] as const;

  it('keeps the user-menu copy in common locales', () => {
    for (const key of keys) {
      expect(zh.common[key]?.trim()).toBeTruthy();
      expect(en.common[key]?.trim()).toBeTruthy();
    }
    expect(zh.common.homepage).toBe('首页');
    expect(zh.common.homepagePanelTitle).toBe('登录首页');
    expect(zh.common.homepageFollowGlobal).toBe('默认首页');
    expect(zh.common.homepageFollowGlobalHint).toBe('登录后进入管理员设置的默认首页');
    expect(zh.common.homepageFollowGlobalCurrent).toBe('（当前：{name}）');
    expect(zh.common.homepageFollowGlobalSuccess).toBe('已设为默认首页');
    expect(zh.common.homepagePinWorkbench).toBe('控制台');
    expect(zh.common.homepagePinWorkbenchHint).toBe('登录后始终进入应用控制台');
    expect(zh.common.homepagePinWorkbenchSuccess).toBe('已设为控制台');
    expect(zh.common.homepageDashboardSettings).toBe('选择仪表盘作为首页');
    expect(zh.common.homepageDashboardSettingsHint).toBe('从运营分析中选择我的登录首页');
    expect(zh.common.homepagePersonalDashboardFallback).toBe('已设个人仪表盘首页');
    expect(zh.common.homepageCurrentHomepage).toBe('当前首页：{name}');
    expect(en.common.homepage).toBe('Homepage');
    expect(en.common.homepagePanelTitle).toBe('Login homepage');
    expect(en.common.homepageFollowGlobal).toBe('Default homepage');
    expect(en.common.homepagePinWorkbench).toBe('Console');
    expect(en.common.homepageFollowGlobalSuccess).toBe('Set as default homepage');
    expect(en.common.homepagePinWorkbenchSuccess).toBe('Set as console');
    expect(en.common.homepageCurrentHomepage).toBe('Current homepage: {name}');
  });
});

describe('homepage menu rules', () => {
  it('places the homepage row between organization and user info', () => {
    const groups = indexSource.indexOf("key: 'groups'");
    const homepage = indexSource.indexOf("key: 'homepage'");
    const userInfo = indexSource.indexOf("key: 'userInfo'");
    expect(groups).toBeGreaterThan(-1);
    expect(groups).toBeLessThan(homepage);
    expect(homepage).toBeLessThan(userInfo);
  });

  it('trusts personal_mode and does not read the logo shortcut', () => {
    expect(switcherSource).not.toContain('usePermissions');
    expect(switcherSource).not.toContain('getShortcut');
    expect(switcherSource).not.toContain('entry');
    expect(homepageParentLabelKey('follow')).toBe('common.homepageFollowGlobal');
    expect(homepageParentLabelKey('workbench')).toBe('common.homepagePinWorkbench');
    expect(homepageParentLabelKey('dashboard')).toBeNull();
    expect(homepageParentLabelKey(null)).toBeNull();
    expect(homepageParentRightLabel('follow', null)).toEqual({ kind: 'i18n', key: 'common.homepageFollowGlobal' });
    expect(homepageParentRightLabel('workbench', null)).toEqual({ kind: 'i18n', key: 'common.homepagePinWorkbench' });
    expect(homepageParentRightLabel('dashboard', '运维总览')).toEqual({ kind: 'text', value: '运维总览' });
    expect(homepageParentRightLabel('dashboard', '  ')).toBeNull();
    expect(homepageParentRightLabel('dashboard', null)).toBeNull();
    expect(homepageParentRightLabel(null, null)).toBeNull();
    expect(homepageRadioChecked('follow', 'follow')).toBe(true);
    expect(homepageRadioChecked('follow', 'workbench')).toBe(false);
    expect(homepageRadioChecked('workbench', 'workbench')).toBe(true);
    expect(homepageRadioChecked('dashboard', 'follow')).toBe(false);
    expect(homepageRadioChecked('dashboard', 'workbench')).toBe(false);
    expect(homepageRadioChecked(null, 'follow')).toBe(false);
  });

  it('appends the administrator dashboard name only when one is available', () => {
    const base = '取消个人设置，使用管理员绑定的首页';
    const current = (name: string) => `（当前：${name}）`;
    expect(followGlobalDescription(base, current, null)).toBe(base);
    expect(followGlobalDescription(base, current, '  ')).toBe(base);
    expect(followGlobalDescription(base, current, '运维总览')).toBe(`${base}（当前：运维总览）`);
  });

  it('describes the personal dashboard under the settings link without a third radio', () => {
    expect(personalDashboardCaption('follow', '业务大盘', true, '已设个人仪表盘首页')).toBeNull();
    expect(personalDashboardCaption('dashboard', null, false, '已设个人仪表盘首页')).toBeNull();
    expect(personalDashboardCaption('dashboard', '业务大盘', true, '已设个人仪表盘首页')).toBe('业务大盘');
    expect(personalDashboardCaption('dashboard', '  ', true, '已设个人仪表盘首页')).toBe('已设个人仪表盘首页');
    expect(personalDashboardCaption('dashboard', null, true, '已设个人仪表盘首页')).toBe('已设个人仪表盘首页');
  });

  it('still exposes landing href helpers, but the switcher no longer navigates after save', () => {
    expect(hrefAfterFollowGlobal({
      global_mode: 'dashboard',
      global_dashboard_id: 9,
    })).toBe('/ops-console/home?dashboard_id=9');
    expect(hrefAfterFollowGlobal({
      global_mode: 'workbench',
      global_dashboard_id: null,
    })).toBe('/ops-console/home');
    expect(hrefAfterFollowGlobal(null)).toBe('/ops-console/home');
    expect(hrefAfterPinWorkbench()).toBe('/ops-console/home');
    expect(switcherSource).not.toContain('hrefAfterFollowGlobal');
    expect(switcherSource).not.toContain('hrefAfterPinWorkbench');
    expect(switcherSource).toContain("message.success(");
    expect(switcherSource).toContain("t('common.homepageFollowGlobalSuccess')");
    expect(switcherSource).toContain("t('common.homepagePinWorkbenchSuccess')");
  });

  it('hides dashboard settings until module access and view permission are both known', () => {
    expect(canShowDashboardSettingsLink({
      clientLoading: true,
      hasModule: true,
      viewAllowed: true,
    })).toBe(false);
    expect(canShowDashboardSettingsLink({
      clientLoading: false,
      hasModule: false,
      viewAllowed: true,
    })).toBe(false);
    expect(canShowDashboardSettingsLink({
      clientLoading: false,
      hasModule: true,
      viewAllowed: null,
    })).toBe(false);
    expect(canShowDashboardSettingsLink({
      clientLoading: false,
      hasModule: true,
      viewAllowed: false,
    })).toBe(false);
    expect(canShowDashboardSettingsLink({
      clientLoading: false,
      hasModule: true,
      viewAllowed: true,
    })).toBe(true);
  });

  it('finds nested view-View and ignores other menus', () => {
    expect(menuGrantsOpsAnalysisView([
      {
        name: 'Operations Analysis',
        children: [{ name: 'view', operation: ['View', 'AddCatalogue'] }],
      },
    ])).toBe(true);
    expect(menuGrantsOpsAnalysisView([
      { name: 'Operations Analysis', children: [{ name: 'view', operation: ['AddCatalogue'] }] },
    ])).toBe(false);
    expect(menuGrantsOpsAnalysisView([
      { name: 'settings', operation: ['View'] },
    ])).toBe(false);
    expect(menuGrantsOpsAnalysisView(null)).toBe(false);
    expect(menuGrantsOpsAnalysisView({ name: 'view', operation: ['View'] })).toBe(false);
  });
});
