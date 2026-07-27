import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { processDataSourceFormParamsForSubmit } from '../src/app/ops-analysis/utils/dataSourceFormParams';
import type { ParamItem } from '../src/app/ops-analysis/types/dataSource';

const paramsConfigPath = fileURLToPath(
  new URL('../src/app/ops-analysis/components/paramsConfig.tsx', import.meta.url),
);
const source = readFileSync(paramsConfigPath, 'utf8');

assert.match(
  source,
  /import DateRangeSelector from ['"]\.\/dateRangeSelector['"];?/,
  'component params should import the dedicated DateRangeSelector',
);

const dateRangeParam: ParamItem = {
  name: 'period',
  alias_name: 'Period',
  type: 'dateRange',
  filterType: 'params',
  value: { rangeType: 'last_30_days' },
};
assert.deepEqual(
  processDataSourceFormParamsForSubmit(
    { period: { rangeType: 'last_7_days' } },
    [dateRangeParam],
  )[0].value,
  { rangeType: 'last_7_days' },
);
assert.equal(
  processDataSourceFormParamsForSubmit({ period: null }, [dateRangeParam])[0].value,
  null,
  'explicitly cleared dateRange form values must not fall back to the saved default',
);
assert.match(
  source,
  /case ['"]dateRange['"]:\s*return <DateRangeSelector disabled=\{isDisabled\} allowClear \/>;/,
  'dateRange params should render the dedicated controlled selector branch',
);
assert.match(
  source,
  /case ['"]dateRange['"]:\s*return value === undefined\s*\? \{ \.\.\.DEFAULT_DATE_RANGE_VALUE \}\s*:\s*value;/,
  'undefined dateRange values should initialize from a cloned default while null remains null',
);

assert.match(
  source,
  /case ['"]timeRange['"]:\s*return <FormTimeSelector disabled=\{isDisabled\} \/>;/,
  'the existing timeRange input branch should remain intact',
);
assert.match(
  source,
  /case ['"]timeRange['"]:\s*return value \?\? 10080;/,
  'the existing timeRange initialization should remain intact',
);

console.log('ops analysis params date range tests passed');
