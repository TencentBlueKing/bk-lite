import assert from 'node:assert/strict';
import test from 'node:test';

import type { DashboardLayoutItem, UnifiedFilterDefinition } from '@/app/ops-analysis/types/dashBoard';
import { applyDashboardProposal, proposalTargetsDashboard } from '../applyDashboardProposal';

const allocateId = (preferred: string | undefined, used: Set<string>) => {
  if (preferred && !used.has(preferred)) return preferred;
  let index = 1;
  while (used.has(`new-${index}`)) index += 1;
  return `new-${index}`;
};

const layout = (): DashboardLayoutItem[] => [
  {
    i: 'group-1',
    itemType: 'group',
    x: 0,
    y: 0,
    w: 12,
    h: 4,
    name: '分组',
  },
  {
    i: 'card-1',
    x: 0,
    y: 0,
    w: 3,
    h: 2,
    groupId: 'group-1',
    name: '资产总数',
    valueConfig: {
      chartType: 'single',
      dataSource: 23,
      selectedFields: ['value'],
      decimalPlaces: 0,
      thresholdColors: [{ value: '10', color: 'red' }],
      dataSourceParams: [{ name: 'organization_id', alias_name: '组织', value: 'org-001' }],
      filterBindings: { filter_organization: true },
    },
  },
  {
    i: 'topo-1',
    x: 0,
    y: 6,
    w: 12,
    h: 8,
    name: '网络拓扑',
    valueConfig: { chartType: 'networkStatusTopology', sceneWidgetType: 'networkStatusTopology' },
  },
];

const filters = (): UnifiedFilterDefinition[] => [
  {
    id: 'filter_organization',
    key: 'organization_id',
    name: '组织',
    type: 'string',
    defaultValue: 'org-001',
    order: 0,
    enabled: true,
    inputConfig: {
      control: 'select',
      optionsSource: { type: 'dynamic', sourceId: 35, valueField: 'id', labelField: 'name' },
    },
  },
];

test('keeps stored config when the contract matches and overlays written format fields', () => {
  const result = applyDashboardProposal({
    layout: layout(),
    filters: filters(),
    filterValues: { filter_organization: 'org-live' },
    allocateId,
    proposal: {
      schemaVersion: '1.0',
      dashboardId: 'current',
      layout: [{
        i: 'card-1',
        x: 1,
        name: '资产总量',
        valueConfig: {
          chartType: 'single',
          dataSource: 23,
          selectedFields: ['value'],
          decimalPlaces: 2,
          dataSourceParams: [{ name: 'organization_id', alias_name: '组织', value: 'org-001' }],
          filterBindings: { filter_organization: true },
        },
      }],
      filters: filters(),
    },
  });

  assert.equal(result.ok, true);
  if (!result.ok) return;
  const card = result.layout.find((item) => item.i === 'card-1');
  assert.ok(card && 'valueConfig' in card);
  if (!card || !('valueConfig' in card)) return;
  assert.equal(card.name, '资产总量');
  assert.equal(card.x, 1);
  assert.equal(card.y, 0);
  assert.equal(card.groupId, 'group-1');
  assert.equal(card.valueConfig?.decimalPlaces, 2);
  assert.deepEqual(card.valueConfig?.thresholdColors, [{ value: '10', color: 'red' }]);
  assert.ok(result.layout.some((item) => item.i === 'group-1'));
  assert.ok(result.layout.some((item) => item.i === 'topo-1'));
  assert.equal(result.filterValues.filter_organization, 'org-live');
});

test('replaces the widget config when the chart contract changes and drops omitted datasource widgets', () => {
  const result = applyDashboardProposal({
    layout: layout(),
    filters: filters(),
    filterValues: { filter_organization: 'org-live' },
    allocateId,
    proposal: {
      schemaVersion: '1.0',
      layout: [{
        i: 'card-1',
        valueConfig: { chartType: 'pie', dataSource: 24, dimensionField: 'type', valueField: 'count' },
      }],
      filters: [],
    },
  });

  assert.equal(result.ok, true);
  if (!result.ok) return;
  const card = result.layout.find((item) => item.i === 'card-1');
  assert.equal(card && 'valueConfig' in card && card.valueConfig?.chartType, 'pie');
  assert.equal(card && 'valueConfig' in card && card.valueConfig?.decimalPlaces, undefined);
  assert.equal(result.filters.length, 0);
  assert.equal(result.filterValues.filter_organization, undefined);
  assert.ok(result.layout.some((item) => item.i === 'topo-1'));
});

