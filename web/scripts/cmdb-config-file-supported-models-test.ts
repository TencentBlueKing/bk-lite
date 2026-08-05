/**
 * 配置文件详情 Tab 模型白名单与文案分流契约。
 *
 * Run: node --import tsx scripts/cmdb-config-file-supported-models-test.ts
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import {
  CONFIG_FILE_SUPPORTED_MODEL_IDS,
  NETWORK_CONFIG_FILE_MODEL_IDS,
  isConfigFileSupportedModel,
  isNetworkConfigFileModel,
} from '../src/app/cmdb/constants/configFile';

assert.deepEqual(
  [...CONFIG_FILE_SUPPORTED_MODEL_IDS],
  ['host', 'switch', 'router', 'firewall', 'loadbalance'],
);
assert.deepEqual(
  [...NETWORK_CONFIG_FILE_MODEL_IDS],
  ['switch', 'router', 'firewall', 'loadbalance'],
);

assert.equal(isConfigFileSupportedModel('host'), true);
assert.equal(isNetworkConfigFileModel('host'), false);
assert.equal(isNetworkConfigFileModel('switch'), true);
assert.equal(isNetworkConfigFileModel('router'), true);
assert.equal(isNetworkConfigFileModel('firewall'), true);
assert.equal(isNetworkConfigFileModel('loadbalance'), true);
assert.equal(isConfigFileSupportedModel('mysql'), false);

const page = readFileSync(
  resolve(process.cwd(), 'src/app/cmdb/(pages)/assetData/detail/configFiles/page.tsx'),
  'utf8',
);
assert.match(page, /descriptionNetwork/);
assert.match(page, /isNetworkConfigFileModel/);

const zh = JSON.parse(
  readFileSync(resolve(process.cwd(), 'src/app/cmdb/locales/zh.json'), 'utf8'),
);
assert.equal(typeof zh.ConfigFile.description, 'string');
assert.equal(typeof zh.ConfigFile.descriptionNetwork, 'string');
assert.match(zh.ConfigFile.description, /主机/);
assert.match(zh.ConfigFile.descriptionNetwork, /网络设备/);

console.log('CMDB 配置文件支持模型白名单测试通过');
