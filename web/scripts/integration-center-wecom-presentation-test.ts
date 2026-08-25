import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(here, '../..');
const utils = readFileSync(new URL('../src/app/system-manager/utils/integrationCenter.ts', import.meta.url), 'utf8');
const modal = readFileSync(
  new URL('../src/app/system-manager/(pages)/integration-center/CreateIntegrationInstanceModal.tsx', import.meta.url),
  'utf8',
);
const zh = JSON.parse(readFileSync(new URL('../src/app/system-manager/locales/zh.json', import.meta.url), 'utf8'));
const en = JSON.parse(readFileSync(new URL('../src/app/system-manager/locales/en.json', import.meta.url), 'utf8'));
const feishuZh = readFileSync(
  resolve(repoRoot, 'server/apps/system_mgmt/providers/builtin/feishu/language/zh-Hans.yaml'),
  'utf8',
);
const feishuEn = readFileSync(
  resolve(repoRoot, 'server/apps/system_mgmt/providers/builtin/feishu/language/en.yaml'),
  'utf8',
);

assert.match(utils, /wecom:\s*['"]wecom['"]/);
assert.match(modal, /provider\.name/);
assert.match(modal, /provider\.description/);
assert.doesNotMatch(modal, /getIntegrationProviderDisplayName/);
assert.doesNotMatch(modal, /getIntegrationProviderDescription/);

assert.equal(zh.system.integrationCenter.provider.feishu, undefined);
assert.equal(zh.system.integrationCenter.providerDesc, undefined);
assert.equal(en.system.integrationCenter.provider.feishu, undefined);
assert.equal(en.system.integrationCenter.providerDesc, undefined);

assert.match(feishuZh, /name:\s*飞书/);
assert.match(
  feishuZh,
  /飞书接入，支持登录认证、用户同步、通知渠道和群协作。/,
);
assert.match(feishuEn, /name:\s*Feishu/);
assert.match(
  feishuEn,
  /Feishu integration for login authentication, user sync, notifications, and group collaboration\./,
);

console.log('WeCom integration-center presentation contract passed');
