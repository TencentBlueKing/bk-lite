import { describe, expect, it } from 'vitest';

import { buildFiltersFromDashboardLayout, syncDashboardLayoutFilterBindings } from '@/app/ops-analysis/(pages)/view/dashBoard/hooks/useDashboardLayoutSync';
import {
  buildFiltersFromScreenItems,
  syncScreenFilterBindings,
} from '@/app/ops-analysis/(pages)/view/screen/utils/layoutUtils';
import { buildFiltersFromNodes } from '@/app/ops-analysis/(pages)/view/topology/utils/namespaceUtils';
import type {
  DashboardLayoutItem,
  FilterBindings,
} from '@/app/ops-analysis/types/dashBoard';
import type { ParamItem } from '@/app/ops-analysis/types/dataSource';
import type { ScreenViewSets } from '@/app/ops-analysis/types/screen';

const FILTER_ID = 'organization__string';

const organizationParam: ParamItem = {
  name: 'organization',
  alias_name: '组织',
  type: 'string',
  filterType: 'filter',
  value: null,
};

const keysOf = (definitions: { key: string }[]) => definitions.map((item) => item.key);

const dashboardLayout = (
  bindings: Array<FilterBindings | undefined>,
): DashboardLayoutItem[] =>
  bindings.map((filterBindings, index) => ({
    i: `widget-${index}`,
    x: 0,
    y: index,
    w: 4,
    h: 4,
    name: `组件 ${index}`,
    valueConfig: {
      chartType: 'single',
      dataSourceParams: [organizationParam],
      ...(filterBindings ? { filterBindings } : {}),
    },
  }));

const discoverDashboard = (bindings: Array<FilterBindings | undefined>) =>
  buildFiltersFromDashboardLayout({
    layout: dashboardLayout(bindings),
    previousDefinitions: [],
    dataSources: [],
  });

const screenView = (bindings: Array<FilterBindings | undefined>): ScreenViewSets => ({
  viewport: { width: 1920, height: 1080, adapter: 'fill' },
  decorations: {},
  items: bindings.map((filterBindings, index) => ({
    id: `screen-${index}`,
    type: 'widget' as const,
    chartType: 'single' as const,
    title: `组件 ${index}`,
    x: 0,
    y: index,
    w: 200,
    h: 120,
    zIndex: index + 1,
    valueConfig: {
      chartType: 'single' as const,
      dataSourceParams: [organizationParam],
      ...(filterBindings ? { filterBindings } : {}),
    },
  })),
});

const discoverScreen = (bindings: Array<FilterBindings | undefined>) =>
  buildFiltersFromScreenItems({
    viewSets: screenView(bindings),
    previousDefinitions: [],
    dataSources: [],
  });

const discoverTopology = (bindings: Array<FilterBindings | undefined>) =>
  buildFiltersFromNodes(
    {
      getNodes: () =>
        bindings.map((filterBindings) => ({
          getData: () => ({
            type: 'single-value',
            valueConfig: {
              dataSourceParams: [organizationParam],
              ...(filterBindings ? { filterBindings } : {}),
            },
          }),
        })),
    } as never,
    [],
    [],
  );

describe('canvas filter chips follow widget bindings', () => {
  it('hides the chip when every widget explicitly opts out', () => {
    const unbound = [{ [FILTER_ID]: false }, { [FILTER_ID]: false }] as FilterBindings[];
    expect(keysOf(discoverDashboard(unbound))).toEqual([]);
    expect(keysOf(discoverScreen(unbound))).toEqual([]);
    expect(keysOf(discoverTopology(unbound))).toEqual([]);
  });

  it('keeps the chip when one widget still follows', () => {
    const mixed = [
      { [FILTER_ID]: false },
      { [FILTER_ID]: true },
    ] as FilterBindings[];
    expect(keysOf(discoverDashboard(mixed))).toEqual(['organization']);
    expect(keysOf(discoverScreen(mixed))).toEqual(['organization']);
    expect(keysOf(discoverTopology(mixed))).toEqual(['organization']);
  });

  it('keeps the chip when widget bindings are missing', () => {
    expect(keysOf(discoverDashboard([undefined, undefined]))).toEqual(['organization']);
    expect(keysOf(discoverScreen([undefined]))).toEqual(['organization']);
    expect(keysOf(discoverTopology([undefined]))).toEqual(['organization']);
    const partial = [undefined, { [FILTER_ID]: false }] as Array<FilterBindings | undefined>;
    expect(keysOf(discoverDashboard(partial))).toEqual(['organization']);
    expect(keysOf(discoverScreen(partial))).toEqual(['organization']);
    expect(keysOf(discoverTopology(partial))).toEqual(['organization']);
  });

  it('keeps explicit opt-outs after sync so the chip does not return', () => {
    const layout = dashboardLayout([
      { [FILTER_ID]: false },
      { [FILTER_ID]: false },
    ]);
    const dropped = discoverDashboard([
      { [FILTER_ID]: false },
      { [FILTER_ID]: false },
    ]);
    const synced = syncDashboardLayoutFilterBindings(layout, dropped, []);
    expect(synced.map((item) => (
      'valueConfig' in item ? item.valueConfig?.filterBindings : undefined
    ))).toEqual([
      { [FILTER_ID]: false },
      { [FILTER_ID]: false },
    ]);
    expect(keysOf(buildFiltersFromDashboardLayout({
      layout: synced,
      previousDefinitions: dropped,
      dataSources: [],
    }))).toEqual([]);

    const screen = screenView([
      { [FILTER_ID]: false },
      { [FILTER_ID]: true },
    ]);
    const screenFilters = discoverScreen([
      { [FILTER_ID]: false },
      { [FILTER_ID]: true },
    ]);
    const syncedScreen = syncScreenFilterBindings(screen, screenFilters, []);
    expect(syncedScreen.items.map((item) => item.valueConfig?.filterBindings)).toEqual([
      { [FILTER_ID]: false },
      { [FILTER_ID]: true },
    ]);
    expect(keysOf(buildFiltersFromScreenItems({
      viewSets: syncedScreen,
      previousDefinitions: screenFilters,
      dataSources: [],
    }))).toEqual(['organization']);
  });
});
