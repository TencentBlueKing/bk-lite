import assert from 'node:assert/strict';

import { readFileSync } from 'node:fs';
import {
  collectIntegrationCapabilityFilterOptions,
  filterIntegrationProvidersByQuery,
} from '../src/app/system-manager/utils/integrationCenter';

const t = (key: string, fallback?: string) => {
  const labels: Record<string, string> = {
    'system.integrationCenter.capability.userSync': '用户同步',
    'system.integrationCenter.capability.loginAuth': '登录认证',
    'system.integrationCenter.capability.imNotification': 'IM通知',
    'system.integrationCenter.capability.imGroup': '群协作',
  };
  return labels[key] || fallback || key;
};
const zh = JSON.parse(readFileSync(new URL('../src/app/system-manager/locales/zh.json', import.meta.url), 'utf8'));
const en = JSON.parse(readFileSync(new URL('../src/app/system-manager/locales/en.json', import.meta.url), 'utf8'));

assert.equal(zh.system.integrationCenter.capability.imNotification, 'IM通知');
assert.equal(en.system.integrationCenter.capability.imNotification, 'IM Notification');

const providers = [
  {
    name: '飞书',
    description: '飞书接入',
    raw: {
      capabilities: [
        { key: 'login_auth' },
        { key: 'user_sync' },
        { key: 'im_notification' },
        { key: 'im_group' },
      ],
    },
  },
  {
    name: '微信',
    description: '微信接入',
    raw: { capabilities: [{ key: 'login_auth' }] },
  },
  {
    name: 'Active Directory',
    description: 'AD 接入',
    raw: { capabilities: [{ key: 'login_auth' }, { key: 'user_sync' }] },
  },
];

assert.deepEqual(
  collectIntegrationCapabilityFilterOptions(
    providers.map((item) => item.raw),
    t,
  ).map((item) => item.value),
  ['user_sync', 'login_auth', 'im_notification', 'im_group'],
);

assert.equal(filterIntegrationProvidersByQuery(providers, '').length, 3);
assert.deepEqual(
  filterIntegrationProvidersByQuery(providers, '飞书').map((item) => item.name),
  ['飞书'],
);
assert.deepEqual(
  filterIntegrationProvidersByQuery(providers, '群协作', [], t).map((item) => item.name),
  ['飞书'],
);
assert.deepEqual(
  filterIntegrationProvidersByQuery(providers, '登录认证 用户同步', [], t).map((item) => item.name),
  ['飞书', 'Active Directory'],
);
assert.deepEqual(
  filterIntegrationProvidersByQuery(providers, '', ['login_auth', 'user_sync']).map((item) => item.name),
  ['飞书', 'Active Directory'],
);
assert.deepEqual(
  filterIntegrationProvidersByQuery(providers, '', ['login_auth', 'im_group']).map((item) => item.name),
  ['飞书'],
);
assert.deepEqual(
  filterIntegrationProvidersByQuery(providers, 'AD', ['login_auth', 'user_sync']).map((item) => item.name),
  ['Active Directory'],
);
assert.equal(
  filterIntegrationProvidersByQuery(providers, '微信', ['im_group']).length,
  0,
);

console.log('integration center provider filter tests passed');
