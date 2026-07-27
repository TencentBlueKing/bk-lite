import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import type { UnifiedFilterDefinition } from '../src/app/ops-analysis/types/dashBoard';
import {
  getBindableFilterParams,
  getFilterDefinitionId,
} from '../src/app/ops-analysis/utils/widgetDataTransform';
import {
  buildResetFilterValues,
  hasInvalidDateRangeDefinitions,
  syncFilterValuesWithDefinitions,
} from '../src/app/ops-analysis/utils/unifiedFilterState';

const dateRangeDefault = { rangeType: 'last_30_days' } as const;
const dateRangeDefinition: UnifiedFilterDefinition = {
  id: 'period__dateRange',
  key: 'period',
  name: 'Period',
  type: 'dateRange',
  defaultValue: dateRangeDefault,
  order: 0,
  enabled: true,
};

const bindableParams = getBindableFilterParams([
  {
    name: 'period',
    alias_name: 'Period',
    type: 'dateRange',
    filterType: 'filter',
    value: { rangeType: 'last_7_days' },
  },
  {
    name: 'created_at',
    alias_name: 'Created at',
    type: 'timeRange',
    filterType: 'filter',
    value: null,
  },
  {
    name: 'keyword',
    alias_name: 'Keyword',
    type: 'string',
    filterType: 'filter',
    value: '',
  },
  {
    name: 'fixed_period',
    alias_name: 'Fixed period',
    type: 'dateRange',
    filterType: 'fixed',
    value: { rangeType: 'today' },
  },
]);

assert.deepEqual(
  bindableParams.map(({ name, type }) => ({ name, type })),
  [
    { name: 'period', type: 'dateRange' },
    { name: 'created_at', type: 'timeRange' },
    { name: 'keyword', type: 'string' },
  ],
);

assert.equal(hasInvalidDateRangeDefinitions([dateRangeDefinition]), false);
assert.equal(hasInvalidDateRangeDefinitions([{
  ...dateRangeDefinition,
  defaultValue: { rangeType: 'unknown' } as never,
}]), true);
assert.deepEqual(buildResetFilterValues([dateRangeDefinition]), {
  period__dateRange: { rangeType: 'last_30_days' },
});
assert.notStrictEqual(
  buildResetFilterValues([dateRangeDefinition]).period__dateRange,
  dateRangeDefinition.defaultValue,
);
assert.deepEqual(buildResetFilterValues([{
  ...dateRangeDefinition,
  defaultValue: { rangeType: 'unknown' } as never,
}]), {});
assert.equal(getFilterDefinitionId('period', 'dateRange'), 'period__dateRange');
assert.equal(getFilterDefinitionId('period', 'timeRange'), 'period__timeRange');
assert.notEqual(
  getFilterDefinitionId('period', 'dateRange'),
  getFilterDefinitionId('period', 'timeRange'),
);

const initializedValues = syncFilterValuesWithDefinitions(
  [dateRangeDefinition],
  {},
);
assert.deepEqual(initializedValues, {
  period__dateRange: { rangeType: 'last_30_days' },
});
assert.notStrictEqual(
  initializedValues.period__dateRange,
  dateRangeDefinition.defaultValue,
  'stored dateRange defaults must be copied as rules',
);

assert.deepEqual(
  syncFilterValuesWithDefinitions([dateRangeDefinition], {
    period__dateRange: null,
  }),
  { period__dateRange: null },
  'an explicitly cleared dateRange must remain null',
);

assert.deepEqual(
  syncFilterValuesWithDefinitions([
    {
      ...dateRangeDefinition,
      defaultValue: {
        rangeType: 'custom',
        startDate: '2026-07-17',
        endDate: '2026-07-01',
      },
    } as UnifiedFilterDefinition,
  ], {}),
  {},
  'invalid stored dateRange defaults must not enter runtime filter state',
);

const configModalSource = readFileSync(
  new URL('../src/app/ops-analysis/components/unifiedFilter/unifiedFilterConfigModal.tsx', import.meta.url),
  'utf8',
);
const filterBarSource = readFileSync(
  new URL('../src/app/ops-analysis/components/unifiedFilter/unifiedFilterBar.tsx', import.meta.url),
  'utf8',
);
const bindingPanelSource = readFileSync(
  new URL('../src/app/ops-analysis/components/unifiedFilter/filterBindingPanel.tsx', import.meta.url),
  'utf8',
);
const filterStateSource = readFileSync(
  new URL('../src/app/ops-analysis/utils/unifiedFilterState.ts', import.meta.url),
  'utf8',
);

for (const source of [configModalSource, filterBarSource]) {
  assert.match(source, /DateRangeSelector/);
  assert.match(source, /type\s*===?\s*['"]dateRange['"]|case\s+['"]dateRange['"]/);
}
assert.match(bindingPanelSource, /dateRange/);
assert.match(bindingPanelSource, /dashboard\.dateRange/);
assert.match(bindingPanelSource, /dateRange[^\n]+(?:purple|magenta|orange|cyan)/);
assert.match(configModalSource, /hasInvalidDateRangeDefinitions/);
assert.match(filterBarSource, /buildResetFilterValues/);
assert.doesNotMatch(filterStateSource, /resolveDateRange/);

console.log('ops analysis date range unified filter tests passed');
