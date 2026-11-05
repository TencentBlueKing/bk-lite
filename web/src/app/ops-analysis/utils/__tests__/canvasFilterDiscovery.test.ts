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
  UnifiedFilterDefinition,
} from '@/app/ops-analysis/types/dashBoard';
import type { DatasourceItem, InputControlConfig, ParamItem } from '@/app/ops-analysis/types/dataSource';
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

const dynamicSource = (
  restApi: string,
  queryParams?: Record<string, { ref: string }>,
): InputControlConfig => ({
  control: 'select',
  optionsSource: {
    type: 'dynamic',
    sourceRef: { type: 'rest_api', value: restApi },
    valueField: 'id',
    labelField: 'name',
    ...(queryParams ? { queryParams } : {}),
  },
});

const filterParam = (
  name: string,
  alias: string,
  inputConfig: InputControlConfig,
): ParamItem => ({
  name,
  alias_name: alias,
  type: 'string',
  filterType: 'filter',
  value: '',
  inputConfig,
});

const chartSource = (
  id: number,
  name: string,
  params: ParamItem[],
): DatasourceItem => ({
  id,
  name,
  rest_api: name,
  desc: '',
  params,
  chart_type: ['line'],
  namespaces: [],
} as DatasourceItem);

const chartLayout = (
  widgets: Array<{ dataSource: number; params: ParamItem[] }>,
): DashboardLayoutItem[] => widgets.map((widget, index) => ({
  i: `chart-${index}`,
  x: 0,
  y: index,
  w: 4,
  h: 4,
  name: `图 ${index}`,
  valueConfig: {
    chartType: 'line',
    dataSource: widget.dataSource,
    dataSourceParams: widget.params,
  },
}));

const queryRef = (definition: UnifiedFilterDefinition | undefined, name: string) => {
  const config = definition?.inputConfig;
  if (!config || config.control !== 'select' || config.optionsSource.type !== 'dynamic') return undefined;
  const value = config.optionsSource.queryParams?.[name];
  return value && typeof value === 'object' && 'ref' in value ? value.ref : undefined;
};

