import assert from 'node:assert/strict';
import test from 'node:test';
import {
  DEFAULT_NETWORK_STATUS_TOPOLOGY_LAYOUT_MODE,
  applyNodePositionsToLayout,
  buildPersistedNetworkStatusTopologyConfig,
  canPersistNetworkStatusTopologyLayout,
  cellPositionToLayoutPoint,
  layoutPointToCellPosition,
  normalizeManualEdgeVertices,
  patchLayoutByMode,
  pruneNetworkStatusTopologyLayout,
  resolveLayoutGeometry,
  resolveLinkEdgeGeometry,
  resetNetworkStatusTopologyLayout,
} from '@/app/ops-analysis/utils/networkStatusTopologyLayout';
import type { NetworkTopologyLayoutResult } from '@/app/cmdb/components/networkTopology/types';

const baseLayout = (): NetworkTopologyLayoutResult => ({
  nodes: [
    { id: 'a', modelId: 'switch', name: 'A', x: 10, y: 20 },
    { id: 'b', modelId: 'switch', name: 'B', x: 100, y: 200 },
  ],
  links: [{ id: 'l1', source: 'a', target: 'b', curveOffset: 0 }],
});

test('canPersistNetworkStatusTopologyLayout requires edit mode, non-share, and writeback', () => {
  assert.equal(
    canPersistNetworkStatusTopologyLayout({
      layoutEditable: true,
      shareMode: false,
      hasWriteback: true,
    }),
    true,
  );
  assert.equal(
    canPersistNetworkStatusTopologyLayout({
      layoutEditable: true,
      shareMode: true,
      hasWriteback: true,
    }),
    false,
  );
  assert.equal(
    canPersistNetworkStatusTopologyLayout({
      layoutEditable: false,
      shareMode: false,
      hasWriteback: true,
    }),
    false,
  );
  assert.equal(
    canPersistNetworkStatusTopologyLayout({
      layoutEditable: true,
      shareMode: false,
      hasWriteback: false,
    }),
    false,
  );
});

test('applyNodePositionsToLayout overrides only matching node ids', () => {
  const next = applyNodePositionsToLayout(baseLayout(), {
    a: { x: 55, y: 66 },
    ghost: { x: 1, y: 2 },
  });
  assert.deepEqual(
    next.nodes.map((node) => ({ id: node.id, x: node.x, y: node.y })),
    [
      { id: 'a', x: 55, y: 66 },
      { id: 'b', x: 100, y: 200 },
    ],
  );
});

test('widget instance layouts stay isolated by their own valueConfig', () => {
  const sharedTopology = baseLayout();
  const widgetA = buildPersistedNetworkStatusTopologyConfig({
    modelId: 'switch',
    instId: '1',
    depth: 2,
    layoutByMode: {
      hierarchical: { nodePositions: { a: { x: 11, y: 22 } } },
    },
  });
  const widgetB = buildPersistedNetworkStatusTopologyConfig({
    modelId: 'switch',
    instId: '1',
    depth: 2,
    layoutByMode: {
      hierarchical: { nodePositions: { a: { x: 77, y: 88 } } },
    },
  });

  const renderedA = applyNodePositionsToLayout(
    sharedTopology,
    resolveLayoutGeometry(widgetA, 'hierarchical').nodePositions,
  );
  const renderedB = applyNodePositionsToLayout(
    sharedTopology,
    resolveLayoutGeometry(widgetB, 'hierarchical').nodePositions,
  );

  assert.deepEqual(
    renderedA.nodes.find((node) => node.id === 'a'),
    { id: 'a', modelId: 'switch', name: 'A', x: 11, y: 22 },
  );
  assert.deepEqual(
    renderedB.nodes.find((node) => node.id === 'a'),
    { id: 'a', modelId: 'switch', name: 'A', x: 77, y: 88 },
  );
  assert.notDeepEqual(
    widgetA.layoutByMode?.hierarchical?.nodePositions,
    widgetB.layoutByMode?.hierarchical?.nodePositions,
  );
  assert.deepEqual(sharedTopology.nodes[0], {
    id: 'a',
    modelId: 'switch',
    name: 'A',
    x: 10,
    y: 20,
  });
});

