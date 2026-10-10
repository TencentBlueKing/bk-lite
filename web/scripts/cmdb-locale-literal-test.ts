import * as assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

import { IntlMessageFormat } from 'intl-messageformat';

const here = dirname(fileURLToPath(import.meta.url));
const webRoot = resolve(here, '..');

type Nested = { [key: string]: string | Nested };

const flatten = (obj: Nested, prefix = ''): Record<string, string> =>
  Object.keys(obj).reduce((acc: Record<string, string>, key) => {
    const value = obj[key];
    const prefixedKey = prefix ? `${prefix}.${key}` : key;
    if (typeof value === 'string') {
      acc[prefixedKey] = value;
    } else {
      Object.assign(acc, flatten(value, prefixedKey));
    }
    return acc;
  }, {});

const load = (relativePath: string) =>
  flatten(JSON.parse(readFileSync(resolve(webRoot, relativePath), 'utf8')) as Nested);

const messages = {
  zh: { ...load('src/locales/zh.json'), ...load('src/app/cmdb/locales/zh.json') },
  en: { ...load('src/locales/en.json'), ...load('src/app/cmdb/locales/en.json') },
};

const expected: Record<string, { zh: string; en: string }> = {
  'common.previousPage': { zh: '上一页', en: 'Previous' },
  'common.nextPage': { zh: '下一页', en: 'Next' },
  'common.loadFailed': { zh: '加载失败', en: 'Failed to load' },
  'common.selectTip': { zh: '请选择', en: 'Please select' },
  'Model.action': { zh: '操作', en: 'Action' },
  'Collection.everyMinuteMin': { zh: '执行间隔最小为1分钟', en: 'Minimum execution interval is 1 minute' },
  'Collection.api_version': { zh: 'API 版本', en: 'API version' },
  'Collection.smartxTask.source': { zh: '认证来源', en: 'Authentication source' },
  'Collection.fusioncomputeTask.userType': { zh: '用户类型', en: 'User type' },
  'Collection.azureTask.subscriptionId': { zh: '订阅 ID', en: 'Subscription ID' },
  'Collection.platformApiTask.identityPort': { zh: '认证服务端口', en: 'Identity service port' },
};

for (const [key, copy] of Object.entries(expected)) {
  assert.equal(messages.zh[key], copy.zh, `zh ${key}`);
  assert.equal(messages.en[key], copy.en, `en ${key}`);
}

const formatted = {
  'CustomReporting.curlHintHost': {
    zh: '把 <CMDB_HOST> 换成 CMDB 后端地址（本地默认 localhost:8011，生产填后端域名或网关）。',
    en: 'Replace <CMDB_HOST> with the CMDB backend address (localhost:8011 locally; use the backend domain or gateway in production).',
  },
  'CustomReporting.curlHintToken': {
    zh: '把 <token> 换成任务凭证 token，把实例里的 <字段> 占位替换成真实值后即可执行。',
    en: 'Replace <token> with the task credential token and each <field> placeholder with an actual value before running.',
  },
};

for (const [key, copy] of Object.entries(formatted)) {
  for (const locale of ['zh', 'en'] as const) {
    const text = new IntlMessageFormat(messages[locale][key], locale).format({}) as string;
    assert.equal(text, copy[locale], `${locale} ${key}`);
  }
}

console.log('cmdb locale literal test passed');