test('adds a root widget and switches the current filter value when the default changes', () => {
  const result = applyDashboardProposal({
    layout: layout(),
    filters: filters(),
    filterValues: { filter_organization: 'org-live' },
    allocateId,
    proposal: {
      schemaVersion: '1.0',
      layout: [
        {
          i: 'card-1',
          valueConfig: {
            chartType: 'single',
            dataSource: 23,
            selectedFields: ['value'],
            filterBindings: { filter_organization: true },
            dataSourceParams: [{ name: 'organization_id', alias_name: '组织', value: 'org-001' }],
          },
        },
        {
          i: 'pie-1',
          x: 3,
          y: 0,
          w: 4,
          h: 4,
          name: '类型分布',
          valueConfig: { chartType: 'pie', dataSource: 24 },
        },
      ],
      filters: [{ ...filters()[0], defaultValue: 'org-002' }],
    },
  });

  assert.equal(result.ok, true);
  if (!result.ok) return;
  const pie = result.layout.find((item) => item.i === 'pie-1');
  assert.equal(pie && 'groupId' in pie && pie.groupId, null);
  assert.equal(result.filterValues.filter_organization, 'org-002');
});

test('rejects a proposal whose schema version is not 1.0', () => {
  const result = applyDashboardProposal({
    layout: [],
    filters: [],
    filterValues: {},
    allocateId,
    proposal: { schemaVersion: '2.0', layout: [], filters: [] },
  });
  assert.deepEqual(result, { ok: false, reason: 'schema' });
});

test('matches widgets written with id and treats omitted filters as an empty set', () => {
  const result = applyDashboardProposal({
    layout: layout(),
    filters: filters(),
    filterValues: { filter_organization: 'org-live' },
    allocateId,
    proposal: {
      schemaVersion: '1.0',
      layout: [{
        id: 'card-1',
        valueConfig: {
          chartType: 'single',
          dataSource: 23,
          selectedFields: ['value'],
          dataSourceParams: [{ name: 'organization_id', value: 'org-001' }],
          filterBindings: { filter_organization: true },
        },
      }],
    },
  });

  assert.equal(result.ok, true);
  if (!result.ok) return;
  assert.equal(result.layout.filter((item) => item.i === 'card-1').length, 1);
  assert.equal(result.filters.length, 0);
  assert.ok(result.layout.some((item) => item.i === 'topo-1'));
});

test('packs a fresh proposal into three widgets per row', () => {
  const result = applyDashboardProposal({
    layout: [],
    filters: [],
    filterValues: {},
    allocateId,
    proposal: {
      schemaVersion: '1.0',
      layout: [
        { i: 'a', valueConfig: { chartType: 'line', dataSource: 1 } },
        { i: 'b', valueConfig: { chartType: 'line', dataSource: 2 } },
        { i: 'c', valueConfig: { chartType: 'line', dataSource: 3 } },
        { i: 'd', valueConfig: { chartType: 'pie', dataSource: 4 } },
      ],
      filters: [],
    },
  });

  assert.equal(result.ok, true);
  if (!result.ok) return;
  assert.deepEqual(
    result.layout.map((item) => [item.i, item.x, item.y, item.w, item.h]),
    [
      ['a', 0, 0, 8, 6],
      ['b', 8, 0, 8, 6],
      ['c', 16, 0, 8, 6],
      ['d', 0, 6, 8, 6],
    ],
  );
});

