import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import { buildFiltersFromDashboardLayout } from '../src/app/ops-analysis/(pages)/view/dashBoard/hooks/useDashboardLayoutSync';
import {
  buildFiltersFromScreenItems,
  syncScreenFilterBindings,
} from '../src/app/ops-analysis/(pages)/view/screen/utils/layout';
import { buildFiltersFromNodes } from '../src/app/ops-analysis/(pages)/view/topology/utils/namespaceUtils';
import { buildDefaultFilterBindings } from '../src/app/ops-analysis/utils/widgetDataTransform';
import type {
  DashboardLayoutItem,
  UnifiedFilterDefinition,
} from '../src/app/ops-analysis/types/dashBoard';
import type { DatasourceItem } from '../src/app/ops-analysis/types/dataSource';
import type { ScreenViewSets } from '../src/app/ops-analysis/types/screen';

const dateRangeDefault = { rangeType: 'last_30_days' } as const;
const dataSource = {
  id: 1,
  params: [
    {
      name: 'period',
      alias_name: 'Period',
      type: 'dateRange',
      filterType: 'filter',
      value: dateRangeDefault,
    },
  ],
} as DatasourceItem;
const staleDefinition: UnifiedFilterDefinition = {
  id: 'period__timeRange',
  key: 'period',
  name: 'Period',
  type: 'timeRange',
  defaultValue: null,
  order: 0,
  enabled: true,
};

const assertDateRangeDefinition = (
  definitions: UnifiedFilterDefinition[],
  host: string,
) => {
  assert.deepEqual(
    definitions.map(({ id, type }) => ({ id, type })),
    [{ id: 'period__dateRange', type: 'dateRange' }],
    `${host} must replace the stale timeRange definition with dateRange`,
  );
  assert.deepEqual(definitions[0].defaultValue, dateRangeDefault);
  assert.equal(Array.isArray(definitions[0].defaultValue), false);
};

const dashboardLayout = [
  {
    i: 'dashboard-widget',
    x: 0,
    y: 0,
    w: 4,
    h: 4,
    name: 'Dashboard widget',
    valueConfig: { dataSource: 1 },
  },
] as DashboardLayoutItem[];
assertDateRangeDefinition(
  buildFiltersFromDashboardLayout({
    layout: dashboardLayout,
    previousDefinitions: [staleDefinition],
    dataSources: [dataSource],
  }),
  'Dashboard',
);

const screenViewSets = {
  viewport: { width: 1920, height: 1080 },
  decorations: {},
  items: [
    {
      id: 'screen-widget',
      type: 'widget',
      chartType: 'line',
      title: 'Screen widget',
      x: 0,
      y: 0,
      w: 4,
      h: 4,
      zIndex: 1,
      valueConfig: {
        dataSource: 1,
        filterBindings: { period__timeRange: true },
      },
    },
  ],
} as ScreenViewSets;
const screenDefinitions = buildFiltersFromScreenItems({
  viewSets: screenViewSets,
  previousDefinitions: [staleDefinition],
  dataSources: [dataSource],
});
assertDateRangeDefinition(screenDefinitions, 'Screen');
assert.deepEqual(
  syncScreenFilterBindings(screenViewSets, screenDefinitions, [dataSource])
    .items[0].valueConfig.filterBindings,
  { period__dateRange: true },
  'Screen must remove the stale timeRange binding and restore the dateRange binding',
);

const topologyGraph = {
  getNodes: () => [
    {
      getData: () => ({
        type: 'chart',
        valueConfig: { dataSource: 1 },
      }),
    },
  ],
};
assertDateRangeDefinition(
  buildFiltersFromNodes(
    topologyGraph as never,
    [dataSource],
    [staleDefinition],
  ),
  'Topology',
);
const topologyDefinitions = buildFiltersFromNodes(
  topologyGraph as never,
  [dataSource],
  [staleDefinition],
);
assert.deepEqual(
  buildDefaultFilterBindings(
    dataSource.params,
    topologyDefinitions,
    { period__timeRange: true },
  ),
  { period__dateRange: true },
  'Topology must remove the stale timeRange binding and restore the dateRange binding',
);

const hostSources = [
  '../src/app/ops-analysis/(pages)/view/dashBoard/hooks/useDashboardLayoutSync.ts',
  '../src/app/ops-analysis/(pages)/view/screen/utils/layout.ts',
  '../src/app/ops-analysis/(pages)/view/topology/utils/namespaceUtils.ts',
].map((path) => readFileSync(new URL(path, import.meta.url), 'utf8'));

hostSources.forEach((source) => {
  assert.match(source, /BindableParamType/);
  assert.match(source, /validateDateRangeValue/);
  assert.doesNotMatch(source, /resolveDateRange/);
  assert.doesNotMatch(source, /type:\s*['"]string['"]\s*\|\s*['"]timeRange['"]/);
});

console.log('ops analysis date range canvas binding tests passed');
