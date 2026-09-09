import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { formatIntegrationInstanceDisplayName } from '../src/app/system-manager/utils/integrationCenter';

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
const wecomZh = readFileSync(
  resolve(repoRoot, 'server/apps/system_mgmt/providers/builtin/wecom/language/zh-Hans.yaml'),
  'utf8',
);
const wecomEn = readFileSync(
  resolve(repoRoot, 'server/apps/system_mgmt/providers/builtin/wecom/language/en.yaml'),
  'utf8',
);

assert.doesNotMatch(utils, /resolveIntegrationProviderIcon/);
assert.doesNotMatch(utils, /providerIconMap/);
assert.match(modal, /icon:\s*provider\.key/);
assert.match(modal, /provider\.name/);
assert.match(modal, /provider\.description/);
assert.doesNotMatch(modal, /getIntegrationProviderDisplayName/);
assert.doesNotMatch(modal, /getIntegrationProviderDescription/);
assert.doesNotMatch(utils, /getIntegrationProviderDisplayName/);
assert.doesNotMatch(utils, /getIntegrationProviderDescription/);
assert.doesNotMatch(utils, /system\.integrationCenter\.provider\.\$\{/);

assert.equal(zh.system.integrationCenter.provider, undefined);
assert.equal(zh.system.integrationCenter.providerDesc, undefined);
assert.equal(en.system.integrationCenter.provider, undefined);
assert.equal(en.system.integrationCenter.providerDesc, undefined);
assert.equal(
  formatIntegrationInstanceDisplayName({
    name: 'Prod',
    provider_key: 'teams',
    provider_name: 'Microsoft Teams',
  }),
  'Prod / Microsoft Teams',
);
assert.equal(
  formatIntegrationInstanceDisplayName({ name: 'Prod', provider_key: 'teams' }),
  'Prod / teams',
);

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
assert.match(wecomZh, /userid:\n\s+label:\s*用户 ID/);
assert.match(wecomEn, /userid:\n\s+label:\s*User ID/);

const teamsZh = readFileSync(
  resolve(repoRoot, 'enterprise/server/apps/system_mgmt/enterprise/providers/builtin/teams/language/zh-Hans.yaml'),
  'utf8',
);
const teamsEn = readFileSync(
  resolve(repoRoot, 'enterprise/server/apps/system_mgmt/enterprise/providers/builtin/teams/language/en.yaml'),
  'utf8',
);
assert.match(teamsZh, /name:\s*Microsoft Teams/);
assert.match(teamsZh, /企业 Microsoft 365 工作租户 Teams 接入，用于 IM 通知。/);
assert.match(teamsEn, /name:\s*Microsoft Teams/);
assert.match(teamsEn, /Microsoft 365 work-tenant Teams integration for IM notifications\./);
assert.match(teamsZh, /id:\n\s+label:\s*Graph 用户 ID/);
assert.match(teamsZh, /mail:\n\s+label:\s*邮箱/);
assert.match(teamsZh, /userPrincipalName:\n\s+label:\s*用户主体名称/);
assert.match(teamsEn, /id:\n\s+label:\s*Graph user ID/);
assert.match(teamsZh, /name:\n\s+label:\s*显示名/);
assert.match(teamsZh, /mobile:\n\s+label:\s*手机号/);

console.log('WeCom integration-center presentation contract passed');