test('applies page settings only when the proposal names them', () => {
  const result = applyDashboardProposal({
    layout: [],
    filters: [],
    filterValues: {},
    allocateId,
    proposal: {
      schemaVersion: '1.0',
      layout: [{ i: 'a', valueConfig: { chartType: 'single', dataSource: 1, selectedFields: ['pct'], unitId: 'percent', decimalPlaces: 2 } }],
      filters: [],
      otherConfig: { displayMode: 'compact' },
      refreshInterval: 60000,
    },
  });

  assert.equal(result.ok, true);
  if (!result.ok) return;
  assert.deepEqual(result.otherConfig, { displayMode: 'compact' });
  assert.equal(result.refreshInterval, 60000);
  assert.equal(result.layout[0].valueConfig?.unitId, 'percent');

  const untouched = applyDashboardProposal({
    layout: [],
    filters: [],
    filterValues: {},
    allocateId,
    proposal: {
      schemaVersion: '1.0',
      layout: [{ i: 'a', valueConfig: { chartType: 'single', dataSource: 1 } }],
      filters: [],
      otherConfig: {},
      refreshInterval: 15,
    },
  });
  assert.equal(untouched.ok, true);
  if (!untouched.ok) return;
  assert.equal(untouched.otherConfig, undefined);
  assert.equal(untouched.refreshInterval, undefined);
});

const dynamicFilter = (
  id: string,
  key: string,
  queryParams: Record<string, unknown>,
): UnifiedFilterDefinition => ({
  id,
  key,
  name: key,
  type: 'string',
  defaultValue: null,
  order: 0,
  enabled: true,
  inputConfig: {
    control: 'select',
    optionsSource: {
      type: 'dynamic',
      sourceId: 9,
      valueField: 'id',
      labelField: 'name',
      queryParams,
    },
  },
});

const dynamicQuery = (filter: UnifiedFilterDefinition | undefined) => {
  const config = filter?.inputConfig;
  if (!config || config.control !== 'select' || config.optionsSource.type !== 'dynamic') return undefined;
  return config.optionsSource.queryParams;
};

test('drops concatenated query params and warns instead of storing them', () => {
  const result = applyDashboardProposal({
    layout: [{
      i: 'card-9',
      x: 0,
      y: 0,
      w: 4,
      h: 4,
      name: '设备',
      valueConfig: {
        chartType: 'single',
        dataSource: 9,
        dataSourceParams: [{
          name: 'device_id',
          alias_name: '设备',
          type: 'string',
          filterType: 'filter',
          value: null,
          inputConfig: {
            control: 'select',
            optionsSource: {
              type: 'dynamic',
              sourceId: 9,
              valueField: 'id',
              labelField: 'name',
              queryParams: { room_id: 'pre-$site$' },
            },
          },
        }],
      },
    }],
    filters: [],
    filterValues: {},
    allocateId,
    proposal: {
      schemaVersion: '1.0',
      layout: [{
        i: 'card-9',
        valueConfig: {
          chartType: 'single',
          dataSource: 9,
          dataSourceParams: [{
            name: 'device_id',
            alias_name: '设备',
            type: 'string',
            filterType: 'filter',
            value: null,
            inputConfig: {
              control: 'select',
              optionsSource: {
                type: 'dynamic',
                sourceId: 9,
                valueField: 'id',
                labelField: 'name',
                queryParams: { room_id: 'pre-$site$' },
              },
            },
          }],
        },
      }],
      filters: [dynamicFilter('device_id__string', 'device_id', { room_id: 'pre-$site$' })],
    },
  });

  assert.equal(result.ok, true);
  if (!result.ok) return;
  assert.equal(dynamicQuery(result.filters[0]), undefined);
  assert.ok(result.warnings?.includes('filter:device_id:concat'));
  const card = result.layout.find((item) => item.i === 'card-9');
  const param = card && 'valueConfig' in card
    ? card.valueConfig?.dataSourceParams?.[0]
    : undefined;
  const paramConfig = param?.inputConfig;
  assert.equal(
    paramConfig && paramConfig.control === 'select' && paramConfig.optionsSource.type === 'dynamic'
      ? paramConfig.optionsSource.queryParams
      : 'kept',
    undefined,
  );
  assert.ok(result.warnings?.includes('param:device_id:concat'));
});

