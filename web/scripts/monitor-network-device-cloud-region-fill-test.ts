import assert from 'node:assert/strict';

import { DataMapper } from '../src/app/monitor/hooks/integration/useDataMapper';

// 网络设备实例接入:Switch/Router/Firewall/Loadbalance 对象名
// 必须从 node_ids 反查 nodeList 拿到 cloud_region_id 并补到 instance dict,
// 否则后端 _extract_network_device_identity_parts 抛
// "network device instance requires cloud_region and ip"。
const context = {
  config_type: ['huawei'],
  collect_type: 'snmp_huawei',
  collector: 'Telegraf',
  instance_type: 'switch',
  instance_id: '{{cloud_region}}_{{instance_type}}_snmp_huawei_{{ip}}',
  nodeList: [
    {
      id: 'node-1',
      value: 'node-1',
      name: 'edge-collector',
      ip: '10.0.0.5',
      // NodeSerializer 字段名是 cloud_region (ForeignKey PK 渲染),
      // 不是 cloud_region_id;故意只用 cloud_region 字段,
      // 验证 useDataMapper.ts 的 fallback 链。
      cloud_region: 42,
    },
    {
      id: 'node-2',
      value: 'node-2',
      name: 'core-collector',
      ip: '10.0.0.6',
      cloud_region: 7,
    },
  ],
  objectId: '100',
  tableColumns: [
    { name: 'node_ids' },
    { name: 'ip' },
    { name: 'instance_name' },
    { name: 'group_ids' },
  ],
};

const tableData = [
  {
    node_ids: ['node-2'],
    ip: '10.0.0.6',
    instance_name: 'sw-core-01',
    group_ids: [3],
  },
];

const result = DataMapper.transformAutoRequest({}, tableData, context);

// 断言 1:cloud_region_id 必须从 nodeList 反查得到,不能丢
assert.equal(
  result.instances[0].cloud_region_id,
  7,
  'cloud_region_id should be derived from nodeList[matching node_ids]'
);

// 断言 2:原有 ip / instance_name / node_ids 不被破坏
assert.deepEqual(result.instances[0].node_ids, ['node-2']);
assert.equal(result.instances[0].ip, '10.0.0.6');
assert.equal(result.instances[0].instance_name, 'sw-core-01');

// 断言 3:instance_id 仍走原 hashInstanceId 流程(已有行为,防止回归)
assert.ok(
  typeof result.instances[0].instance_id === 'string' &&
    result.instances[0].instance_id.length > 0,
  'instance_id should still be produced by hashInstanceId'
);

// 断言 4:node_ids 为字符串(单选)时也能反查
const singleSelect = DataMapper.transformAutoRequest(
  {},
  [{ node_ids: 'node-1', ip: '10.0.0.5', instance_name: 'edge', group_ids: [1] }],
  context
);
assert.equal(singleSelect.instances[0].cloud_region_id, 42);

// 断言 5:nodeList 缺失时不应崩,cloud_region_id 可空(后端兜底会再校验)
const noNodeListCtx = { ...context, nodeList: undefined };
const noNodeList = DataMapper.transformAutoRequest(
  {},
  [{ node_ids: ['node-1'], ip: '10.0.0.5', instance_name: 'edge', group_ids: [1] }],
  noNodeListCtx
);
assert.ok(
  noNodeList.instances[0].cloud_region_id === undefined ||
    noNodeList.instances[0].cloud_region_id === null
);

// 断言 6:若 node 项只有 cloud_region_id(老字段),也要兼容
const legacyCtx = {
  ...context,
  nodeList: [
    { id: 'node-3', value: 'node-3', name: 'legacy', ip: '10.0.0.7', cloud_region_id: 99 }
  ]
};
const legacy = DataMapper.transformAutoRequest(
  {},
  [{ node_ids: ['node-3'], ip: '10.0.0.7', instance_name: 'legacy', group_ids: [1] }],
  legacyCtx
);
assert.equal(legacy.instances[0].cloud_region_id, 99);

console.log('monitor-network-device-cloud-region-fill test passed');