/**
 * 主机采集凭据可空提示与 SSH 用户/密码非必填星号契约。
 *
 * Run: node --import tsx scripts/cmdb-host-credential-optional-test.ts
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const root = process.cwd();
const hostTask = readFileSync(
  resolve(root, 'src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/components/hostTask.tsx'),
  'utf8',
);
const credentialEditor = readFileSync(
  resolve(root, 'src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/components/credentialPoolEditor.tsx'),
  'utf8',
);
const baseTask = readFileSync(
  resolve(root, 'src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/components/baseTask.tsx'),
  'utf8',
);
const zh = JSON.parse(
  readFileSync(resolve(root, 'src/app/cmdb/locales/zh.json'), 'utf8'),
);

assert.match(
  hostTask,
  /hostCredentialOptionalTip/,
  '主机采集表单应展示凭据可空提示',
);
assert.match(
  credentialEditor,
  /required=\{shape !== 'ssh'\}/,
  'SSH 凭据的用户/密码不应显示必填星号',
);
assert.match(
  baseTask,
  /IP_RANGE_CYCLE_HINT_THRESHOLD/,
  'IP 范围字段应在地址数过大时展示周期提示',
);
assert.match(
  baseTask,
  /ipRangeCycleHint/,
  'IP 范围周期提示文案 key 应存在',
);

assert.equal(
  typeof zh.Collection.hostCredentialOptionalTip,
  'string',
);
assert.equal(
  typeof zh.Collection.ipRangeCycleHint,
  'string',
);
assert.match(
  zh.Collection.credentialHelp.instruction.ssh,
  /Agent|可不填/,
);

console.log('CMDB 主机凭据可空与大网段提示契约测试通过');
