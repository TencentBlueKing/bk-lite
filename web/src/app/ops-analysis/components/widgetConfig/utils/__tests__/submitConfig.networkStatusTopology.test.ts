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
        modelId: 'switch',
        instId: '12',
        depth: 2,
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
      modelId: 'switch',
      instId: '12',
      depth: 2,
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
    modelId: 'switch',
    instId: '12',
    depth: 2,
    layoutMode: 'force' as const,
    layoutByMode: {
      hierarchical: { nodePositions: { n1: { x: 10, y: 20 } } },
      force: { linkVertices: { e1: [{ x: 1, y: 2 }] } },
    },
  };
  const formTopology = {
    modelId: 'router',
    instId: '99',
    depth: 3,
  };
  const merged = {
    modelId: formTopology.modelId || existing.modelId,
    instId: formTopology.instId || existing.instId,
    depth: formTopology.depth || existing.depth,
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
    modelId: 'router',
    instId: '99',
    depth: 3,
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
        modelId: 'switch',
        instId: '12',
        depth: 2,
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
    modelId: 'switch',
    instId: '12',
    depth: 2,
  });
});

test('scene widget submit migrates legacy flat geometry into layoutByMode', () => {
  const result = buildWidgetSubmitConfig({
    values: {
      name: 'topo',
      chartType: 'networkStatusTopology',
      sceneWidgetType: 'networkStatusTopology',
      networkStatusTopology: {
        modelId: 'switch',
        instId: '12',
        depth: 2,
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
    modelId: 'switch',
    instId: '12',
    depth: 2,
    layoutMode: 'hierarchical',
    layoutByMode: {
      hierarchical: { nodePositions: { n1: { x: 10, y: 20 } } },
    },
  });
});
