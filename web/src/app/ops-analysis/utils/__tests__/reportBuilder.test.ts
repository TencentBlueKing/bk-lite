import assert from 'node:assert/strict';
import test from 'node:test';

import {
  appendReportSection,
  beginReportLoad,
  canEnterReportEdit,
  createReportLoadGuard,
  invalidateReportLoads,
  isReportDraftDirty,
  isCurrentReportLoad,
  normalizeReportViewSets,
  removeReportSection,
  reorderReportSection,
  syncReportFiltersFromSections,
  updateReportSection,
} from '@/app/ops-analysis/utils/reportBuilder';
import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';
import { buildWidgetRequestParams } from '@/app/ops-analysis/utils/widgetDataTransform';

test('legacy empty report normalizes to schema version one', () => {
  assert.deepEqual(normalizeReportViewSets({}), {
    schema_version: 1,
    filters: [],
    sections: [],
  });
});

test('legacy report time_range is dropped while unified filter definitions are preserved', () => {
  const filter = {
    id: 'billing_period__dateRange',
    key: 'billing_period',
    name: '账期',
    type: 'dateRange' as const,
    order: 0,
    enabled: true,
  };
  assert.deepEqual(normalizeReportViewSets({ time_range: 60, filters: [filter] }).filters, [filter]);
  assert.equal('time_range' in normalizeReportViewSets({ time_range: 60 }), false);
});

test('explicit future report schema is rejected instead of downgraded', () => {
  assert.throws(
    () => normalizeReportViewSets({ schema_version: 2, sections: [] }),
    /schema_version/,
  );
});

test('a stale report response is invalid after the selection starts a newer load', () => {
  const guard = createReportLoadGuard();
  const reportARequest = beginReportLoad(guard);
  invalidateReportLoads(guard);
  const reportBRequest = beginReportLoad(guard);

  assert.equal(isCurrentReportLoad(guard, reportARequest), false);
  assert.equal(isCurrentReportLoad(guard, reportBRequest), true);
});

test('report edit is blocked until a successful load provides a save token', () => {
  const ready = {
    reportId: 12,
    isBuiltIn: false,
    savedVersion: '2026-08-17T07:00:00.000000Z',
    loading: false,
  };

  assert.equal(canEnterReportEdit(ready), true);
  assert.equal(canEnterReportEdit({ ...ready, savedVersion: '' }), false);
  assert.equal(canEnterReportEdit({ ...ready, loading: true }), false);
  assert.equal(canEnterReportEdit({ ...ready, isBuiltIn: true }), false);
  assert.equal(canEnterReportEdit({ ...ready, reportId: undefined }), false);
});

test('report dirty comparison follows persisted view sets', () => {
  const saved = normalizeReportViewSets({});
  const draft = {
    ...saved,
    filters: [{ id: 'env__string', key: 'env', name: '环境', type: 'string' as const, order: 0, enabled: true }],
  };

  assert.equal(isReportDraftDirty(saved, saved), false);
  assert.equal(isReportDraftDirty(saved, draft), true);
});

test('draft section operations preserve stable ids and only change the draft copy', () => {
  const saved = normalizeReportViewSets({
    sections: [
      { id: 'a', valueConfig: { chartType: 'table', dataSource: 1, name: 'A' } },
      { id: 'b', valueConfig: { chartType: 'eventTable', dataSource: 2, name: 'B' } },
    ],
  });
  const appended = appendReportSection(saved, {
    id: 'c',
    valueConfig: { chartType: 'table', dataSource: 3, name: 'C' },
  });
  const updated = updateReportSection(appended, 'a', {
    chartType: 'table',
    dataSource: 1,
    name: 'A2',
  });
  const reordered = reorderReportSection(updated, 'c', 'a');
  const removed = removeReportSection(reordered, 'b');

  assert.deepEqual(saved.sections.map((section) => section.id), ['a', 'b']);
  assert.deepEqual(removed.sections.map((section) => section.id), ['c', 'a']);
  assert.equal(removed.sections[1].valueConfig.name, 'A2');
});

test('report unified date filter is injected only through a matching enabled component binding', () => {
  const config = {
    chartType: 'table',
    dataSource: 7,
    dataSourceParams: [
      { name: 'billing_period', alias_name: '账期', type: 'dateRange', filterType: 'filter', value: null },
    ],
    filterBindings: { billing_period__dateRange: true },
  };
  const filterDefinitions = [
    { id: 'billing_period__dateRange', key: 'billing_period', name: '账期', type: 'dateRange' as const, order: 0, enabled: true },
  ];

  assert.deepEqual(buildWidgetRequestParams({
    config,
    unifiedFilterValues: { billing_period__dateRange: { rangeType: 'custom', startDate: '2026-08-01', endDate: '2026-08-17' } },
    filterBindings: config.filterBindings,
    filterDefinitions,
  }), { billing_period: ['2026-08-01', '2026-08-17'] });
});

test('adding a report table enables matching unified filters and component bindings by default', () => {
  const dataSources = [
    {
      id: 7,
      params: [
        { name: 'billing_period', alias_name: '账期', type: 'dateRange', filterType: 'filter', value: null },
        { name: 'org', alias_name: '组织', type: 'string', filterType: 'fixed', value: 'ops' },
      ],
    },
  ] as DatasourceItem[];
  const draft = syncReportFiltersFromSections(
    appendReportSection(normalizeReportViewSets({}), {
      id: 'table-1',
      valueConfig: { chartType: 'table', dataSource: 7, name: '账单表' },
    }),
    dataSources,
  );

  assert.deepEqual(draft.filters.map((definition) => ({
    id: definition.id,
    enabled: definition.enabled,
  })), [
    { id: 'billing_period__dateRange', enabled: true },
  ]);
  assert.deepEqual(draft.sections[0].valueConfig.filterBindings, {
    billing_period__dateRange: true,
  });
});

test('existing disabled report filter stays disabled when another matching table is added', () => {
  const dataSources = [
    {
      id: 7,
      params: [
        { name: 'env', alias_name: '环境', type: 'string', filterType: 'filter', value: null },
      ],
    },
  ] as DatasourceItem[];
  const existing = normalizeReportViewSets({
    filters: [
      { id: 'env__string', key: 'env', name: '环境', type: 'string', order: 0, enabled: false },
    ],
    sections: [
      {
        id: 'table-1',
        valueConfig: {
          chartType: 'table',
          dataSource: 7,
          name: 'A',
          filterBindings: { env__string: false },
        },
      },
    ],
  });
  const draft = syncReportFiltersFromSections(
    appendReportSection(existing, {
      id: 'table-2',
      valueConfig: { chartType: 'table', dataSource: 7, name: 'B' },
    }),
    dataSources,
  );

  assert.equal(draft.filters[0].enabled, false);
  assert.equal(draft.sections[0].valueConfig.filterBindings?.env__string, false);
  assert.equal(draft.sections[1].valueConfig.filterBindings?.env__string, true);
});
