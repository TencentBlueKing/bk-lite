import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const utils = readFileSync(new URL('../src/app/system-manager/utils/integrationCenter.ts', import.meta.url), 'utf8');
const modal = readFileSync(
  new URL('../src/app/system-manager/(pages)/integration-center/CreateIntegrationInstanceModal.tsx', import.meta.url),
  'utf8',
);
const zh = JSON.parse(readFileSync(new URL('../src/app/system-manager/locales/zh.json', import.meta.url), 'utf8'));
const en = JSON.parse(readFileSync(new URL('../src/app/system-manager/locales/en.json', import.meta.url), 'utf8'));

assert.match(utils, /wecom:\s*['"]wecom['"]/);
assert.match(utils, /return t\(`system\.integrationCenter\.provider\.\$\{providerKey\}`,\s*providerKey\);/);
assert.match(utils, /system\.integrationCenter\.providerDesc\.\$\{providerKey\}/);
assert.match(modal, /getIntegrationProviderDescription/);

assert.equal(zh.system.integrationCenter.provider.feishu, '飞书');
assert.equal(zh.system.integrationCenter.provider.wechat, '微信');
assert.equal(zh.system.integrationCenter.provider.wecom, '企业微信');
assert.equal(zh.system.integrationCenter.provider.ad, 'Active Directory');
assert.equal(zh.system.integrationCenter.providerDesc.feishu, '飞书接入，支持登录认证、用户同步、通知渠道和群协作。');
assert.equal(zh.system.integrationCenter.providerDesc.wechat, '微信接入，用于登录认证。');
assert.equal(zh.system.integrationCenter.providerDesc.wecom, '企业微信接入，支持登录认证、用户同步、通知渠道和群协作。');
assert.equal(zh.system.integrationCenter.providerDesc.ad, 'Active Directory 接入，用于登录认证和用户同步。');

assert.equal(en.system.integrationCenter.provider.feishu, 'Feishu');
assert.equal(en.system.integrationCenter.provider.wechat, 'WeChat');
assert.equal(en.system.integrationCenter.provider.wecom, 'WeCom');
assert.equal(en.system.integrationCenter.provider.ad, 'Active Directory');
assert.equal(
  en.system.integrationCenter.providerDesc.feishu,
  'Feishu integration for login authentication, user sync, notifications, and group collaboration.',
);
assert.equal(en.system.integrationCenter.providerDesc.wechat, 'WeChat integration for login authentication.');
assert.equal(
  en.system.integrationCenter.providerDesc.wecom,
  'WeCom integration for login authentication, user sync, notifications, and group collaboration.',
);
assert.equal(
  en.system.integrationCenter.providerDesc.ad,
  'Active Directory integration for login authentication and user sync.',
);

console.log('WeCom integration-center presentation contract passed');