describe('same data source filter discovery', () => {
  it('builds one definition when two charts share a data source id', () => {
    const catalog = filterParam(
      'object_id',
      '监控对象',
      dynamicSource('demo/accept_monitor_objects'),
    );
    const drifted = filterParam(
      'object_id',
      '监控对象',
      dynamicSource('demo/accept_monitor_objects', { object_id: { ref: 'object_id' } }),
    );
    const filters = buildFiltersFromDashboardLayout({
      layout: chartLayout([
        { dataSource: 7, params: [drifted] },
        { dataSource: 7, params: [catalog] },
      ]),
      previousDefinitions: [],
      dataSources: [chartSource(7, '验收·级联指标图', [catalog])],
    });

    expect(filters.map((item) => item.id)).toEqual(['object_id__string']);
    expect(queryRef(filters[0], 'object_id')).toBeUndefined();
  });

  it('writes a bare ref to the single same-name row', () => {
    const objectCatalog = (restApi: string) => filterParam(
      'object_id',
      '监控对象',
      dynamicSource(restApi),
    );
    const metricCatalog = (restApi: string) => filterParam(
      'metric_id',
      '指标',
      dynamicSource(restApi, { object_id: { ref: 'object_id' } }),
    );
    const sourceA = chartSource(1, 'cmdb/chart', [
      objectCatalog('cmdb/objects'),
      metricCatalog('cmdb/metrics'),
    ]);
    const sourceB = chartSource(2, 'monitor/chart', [
      objectCatalog('monitor/objects'),
      metricCatalog('monitor/metrics'),
    ]);
    const filters = buildFiltersFromDashboardLayout({
      layout: chartLayout([
        { dataSource: 1, params: sourceA.params },
        { dataSource: 2, params: sourceB.params },
      ]),
      previousDefinitions: [],
      dataSources: [sourceA, sourceB],
    });
    const sourceOf = (definition: UnifiedFilterDefinition) => {
      const config = definition.inputConfig;
      if (!config || config.control !== 'select' || config.optionsSource.type !== 'dynamic') return '';
      return config.optionsSource.sourceRef?.value ?? '';
    };
    const objectRow = filters.find((item) => item.key === 'object_id');
    const metricRow = filters.find((item) => item.key === 'metric_id');
    expect(filters.filter((item) => item.key === 'object_id')).toHaveLength(1);
    expect(filters.filter((item) => item.key === 'metric_id')).toHaveLength(1);
    expect(objectRow?.id).toBe('object_id__string');
    expect(metricRow?.id).toBe('metric_id__string');
    expect(objectRow?.name).toBe('监控对象');
    expect(metricRow?.name).toBe('指标');
    expect(sourceOf(objectRow)).toBe('cmdb/objects');
    expect(sourceOf(metricRow)).toBe('cmdb/metrics');
    expect(queryRef(metricRow, 'object_id')).toBe('object_id__string');
  });

  it('keeps the configured cascade when a second chart uses another metric universe', () => {
    const object = filterParam('object_id', '监控对象', dynamicSource('demo/accept_monitor_objects'));
    const metricA = filterParam(
      'metric_id',
      '指标',
      dynamicSource('demo/accept_metrics', { object_id: { ref: 'object_id__string' } }),
    );
    const metricB = filterParam(
      'metric_id',
      '指标',
      dynamicSource('demo/accept_metrics_b', { object_id: { ref: 'object_id' } }),
    );
    const instance = filterParam(
      'instance_id',
      '实例',
      dynamicSource('demo/accept_instances', {
        object_id: { ref: 'object_id' },
        metric_id: { ref: 'metric_id__string' },
      }),
    );
    const sourceA = chartSource(1, '验收·级联指标图', [object, metricA, instance]);
    const sourceB = chartSource(2, '验收·级联指标图 B', [object, metricB, instance]);
    const previous: UnifiedFilterDefinition[] = [
      {
        id: 'object_id__string',
        key: 'object_id',
        name: '监控对象',
        type: 'string',
        defaultValue: null,
        order: 0,
        enabled: true,
        inputConfig: object.inputConfig,
      },
      {
        id: 'metric_id__string',
        key: 'metric_id',
        name: '指标',
        type: 'string',
        defaultValue: null,
        order: 1,
        enabled: true,
        inputConfig: metricA.inputConfig,
      },
      {
        id: 'instance_id__string',
        key: 'instance_id',
        name: '实例',
        type: 'string',
        defaultValue: null,
        order: 2,
        enabled: true,
        inputConfig: instance.inputConfig,
      },
    ];
    const filters = buildFiltersFromDashboardLayout({
      layout: chartLayout([
        { dataSource: 1, params: sourceA.params },
        { dataSource: 2, params: sourceB.params },
      ]),
      previousDefinitions: previous,
      dataSources: [sourceA, sourceB],
    });
    expect(filters.map((item) => item.id).sort()).toEqual([
      'instance_id__string',
      'metric_id__string',
      'object_id__string',
    ]);
    const metric = filters.find((item) => item.id === 'metric_id__string');
    const instanceRow = filters.find((item) => item.id === 'instance_id__string');
    expect(metric?.name).toBe('指标');
    expect(queryRef(metric, 'object_id')).toBe('object_id__string');
    expect(queryRef(instanceRow, 'metric_id')).toBe('metric_id__string');
    expect(queryRef(instanceRow, 'object_id')).toBe('object_id__string');
    const metricSource = metric?.inputConfig;
    expect(metricSource && metricSource.control === 'select' && metricSource.optionsSource.type === 'dynamic'
      ? metricSource.optionsSource.sourceRef?.value
      : undefined).toBe('demo/accept_metrics');

    const layout = chartLayout([
      { dataSource: 1, params: sourceA.params },
      { dataSource: 2, params: sourceB.params },
    ]);
    const synced = syncDashboardLayoutFilterBindings(layout, filters, [sourceA, sourceB]);
    synced.forEach((item) => {
      const bindings = item.valueConfig && 'filterBindings' in item.valueConfig
        ? item.valueConfig.filterBindings
        : undefined;
      expect(bindings?.object_id__string).toBe(true);
      expect(bindings?.metric_id__string).toBe(true);
      expect(bindings?.instance_id__string).toBe(true);
      expect(Object.keys(bindings || {}).some((id) => id.includes('__string__'))).toBe(false);
    });
  });

  it('rewrites query refs that still point at a retired summary id', () => {
    const object = filterParam('object_id', '监控对象', dynamicSource('cmdb/objects'));
    const metric = filterParam(
      'metric_id',
      '指标',
      dynamicSource('cmdb/metrics', { object_id: { ref: 'object_id__string__abcd1234' } }),
    );
    const source = chartSource(1, 'cmdb/chart', [object, metric]);
    const previous: UnifiedFilterDefinition[] = [
      {
        id: 'object_id__string__abcd1234',
        key: 'object_id',
        name: '监控对象',
        type: 'string',
        defaultValue: null,
        order: 0,
        enabled: true,
        inputConfig: object.inputConfig,
      },
      {
        id: 'metric_id__string__bbbbbbbb',
        key: 'metric_id',
        name: '指标',
        type: 'string',
        defaultValue: null,
        order: 1,
        enabled: true,
        inputConfig: metric.inputConfig,
      },
    ];
    const filters = buildFiltersFromDashboardLayout({
      layout: chartLayout([{ dataSource: 1, params: source.params }]),
      previousDefinitions: previous,
      dataSources: [source],
    });
    expect(filters.map((item) => item.id).sort()).toEqual([
      'metric_id__string',
      'object_id__string',
    ]);
    expect(queryRef(filters.find((item) => item.key === 'metric_id'), 'object_id'))
      .toBe('object_id__string');

    const componentParam: ParamItem = {
      name: 'zone_id',
      alias_name: '可用区',
      type: 'string',
      filterType: 'params',
      value: 'zone-old',
      inputConfig: dynamicSource('cmdb/zones', { object_id: { ref: 'object_id__string__abcd1234' } }),
    };
    const layout = chartLayout([{ dataSource: 1, params: [object, metric, componentParam] }]);
    const synced = syncDashboardLayoutFilterBindings(layout, filters, [source]);
    const card = synced[0];
    const stored = card.valueConfig && 'dataSourceParams' in card.valueConfig
      ? card.valueConfig.dataSourceParams?.find((item) => item.name === 'zone_id')
      : undefined;
    const storedConfig = stored?.inputConfig;
    const storedRef = storedConfig
      && storedConfig.control === 'select'
      && storedConfig.optionsSource.type === 'dynamic'
      ? storedConfig.optionsSource.queryParams?.object_id
      : undefined;
    expect(storedRef).toEqual({ ref: 'object_id__string' });
  });
});
