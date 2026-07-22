import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { validateMultiValueData } from '../src/app/ops-analysis/utils/multiValueData';

const mismatch = 'format mismatch';

assert.deepEqual(
  validateMultiValueData([
    { label: 'CPU', value: 80 },
    { label: 2, value: '65%' },
  ], mismatch),
  {
    isValid: true,
    items: [
      { label: 'CPU', value: '80' },
      { label: '2', value: '65%' },
    ],
  },
);

for (const wrapped of [
  { items: [{ label: 'Tomcat', value: 100 }] },
  { data: { items: [{ label: 'Tomcat', value: 100 }] } },
]) {
  assert.deepEqual(validateMultiValueData(wrapped, mismatch), {
    isValid: true,
    items: [{ label: 'Tomcat', value: '100' }],
  });
}

for (const empty of [[], { items: [] }, { data: { items: [] } }]) {
  assert.deepEqual(validateMultiValueData(empty, mismatch), {
    isValid: true,
    items: [],
  });
}

for (const malformed of [
  {},
  { items: null },
  { items: {} },
  { data: null },
  { data: {} },
  { data: { items: 'invalid' } },
]) {
  assert.deepEqual(validateMultiValueData(malformed, mismatch), {
    isValid: false,
    errorMessage: mismatch,
    items: [],
  });
}

assert.deepEqual(
  validateMultiValueData([
    { label: null, value: '' },
    { label: 'disk', value: undefined },
  ], mismatch),
  {
    isValid: true,
    items: [
      { label: '--', value: '--' },
      { label: 'disk', value: '--' },
    ],
  },
);

for (const invalid of [
  [{ label: 'CPU' }],
  [{ value: 80 }],
  [{ label: 'CPU', value: { nested: true } }],
  [{ label: ['CPU'], value: 80 }],
]) {
  assert.deepEqual(validateMultiValueData(invalid, mismatch), {
    isValid: false,
    errorMessage: mismatch,
    items: [],
  });
}

const read = (relative: string) =>
  fs.readFileSync(path.resolve(process.cwd(), relative), 'utf8');

assert.match(
  read('src/app/ops-analysis/components/widgetRegistry.ts'),
  /multiValue:\s*ComMultiValue/,
);

assert.match(read('src/app/ops-analysis/types/dataSource.ts'), /\| 'multiValue'/);
assert.match(read('src/app/ops-analysis/types/screen.ts'), /\| 'multiValue'/);
assert.match(
  read('src/app/ops-analysis/constants/common.ts'),
  /dataSource\.multiValue[\s\S]*multiValue/,
);
assert.match(
  read('src/app/ops-analysis/components/widgetSelector.tsx'),
  /multiValue:\s*t\('dataSource\.multiValue'\)/,
);

const screenWidgets = read(
  'src/app/ops-analysis/(pages)/view/screen/constants/widgets.ts',
);
assert.match(screenWidgets, /chartType:\s*'multiValue'/);
assert.match(screenWidgets, /defaultWidth:\s*360/);
assert.match(screenWidgets, /defaultHeight:\s*260/);

for (const locale of ['zh', 'en']) {
  const messages = JSON.parse(
    read(`src/app/ops-analysis/locales/${locale}.json`),
  );
  assert.equal(typeof messages.dataSource.multiValue, 'string');
  assert.equal(messages.dataSource.multiValue, locale === 'zh' ? '指标列表' : 'Metric List');
  assert.equal(typeof messages.opsAnalysis.screen.widgets.multiValue, 'string');
  assert.equal(
    messages.opsAnalysis.screen.widgets.multiValue,
    locale === 'zh' ? '指标列表' : 'Metric List',
  );
  assert.equal(
    typeof messages.opsAnalysis.screen.widgetDescriptions.multiValue,
    'string',
  );
  assert.equal(
    messages.opsAnalysis.screen.widgetDescriptions.multiValue,
    locale === 'zh' ? '按行展示多个指标名称及其数值' : 'Show multiple metric names and values in rows',
  );
}

assert.match(
  read('src/app/ops-analysis/(pages)/view/topology/components/chartNode.tsx'),
  /chartType=\{chartType\}/,
);
