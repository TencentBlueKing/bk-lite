import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { applyPatch } from '@/app/(core)/api/menu/route';
import monitorZh from '@/app/monitor/locales/zh.json';
import menu from '@/app/system-manager/constants/menu.json';
import en from '@/app/system-manager/locales/en.json';
import zh from '@/app/system-manager/locales/zh.json';

interface EnterpriseMenuChild {
  name: string;
  url: string;
  title: string;
}

interface EnterpriseMenuPatch {
  target: string;
  after?: string;
  children: EnterpriseMenuChild[];
}

interface EnterpriseMenus {
  zh_patches: EnterpriseMenuPatch[];
  en_patches: EnterpriseMenuPatch[];
}

const enterpriseMenus = JSON.parse(
  readFileSync(resolve(process.cwd(), '../enterprise/web/manifests/menus.json'), 'utf8'),
) as EnterpriseMenus;

const STABLE_USER_NAMES = ['user_group', 'login_auth', 'user_sync', 'user_fields'] as const;

const STABLE_SECURITY_NAMES = ['security_settings', 'super_admin', 'network_white_list'] as const;

const STABLE_SETTING_NAMES = ['audit_log', 'error_logs', 'openapi_docs', 'api_secret_key'] as const;

const FIRST_LEVEL_NAMES = [
  'Organization',
  'Security',
  'application_list',
  'channel_list',
  'integration_center',
  'credential',
  'Setting',
] as const;

const STABLE_USER_URLS = [
  '/system-manager/user/structure',
  '/system-manager/user/login-auth',
  '/system-manager/user/user-sync',
  '/system-manager/user/fields',
] as const;

const STABLE_SECURITY_URLS = [
  '/system-manager/user/security-settings',
  '/system-manager/user/adminstrator',
  '/system-manager/settings/network-whitelist',
] as const;

const STABLE_SETTING_URLS = [
  '/system-manager/settings/audit-log',
  '/system-manager/settings/error-logs',
  '/system-manager/settings/openapi-docs',
  '/system-manager/settings/key',
] as const;