test('drops a query-param cycle with the same validator and warns', () => {
  const result = applyDashboardProposal({
    layout: [],
    filters: [],
    filterValues: {},
    allocateId,
    proposal: {
      schemaVersion: '1.0',
      layout: [],
      filters: [
        dynamicFilter('device_id__string', 'device_id', { rack_id: { ref: 'rack_id' } }),
        dynamicFilter('rack_id__string', 'rack_id', { device_id: { ref: 'device_id' } }),
      ],
    },
  });

  assert.equal(result.ok, true);
  if (!result.ok) return;
  assert.equal(dynamicQuery(result.filters[0]), undefined);
  assert.equal(dynamicQuery(result.filters[1]), undefined);
  assert.ok(result.warnings?.includes('graph:cycle'));
});

test('drops a query-param chain longer than three nodes and warns', () => {
  const result = applyDashboardProposal({
    layout: [],
    filters: [],
    filterValues: {},
    allocateId,
    proposal: {
      schemaVersion: '1.0',
      layout: [],
      filters: [
        dynamicFilter('room_id__string', 'room_id', {}),
        dynamicFilter('device_id__string', 'device_id', { room_id: { ref: 'room_id' } }),
        dynamicFilter('rack_id__string', 'rack_id', { device_id: { ref: 'device_id' } }),
        dynamicFilter('port_id__string', 'port_id', { rack_id: { ref: 'rack_id' } }),
      ],
    },
  });

  assert.equal(result.ok, true);
  if (!result.ok) return;
  assert.ok(result.warnings?.includes('graph:depth'));
  assert.deepEqual(dynamicQuery(result.filters.find((item) => item.key === 'device_id')), {
    room_id: { ref: 'room_id' },
  });
  assert.deepEqual(dynamicQuery(result.filters.find((item) => item.key === 'rack_id')), {
    device_id: { ref: 'device_id' },
  });
  assert.equal(dynamicQuery(result.filters.find((item) => item.key === 'port_id')), undefined);
});

test('keeps legal filter prefixes and reports every graph problem', () => {
  const flag = dynamicFilter('flag__boolean', 'flag', {});
  flag.type = 'boolean' as UnifiedFilterDefinition['type'];
  const result = applyDashboardProposal({
    layout: [],
    filters: [],
    filterValues: {},
    allocateId,
    proposal: {
      schemaVersion: '1.0',
      layout: [],
      filters: [
        dynamicFilter('room_id__string', 'room_id', {}),
        dynamicFilter('device_id__string', 'device_id', { room_id: { ref: 'room_id' } }),
        dynamicFilter('rack_id__string', 'rack_id', { device_id: { ref: 'device_id' } }),
        dynamicFilter('port_id__string', 'port_id', {
          rack_id: { ref: 'rack_id' },
          note: 'stay',
          room_id: { ref: 'room_id' },
        }),
        dynamicFilter('left__string', 'left', { peer: { ref: 'right' } }),
        dynamicFilter('right__string', 'right', { peer: { ref: 'left' }, fixed: 1 }),
        dynamicFilter('typed__string', 'typed', { flag: { ref: 'flag' }, kept: 'yes' }),
        flag,
      ],
    },
  });

  assert.equal(result.ok, true);
  if (!result.ok) return;
  assert.deepEqual(dynamicQuery(result.filters.find((item) => item.key === 'rack_id')), {
    device_id: { ref: 'device_id' },
  });
  assert.deepEqual(dynamicQuery(result.filters.find((item) => item.key === 'port_id')), {
    note: 'stay',
    room_id: { ref: 'room_id' },
  });
  assert.equal(dynamicQuery(result.filters.find((item) => item.key === 'left')), undefined);
  assert.deepEqual(dynamicQuery(result.filters.find((item) => item.key === 'right')), { fixed: 1 });
  assert.deepEqual(dynamicQuery(result.filters.find((item) => item.key === 'typed')), { kept: 'yes' });
  assert.ok(result.warnings?.includes('graph:depth'));
  assert.ok(result.warnings?.includes('graph:cycle'));
  assert.ok(result.warnings?.includes('graph:type'));
});

