import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const metricPageSource = readFileSync(
  resolve(
    process.cwd(),
    'src/app/monitor/(pages)/integration/list/detail/metric/page.tsx'
  ),
  'utf8'
);
const metricModalSource = readFileSync(
  resolve(
    process.cwd(),
    'src/app/monitor/(pages)/integration/list/detail/metric/metricModal.tsx'
  ),
  'utf8'
);

assert.match(
  metricPageSource,
  /record\.is_pre[\s\S]*openMetricModal\('view', record\)[\s\S]*t\('common\.view'\)/,
  'built-in metrics should expose a view action'
);
assert.match(
  metricPageSource,
  /sortable=\{!metricItem\.is_pre\}/,
  'built-in metric groups should not expose drag sorting'
);
assert.match(
  metricPageSource,
  /metricItem\.child\.every\(\(item\) => !item\.is_pre\)/,
  'groups containing built-in metrics should not expose row drag sorting'
);
assert.doesNotMatch(
  metricPageSource,
  /scroll=\{\{\s*x:\s*'calc\(100vw - 260px\)'\s*\}\}/,
  'metric tables should use their content container instead of forcing viewport-based horizontal overflow'
);
assert.match(
  metricModalSource,
  /const isView = type === 'view'/,
  'metric modal should model view mode explicitly'
);
assert.match(
  metricModalSource,
  /isView \? \([\s\S]*<Descriptions bordered/,
  'view mode should render read-only descriptions'
);
assert.match(
  metricModalSource,
  /isView \? \([\s\S]*t\('common\.close'\)[\s\S]*\) : \(/,
  'view mode should expose only a close footer action'
);

for (const localeFile of ['zh.json', 'en.json']) {
  const locale = JSON.parse(
    readFileSync(
      resolve(process.cwd(), `src/app/monitor/locales/${localeFile}`),
      'utf8'
    )
  );
  assert.equal(typeof locale.monitor.integrations.viewMetric, 'string');
}

console.log('monitor built-in metric readonly tests passed');
