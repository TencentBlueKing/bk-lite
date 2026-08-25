import assert from 'node:assert/strict';
import test from 'node:test';
import { buildPersistedNetworkStatusTopologyConfig } from '@/app/ops-analysis/utils/networkStatusTopologyLayout';
import { buildWidgetSubmitConfig } from '../submitConfig';

test('scene widget submit preserves layoutByMode geometry fields', () => {
  const result = buildWidgetSubmitConfig({
    values: {
      name: 'topo',
      chartType: 'networkStatusTopology',
      sceneWidgetType: 'networkStatusTopology',
      networkStatusTopology: {
        instUuids: ['12'],
        nodeLimit: 100,
        layoutMode: 'force',
        layoutByMode: {
          hierarchical: { nodePositions: { n1: { x: 10, y: 20 } } },
          force: { linkVertices: { e1: [{ x: 1, y: 2 }] } },
        },
      },
    },
    chartType: 'networkStatusTopology',
    showChartThemeMode: false,
    showTableFilterFields: false,
    selectedFields: [],
    thresholdColors: [],
    filterBindings: {},
    displayColumns: [],
    filterFields: [],
    actions: [],
  });

  assert.ok(result.config);
  assert.deepEqual(
    result.config?.networkStatusTopology,
    buildPersistedNetworkStatusTopologyConfig({
      instUuids: ['12'],
      nodeLimit: 100,
      layoutMode: 'force',
      layoutByMode: {
        hierarchical: { nodePositions: { n1: { x: 10, y: 20 } } },
        force: { linkVertices: { e1: [{ x: 1, y: 2 }] } },
      },
    }),
  );
});

test('scene widget submit keeps layoutByMode when form only returns query fields', () => {
  const existing = {
    instUuids: ['12'],
    nodeLimit: 100,
    layoutMode: 'force' as const,
    layoutByMode: {
      hierarchical: { nodePositions: { n1: { x: 10, y: 20 } } },
      force: { linkVertices: { e1: [{ x: 1, y: 2 }] } },
    },
  };
  const formTopology = {
    instUuids: ['99'],
    nodeLimit: 100,
  };
  const merged = {
    instUuids: formTopology.instUuids || existing.instUuids,
    nodeLimit: formTopology.nodeLimit || existing.nodeLimit,
    layoutMode: (formTopology as typeof existing).layoutMode ?? existing.layoutMode,
    layoutByMode:
      (formTopology as typeof existing).layoutByMode ?? existing.layoutByMode,
  };
  const result = buildWidgetSubmitConfig({
    values: {
      name: 'topo',
      chartType: 'networkStatusTopology',
      sceneWidgetType: 'networkStatusTopology',
      networkStatusTopology: merged,
    },
    chartType: 'networkStatusTopology',
    showChartThemeMode: false,
    showTableFilterFields: false,
    selectedFields: [],
    thresholdColors: [],
    filterBindings: {},
    displayColumns: [],
    filterFields: [],
    actions: [],
  });
  assert.deepEqual(result.config?.networkStatusTopology, {
    instUuids: ['99'],
    nodeLimit: 100,
    layoutMode: 'force',
    layoutByMode: {
      hierarchical: { nodePositions: { n1: { x: 10, y: 20 } } },
      force: { linkVertices: { e1: [{ x: 1, y: 2 }] } },
    },
  });
});

test('scene widget submit without layout stays query-only', () => {
  const result = buildWidgetSubmitConfig({
    values: {
      name: 'topo',
      chartType: 'networkStatusTopology',
      sceneWidgetType: 'networkStatusTopology',
      networkStatusTopology: {
        instUuids: ['12'],
        nodeLimit: 100,
      },
    },
    chartType: 'networkStatusTopology',
    showChartThemeMode: false,
    showTableFilterFields: false,
    selectedFields: [],
    thresholdColors: [],
    filterBindings: {},
    displayColumns: [],
    filterFields: [],
    actions: [],
  });

  assert.deepEqual(result.config?.networkStatusTopology, {
    instUuids: ['12'],
    nodeLimit: 100,
  });
});

test('scene widget submit persists inbound-only and empty linkTrafficDisplays', () => {
  const inboundOnly = buildWidgetSubmitConfig({
    values: {
      name: 'topo',
      chartType: 'networkStatusTopology',
      sceneWidgetType: 'networkStatusTopology',
      networkStatusTopology: {
        instUuids: ['12'],
        nodeLimit: 100,
        linkTrafficDisplays: ['inbound'],
      },
    },
    chartType: 'networkStatusTopology',
    showChartThemeMode: false,
    showTableFilterFields: false,
    selectedFields: [],
    thresholdColors: [],
    filterBindings: {},
    displayColumns: [],
    filterFields: [],
    actions: [],
  });
  assert.deepEqual(inboundOnly.config?.networkStatusTopology?.linkTrafficDisplays, ['inbound']);

  const cleared = buildWidgetSubmitConfig({
    values: {
      name: 'topo',
      chartType: 'networkStatusTopology',
      sceneWidgetType: 'networkStatusTopology',
      networkStatusTopology: {
        instUuids: ['12'],
        nodeLimit: 100,
        linkTrafficDisplays: [],
      },
    },
    chartType: 'networkStatusTopology',
    showChartThemeMode: false,
    showTableFilterFields: false,
    selectedFields: [],
    thresholdColors: [],
    filterBindings: {},
    displayColumns: [],
    filterFields: [],
    actions: [],
  });
  assert.deepEqual(cleared.config?.networkStatusTopology?.linkTrafficDisplays, []);
});

test('scene widget submit persists inbound and outbound traffic thresholds', () => {
  const result = buildWidgetSubmitConfig({
    values: {
      name: 'topo',
      chartType: 'networkStatusTopology',
      sceneWidgetType: 'networkStatusTopology',
      networkStatusTopology: {
        instUuids: ['12'],
        nodeLimit: 100,
        inboundTrafficThresholds: [{ value: '1024', color: '#dc2626' }],
        outboundTrafficThresholds: [],
      },
    },
    chartType: 'networkStatusTopology',
    showChartThemeMode: false,
    showTableFilterFields: false,
    selectedFields: [],
    thresholdColors: [],
    filterBindings: {},
    displayColumns: [],
    filterFields: [],
    actions: [],
  });
  assert.deepEqual(result.config?.networkStatusTopology?.inboundTrafficThresholds, [
    { value: '1024', color: '#dc2626' },
  ]);
  assert.deepEqual(result.config?.networkStatusTopology?.outboundTrafficThresholds, []);
});

test('scene widget submit migrates legacy flat geometry into layoutByMode', () => {
  const result = buildWidgetSubmitConfig({
    values: {
      name: 'topo',
      chartType: 'networkStatusTopology',
      sceneWidgetType: 'networkStatusTopology',
      networkStatusTopology: {
        instUuids: ['12'],
        nodeLimit: 100,
        layoutMode: 'hierarchical',
        nodePositions: { n1: { x: 10, y: 20 } },
      },
    },
    chartType: 'networkStatusTopology',
    showChartThemeMode: false,
    showTableFilterFields: false,
    selectedFields: [],
    thresholdColors: [],
    filterBindings: {},
    displayColumns: [],
    filterFields: [],
    actions: [],
  });

  assert.deepEqual(result.config?.networkStatusTopology, {
    instUuids: ['12'],
    nodeLimit: 100,
    layoutMode: 'hierarchical',
    layoutByMode: {
      hierarchical: { nodePositions: { n1: { x: 10, y: 20 } } },
    },
  });
});
