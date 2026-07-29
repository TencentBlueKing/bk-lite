import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import {
  normalizeParams,
  validateParams,
} from '../src/app/ops-analysis/(pages)/settings/dataSource/operateModalUtils';
import type { ParamItem } from '../src/app/ops-analysis/types/dataSource';

const validParam: ParamItem = {
  id: 'period',
  name: 'period',
  alias_name: 'Period',
  type: 'dateRange',
  filterType: 'filter',
  value: { rangeType: 'last_30_days' },
};

assert.equal(validateParams([validParam]).isValid, true);
assert.equal(validateParams([{ ...validParam, value: null }]).isValid, true);
assert.equal(validateParams([{
  ...validParam,
  value: { rangeType: 'custom', startDate: '2026-07-17', endDate: '2026-07-01' },
}]).isValid, false);
const paramWithoutId = { ...validParam };
delete paramWithoutId.id;
assert.equal(validateParams([{
  ...paramWithoutId,
  value: { rangeType: 'unknown' } as never,
}]).isValid, false);
assert.deepEqual(validateParams([{
  ...validParam,
  value: { rangeType: 'unknown' } as never,
}]).invalidDateRangeIds, ['period']);
assert.deepEqual(normalizeParams([validParam]), [{
  name: 'period',
  alias_name: 'Period',
  type: 'dateRange',
  filterType: 'filter',
  value: { rangeType: 'last_30_days' },
}]);

const paramTableSource = readFileSync(
  new URL('../src/app/ops-analysis/(pages)/settings/dataSource/paramTable.tsx', import.meta.url),
  'utf8',
);
assert.match(paramTableSource, /value:\s*["']dateRange["']/);
assert.match(paramTableSource, /DEFAULT_DATE_RANGE_VALUE/);
assert.match(paramTableSource, /<DateRangeSelector/);
assert.match(paramTableSource, /invalidDateRangeIds/);

console.log('ops analysis date range data source tests passed');
