import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import {
  buildWidgetRequestParams,
  buildWidgetRequestSignatureParams,
  formatTimeRange,
  processDataSourceParams,
} from '../src/app/ops-analysis/utils/widgetDataTransform';
import { buildCompareRequestParams, canEnableCompare } from '../src/app/ops-analysis/utils/compareQuery';
import type { ParamItem } from '../src/app/ops-analysis/types/dataSource';

const resolutionContext = {
  referenceNow: '2026-07-17T03:08:00.176Z',
  timezone: 'Asia/Shanghai',
};

const dateRangeParam = (
  filterType: 'fixed' | 'filter' | 'params',
  value: unknown,
): ParamItem => ({
  name: 'period',
  alias_name: 'Period',
  type: 'dateRange' as const,
  filterType,
  value: value as ParamItem['value'],
});

assert.deepEqual(
  processDataSourceParams({
    sourceParams: [dateRangeParam('fixed', { rangeType: 'last_7_days' })],
    resolutionContext,
  }),
  { period: ['2026-07-11', '2026-07-17'] },
  'fixed dateRange resolves immediately before request',
);

const rendererSource = readFileSync(
  new URL('../src/app/ops-analysis/components/widgetDataRenderer.tsx', import.meta.url),
  'utf8',
);
assert.match(rendererSource, /dateRangeResolutionInputKey/);
for (const requestInput of [
  'dataSourceParams',
  'requestExtraParams',
  'unifiedFilterValues',
  'filterBindings',
  'filterDefinitions',
  'compare',
]) {
  assert.match(
    rendererSource,
    new RegExp(`dateRangeResolutionInputKey[\\s\\S]{0,600}${requestInput}`),
  );
}
assert.match(
  rendererSource,
  /dateRangeResolutionContext[\s\S]{0,300}dateRangeResolutionInputKey/,
);

assert.deepEqual(
  processDataSourceParams({
    sourceParams: [dateRangeParam('params', { rangeType: 'last_30_days' })],
    userParams: { period: { rangeType: 'last_7_days' } },
    resolutionContext,
  }),
  { period: ['2026-07-11', '2026-07-17'] },
  'component parameter value overrides the data-source default',
);

assert.deepEqual(
  processDataSourceParams({
    sourceParams: [dateRangeParam('params', { rangeType: 'last_30_days' })],
    userParams: { period: null },
    resolutionContext,
  }),
  {},
  'an explicit null component value is omitted without default fallback',
);

const filterDefinition = {
  id: 'period__dateRange',
  key: 'period',
  name: 'Period',
  type: 'dateRange' as const,
  label: 'Period',
  enabled: true,
  order: 0,
  defaultValue: { rangeType: 'last_30_days' as const },
};

assert.deepEqual(
  processDataSourceParams({
    sourceParams: [dateRangeParam('filter', { rangeType: 'last_90_days' })],
    unifiedFilterValues: {
      'period__dateRange': { rangeType: 'last_7_days' },
    },
    filterBindings: { 'period__dateRange': true },
    filterDefinitions: [filterDefinition],
    resolutionContext,
  }),
  { period: ['2026-07-11', '2026-07-17'] },
  'enabled unified filter overrides the configured filter value',
);

for (const unifiedValue of [null, { rangeType: 'unknown' }]) {
  assert.deepEqual(
    processDataSourceParams({
      sourceParams: [dateRangeParam('filter', { rangeType: 'last_7_days' })],
      unifiedFilterValues: { 'period__dateRange': unifiedValue as never },
      filterBindings: { 'period__dateRange': true },
      filterDefinitions: [filterDefinition],
      resolutionContext,
    }),
    {},
    'cleared or invalid unified values are omitted without fallback',
  );
}

assert.deepEqual(
  processDataSourceParams({
    sourceParams: [dateRangeParam('filter', { rangeType: 'last_7_days' })],
    unifiedFilterValues: {
      'period__dateRange': { rangeType: 'last_30_days' },
    },
    filterBindings: { 'period__dateRange': false },
    filterDefinitions: [filterDefinition],
    resolutionContext,
  }),
  {},
  'a disabled binding omits the parameter without fallback',
);

assert.deepEqual(
  processDataSourceParams({
    sourceParams: [dateRangeParam('filter', { rangeType: 'last_30_days' })],
    resolutionContext,
  }),
  { period: ['2026-06-18', '2026-07-17'] },
  'an unbound filter uses its configured default rule',
);

assert.deepEqual(
  processDataSourceParams({
    sourceParams: [dateRangeParam('fixed', {
      rangeType: 'custom',
      startDate: '2026-07-01',
      endDate: '2026-07-17',
    })],
    resolutionContext,
  }),
  { period: ['2026-07-01', '2026-07-17'] },
  'custom date ranges remain date-only tuples',
);

for (const invalidValue of [
  { rangeType: 'unknown' },
  { rangeType: 'custom', startDate: '2026-07-01' },
  { rangeType: 'custom', startDate: '2026-07-17', endDate: '2026-07-01' },
]) {
  assert.deepEqual(
    processDataSourceParams({
      sourceParams: [dateRangeParam('fixed', invalidValue)],
      resolutionContext,
    }),
    {},
    'invalid dateRange values are omitted',
  );
}

const widgetConfig = {
  dataSourceParams: [
    dateRangeParam('fixed', { rangeType: 'last_7_days' }),
  ],
};
const requestParams = buildWidgetRequestParams({
  config: widgetConfig,
  resolutionContext,
});
const signatureParams = buildWidgetRequestSignatureParams({
  config: widgetConfig,
  resolutionContext,
});
assert.deepEqual(requestParams, signatureParams);
assert.deepEqual(requestParams, {
  period: ['2026-07-11', '2026-07-17'],
});

assert.deepEqual(
  buildCompareRequestParams({
    config: {
      dataSourceParams: [dateRangeParam('params', { rangeType: 'last_30_days' })],
    },
    extraParams: { period: { rangeType: 'last_7_days' } },
    resolutionContext,
  }),
  {
    currentParams: { period: ['2026-07-11', '2026-07-17'] },
    baselineParams: null,
  },
  'compare requests must resolve component dateRange values with the shared context exactly once',
);

assert.equal(
  canEnableCompare({
    config: { dataSourceParams: [dateRangeParam('params', { rangeType: 'last_7_days' })] },
  }),
  true,
  'single-value compare is available for one dateRange parameter',
);

assert.deepEqual(
  buildCompareRequestParams({
    config: {
      compare: true,
      dataSourceParams: [dateRangeParam('params', {
        rangeType: 'custom',
        startDate: '2026-07-01',
        endDate: '2026-07-17',
      })],
    },
    resolutionContext,
  }),
  {
    currentParams: { period: ['2026-07-01', '2026-07-17'] },
    baselineParams: { period: ['2026-06-14', '2026-06-30'] },
  },
  'dateRange compare uses the previous adjacent equal-length date interval',
);

const absoluteTimeRange = [1784246400000, 1784332800000];
assert.deepEqual(
  processDataSourceParams({
    sourceParams: [{
      name: 'time',
      type: 'timeRange',
      filterType: 'fixed',
      value: absoluteTimeRange,
    }],
    resolutionContext,
  }),
  { time: formatTimeRange(absoluteTimeRange) },
  'timeRange request formatting remains unchanged',
);

console.log('ops analysis date range request tests passed');