const selectParam = (
  name: string,
  queryParams: Record<string, unknown> | undefined,
  componentSwitch?: boolean,
) => ({
  name,
  alias_name: name,
  type: 'string',
  filterType: 'params' as const,
  value: null,
  inputConfig: {
    control: 'select' as const,
    ...(componentSwitch ? { componentSwitch: true } : {}),
    optionsSource: {
      type: 'dynamic' as const,
      sourceId: 9,
      valueField: 'id',
      labelField: 'name',
      ...(queryParams ? { queryParams } : {}),
    },
  },
});

const proposalWidget = (id: string, params: ReturnType<typeof selectParam>[]) => ({
  i: id,
  valueConfig: {
    chartType: 'line',
    dataSource: 9,
    dataSourceParams: params,
  },
});

const widgetParamQuery = (
  layoutItems: DashboardLayoutItem[],
  widgetId: string,
  name: string,
) => {
  const card = layoutItems.find((item) => item.i === widgetId);
  if (!card || !('valueConfig' in card)) return 'missing-widget';
  const param = card.valueConfig?.dataSourceParams?.find((item) => item.name === name);
  const config = param?.inputConfig;
  if (!config || config.control !== 'select' || config.optionsSource.type !== 'dynamic') return undefined;
  return config.optionsSource.queryParams;
};

test('drops illegal component-param query graphs and keeps a three-node chain', () => {
  const result = applyDashboardProposal({
    layout: [],
    filters: [],
    filterValues: {},
    allocateId,
    proposal: {
      schemaVersion: '1.0',
      layout: [
        proposalWidget('deep', [
          selectParam('room', undefined),
          selectParam('device', { room: { ref: 'room' } }),
          selectParam('rack', { device: { ref: 'device' } }),
          selectParam('port', { rack: { ref: 'rack' } }),
          selectParam('note', { label: 'kept' }),
        ]),
        proposalWidget('cycle', [
          selectParam('left', { peer: { ref: 'right' } }),
          selectParam('right', { peer: { ref: 'left' } }),
        ]),
        proposalWidget('ok', [
          selectParam('room', undefined),
          selectParam('device', { room: { ref: 'room' } }),
          selectParam('rack', { device: { ref: 'device' } }),
        ]),
        proposalWidget('foreign', [
          selectParam('device', { secret: { ref: 'secret' } }),
        ]),
      ],
      filters: [dynamicFilter('flag__boolean', 'flag', {})],
    },
  });

  assert.equal(result.ok, true);
  if (!result.ok) return;
  assert.equal(widgetParamQuery(result.layout, 'deep', 'port'), undefined);
  assert.deepEqual(widgetParamQuery(result.layout, 'deep', 'device'), { room: { ref: 'room' } });
  assert.deepEqual(widgetParamQuery(result.layout, 'deep', 'rack'), { device: { ref: 'device' } });
  assert.equal(widgetParamQuery(result.layout, 'deep', 'note')?.label, 'kept');
  assert.equal(widgetParamQuery(result.layout, 'cycle', 'left'), undefined);
  assert.equal(widgetParamQuery(result.layout, 'cycle', 'right'), undefined);
  assert.deepEqual(widgetParamQuery(result.layout, 'ok', 'rack'), { device: { ref: 'device' } });
  assert.equal(widgetParamQuery(result.layout, 'foreign', 'device'), undefined);
  assert.ok(result.warnings?.includes('param:port:depth'));
  assert.ok(result.warnings?.includes('param:left:cycle'));
  assert.ok(result.warnings?.includes('param:device:missing'));
});

