import { describe, expect, it } from 'vitest';
import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';
import {
  nextReportViewSetsAfterLookup,
  normalizeReportViewSets,
  syncReportFiltersFromSections,
} from '@/app/ops-analysis/utils/reportBuilder';

const dataSources = [
  {
    id: 7,
    params: [
      { name: 'env', alias_name: '环境', type: 'string', filterType: 'filter', value: null },
    ],
  },
] as DatasourceItem[];

const current = normalizeReportViewSets({
  filters: [
    { id: 'env__string', key: 'env', name: '环境', type: 'string', order: 0, enabled: true },
  ],
  sections: [
    {
      id: 'table-1',
      valueConfig: {
        chartType: 'table',
        dataSource: 7,
        name: 'A',
        filterBindings: { env__string: true },
      },
    },
  ],
});

describe('report data source lookup apply', () => {
  it('keeps filters and bindings when the lookup was cancelled or belongs to another report', () => {
    expect(nextReportViewSetsAfterLookup(current, null, 'report-a', 'report-a')).toBe(current);
    expect(nextReportViewSetsAfterLookup(current, dataSources, 'report-a', 'report-b')).toBe(current);
    expect(current.sections[0].valueConfig.filterBindings).toEqual({ env__string: true });
  });

  it('still rewrites from a real empty detail response for the current report', () => {
    const emptied = syncReportFiltersFromSections(current, []);
    const applied = nextReportViewSetsAfterLookup(current, [], 'report-a', 'report-a');
    expect(applied).not.toBe(current);
    expect(applied.filters).toEqual(emptied.filters);
    expect(applied.sections[0].valueConfig.filterBindings).toEqual(
      emptied.sections[0].valueConfig.filterBindings,
    );
    expect(applied.filters.some((filter) => filter.id === 'env__string')).toBe(false);
  });

  it('keeps the binding when the current lookup returns the data source', () => {
    const applied = nextReportViewSetsAfterLookup(current, dataSources, 'report-a', 'report-a');
    expect(applied.sections[0].valueConfig.filterBindings).toEqual({ env__string: true });
    expect(applied.filters.map((filter) => filter.id)).toContain('env__string');
  });
});