test('resolveLayoutGeometry keeps mode buckets isolated when switching modes', () => {
  const config = {
    layoutMode: 'hierarchical' as const,
    layoutByMode: {
      hierarchical: {
        nodePositions: { a: { x: 11, y: 22 } },
        linkVertices: { l1: [{ x: 1, y: 2 }] },
      },
      force: {
        nodePositions: { a: { x: 90, y: 91 } },
      },
    },
  };

  assert.deepEqual(resolveLayoutGeometry(config, 'hierarchical'), {
    nodePositions: { a: { x: 11, y: 22 } },
    linkVertices: { l1: [{ x: 1, y: 2 }] },
  });
  assert.deepEqual(resolveLayoutGeometry(config, 'force'), {
    nodePositions: { a: { x: 90, y: 91 } },
  });
  assert.deepEqual(resolveLayoutGeometry(config, 'circular'), {});
});

test('resolveLayoutGeometry maps legacy flat fields into then-current layoutMode only', () => {
  const legacy = {
    layoutMode: 'force' as const,
    nodePositions: { a: { x: 3, y: 4 } },
    linkVertices: { l1: [{ x: 5, y: 6 }] },
  };
  assert.deepEqual(resolveLayoutGeometry(legacy, 'force'), {
    nodePositions: { a: { x: 3, y: 4 } },
    linkVertices: { l1: [{ x: 5, y: 6 }] },
  });
  assert.deepEqual(resolveLayoutGeometry(legacy, 'hierarchical'), {});
  assert.deepEqual(resolveLayoutGeometry(legacy, 'circular'), {});
});

test('resolveLinkEdgeGeometry prefers manual vertices over parallel offset', () => {
  const manual = resolveLinkEdgeGeometry({
    parallelOffset: 16,
    manualVertices: [
      { x: 1, y: 2 },
      { x: 3, y: 4 },
    ],
  });
  assert.deepEqual(manual, {
    kind: 'manual',
    vertices: [
      { x: 1, y: 2 },
      { x: 3, y: 4 },
    ],
    parallelOffset: 0,
  });

  const parallel = resolveLinkEdgeGeometry({
    parallelOffset: 16,
    manualVertices: [],
  });
  assert.deepEqual(parallel, {
    kind: 'parallel',
    vertices: [],
    parallelOffset: 16,
  });
});

test('buildPersistedNetworkStatusTopologyConfig keeps layoutByMode and drops flat fields', () => {
  const next = buildPersistedNetworkStatusTopologyConfig({
    modelId: 'router',
    instId: '99',
    depth: 3,
    layoutMode: 'force',
    layoutByMode: {
      hierarchical: { nodePositions: { a: { x: 1, y: 2 } } },
      force: { linkVertices: { l1: [{ x: 0, y: 0 }] } },
    },
    nodePositions: { legacy: { x: 9, y: 9 } },
  });
  assert.deepEqual(next, {
    modelId: 'router',
    instId: '99',
    depth: 3,
    layoutMode: 'force',
    layoutByMode: {
      hierarchical: { nodePositions: { a: { x: 1, y: 2 } } },
      force: { linkVertices: { l1: [{ x: 0, y: 0 }] } },
    },
  });
  assert.equal('nodePositions' in next, false);
  assert.equal('linkVertices' in next, false);
});

test('buildPersistedNetworkStatusTopologyConfig migrates legacy flat into layoutMode bucket', () => {
  const next = buildPersistedNetworkStatusTopologyConfig({
    modelId: 'router',
    instId: '1',
    depth: 2,
    layoutMode: 'circular',
    nodePositions: { a: { x: 1, y: 2 } },
    linkVertices: { l1: [{ x: 0, y: 0 }] },
  });
  assert.deepEqual(next, {
    modelId: 'router',
    instId: '1',
    depth: 2,
    layoutMode: 'circular',
    layoutByMode: {
      circular: {
        nodePositions: { a: { x: 1, y: 2 } },
        linkVertices: { l1: [{ x: 0, y: 0 }] },
      },
    },
  });
});