test('keeps a component prefix and reports every problem on the same widget', () => {
  const flag = dynamicFilter('flag__boolean', 'flag', {});
  flag.type = 'boolean' as UnifiedFilterDefinition['type'];
  const result = applyDashboardProposal({
    layout: [],
    filters: [],
    filterValues: {},
    allocateId,
    proposal: {
      schemaVersion: '1.0',
      layout: [
        proposalWidget('mixed', [
          selectParam('room', undefined),
          selectParam('device', { room: { ref: 'room' } }),
          selectParam('rack', { device: { ref: 'device' } }),
          selectParam('port', { rack: { ref: 'rack' }, note: 'stay', room: { ref: 'room' } }),
          selectParam('left', { peer: { ref: 'right' } }),
          selectParam('right', { peer: { ref: 'left' }, fixed: 1 }),
          selectParam('typed', { flag: { ref: 'flag' }, kept: 'yes' }),
        ]),
      ],
      filters: [flag],
    },
  });

  assert.equal(result.ok, true);
  if (!result.ok) return;
  assert.deepEqual(widgetParamQuery(result.layout, 'mixed', 'device'), { room: { ref: 'room' } });
  assert.deepEqual(widgetParamQuery(result.layout, 'mixed', 'rack'), { device: { ref: 'device' } });
  assert.deepEqual(widgetParamQuery(result.layout, 'mixed', 'port'), {
    note: 'stay',
    room: { ref: 'room' },
  });
  assert.equal(widgetParamQuery(result.layout, 'mixed', 'left'), undefined);
  assert.deepEqual(widgetParamQuery(result.layout, 'mixed', 'right'), { fixed: 1 });
  assert.deepEqual(widgetParamQuery(result.layout, 'mixed', 'typed'), { kept: 'yes' });
  assert.ok(result.warnings?.includes('param:port:depth'));
  assert.ok(result.warnings?.includes('param:left:cycle'));
  assert.ok(result.warnings?.includes('param:right:cycle'));
  assert.ok(result.warnings?.includes('param:typed:type'));
});

test('drops a component-param reference to an unbindable type and turns off component switch', () => {
  const flag = dynamicFilter('flag__boolean', 'flag', {});
  flag.type = 'boolean' as UnifiedFilterDefinition['type'];
  const result = applyDashboardProposal({
    layout: [],
    filters: [],
    filterValues: {},
    allocateId,
    proposal: {
      schemaVersion: '1.0',
      layout: [
        proposalWidget('typed', [
          selectParam('device', { flag: { ref: 'flag' } }, true),
        ]),
        proposalWidget('switch', [
          selectParam('device', { room_id: { ref: 'room_id' } }, true),
        ]),
      ],
      filters: [
        flag,
        dynamicFilter('room_id__string', 'room_id', {}),
      ],
    },
  });

  assert.equal(result.ok, true);
  if (!result.ok) return;
  assert.equal(widgetParamQuery(result.layout, 'typed', 'device'), undefined);
  assert.ok(result.warnings?.includes('param:device:type'));
  assert.deepEqual(widgetParamQuery(result.layout, 'switch', 'device'), { room_id: { ref: 'room_id' } });
  const card = result.layout.find((item) => item.i === 'switch');
  const param = card && 'valueConfig' in card
    ? card.valueConfig?.dataSourceParams?.find((item) => item.name === 'device')
    : undefined;
  const config = param?.inputConfig;
  assert.equal(config && config.control === 'select' ? config.componentSwitch : 'missing-config', undefined);
});

test('keeps a component-param ref when its name matches a global filter key', () => {
  const result = applyDashboardProposal({
    layout: [],
    filters: [],
    filterValues: {},
    allocateId,
    proposal: {
      schemaVersion: '1.0',
      layout: [
        proposalWidget('card', [
          selectParam('site_id', undefined),
          selectParam('device_id', { room_id: { ref: 'site_id' } }),
          selectParam('rack_id', { room_id: { ref: 'site_id__string' } }),
        ]),
      ],
      filters: [dynamicFilter('site_id__string', 'site_id', {})],
    },
  });

  assert.equal(result.ok, true);
  if (!result.ok) return;
  assert.deepEqual(widgetParamQuery(result.layout, 'card', 'device_id'), {
    room_id: { ref: 'site_id' },
  });
  assert.deepEqual(widgetParamQuery(result.layout, 'card', 'rack_id'), {
    room_id: { ref: 'site_id__string' },
  });
  assert.equal(result.warnings?.some((warning) => warning.includes('ambiguous')) ?? false, false);
});

test('directory node id matches the open dashboard numeric id', () => {
  assert.equal(proposalTargetsDashboard('current', 426), true);
  assert.equal(proposalTargetsDashboard('dashboard_426', 426), true);
  assert.equal(proposalTargetsDashboard(426, 426), true);
  assert.equal(proposalTargetsDashboard('dashboard_419', 426), false);
  assert.equal(proposalTargetsDashboard('dashboard_426', undefined), false);
});

