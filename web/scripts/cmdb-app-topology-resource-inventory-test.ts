import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {
  filterResourceGroups,
} from '../src/app/cmdb/(pages)/assetData/detail/relationships/applicationResourceOverview/resourceInventory';

const groups = [
  {
    model_id: 'application',
    model_name: '应用',
    columns: ['inst_name', 'owner'],
    column_defs: [
      { key: 'inst_name', title: '实例名称' },
      { key: 'owner', title: '负责人' },
    ],
    count: 2,
    items: [
      { inst_name: 'ops-portal', owner: '张备份', inst_uuid: 'u1', model_id: 'application' },
      { inst_name: 'pay-svc', owner: '李运维', inst_uuid: 'u2', model_id: 'application' },
    ],
  },
  {
    model_id: 'host',
    model_name: '主机',
    columns: ['inst_name', 'ip_addr'],
    column_defs: [
      { key: 'inst_name', title: '实例名称' },
      { key: 'ip_addr', title: 'IP' },
    ],
    count: 1,
    items: [
      { inst_name: 'host-web-01', ip_addr: '10.0.0.1', inst_uuid: 'h1', model_id: 'host' },
    ],
  },
];

assert.equal(filterResourceGroups(groups, '').length, 2);
assert.equal(filterResourceGroups(groups, '   ')[0].count, 2);

const byOwner = filterResourceGroups(groups, '张备份');
assert.equal(byOwner.length, 1);
assert.equal(byOwner[0].model_id, 'application');
assert.deepEqual(byOwner[0].items.map((item) => item.inst_name), ['ops-portal']);

const byIp = filterResourceGroups(groups, '10.0.0.1');
assert.equal(byIp.length, 1);
assert.equal(byIp[0].model_id, 'host');

assert.equal(filterResourceGroups(groups, 'no-such').length, 0);

const overviewSrc = fs.readFileSync(
  path.resolve('src/app/cmdb/(pages)/assetData/detail/relationships/applicationResourceOverview/index.tsx'),
  'utf8'
);
assert.match(overviewSrc, /filterResourceGroups/);
assert.match(overviewSrc, /resourceSearchPlaceholder/);
assert.match(overviewSrc, /instanceNameLink/);
assert.match(overviewSrc, /buildBaseInfoPath/);

console.log('cmdb-app-topology-resource-inventory test passed');