test('buildPersistedNetworkStatusTopologyConfig omits empty layout fields', () => {
  const next = buildPersistedNetworkStatusTopologyConfig({
    modelId: 'router',
    instId: '1',
    depth: 2,
  });
  assert.deepEqual(next, {
    modelId: 'router',
    instId: '1',
    depth: 2,
  });
});

test('pruneNetworkStatusTopologyLayout drops missing node and link geometry across buckets', () => {
  const pruned = pruneNetworkStatusTopologyLayout(
    {
      layoutMode: 'circular',
      layoutByMode: {
        hierarchical: {
          nodePositions: { a: { x: 1, y: 2 }, gone: { x: 9, y: 9 } },
        },
        force: {
          linkVertices: {
            l1: [{ x: 0, y: 1 }],
            old: [{ x: 2, y: 3 }],
          },
        },
      },
    },
    ['a'],
    ['l1'],
  );
  assert.deepEqual(pruned, {
    layoutMode: 'circular',
    layoutByMode: {
      hierarchical: { nodePositions: { a: { x: 1, y: 2 } } },
      force: { linkVertices: { l1: [{ x: 0, y: 1 }] } },
    },
  });
});

test('layoutByMode mode switch preserves all buckets and only changes layoutMode', () => {
  const topoConfig = {
    modelId: 'router',
    instId: '1',
    depth: 2,
    layoutMode: 'hierarchical' as const,
    layoutByMode: {
      hierarchical: {
        nodePositions: { a: { x: 11, y: 22 } },
        linkVertices: { l1: [{ x: 1, y: 2 }] },
      },
      force: {
        nodePositions: { a: { x: 90, y: 91 } },
      },
    },
  };
  const pruned = pruneNetworkStatusTopologyLayout(
    {
      layoutMode: 'force',
      layoutByMode: topoConfig.layoutByMode,
    },
    ['a'],
    ['l1'],
  );
  const emitted = buildPersistedNetworkStatusTopologyConfig({
    modelId: topoConfig.modelId,
    instId: topoConfig.instId,
    depth: topoConfig.depth,
    ...pruned,
  });
  assert.deepEqual(emitted, {
    modelId: 'router',
    instId: '1',
    depth: 2,
    layoutMode: 'force',
    layoutByMode: {
      hierarchical: {
        nodePositions: { a: { x: 11, y: 22 } },
        linkVertices: { l1: [{ x: 1, y: 2 }] },
      },
      force: {
        nodePositions: { a: { x: 90, y: 91 } },
      },
    },
  });
});

test('persisted layoutMode restores geometry for that mode on reopen', () => {
  const saved = buildPersistedNetworkStatusTopologyConfig({
    modelId: 'router',
    instId: '1',
    depth: 2,
    layoutMode: 'circular',
    layoutByMode: {
      hierarchical: { nodePositions: { a: { x: 1, y: 2 } } },
      circular: {
        nodePositions: { a: { x: 40, y: 50 } },
        linkVertices: { l1: [{ x: 3, y: 4 }] },
      },
    },
  });
  assert.equal(saved.layoutMode, 'circular');
  assert.deepEqual(resolveLayoutGeometry(saved, 'circular'), {
    nodePositions: { a: { x: 40, y: 50 } },
    linkVertices: { l1: [{ x: 3, y: 4 }] },
  });
  assert.deepEqual(resolveLayoutGeometry(saved, 'hierarchical'), {
    nodePositions: { a: { x: 1, y: 2 } },
  });
});