describe('系统管理菜单文案与二级顺序', () => {
  it.each(['zh', 'en'] as const)('%s 一级顺序、用户页签和安全管理分组可观察', (locale) => {
    const items = menu[locale];
    const userMenu = items.find((item) => item.name === 'Organization');
    const securityMenu = items.find((item) => item.name === 'Security');
    const channelMenu = items.find((item) => item.name === 'channel_list');

    expect(items.map((item) => item.name)).toEqual([...FIRST_LEVEL_NAMES]);
    expect(userMenu?.title).toBe(locale === 'zh' ? '用户管理' : 'User Management');
    expect(userMenu?.children?.map((item) => item.name)).toEqual([...STABLE_USER_NAMES]);
    expect(userMenu?.children?.map((item) => item.url)).toEqual([...STABLE_USER_URLS]);
    expect(userMenu?.children?.map((item) => item.title)).toEqual(
      locale === 'zh'
        ? ['组织架构', '登录认证', '用户同步', '用户字段']
        : ['Organization Structure', 'Login Auth', 'User Sync', 'User Fields'],
    );

    expect(securityMenu?.title).toBe(locale === 'zh' ? '安全管理' : 'Security');
    expect(securityMenu?.url).toBe('/system-manager/user/security-settings');
    expect(securityMenu?.icon).toBe('guanlipingju');
    expect(securityMenu).not.toHaveProperty('hasDetail');
    expect(securityMenu?.children?.map((item) => item.name)).toEqual([...STABLE_SECURITY_NAMES]);
    expect(securityMenu?.children?.map((item) => item.url)).toEqual([...STABLE_SECURITY_URLS]);
    expect(channelMenu?.title).toBe(locale === 'zh' ? '通知渠道' : 'Channel');
  });

  it.each(['zh', 'en'] as const)('%s 平台管理不再包含网络白名单', (locale) => {
    const settingMenu = menu[locale].find((item) => item.name === 'Setting');
    const names = settingMenu?.children?.map((item) => item.name) ?? [];
    const urls = settingMenu?.children?.map((item) => item.url) ?? [];

    expect(settingMenu?.url).toBe('/system-manager/settings');
    expect(names).toEqual([...STABLE_SETTING_NAMES]);
    expect(urls).toEqual([...STABLE_SETTING_URLS]);
    expect(names).not.toContain('network_white_list');
    expect(urls[0]).toBe('/system-manager/settings/audit-log');
  });

  it('中文菜单使用目标文案', () => {
    const userMenu = menu.zh.find((item) => item.name === 'Organization');
    const securityMenu = menu.zh.find((item) => item.name === 'Security');
    const settingMenu = menu.zh.find((item) => item.name === 'Setting');

    expect(userMenu?.children?.map((item) => item.title)).toEqual(['组织架构', '登录认证', '用户同步', '用户字段']);
    expect(securityMenu?.children?.map((item) => item.title)).toEqual(['安全策略', '超级管理员', '网络白名单']);
    expect(settingMenu?.title).toBe('平台管理');
    expect(settingMenu?.children?.map((item) => item.title)).toEqual(['审计日志', '错误日志', 'API 文档', 'API 令牌']);
  });

  it('英文菜单使用目标文案', () => {
    const securityMenu = menu.en.find((item) => item.name === 'Security');
    const settingMenu = menu.en.find((item) => item.name === 'Setting');

    expect(securityMenu?.children?.map((item) => item.title)).toEqual([
      'Security Settings',
      'Super Administrator',
      'Network Whitelist',
    ]);
    expect(settingMenu?.title).toBe('Platform Management');
    expect(settingMenu?.children?.map((item) => item.title)).toEqual([
      'Audit Logs',
      'Error Logs',
      'API Documentation',
      'API Token',
    ]);
  });

  it('企业版敏感信息挂到安全管理，门户与许可仍追加到平台管理', () => {
    const zhPatch = enterpriseMenus.zh_patches.find((item) => item.target === 'Setting');
    const enPatch = enterpriseMenus.en_patches.find((item) => item.target === 'Setting');

    expect(zhPatch?.after).toBeUndefined();
    expect(zhPatch?.children.map((item) => item.name)).toEqual(['portal_settings', 'license_mgmt']);
    expect(zhPatch?.children.map((item) => item.url)).toEqual([
      '/system-manager/settings/portal',
      '/system-manager/settings/license',
    ]);
    expect(zhPatch?.children.map((item) => item.title)).toEqual(['门户设置', '许可管理']);
    expect(enPatch?.children.map((item) => item.title)).toEqual(['Portal Settings', 'License Management']);

    const zhSensitive = enterpriseMenus.zh_patches.find((item) => item.children.some((child) => child.name === 'sensitive_info'));
    const enSensitive = enterpriseMenus.en_patches.find((item) => item.children.some((child) => child.name === 'sensitive_info'));
    expect(zhSensitive?.target).toBe('Security');
    expect(zhSensitive?.after).toBe('super_admin');
    expect(zhSensitive?.children[0]).toMatchObject({
      title: '敏感信息',
      url: '/system-manager/user/sensitive-info',
      name: 'sensitive_info',
    });
    expect(enSensitive?.target).toBe('Security');
    expect(enSensitive?.after).toBe('super_admin');
    expect(enSensitive?.children[0]).toMatchObject({
      title: 'Sensitive Info',
      url: '/system-manager/user/sensitive-info',
      name: 'sensitive_info',
    });

    (['zh', 'en'] as const).forEach((locale) => {
      const items = structuredClone(menu[locale]);
      const sensitivePatch = locale === 'zh' ? zhSensitive : enSensitive;
      const settingPatch = locale === 'zh' ? zhPatch : enPatch;
      expect(applyPatch(items, (sensitivePatch?.target ?? '').split('.'), sensitivePatch?.children ?? [], sensitivePatch?.after)).toBe(true);
      expect(applyPatch(items, (settingPatch?.target ?? '').split('.'), settingPatch?.children ?? [], settingPatch?.after)).toBe(true);

      const securityMenu = items.find((item) => item.name === 'Security');
      const settingMenu = items.find((item) => item.name === 'Setting');
      expect(securityMenu?.children?.map((item) => item.name)).toEqual([
        'security_settings',
        'super_admin',
        'sensitive_info',
        'network_white_list',
      ]);
      expect(settingMenu?.children?.map((item) => item.name)).toEqual([
        ...STABLE_SETTING_NAMES,
        'portal_settings',
        'license_mgmt',
      ]);
    });

    const missingSibling = [{ name: 'Security', children: [{ name: 'super_admin' }] }];
    expect(applyPatch(missingSibling, ['Security'], [{ name: 'sensitive_info' }], 'security_settings')).toBe(true);
    expect(missingSibling[0].children?.map((item) => item.name)).toEqual(['super_admin', 'sensitive_info']);
  });

  it('页面文案与菜单同步，且未误改 OTP 白名单、应用密钥和签名密钥', () => {
    expect(zh.system.settings.secret.title).toBe('API 令牌');
    expect(zh.system.settings.secret.personalTab).toBe('个人令牌');
    expect(zh.system.settings.secret.systemTab).toBe('系统令牌');
    expect(zh.system.settings.openapiDocs.title).toBe('API 文档');
    expect(zh.system.settings.openapiDocs.authHeaderKeyPath).toBe('平台管理 → API 令牌');
    expect(zh.system.settings.networkWhitelist.title).toBe('网络白名单');
    expect(zh.system.settings.tabs.portal).toBe('门户设置');
    expect(zh.system.settings.tabs.license).toBe('许可管理');
    expect(zh.system.security.otpWhitelist).toBe('OTP 白名单');
    expect(zh.system.security.appSecret).toBe('应用密钥');
    expect(zh.system.channel.settings.sign_secret).toBe('签名密钥');
    expect(monitorZh.monitor.integrations.customApi.apiKey).toBe('API 令牌');
    expect(monitorZh.monitor.integrations.customApi.noApiKeyWarning).toContain('API 令牌');

    expect(en.system.settings.secret.title).toBe('API Token');
    expect(en.system.settings.openapiDocs.title).toBe('API Documentation');
    expect(en.system.settings.openapiDocs.authHeaderKeyPath).toBe('Platform Management → API Token');
    expect(en.system.settings.networkWhitelist.title).toBe('Network Whitelist');
    expect(en.system.settings.tabs.portal).toBe('Portal Settings');
    expect(en.system.settings.tabs.license).toBe('License Management');
  });
});
