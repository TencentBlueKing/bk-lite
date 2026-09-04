/**
 * 网络拓扑画布渲染优化：连线样式、指纹跳过、运行态批量、端口/工具显隐。
 * 运行: pnpm exec tsx scripts/ops-analysis-network-topology-canvas-perf-test.ts
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import {
  NETWORK_CANVAS_COMPACT_SCALE,
  NETWORK_EDGE_FLOW_CLASS,
  buildLinkLineAttrs,
  buildLinkRuntimeFingerprint,
  buildNodeRuntimeFingerprint,
  isTransientConnectingEdge,
  shouldShowEdgeTools,
  shouldShowNodePorts,
  shouldUseCompactNodeDetail,
} from '../src/app/ops-analysis/(pages)/view/networkTopology/utils/networkCanvasRender';
import { createNetworkTopologyRuntimeBatcher } from '../src/app/ops-analysis/(pages)/view/networkTopology/utils/runtimeUpdateBatcher';
import type { NetworkLinkRuntime } from '../src/app/ops-analysis/types/networkTopology';

const readRepoFile = (path: string) =>
  readFileSync(new URL(`../${path}`, import.meta.url), 'utf8');

const normalLine = buildLinkLineAttrs('normal');
assert.equal(normalLine.strokeDasharray, null, 'healthy links should be solid');
assert.equal(normalLine.class, '', 'healthy links should not animate');

const unknownLine = buildLinkLineAttrs('unknown');
assert.equal(unknownLine.strokeDasharray, null, 'unknown links should be solid');
assert.equal(unknownLine.class, '', 'unknown links should not animate');

const criticalLine = buildLinkLineAttrs('critical');
assert.equal(criticalLine.strokeDasharray, '5 3', 'alert links keep the flow dash');
assert.equal(
  criticalLine.class,
  NETWORK_EDGE_FLOW_CLASS,
  'only alert links get the CSS flow class',
);

const pendingLine = buildLinkLineAttrs('unknown', { pending: true });
assert.equal(pendingLine.strokeDasharray, '5 3', 'draft links stay dashed');
assert.equal(pendingLine.class, '', 'draft dashes must not animate');

assert.equal(shouldShowNodePorts(false, 'n1', 'n1'), false);
assert.equal(shouldShowNodePorts(true, null, 'n1'), false);
assert.equal(shouldShowNodePorts(true, 'n2', 'n1'), false);
assert.equal(shouldShowNodePorts(true, 'n1', 'n1'), true);
assert.equal(shouldShowNodePorts(true, null, 'n1', { connecting: true }), true);
assert.equal(shouldShowNodePorts(false, null, 'n1', { connecting: true }), false);

assert.equal(isTransientConnectingEdge({ connecting: true }), true);
assert.equal(isTransientConnectingEdge({}), false);
assert.equal(isTransientConnectingEdge({ link: { id: 'l1' } }), false);

assert.equal(shouldShowEdgeTools(true, 'e1', 'e1'), true);
assert.equal(shouldShowEdgeTools(true, 'e1', 'e2'), false);
assert.equal(shouldShowEdgeTools(false, 'e1', 'e1'), false);

assert.equal(shouldUseCompactNodeDetail(0.49), true);
assert.equal(shouldUseCompactNodeDetail(NETWORK_CANVAS_COMPACT_SCALE), false);

const node = {
  id: 'n1',
  bk_inst_name: 'sw-1',
  metrics: [
    {
      metric_field: 'cpu',
      result_table_id: 'rt',
      display_name: 'CPU',
    },
  ],
};
const fingerprintA = buildNodeRuntimeFingerprint(node, {
  metrics: [{ metric_field: 'cpu', result_table_id: 'rt', value: 1, status: 'ok' }],
});
const fingerprintB = buildNodeRuntimeFingerprint(node, {
  metrics: [{ metric_field: 'cpu', result_table_id: 'rt', value: 2, status: 'ok' }],
});
assert.notEqual(fingerprintA, fingerprintB, 'metric value changes must bust the node fingerprint');
assert.equal(
  fingerprintA,
  buildNodeRuntimeFingerprint(node, {
    metrics: [{ metric_field: 'cpu', result_table_id: 'rt', value: 1, status: 'ok' }],
  }),
  'unchanged runtime should keep the same node fingerprint',
);

const link = {
  id: 'l1',
  source_node_id: 'n1',
  target_node_id: 'n2',
  vertices: [{ x: 1, y: 2 }],
};
assert.equal(
  buildLinkRuntimeFingerprint(link, { status: 'normal' }),
  buildLinkRuntimeFingerprint(link, { status: 'normal' }),
);
assert.notEqual(
  buildLinkRuntimeFingerprint(link, { status: 'normal' }),
  buildLinkRuntimeFingerprint(link, { status: 'critical' }),
);

{
  const applied: Array<{ metrics: string[] }> = [];
  const batcher = createNetworkTopologyRuntimeBatcher({
    apply: (pending) => {
      applied.push({ metrics: Object.keys(pending.metrics).sort() });
    },
    flushMs: 10_000,
  });
  batcher.pushMetrics('n1', [{ metric_field: 'cpu', result_table_id: 'rt', status: 'ok', value: 1 }]);
  batcher.pushMetrics('n2', [{ metric_field: 'cpu', result_table_id: 'rt', status: 'ok', value: 2 }]);
  batcher.pushMetrics('n1', [{ metric_field: 'cpu', result_table_id: 'rt', status: 'ok', value: 3 }]);
  assert.equal(applied.length, 0, 'pushes should wait for the flush window');
  batcher.flush();
  assert.equal(applied.length, 1, 'one flush should emit one React state update');
  assert.deepEqual(applied[0].metrics, ['n1', 'n2']);
  batcher.dispose();
}

{
  let lastValue: unknown;
  const batcher = createNetworkTopologyRuntimeBatcher({
    apply: (pending) => {
      lastValue = pending.metrics.n1?.[0]?.value;
    },
    flushMs: 10_000,
  });
  batcher.pushMetrics('n1', [
    { metric_field: 'cpu', result_table_id: 'rt', status: 'loading', value: null },
  ]);
  batcher.pushMetrics('n1', [
    { metric_field: 'cpu', result_table_id: 'rt', status: 'ok', value: 42 },
  ]);
  batcher.flush();
  assert.equal(lastValue, 42, 'later metric writes in the same window should win');
  batcher.dispose();
}

{
  let links: Record<string, NetworkLinkRuntime> = {};
  let removed: string[] = [];
  const batcher = createNetworkTopologyRuntimeBatcher({
    apply: (pending) => {
      links = pending.links;
      removed = pending.removeLinkIds;
    },
    flushMs: 10_000,
  });
  batcher.pushLink({ id: 'l1' } as NetworkLinkRuntime);
  batcher.removeLink('l1');
  batcher.flush();
  assert.equal(Object.keys(links).length, 0);
  assert.deepEqual(removed, ['l1']);
  batcher.dispose();
}

{
  let flushed = 0;
  const batcher = createNetworkTopologyRuntimeBatcher({
    apply: () => {
      flushed += 1;
    },
    flushMs: 10_000,
  });
  batcher.pushMetrics('n1', [
    { metric_field: 'cpu', result_table_id: 'rt', status: 'ok', value: 1 },
  ]);
  batcher.clear();
  batcher.flush();
  assert.equal(flushed, 0, 'clear should drop pending runtime writes');
  batcher.dispose();
}

const canvasSource = readRepoFile(
  'src/app/ops-analysis/(pages)/view/networkTopology/components/networkCanvas.tsx',
);
assert.doesNotMatch(canvasSource, /dropShadow/, 'node cards should not pay SVG dropShadow');
assert.doesNotMatch(canvasSource, /textWrap/, 'node cards should not use X6 textWrap');
assert.match(canvasSource, /batchUpdate\("network-sync-nodes"/);
assert.match(canvasSource, /batchUpdate\("network-sync-links"/);
assert.match(canvasSource, /node:mouseenter/);
assert.match(canvasSource, /runtimeFingerprint === fingerprint/);
assert.match(canvasSource, /NETWORK_CANVAS_COMPACT_CLASS/);
assert.match(canvasSource, /data: \{ connecting: true \}/);
assert.match(canvasSource, /isTransientConnectingEdge\(data\)/);
assert.match(canvasSource, /connectingRef\.current/);
assert.doesNotMatch(
  canvasSource,
  /class:\s*"network-edge-flow"/,
  'flow class must come from buildLinkLineAttrs, not a hardcoded all-edge attr',
);

const indexSource = readRepoFile(
  'src/app/ops-analysis/(pages)/view/networkTopology/index.tsx',
);
assert.match(indexSource, /createNetworkTopologyRuntimeBatcher/);
assert.match(
  indexSource,
  /runtimeBatcher\.pushMetrics/,
  'configured runtime should batch node metric writes',
);
assert.match(indexSource, /runtimeBatcher\.pushLink/);
assert.match(indexSource, /selectedLinkId=\{editor\.selectedLinkId\}/);

const scssSource = readRepoFile(
  'src/app/ops-analysis/(pages)/view/networkTopology/index.module.scss',
);
assert.match(scssSource, /network-canvas-compact/);
assert.match(scssSource, /nt-node-detail/);

console.log('ops-analysis-network-topology-canvas-perf-test: ok');