test('resetNetworkStatusTopologyLayout clears only the current mode bucket', () => {
  const reset = resetNetworkStatusTopologyLayout(
    {
      modelId: 'router',
      instId: '1',
      depth: 2,
      layoutMode: 'force',
      layoutByMode: {
        hierarchical: { nodePositions: { a: { x: 1, y: 2 } } },
        force: {
          nodePositions: { a: { x: 3, y: 4 } },
          linkVertices: { l1: [{ x: 0, y: 1 }] },
        },
      },
    },
    'force',
  );
  assert.deepEqual(reset, {
    modelId: 'router',
    instId: '1',
    depth: 2,
    layoutMode: 'force',
    layoutByMode: {
      hierarchical: { nodePositions: { a: { x: 1, y: 2 } } },
    },
  });
  assert.notEqual(reset.layoutMode, DEFAULT_NETWORK_STATUS_TOPOLOGY_LAYOUT_MODE);
  assert.equal('force' in (reset.layoutByMode || {}), false);
});

test('patchLayoutByMode writes into the active mode without touching others', () => {
  const next = patchLayoutByMode(
    {
      modelId: 'router',
      instId: '1',
      depth: 2,
      layoutMode: 'hierarchical',
      layoutByMode: {
        hierarchical: { nodePositions: { a: { x: 1, y: 2 } } },
        force: { nodePositions: { a: { x: 9, y: 9 } } },
      },
    },
    'hierarchical',
    {
      nodePositions: { a: { x: 5, y: 6 }, b: { x: 7, y: 8 } },
    },
  );
  assert.deepEqual(next, {
    hierarchical: {
      nodePositions: { a: { x: 5, y: 6 }, b: { x: 7, y: 8 } },
    },
    force: { nodePositions: { a: { x: 9, y: 9 } } },
  });
});

test('cell and layout point conversion round-trips', () => {
  const layout = { x: 120, y: 80 };
  assert.deepEqual(
    cellPositionToLayoutPoint(layoutPointToCellPosition(layout)),
    layout,
  );
});

test('normalizeManualEdgeVertices keeps vertices clearly off the line', () => {
  const source = { x: 0, y: 0 };
  const target = { x: 100, y: 0 };
  const kept = normalizeManualEdgeVertices(source, target, [
    { x: 50, y: 30 },
  ]);
  assert.deepEqual(kept, [{ x: 50, y: 30 }]);
});

test('normalizeManualEdgeVertices clears near-collinear vertices', () => {
  const source = { x: 0, y: 0 };
  const target = { x: 100, y: 0 };
  const cleared = normalizeManualEdgeVertices(source, target, [
    { x: 30, y: 2 },
    { x: 70, y: -3 },
  ]);
  assert.deepEqual(cleared, []);
});

test('normalizeManualEdgeVertices clears empty or on-line single point', () => {
  const source = { x: 0, y: 0 };
  const target = { x: 100, y: 0 };
  assert.deepEqual(normalizeManualEdgeVertices(source, target, []), []);
  assert.deepEqual(
    normalizeManualEdgeVertices(source, target, [{ x: 40, y: 1 }]),
    [],
  );
});

test('normalizeManualEdgeVertices collapses nearby redundant points', () => {
  const source = { x: 0, y: 0 };
  const target = { x: 100, y: 0 };
  const collapsed = normalizeManualEdgeVertices(source, target, [
    { x: 40, y: 25 },
    { x: 41, y: 26 },
    { x: 70, y: 25 },
  ]);
  assert.deepEqual(collapsed, [
    { x: 40, y: 25 },
    { x: 70, y: 25 },
  ]);
});

test('resolveLinkEdgeGeometry falls back to parallel after cleared vertices', () => {
  const cleared = normalizeManualEdgeVertices(
    { x: 0, y: 0 },
    { x: 100, y: 0 },
    [
      { x: 25, y: 1 },
      { x: 75, y: -1 },
    ],
  );
  assert.deepEqual(
    resolveLinkEdgeGeometry({
      parallelOffset: 12,
      manualVertices: cleared,
    }),
    {
      kind: 'parallel',
      vertices: [],
      parallelOffset: 12,
    },
  );
});
