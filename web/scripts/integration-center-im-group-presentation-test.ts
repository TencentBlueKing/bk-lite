import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const page = readFileSync(
  new URL('../src/app/system-manager/(pages)/integration-center/page.tsx', import.meta.url),
  'utf8',
);
const detailPage = readFileSync(
  new URL('../src/app/system-manager/(pages)/integration-center/detail/page.tsx', import.meta.url),
  'utf8',
);
const zh = JSON.parse(
  readFileSync(new URL('../src/app/system-manager/locales/zh.json', import.meta.url), 'utf8'),
);
const en = JSON.parse(
  readFileSync(new URL('../src/app/system-manager/locales/en.json', import.meta.url), 'utf8'),
);

assert.match(
  page,
  /getIntegrationCapabilityLabel\(capability\.key,\s*t\)/,
  'integration cards must use the shared capability label resolver',
);
assert.equal(zh.system.integrationCenter.capability.imGroup, '群协作');
assert.equal(en.system.integrationCenter.capability.imGroup, 'Group Collaboration');
assert.match(detailPage, /activeTab === 'im_group'/);
assert.match(detailPage, /system\.integrationCenter\.imGroupOverviewDescription/);
assert.match(detailPage, /system\.integrationCenter\.imGroupNoExtraConfig/);
assert.match(detailPage, /system\.integrationCenter\.checkGroupCapability/);
assert.doesNotMatch(detailPage, /im_group_create_chat_url|im_group_members_url/);
assert.equal(
  zh.system.integrationCenter.imGroupOverviewDescription,
  '使用当前集成应用创建 Incident 协作群，并持续同步新增负责人和协作者。',
);
assert.equal(zh.system.integrationCenter.imGroupNoExtraConfig, '无需额外填写接口地址。');
assert.equal(zh.system.integrationCenter.checkGroupCapability, '检查群协作能力');
assert.equal(zh.system.integrationCenter.checkGroupCapabilitySuccess, '群协作基础能力检查通过');
assert.match(zh.system.integrationCenter.imGroupFeishuPermissionHint, /im:chat:create/);
assert.match(zh.system.integrationCenter.imGroupFeishuPermissionHint, /im:message:send_as_bot/);
assert.equal(en.system.integrationCenter.checkGroupCapability, 'Check group collaboration');

console.log('IM group integration-center presentation contract passed');
