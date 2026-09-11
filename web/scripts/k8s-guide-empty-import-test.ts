import * as assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const alarmDir = resolve(here, '../src/app/alarm');
const guideSource = readFileSync(resolve(alarmDir, 'components/k8sGuide/index.tsx'), 'utf8');
const zhLocale = readFileSync(resolve(alarmDir, 'locales/zh.json'), 'utf8');
const enLocale = readFileSync(resolve(alarmDir, 'locales/en.json'), 'utf8');

assert.match(
  guideSource,
  /import CompactEmptyState from '@\/components\/compact-empty-state'/,
  'K8s 失败态使用 CompactEmptyState 时必须导入该组件'
);
assert.match(
  guideSource,
  /<CompactEmptyState description=\{t\('integration\.k8sMetaLoadFailed'\)\}>/,
  '元数据失败态使用 CompactEmptyState 承载重试按钮'
);
assert.match(guideSource, /common\.retry/, '失败态必须提供显式重试');
assert.match(
  guideSource,
  /CompactEmptyState description=\{t\('common\.noData'\)\}/,
  '无数据空态继续走 CompactEmptyState'
);
assert.match(zhLocale, /"k8sMetaLoadFailed"/);
assert.match(enLocale, /"k8sMetaLoadFailed"/);

console.log('k8s-guide-empty-import-test: ok');
