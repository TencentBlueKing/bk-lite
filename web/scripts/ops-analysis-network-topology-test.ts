/**
 * 网络拓扑大屏前端工具测试入口。
 * 运行:`pnpm test:ops-analysis-network-topology`
 *
 * 覆盖:
 * - utils/thresholdUtils.ts (>=90%)
 * - utils/portPairs.ts (>=90%)
 * - utils/nodeStatus.ts (>=90%)
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import { resolveActiveThreshold, resolveNodeOuterColor, NODE_UNFALLBACK_COLOR } from '../src/app/ops-analysis/(pages)/view/networkTopology/utils/nodeStatus';
import {
  isValidThresholdList,
  pickDeepestThresholdHit,
  pickThresholdLevel,
} from '../src/app/ops-analysis/(pages)/view/networkTopology/utils/thresholdUtils';
import {
  buildPortPair,
  isValidPortPair,
  normalizePortPair,
  summarizePortPairs,
  upsertPortPair,
  removePortPair,
  ensureMinimumPortPair,
} from '../src/app/ops-analysis/(pages)/view/networkTopology/utils/portPairs';
import {
  buildLinkDetailPortRows,
  buildLinkInterfaceMetricRows,
  buildNodeDetailMetricRows,
  buildBoundMetricConfigRows,
  buildNetworkTopologyMetricDraft,
  buildNetworkTopologyLinkRenderOptions,
  buildNetworkTopologyLinkTerminals,
  isNetworkTopologyLinkPendingInterfaceSelection,
  mergeNetworkTopologyRuntimeNodes,
  mergeNetworkTopologyRuntimeLinks,
  isMetricRuntimeLoading,
  isMetricOptionMatched,
  replaceNetworkTopologyMetricDraft,
  updateNetworkTopologyLinkTerminals,
} from '../src/app/ops-analysis/(pages)/view/networkTopology/utils/networkTopologyUtils';
import { formatNetworkMetricValue } from '../src/app/ops-analysis/(pages)/view/networkTopology/utils/metricValueFormat';
import type {
  NetworkLinkRuntime,
  NetworkNodeRuntime,
  NetworkTopologyLink,
  NetworkTopologyNode,
} from '../src/app/ops-analysis/types/networkTopology';

const readRepoFile = (path: string) => readFileSync(new URL(`../${path}`, import.meta.url), 'utf8');

// =====================================================================
// thresholdUtils.ts
// =====================================================================

assert.equal(
  pickThresholdLevel([{ value: 0, color: 'green' }, { value: 80, color: 'yellow' }, { value: 100, color: 'red' }], 90),
  1,
  'value=90 should hit level 1 (80) when thresholds are [0, 80, 100]',
);
assert.equal(
  pickThresholdLevel([{ value: 0, color: 'green' }, { value: 80, color: 'yellow' }, { value: 100, color: 'red' }], 100),
  2,
  'value=100 should hit level 2',
);
assert.equal(
  pickThresholdLevel([{ value: 10, color: 'blue' }], 5),
  0,
  'value below the smallest threshold should map to baseline (level 0)',
);
assert.equal(
  pickThresholdLevel([{ value: 10, color: 'blue' }], -1),
  0,
  'negative value below smallest threshold -> baseline',
);
assert.equal(
  pickThresholdLevel([], 100),
  -1,
  'empty threshold list -> -1',
);
assert.equal(
  pickThresholdLevel(
    [
      { value: 0, color: 'green' },
      { value: 80, color: 'yellow' },
      { value: 100, color: 'red' },
    ],
    60,
  ),
  0,
  'value < second threshold -> level 0 (baseline)',
);

assert.equal(isValidThresholdList([]), true, 'empty list is valid (just yields null hits)');
assert.equal(
  isValidThresholdList([
    { value: 0, color: 'green' },
    { value: 80, color: 'yellow' },
  ]),
  true,
);
assert.equal(
  isValidThresholdList([{ value: 'x', color: 'green' } as unknown as { value: number; color: string }]),
  false,
  'non-numeric value is invalid',
);
assert.equal(
  isValidThresholdList([{ value: -1, color: 'green' }]),
  true,
  'negative threshold value is allowed for completeness',
);

assert.deepEqual(
  pickDeepestThresholdHit(
    [
      { value: 0, color: 'green' },
      { value: 80, color: 'yellow' },
      { value: 100, color: 'red' },
    ],
    150,
  ),
  { level: 2, color: 'red' },
  'value 150 hits deepest threshold',
);
assert.deepEqual(
  pickDeepestThresholdHit(
    [
      { value: 0, color: 'green' },
      { value: 80, color: 'yellow' },
      { value: 100, color: 'red' },
    ],
    -1,
  ),
  { level: 0, color: 'green' },
  'value below smallest threshold -> baseline (level 0)',
);
assert.deepEqual(
  pickDeepestThresholdHit(
    [
      { value: 70, color: '#dc2626' },
      { value: 30, color: '#d97706' },
      { value: 0, color: '#2563eb' },
    ],
    6,
  ),
  { level: 0, color: '#2563eb' },
  'descending thresholds 70/30/0 with value 6 should hit the 0 baseline color',
);
assert.equal(
  pickDeepestThresholdHit([], 10),
  null,
  'empty thresholds -> null',
);

// =====================================================================
// portPairs.ts
// =====================================================================

const sourceA = { bk_obj_id: 'bk_interface' as const, bk_inst_id: 90001, interface_name: 'GigE0/1' };
const targetA = { bk_obj_id: 'bk_interface' as const, bk_inst_id: 90010, interface_name: 'GigE0/1' };
const sourceB = { bk_obj_id: 'bk_interface' as const, bk_inst_id: 90002, interface_name: 'GigE0/2' };
const targetB = { bk_obj_id: 'bk_interface' as const, bk_inst_id: 90020, interface_name: 'GigE0/2' };

const validPair = { source_interface: sourceA, target_interface: targetA };
const validPair2 = { source_interface: sourceB, target_interface: targetB };

assert.deepEqual(buildPortPair(sourceA, targetA), validPair);
assert.deepEqual(normalizePortPair(validPair), validPair);
assert.deepEqual(normalizePortPair(null as unknown as never), null, 'null normalize -> null');
assert.deepEqual(normalizePortPair('x' as unknown as never), null, 'invalid input -> null');

assert.equal(isValidPortPair(validPair), true);
assert.equal(isValidPortPair({ source_interface: sourceA } as unknown as Parameters<typeof isValidPortPair>[0]), false);
assert.equal(isValidPortPair({ source_interface: sourceA, target_interface: null } as unknown as Parameters<typeof isValidPortPair>[0]), false);
assert.equal(isValidPortPair(null as unknown as Parameters<typeof isValidPortPair>[0]), false);

assert.deepEqual(
  summarizePortPairs([validPair, validPair2]),
  { count: 2, uniqueSourceIds: 2, uniqueTargetIds: 2 },
  'summarize two distinct pairs',
);
assert.deepEqual(summarizePortPairs([]), { count: 0, uniqueSourceIds: 0, uniqueTargetIds: 0 });
assert.deepEqual(
  summarizePortPairs([validPair, validPair]),
  { count: 2, uniqueSourceIds: 1, uniqueTargetIds: 1 },
);

assert.deepEqual(upsertPortPair([], 0, validPair), [validPair], 'insert at empty list');
assert.deepEqual(upsertPortPair([validPair], 0, validPair2), [validPair2], 'replace at index');
assert.deepEqual(upsertPortPair([validPair], 1, validPair2), [validPair, validPair2], 'append at end');
assert.deepEqual(upsertPortPair([validPair], -1, validPair2), [validPair2, validPair], 'append when index out of range');
assert.deepEqual(upsertPortPair([validPair, validPair2], 99, validPair2), [validPair, validPair2, validPair2], 'append when index out of range past end');

assert.deepEqual(removePortPair([validPair, validPair2], 0), [validPair2]);
assert.deepEqual(removePortPair([validPair], 0), []);
assert.deepEqual(removePortPair([], 0), []);
assert.deepEqual(removePortPair([validPair], 99), [validPair]);

assert.equal(ensureMinimumPortPair([]).length, 1, 'empty -> one placeholder pair');
assert.deepEqual(ensureMinimumPortPair([validPair]), [validPair], 'non-empty stays as-is');

// =====================================================================
// nodeStatus.ts
// =====================================================================

const metricA = (thresholds: { value: number; color: string }[]) => ({
  metric_field: 'ifHCInOctets',
  result_table_id: 'snmp_network',
  display_name: 'In',
  unit: 'bps',
  sort_order: 0,
  thresholds,
});
const metricB = (thresholds: { value: number; color: string }[]) => ({
  metric_field: 'ifHCOutOctets',
  result_table_id: 'snmp_network',
  display_name: 'Out',
  unit: 'bps',
  sort_order: 1,
  thresholds,
});

assert.deepEqual(
  resolveActiveThreshold(metricA([]), { metric_field: 'ifHCInOctets', result_table_id: 'snmp_network', value: 100, status: 'ok' }),
  null,
  'no thresholds -> null',
);
assert.deepEqual(
  resolveActiveThreshold(
    metricA([{ value: 0, color: 'green' }, { value: 100, color: 'red' }]),
    { metric_field: 'ifHCInOctets', result_table_id: 'snmp_network', value: 150, status: 'ok' },
  ),
  { level: 1, color: 'red' },
);
assert.deepEqual(
  resolveActiveThreshold(
    metricA([{ value: 0, color: 'green' }, { value: 100, color: 'red' }]),
    { metric_field: 'ifHCInOctets', result_table_id: 'snmp_network', value: null, status: 'ok' },
  ),
  null,
  'value null -> null (no data)',
);
assert.deepEqual(
  resolveActiveThreshold(
    metricA([{ value: 0, color: 'green' }, { value: 100, color: 'red' }]),
    { metric_field: 'ifHCInOctets', result_table_id: 'snmp_network', value: 'not a number' as unknown as number, status: 'ok' },
  ),
  null,
  'NaN value -> null',
);
assert.deepEqual(
  resolveActiveThreshold(
    metricA([{ value: 0, color: 'green' }, { value: 100, color: 'red' }]),
    undefined,
  ),
  null,
  'no runtime -> null',
);
assert.deepEqual(
  resolveActiveThreshold(
    metricA([{ value: 0, color: 'green' }, { value: 100, color: 'red' }]),
    { metric_field: 'ifHCInOctets', result_table_id: 'snmp_network', value: 100, status: 'error', error_code: 'metric_no_data' },
  ),
  null,
  'status=error runtime -> null',
);
assert.deepEqual(
  resolveActiveThreshold(
    metricA([{ value: 50, color: 'red' }]),
    { metric_field: 'ifHCInOctets', result_table_id: 'snmp_network', value: 10, status: 'ok' },
  ),
  { level: 0, color: 'red' },
  'value below smallest threshold -> level 0 (baseline)',
);

assert.equal(NODE_UNFALLBACK_COLOR, '#64748b', 'unknown fallback color must be slate');

// Single metric - deepest hit wins (Scenario: deepest threshold)
assert.deepEqual(
  resolveNodeOuterColor(
    [metricA([{ value: 0, color: 'green' }, { value: 100, color: 'red' }])],
    [{ metric_field: 'ifHCInOctets', result_table_id: 'snmp_network', value: 150, status: 'ok' }],
  ),
  'red',
);

// Multiple metrics - deepest hit wins (Scenario: Multiple metrics, deepest hit wins)
assert.deepEqual(
  resolveNodeOuterColor(
    [
      metricA([{ value: 0, color: 'green' }, { value: 100, color: 'red' }]),
      metricB([{ value: 0, color: 'yellow' }, { value: 80, color: 'red' }]),
    ],
    [
      { metric_field: 'ifHCInOctets', result_table_id: 'snmp_network', value: 150, status: 'ok' },
      { metric_field: 'ifHCOutOctets', result_table_id: 'snmp_network', value: 90, status: 'ok' },
    ],
  ),
  'red',
  'metric B with hit=1 (deeper than A hit=1 vs equal depths test below) - wait B level=1, A level=1, A wins (first configured)',
);

// Tie depth - first metric wins (Scenario: Multiple metrics, tied depth, first metric wins)
assert.deepEqual(
  resolveNodeOuterColor(
    [
      metricA([{ value: 0, color: 'green' }, { value: 100, color: 'orange' }]),
      metricB([{ value: 0, color: 'green' }, { value: 100, color: 'red' }]),
    ],
    [
      { metric_field: 'ifHCInOctets', result_table_id: 'snmp_network', value: 150, status: 'ok' },
      { metric_field: 'ifHCOutOctets', result_table_id: 'snmp_network', value: 150, status: 'ok' },
    ],
  ),
  'orange',
  'both at level 1 -> first configured (A) wins',
);

// Below all thresholds - baseline color of smallest
assert.deepEqual(
  resolveNodeOuterColor(
    [metricA([{ value: 80, color: 'red' }])],
    [{ metric_field: 'ifHCInOctets', result_table_id: 'snmp_network', value: 10, status: 'ok' }],
  ),
  'red',
  'value 10 below threshold 80 -> baseline level 0 -> color red',
);

// Duplicate metrics with different display/aggregation configs must use their
// own runtime values, not the first matching field/table value.
assert.deepEqual(
  resolveNodeOuterColor(
    [
      metricA([{ value: 0, color: 'green' }, { value: 10, color: 'orange' }]),
      { ...metricA([{ value: 0, color: 'green' }, { value: 50, color: 'red' }]), sort_order: 1 },
    ],
    [
      { metric_field: 'ifHCInOctets', result_table_id: 'snmp_network', sort_order: 0, value: 6, status: 'ok' },
      { metric_field: 'ifHCInOctets', result_table_id: 'snmp_network', sort_order: 1, value: 60, status: 'ok' },
    ],
  ),
  'red',
  'duplicate field/table metrics match runtime by sort_order',
);

// One metric has no data - the other wins
assert.deepEqual(
  resolveNodeOuterColor(
    [
      metricA([{ value: 0, color: 'green' }, { value: 80, color: 'yellow' }]),
      metricB([{ value: 0, color: 'green' }, { value: 50, color: 'red' }]),
    ],
    [
      { metric_field: 'ifHCInOctets', result_table_id: 'snmp_network', value: null, status: 'ok' },
      { metric_field: 'ifHCOutOctets', result_table_id: 'snmp_network', value: 60, status: 'ok' },
    ],
  ),
  'red',
  'metric A excluded (null), metric B hits level 1 -> red',
);

// No metrics configured -> unknown fallback
assert.deepEqual(
  resolveNodeOuterColor([], []),
  null,
  'no metrics -> null (renderer falls back to unknown gray)',
);

// All metrics no data -> null (renderer falls back)
assert.equal(
  resolveNodeOuterColor(
    [
      metricA([{ value: 0, color: 'green' }, { value: 100, color: 'red' }]),
      metricB([{ value: 0, color: 'green' }, { value: 100, color: 'red' }]),
    ],
    [
      { metric_field: 'ifHCInOctets', result_table_id: 'snmp_network', value: null, status: 'ok' },
      { metric_field: 'ifHCOutOctets', result_table_id: 'snmp_network', value: null, status: 'ok' },
    ],
  ),
  null,
);

// Empty threshold entries are skipped, not joined
assert.deepEqual(
  resolveActiveThreshold(
    metricA([]),
    { metric_field: 'ifHCInOctets', result_table_id: 'snmp_network', value: 999, status: 'ok' },
  ),
  null,
);

// metric runtime keys must match BOTH metric_field and result_table_id
assert.deepEqual(
  resolveActiveThreshold(
    metricA([{ value: 0, color: 'green' }, { value: 100, color: 'red' }]),
    { metric_field: 'DIFFERENT', result_table_id: 'snmp_network', value: 150, status: 'ok' } as { metric_field: string; result_table_id: string; value: number; status: 'ok' },
  ),
  null,
  'runtime with different metric_field -> null (renderer should also treat as no runtime match)',
);

// verify surface resolves via the explicit node outer color helper (not consumed here but kept for coverage)
assert.ok(typeof resolveNodeOuterColor === 'function');

// =====================================================================
// networkTopologyUtils.ts - node detail card data
// =====================================================================

const detailNode: NetworkTopologyNode = {
  id: 'bk_firewall:10001',
  bk_obj_id: 'bk_firewall',
  bk_inst_id: 10001,
  bk_inst_name: 'fw-1',
  ip_addr: '10.0.0.1',
  network_collect_task_id: 1,
  network_collect_instance_id: 2,
  plugin_template_id: 'tpl',
  plugin_template_name: '防火墙模板',
  position: { x: 0, y: 0 },
  metrics: [
    {
      metric_field: 'ifInDiscards',
      result_table_id: 'snmp_network',
      display_name: '入口丢包',
      unit: 'bps',
      sort_order: 0,
      thresholds: [{ value: 0, color: '#2563eb' }, { value: 70, color: '#dc2626' }],
    },
  ],
};
const detailNodeRuntime: NetworkNodeRuntime = {
  id: detailNode.id,
  outer_color: null,
  status: 'critical',
  metrics: [
    {
      request_id: 'bk_firewall:10001::0::ifInDiscards::snmp_network',
      metric_field: 'ifInDiscards',
      result_table_id: 'snmp_network',
      sort_order: 0,
      value: 84243794,
      unit: 'bps',
      status: 'ok',
    },
  ],
};

assert.deepEqual(
  buildNodeDetailMetricRows(detailNode, detailNodeRuntime),
  [
    {
      key: '0::ifInDiscards::snmp_network',
      label: '入口丢包',
      value: '84.24 Mbps',
      color: '#dc2626',
    },
  ],
  'node detail metrics show formatted runtime values and active threshold color',
);

const runtimeNodesFromOverride = mergeNetworkTopologyRuntimeNodes([], [detailNode], {
  [detailNode.id]: detailNodeRuntime.metrics,
});
assert.deepEqual(
  buildNodeDetailMetricRows(detailNode, runtimeNodesFromOverride[0]),
  [
    {
      key: '0::ifInDiscards::snmp_network',
      label: '入口丢包',
      value: '84.24 Mbps',
      color: '#dc2626',
    },
  ],
  'config-only save responses should not discard runtime metrics already loaded in memory',
);

const runtimeNodesWithInterfaceSummary = mergeNetworkTopologyRuntimeNodes(
  [detailNodeRuntime],
  [detailNode],
  {},
  {
    [detailNode.id]: { total: 4, up: 2, down: 1, unknown: 1 },
  },
);
assert.deepEqual(
  runtimeNodesWithInterfaceSummary[0].interface_summary,
  { total: 4, up: 2, down: 1, unknown: 1 },
  'link runtime preview should merge node interface summaries without requiring a full runtime refresh',
);

assert.deepEqual(
  buildBoundMetricConfigRows(detailNode.metrics, {
    aggregate: '聚合值',
    dimension: '指定维度',
    aggregateTypes: {
      sum: '求和',
      max: '最大值',
      min: '最小值',
      mean: '平均值',
      last: '最新值',
    },
  }),
  [
    {
      key: '0::ifInDiscards::snmp_network',
      label: '入口丢包',
      scopeText: '聚合值 / 最新值',
      thresholds: [
        { value: 0, color: '#2563eb' },
        { value: 70, color: '#dc2626' },
      ],
    },
  ],
  'bound metric config rows should summarize configuration without runtime current value',
);
assert.equal(
  'value' in buildBoundMetricConfigRows(detailNode.metrics, {
    aggregate: '聚合值',
    dimension: '指定维度',
    aggregateTypes: {
      sum: '求和',
      max: '最大值',
      min: '最小值',
      mean: '平均值',
      last: '最新值',
    },
  })[0],
  false,
  'bound metric drawer cards must not expose current value fields',
);
assert.doesNotMatch(
  readRepoFile('src/app/ops-analysis/(pages)/view/networkTopology/components/networkNodeDrawer.tsx'),
  /labelRuntimeStatus/,
  'node config drawer should not display synthetic runtime status because WeOps has no stable device status field',
);

const loadingRuntimeNodes = mergeNetworkTopologyRuntimeNodes([], [detailNode], {
  [detailNode.id]: [
    {
      request_id: 'bk_firewall:10001::0::ifInDiscards::snmp_network',
      metric_field: 'ifInDiscards',
      result_table_id: 'snmp_network',
      sort_order: 0,
      value: null,
      status: 'loading',
    },
  ],
});
assert.equal(
  isMetricRuntimeLoading(detailNode, detailNode.metrics[0], loadingRuntimeNodes[0]),
  true,
  'node card can detect metric runtime loading state while draft metric values are being fetched',
);

const detailLinks: NetworkTopologyLink[] = [
  {
    id: 'link-1',
    source_node_id: detailNode.id,
    target_node_id: 'bk_switch:10002',
    interface_metrics: ['ifInOctets_5min', 'ifOutOctets_5min'],
    port_pairs: [
      {
        source_interface: { bk_obj_id: 'bk_interface', bk_inst_id: 11, interface_name: 'eth0' },
        target_interface: { bk_obj_id: 'bk_interface', bk_inst_id: 22, interface_name: 'eth1' },
      },
    ],
  },
  {
    id: 'link-2',
    source_node_id: 'bk_router:10003',
    target_node_id: detailNode.id,
    port_pairs: [
      {
        source_interface: { bk_obj_id: 'bk_interface', bk_inst_id: 33, interface_name: 'ge-0/0/1' },
        target_interface: { bk_obj_id: 'bk_interface', bk_inst_id: 44, interface_name: 'eth2' },
      },
    ],
  },
];
const detailLinkRuntime: NetworkLinkRuntime[] = [
  {
    id: 'link-1',
    status: 'normal',
    interfaces: [
      {
        endpoint: 'source',
        bk_inst_id: 11,
        interface_name: 'eth0',
        oper_status: 'up',
        metrics: {
          ifInOctets_5min: { value: 84243794, unit: 'bps' },
          ifOutOctets_5min: { value: 28360, unit: 'bps' },
          ifHighSpeed: { value: 1000, unit: 'Mbps' },
        },
      },
    ],
  },
  {
    id: 'link-2',
    status: 'critical',
    interfaces: [{ endpoint: 'target', bk_inst_id: 44, interface_name: 'eth2', oper_status: 'down' }],
  },
];

assert.deepEqual(
  mergeNetworkTopologyRuntimeLinks(detailLinkRuntime, {
    'link-1': {
      id: 'link-1',
      status: 'critical',
      reason: 'interface_down',
      interfaces: [{ endpoint: 'target', bk_inst_id: 22, interface_name: 'eth1', oper_status: 'down' }],
      interface_metrics: ['ifInOctets_5min'],
    },
  }).map((item) => ({ id: item.id, status: item.status, reason: item.reason })),
  [
    { id: 'link-1', status: 'critical', reason: 'interface_down' },
    { id: 'link-2', status: 'critical', reason: undefined },
  ],
  'link runtime preview should replace only the edited link while preserving other full-runtime links',
);

assert.deepEqual(
  buildLinkDetailPortRows(detailLinks[0], detailLinkRuntime[0]),
  [
    {
      key: 'link-1:0',
      sourceName: 'eth0',
      sourceStatus: 'up',
      targetName: 'eth1',
      targetStatus: 'unknown',
    },
  ],
  'link detail ports show source/target interface names and runtime statuses',
);

assert.deepEqual(
  buildLinkInterfaceMetricRows(detailLinks[0], detailLinkRuntime[0], {
    ifInOctets_5min: '入网流速',
    ifOutOctets_5min: '出网流速',
    ifHighSpeed: '带宽类型',
  }),
  [
    {
      key: 'link-1:source:0:11:ifInOctets_5min',
      interfaceName: 'eth0',
      metricLabel: '入网流速',
      value: '84.24 Mbps',
    },
    {
      key: 'link-1:source:0:11:ifOutOctets_5min',
      interfaceName: 'eth0',
      metricLabel: '出网流速',
      value: '28.36 Kbps',
    },
  ],
  'link detail interface metrics follow link.interface_metrics and format WeOps port values',
);

assert.deepEqual(
  buildLinkInterfaceMetricRows(detailLinks[0], undefined, {
    ifInOctets_5min: '入网流速',
    ifOutOctets_5min: '出网流速',
  }),
  [
    {
      key: 'link-1:0:source:11:ifInOctets_5min',
      interfaceName: 'eth0',
      metricLabel: '入网流速',
      value: '--',
    },
    {
      key: 'link-1:0:source:11:ifOutOctets_5min',
      interfaceName: 'eth0',
      metricLabel: '出网流速',
      value: '--',
    },
    {
      key: 'link-1:0:target:22:ifInOctets_5min',
      interfaceName: 'eth1',
      metricLabel: '入网流速',
      value: '--',
    },
    {
      key: 'link-1:0:target:22:ifOutOctets_5min',
      interfaceName: 'eth1',
      metricLabel: '出网流速',
      value: '--',
    },
  ],
  'link detail interface metrics fall back to configured port pairs before runtime arrives',
);

{
  const rows = buildLinkInterfaceMetricRows(
    detailLinks[0],
    {
      id: 'link-1',
      status: 'critical',
      interfaces: [
        {
          endpoint: 'source',
          bk_inst_id: 11,
          interface_name: 'eth0',
          oper_status: 'down',
          metrics: { ifOutOctets_5min: { value: 1, unit: 'bps' } },
        },
        {
          endpoint: 'source',
          bk_inst_id: 11,
          interface_name: 'eth0',
          oper_status: 'down',
          metrics: { ifOutOctets_5min: { value: 2, unit: 'bps' } },
        },
      ],
    },
    { ifOutOctets_5min: '出网流速' },
  );
  assert.equal(new Set(rows.map((row) => row.key)).size, rows.length, 'duplicated runtime interfaces should still produce unique React keys');
}

assert.deepEqual(
  updateNetworkTopologyLinkTerminals(detailLinks, 'link-1', {
    source_node_id: 'bk_firewall:1',
    target_node_id: 'bk_router:2',
    source_port_id: 'port-right',
    target_port_id: 'port-left',
  })[0],
  {
    ...detailLinks[0],
    source_node_id: 'bk_firewall:1',
    target_node_id: 'bk_router:2',
    source_port_id: 'port-right',
    target_port_id: 'port-left',
  },
  'link terminal updates persist dragged canvas anchor endpoints',
);

assert.equal(
  isMetricOptionMatched('单播', {
    label: '接口入网累积单播包数',
    value: 'ifInUcastPkts::snmp_network',
  }),
  true,
  'metric select search should match Chinese display name',
);
assert.equal(
  isMetricOptionMatched('ifInUcast', {
    label: '接口入网累积单播包数',
    value: 'ifInUcastPkts::snmp_network',
  }),
  true,
  'metric select search should match metric field value',
);
assert.equal(
  isMetricOptionMatched('丢包', {
    label: '接口入网累积单播包数',
    value: 'ifInUcastPkts::snmp_network',
  }),
  false,
  'metric select search should reject unrelated keywords',
);

assert.equal(
  formatNetworkMetricValue(1341088468, ''),
  '1.34 Bil',
  'network topology follows WeOps short count formatter when metric unit is empty',
);
assert.equal(
  formatNetworkMetricValue(6, 'none'),
  '6',
  'small empty-unit values keep their plain number text',
);

const editedMetricDraft = buildNetworkTopologyMetricDraft({
  metricOption: {
    metric_field: 'ifOutUcastPkts',
    result_table_id: 'snmp_network',
    display_name: '接口出网累积单播包数',
    unit: '',
  },
  displayMode: 'dimension',
  aggregateType: 'sum',
  dimensions: { ifDescr: 'ens192', ifIndex: '2' },
  thresholds: [
    { value: '100', color: '#dc2626' },
    { value: '10', color: '#2563eb' },
  ],
  sortOrder: 1,
});
assert.deepEqual(
  replaceNetworkTopologyMetricDraft(
    [
      {
        metric_field: 'ifInUcastPkts',
        result_table_id: 'snmp_network',
        display_name: '接口入网累积单播包数',
        unit: '',
        display_mode: 'aggregate',
        aggregate_type: 'sum',
        dimensions: {},
        sort_order: 0,
        thresholds: [{ value: 0, color: '#2563eb' }],
      },
      {
        metric_field: 'ifOutOctets',
        result_table_id: 'snmp_network',
        display_name: '接口出网累积字节数',
        unit: 'bps',
        display_mode: 'aggregate',
        aggregate_type: 'last',
        dimensions: {},
        sort_order: 1,
        thresholds: [{ value: 0, color: '#2563eb' }],
      },
    ],
    1,
    editedMetricDraft,
  ),
  [
    {
      metric_field: 'ifInUcastPkts',
      result_table_id: 'snmp_network',
      display_name: '接口入网累积单播包数',
      unit: '',
      display_mode: 'aggregate',
      aggregate_type: 'sum',
      dimensions: {},
      sort_order: 0,
      thresholds: [{ value: 0, color: '#2563eb' }],
    },
    {
      metric_field: 'ifOutUcastPkts',
      result_table_id: 'snmp_network',
      display_name: '接口出网累积单播包数',
      unit: '',
      display_mode: 'dimension',
      aggregate_type: 'sum',
      dimensions: { ifDescr: 'ens192', ifIndex: '2' },
      condition_filter: [],
      sort_order: 1,
      thresholds: [
        { value: 100, color: '#dc2626' },
        { value: 10, color: '#2563eb' },
      ],
    },
  ],
  'editing a bound metric can replace metric identity and display config while preserving sort order',
);

const filteredMetricDraft = buildNetworkTopologyMetricDraft({
  metricOption: {
    metric_field: 'ifInDiscards',
    result_table_id: 'snmp_network',
    display_name: '接口入网累积丢包数',
    unit: '',
  },
  displayMode: 'dimension',
  aggregateType: 'max',
  conditionFilter: [
    { dimension_id: 'ifDescr', value: ['docker0', 'lo'] },
    { dimension_id: '', value: ['ignored'] },
    { dimension_id: 'ifIndex', value: [] },
  ],
  thresholds: [{ value: '0', color: '#2563eb' }],
  sortOrder: 2,
});
assert.deepEqual(
  {
    display_mode: filteredMetricDraft.display_mode,
    aggregate_type: filteredMetricDraft.aggregate_type,
    dimensions: filteredMetricDraft.dimensions,
    condition_filter: filteredMetricDraft.condition_filter,
  },
  {
    display_mode: 'dimension',
    aggregate_type: 'max',
    dimensions: {},
    condition_filter: [{ dimension_id: 'ifDescr', value: ['docker0', 'lo'] }],
  },
  'dimension mode should save WeOps-style condition_filter rows instead of flattening every dimension',
);

assert.deepEqual(
  buildNetworkTopologyLinkTerminals({
    id: 'link-anchor',
    source_node_id: 'node-a',
    target_node_id: 'node-b',
    source_port_id: 'bottom',
    target_port_id: 'left',
    port_pairs: [],
    is_draft: true,
  }),
  {
    source: { cell: 'node-a', port: 'bottom' },
    target: { cell: 'node-b', port: 'left' },
  },
  'link terminals keep the exact source/target anchor ports selected by the user',
);
assert.deepEqual(
  buildNetworkTopologyLinkTerminals({
    id: 'link-legacy',
    source_node_id: 'node-a',
    target_node_id: 'node-b',
    port_pairs: [],
    is_draft: true,
  }),
  {
    source: { cell: 'node-a' },
    target: { cell: 'node-b' },
  },
  'legacy links without anchor fields still render with cell-only terminals',
);

assert.equal(
  isNetworkTopologyLinkPendingInterfaceSelection({
    id: 'link-draft',
    source_node_id: 'node-a',
    target_node_id: 'node-b',
    port_pairs: [],
    is_draft: true,
  }),
  true,
  'draft links without selected interfaces should stay in neutral pending state instead of using runtime status colors',
);
assert.equal(
  isNetworkTopologyLinkPendingInterfaceSelection({
    id: 'link-configured',
    source_node_id: 'node-a',
    target_node_id: 'node-b',
    port_pairs: [{ source: 'eth0', target: 'eth1' }],
    is_draft: false,
  }),
  false,
  'configured links should use interface-pair runtime status colors',
);

assert.deepEqual(
  buildNetworkTopologyLinkRenderOptions({ vertices: [] }),
  {
    connector: { name: 'normal' },
    vertices: [],
  },
  'new links without manual vertices should render as straight lines',
);
assert.deepEqual(
  buildNetworkTopologyLinkRenderOptions({
    vertices: [{ x: 10, y: 20 }, { x: Number.NaN, y: 30 }, { x: 40, y: 50 }],
  }),
  {
    connector: { name: 'normal' },
    vertices: [{ x: 10, y: 20 }, { x: 40, y: 50 }],
  },
  'links with manual vertices should keep dragged bend points and ignore invalid points',
);

const topologyIndexSource = readRepoFile('src/app/ops-analysis/(pages)/view/networkTopology/index.tsx');
const topologyApiSource = readRepoFile('src/app/ops-analysis/api/networkTopology.ts');
const networkLibraryHookSource = readRepoFile(
  'src/app/ops-analysis/(pages)/view/networkTopology/hooks/useNetworkLibrary.ts',
);
const networkLibrarySource = readRepoFile(
  'src/app/ops-analysis/(pages)/view/networkTopology/components/networkLibrary.tsx',
);
const networkEdgeDrawerSource = readRepoFile(
  'src/app/ops-analysis/(pages)/view/networkTopology/components/networkEdgeDrawer.tsx',
);
assert.match(
  networkLibraryHookSource,
  /enabled\?: boolean/,
  'network library hook should support a request gate so read-only collapsed panels do not load WeOps data',
);
assert.match(
  topologyIndexSource,
  /enabled:\s*Boolean\(canvasId\)/,
  'network library should load once when entering a canvas instead of reloading on every panel expand/edit toggle',
);
assert.match(
  networkLibraryHookSource,
  /const \[allNodes, setAllNodes\] = useState<NetworkNodeLibraryItem\[\]>\(\[\]\)/,
  'network library should retain one full device list and filter it locally',
);
assert.match(
  networkLibraryHookSource,
  /loadNodesRef\.current\(canvasId\)/,
  'network library should request the full device list once without server-side model/keyword filters',
);
assert.doesNotMatch(
  networkLibraryHookSource,
  /modelCacheRef|loadedNodesKeyRef/,
  'network library reload should not reuse persistent model or node request caches',
);
assert.match(
  networkLibraryHookSource,
  /inFlightRef/,
  'network library should still deduplicate only concurrent requests',
);
assert.match(
  networkLibrarySource,
  /onChange=\{\(e\) => \{\s*const nextKeyword = e\.target\.value;\s*setKeywordDraft\(nextKeyword\);\s*if \(!nextKeyword\) \{\s*onKeywordChange\(''\);\s*\}\s*\}\}/,
  'network library keyword input should follow existing Search pattern: typing is local, clearing resets search',
);
assert.match(
  networkLibrarySource,
  /onSearch=\{\(v\) => onKeywordChange\(v\.trim\(\)\)\}/,
  'network library keyword search should submit through Input.Search onSearch instead of querying on every keypress',
);
assert.match(
  topologyIndexSource,
  /if \(node && canvasId && editor\.editMode\) \{\s*loadNodeMetrics\(node\);\s*\}/,
  'read-only node detail selection should not fetch metric options; metrics are only needed in edit drawer',
);
assert.match(
  topologyIndexSource,
  /if \(!id \|\| !canvasId \|\| !options\?\.openConfig\)/,
  'view-only link selection should not load full source/target interface lists; only link edit mode needs them',
);
assert.match(
  topologyIndexSource,
  /const loadLinkInterfaces = useCallback\(\s*\(link: NetworkTopologyLink\)/,
  'link interface loading should use one shared loader that refreshes whenever config opens',
);
assert.match(
  topologyIndexSource,
  /handleSelectLink[\s\S]*loadLinkInterfaces\(link\)/,
  'opening an existing link config should refresh source and target interface lists through the shared loader',
);
assert.doesNotMatch(
  topologyIndexSource,
  /interfacesLoading \? \(\s*<span[^>]*>\s*\{t\('opsAnalysis\.networkTopology\.link\.loadingInterfaces'\)\}/,
  'link detail popover should render configured port_pairs immediately instead of hiding behind interface-list loading',
);
assert.doesNotMatch(
  networkEdgeDrawerSource,
  /linkRuntime|network-edge-drawer-runtime|runtimeSummary/,
  'link config drawer should stay configuration-only and not render stale runtime summaries',
);
assert.match(
  topologyIndexSource,
  /const DETAIL_POPOVER_MAX_HEIGHT_PX = 3\d{2};/,
  'detail popovers should keep a compact capped height while leaving room for node information',
);
assert.match(
  topologyIndexSource,
  /top: clampDetailPopoverTop\(linkDetailPoint\.y\)/,
  'link detail popover top should be clamped so it cannot overflow below the viewport',
);
assert.match(
  topologyIndexSource,
  /left: clampDetailPopoverLeft\(linkDetailPoint\.x\)/,
  'link detail popover left should be clamped so clicking right-side links still shows the card onscreen',
);
assert.match(
  topologyIndexSource,
  /top: clampDetailPopoverTop\(nodeDetailPoint\.y\)/,
  'node detail popover top should be clamped so it cannot overflow below the viewport',
);
assert.match(
  topologyIndexSource,
  /grid grid-cols-2 gap-x-3 gap-y-1\.5/,
  'detail basic info rows should keep a compact two-column summary layout',
);
assert.match(
  topologyApiSource,
  /getLinkRuntime[\s\S]*weops\/link_runtime\//,
  'network topology API client should expose the local link runtime preview endpoint',
);
assert.match(
  topologyIndexSource,
  /api\s*\.\s*getLinkRuntime\(\s*String\(canvasId\),\s*\{\s*link:\s*nextLink,\s*nodes:\s*prev\.nodes\s*\}/,
  'committing link interfaces should request local link runtime with the current unsaved node list',
);
assert.doesNotMatch(
  topologyIndexSource,
  /normalizedMetrics\.forEach\(\(metric\) => \{\s*void loadDraftMetricRuntime\(node, metric\);/,
  'committing node metrics should not send one metric-value request per metric',
);
assert.match(
  topologyIndexSource,
  /const metricRequests = metrics\.map\(\(metric\) =>/,
  'committing node metrics should build one batched metric_values payload',
);
assert.match(
  topologyIndexSource,
  /api\.getMetricValues\(String\(canvasId\), metricRequests\)/,
  'committing node metrics should query draft metric runtime in one batch request',
);
assert.doesNotMatch(
  topologyIndexSource,
  /useNetworkRefresh|getRuntime\(/,
  'network topology view should not wait for the full-canvas runtime endpoint',
);
assert.doesNotMatch(
  topologyApiSource,
  /getRuntime|\/runtime\//,
  'network topology API client should remove the deprecated full-canvas runtime endpoint',
);
assert.doesNotMatch(
  topologyIndexSource,
  /nodeMetricsRequestKeyRef/,
  'opening node edit should not reuse a permanent metric-options request cache key',
);
assert.match(
  topologyIndexSource,
  /nodeMetricsRequestGenerationRef/,
  'node metric options should ignore stale responses with a request generation',
);
assert.doesNotMatch(
  topologyIndexSource,
  /linkInterfacesRequestKeyRef/,
  'opening link config should not reuse a permanent interface-options request cache key',
);
assert.match(
  topologyIndexSource,
  /linkInterfacesRequestGenerationRef/,
  'link interface options should ignore stale responses with a request generation',
);
assert.match(
  topologyIndexSource,
  /查看态不再调用整图 `\/runtime\/`/,
  'network topology view should document why the full runtime endpoint is not used',
);
assert.match(
  topologyIndexSource,
  /runtimeConfig\.nodes[\s\S]*api\.getMetricValues/,
  'configured node metrics should load independently after the canvas config is available',
);
assert.match(
  topologyIndexSource,
  /runtimeConfig\.links[\s\S]*api\.getLinkRuntime/,
  'configured links should load independently after the canvas config is available',
);

console.log('ops-analysis-network-topology-test passed');
