import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { resolve } from 'node:path';

import { DATE_RANGE_TYPES } from '../src/app/ops-analysis/types/dateRange';

const read = (path: string) => readFileSync(resolve(process.cwd(), path), 'utf8');
const readTree = (path: string): string => readdirSync(resolve(process.cwd(), path), {
  recursive: true,
  withFileTypes: true,
}).filter((entry) => entry.isFile() && /\.(?:ts|tsx)$/.test(entry.name))
  .map((entry) => read(resolve(entry.parentPath, entry.name)))
  .join('\n');

const paramTableSource = read('src/app/ops-analysis/(pages)/settings/dataSource/paramTable.tsx');
const dashboardSyncSource = read(
  'src/app/ops-analysis/(pages)/view/dashBoard/hooks/useDashboardLayoutSync.ts',
);
const screenLayoutSource = read('src/app/ops-analysis/(pages)/view/screen/utils/layout.ts');
const topologyNamespaceSource = read(
  'src/app/ops-analysis/(pages)/view/topology/utils/namespaceUtils.ts',
);
const widgetTransformSource = read('src/app/ops-analysis/utils/widgetDataTransform.ts');
const dateRangeDomainSource = read('src/app/ops-analysis/utils/dateRange.ts');
const dateRangeSelectorSource = read('src/app/ops-analysis/components/dateRangeSelector.tsx');
const en = JSON.parse(read('src/app/ops-analysis/locales/en.json'));
const zh = JSON.parse(read('src/app/ops-analysis/locales/zh.json'));

assert.equal((paramTableSource.match(/value:\s*["']dateRange["']/g) ?? []).length, 1);
for (const key of DATE_RANGE_TYPES) {
  assert.equal(typeof en.dateRange[key], 'string');
  assert.equal(typeof zh.dateRange[key], 'string');
}
for (const source of [dashboardSyncSource, screenLayoutSource, topologyNamespaceSource]) {
  assert.match(source, /BindableParamType/);
}
assert.match(widgetTransformSource, /resolveDateRange/);

for (const path of ['src/app/ops-analysis/components/widgetConfig/sections/tableSettingsSection.tsx']) {
  assert.doesNotMatch(read(path), /dateRange/);
}
assert.doesNotMatch(readTree('src/app/ops-analysis/(pages)/view/report'), /dateRange/);
assert.doesNotMatch(read('src/app/ops-analysis/utils/dashboardActions.ts'), /dateRange/);
const operateModalSource = read(
  'src/app/ops-analysis/(pages)/settings/dataSource/operateModal.tsx',
);
assert.match(operateModalSource, /\{isNatsSource\s*&&\s*\([\s\S]{0,300}<ParamTable/);
for (const source of [paramTableSource, dateRangeSelectorSource, dateRangeDomainSource]) {
  assert.doesNotMatch(
    source,
    /dateRange[\s\S]{0,80}required|required[\s\S]{0,80}dateRange/,
  );
}
assert.doesNotMatch(
  read('src/app/ops-analysis/utils/compareQuery.ts'),
  /type\s*===\s*["']dateRange["']|resolveDateRange|DateRangeSelector/,
);
for (const source of [dateRangeDomainSource, dateRangeSelectorSource]) {
  assert.doesNotMatch(source, /toISOString\(\)|formatTimeRange|TimeSelector/);
}

console.log('ops analysis date range scope tests passed');
