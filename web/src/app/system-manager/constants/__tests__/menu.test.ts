import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
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
  children: EnterpriseMenuChild[];
}

interface EnterpriseMenus {
  zh_patches: EnterpriseMenuPatch[];
  en_patches: EnterpriseMenuPatch[];
}

const enterpriseMenus = JSON.parse(
  readFileSync(resolve(process.cwd(), '../enterprise/web/manifests/menus.json'), 'utf8'),
) as EnterpriseMenus;

const STABLE_USER_NAMES = [
  'user_group',
  'login_auth',
  'user_sync',
  'security_settings',
  'super_admin',
] as const;

const STABLE_SETTING_NAMES = [
  'audit_log',
  'error_logs',
  'network_white_list',
  'openapi_docs',
  'api_secret_key',
] as const;

const STABLE_USER_URLS = [
  '/system-manager/user/structure',
  '/system-manager/user/login-auth',
  '/system-manager/user/user-sync',
  '/system-manager/user/security-settings',
  '/system-manager/user/adminstrator',
] as const;

const STABLE_SETTING_URLS = [
  '/system-manager/settings/audit-log',
  '/system-manager/settings/error-logs',
  '/system-manager/settings/network-whitelist',
  '/system-manager/settings/openapi-docs',
  '/system-manager/settings/key',
] as const;

describe('系统管理菜单文案与二级顺序', () => {
  it.each(['zh', 'en'] as const)('%s 用户管理顺序与稳定标识保持不变', (locale) => {
    const userMenu = menu[locale].find((item) => item.url === '/system-manager/user');
    const names = userMenu?.children?.map((item) => item.name) ?? [];
    const urls = userMenu?.children?.map((item) => item.url) ?? [];

    expect(names).toEqual([...STABLE_USER_NAMES]);
    expect(urls).toEqual([...STABLE_USER_URLS]);
  });

  it.each(['zh', 'en'] as const)('%s 平台管理顺序、URL 与父级标识保持不变', (locale) => {
    const settingMenu = menu[locale].find((item) => item.name === 'Setting');
    const names = settingMenu?.children?.map((item) => item.name) ?? [];
    const urls = settingMenu?.children?.map((item) => item.url) ?? [];

    expect(settingMenu?.url).toBe('/system-manager/settings');
    expect(names).toEqual([...STABLE_SETTING_NAMES]);
    expect(urls).toEqual([...STABLE_SETTING_URLS]);
    expect(urls[0]).toBe('/system-manager/settings/audit-log');
  });

  it('中文菜单使用目标文案', () => {
    const userMenu = menu.zh.find((item) => item.url === '/system-manager/user');
    const settingMenu = menu.zh.find((item) => item.name === 'Setting');

    expect(userMenu?.children?.map((item) => item.title)).toEqual([
      '组织架构',
      '登录认证',
      '用户同步',
      '安全策略',
      '超级管理员',
    ]);
    expect(settingMenu?.title).toBe('平台管理');
    expect(settingMenu?.children?.map((item) => item.title)).toEqual([
      '审计日志',
      '错误日志',
      '网络白名单',
      'API 文档',
      'API 令牌',
    ]);
  });

  it('英文菜单使用目标文案', () => {
    const settingMenu = menu.en.find((item) => item.name === 'Setting');

    expect(settingMenu?.title).toBe('Platform Management');
    expect(settingMenu?.children?.map((item) => item.title)).toEqual([
      'Audit Logs',
      'Error Logs',
      'Network Whitelist',
      'API Documentation',
      'API Token',
    ]);
  });

  it('企业版仅追加门户与许可，并使用新文案', () => {
    const zhPatch = enterpriseMenus.zh_patches.find((item) => item.target === 'Setting');
    const enPatch = enterpriseMenus.en_patches.find((item) => item.target === 'Setting');

    expect(zhPatch?.children.map((item) => item.name)).toEqual(['portal_settings', 'license_mgmt']);
    expect(zhPatch?.children.map((item) => item.url)).toEqual([
      '/system-manager/settings/portal',
      '/system-manager/settings/license',
    ]);
    expect(zhPatch?.children.map((item) => item.title)).toEqual(['门户设置', '许可管理']);
    expect(enPatch?.children.map((item) => item.title)).toEqual(['Portal Settings', 'License Management']);
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
