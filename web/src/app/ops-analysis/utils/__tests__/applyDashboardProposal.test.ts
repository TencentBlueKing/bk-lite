import assert from 'node:assert/strict';
import test from 'node:test';

import type { DashboardLayoutItem, UnifiedFilterDefinition } from '@/app/ops-analysis/types/dashBoard';
import { applyDashboardProposal } from '../applyDashboardProposal';

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
      ['a', 0, 0, 4, 3],
      ['b', 4, 0, 4, 3],
      ['c', 8, 0, 4, 3],
      ['d', 0, 3, 4, 3],
    ],
  );
});

