import assert from 'node:assert/strict';
import {
  filterNetworkDeviceModels,
  isNetworkModel,
  extractDevicePorts,
  buildConnectPayload,
  buildBelongPayload,
  validateConnection,
  buildLinkFromConnection,
  relationshipIdFromEdgeId,
  nextFloatingPosition,
  extractOccupiedPortNames,
} from '../src/app/cmdb/(pages)/assetData/detail/relationships/networkTopo/topoEditingUtils';

// filterNetworkDeviceModels
assert.deepEqual(
  filterNetworkDeviceModels([
    { asst_id: 'belong', src_model_id: 'interface', dst_model_id: 'switch' },
    { asst_id: 'belong', src_model_id: 'interface', dst_model_id: 'router' },
    { asst_id: 'connect', src_model_id: 'interface', dst_model_id: 'interface' },
    { asst_id: 'belong', src_model_id: 'host', dst_model_id: 'rack' },
  ]),
  ['switch', 'router']
);
assert.equal(isNetworkModel('switch', ['switch', 'router']), true);
assert.equal(isNetworkModel('host', ['switch', 'router']), false);

// extractDevicePorts
assert.deepEqual(
  extractDevicePorts(
    [
      {
        model_asst_id: 'interface_belong_switch',
        inst_list: [{ _id: 11, inst_name: 'sw1-GE0/0/1' }],
      },
      { model_asst_id: 'switch_run_router', inst_list: [{ _id: 99, inst_name: 'x' }] },
    ],
    'switch'
  ),
  [{ id: '11', name: 'sw1-GE0/0/1' }]
);
assert.deepEqual(extractDevicePorts([], 'switch'), []);

// payloads
assert.deepEqual(buildConnectPayload('11', '22'), {
  model_asst_id: 'interface_connect_interface',
  src_model_id: 'interface',
  dst_model_id: 'interface',
  asst_id: 'connect',
  src_inst_id: 11,
  dst_inst_id: 22,
});
assert.deepEqual(buildBelongPayload('11', '5', 'switch'), {
  model_asst_id: 'interface_belong_switch',
  src_model_id: 'interface',
  dst_model_id: 'switch',
  asst_id: 'belong',
  src_inst_id: 11,
  dst_inst_id: 5,
});

// validateConnection
const modelOf = (id: string) =>
  ({ a: 'switch', b: 'router', c: 'host' } as Record<string, string>)[id];
const nets = ['switch', 'router'];
assert.deepEqual(
  validateConnection({ sourceId: 'a', targetId: 'b', modelOf, networkModels: nets }),
  { ok: true }
);
assert.equal(
  validateConnection({ sourceId: 'a', targetId: 'a', modelOf, networkModels: nets }).reason,
  'self'
);
assert.equal(
  validateConnection({ sourceId: 'a', targetId: 'c', modelOf, networkModels: nets }).reason,
  'not_network'
);

// buildLinkFromConnection
assert.deepEqual(
  buildLinkFromConnection({
    relationshipId: '77',
    sourceDevice: 'a',
    targetDevice: 'b',
    sourcePortName: 'sw1-GE0/0/1',
    targetPortName: 'r1-Eth1',
  }),
  {
    relationship_id: '77',
    source_device: 'a',
    source_inst_name: 'sw1-GE0/0/1',
    target_device: 'b',
    target_inst_name: 'r1-Eth1',
    asst_id: 'connect',
  }
);

// extractOccupiedPortNames: 取出指定设备已占用的端口名（source/target 两侧都算）
{
  const links = [
    { source_device: '220', source_inst_name: 'sw-GE0/0/7', target_device: '222', target_inst_name: 'r-Eth1' },
    { source_device: '300', source_inst_name: 'x-1', target_device: '220', target_inst_name: 'sw-GE0/0/8' },
    { source_device: '999', source_inst_name: 'y-1', target_device: '888', target_inst_name: 'y-2' },
  ];
  const occ = extractOccupiedPortNames(links, '220');
  assert.equal(occ.has('sw-GE0/0/7'), true); // 作为 source
  assert.equal(occ.has('sw-GE0/0/8'), true); // 作为 target
  assert.equal(occ.has('r-Eth1'), false); // 别的设备的端口
  assert.equal(occ.size, 2);
  assert.equal(extractOccupiedPortNames([], '220').size, 0);
}

// relationshipIdFromEdgeId
assert.equal(relationshipIdFromEdgeId('edge-123'), '123');
assert.equal(relationshipIdFromEdgeId('123'), '123');

// nextFloatingPosition determinism
const p0 = nextFloatingPosition(0);
assert.ok(Math.abs(p0.x - 320) < 1e-6 && Math.abs(p0.y) < 1e-6);
assert.notDeepEqual(nextFloatingPosition(1), nextFloatingPosition(0));

console.log('cmdb-network-topo-editing-test passed');
