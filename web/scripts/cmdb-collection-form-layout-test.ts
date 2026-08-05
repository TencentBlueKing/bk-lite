/**
 * 自动发现采集任务表单布局回归测试。
 *
 * 所有对象的新增/编辑任务表单都必须沿用历史横向布局：
 * - Form 使用 horizontal；
 * - 中文标签占 5 格，英文标签占 6 格；
 * - 使用 BaseTaskForm 的 IP/资产选择器同步恢复横向缩进。
 *
 * Run: pnpm exec tsx scripts/cmdb-collection-form-layout-test.ts
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const componentDir = resolve(
  process.cwd(),
  'src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/components'
);

const taskForms = [
  'cloudTask.tsx',
  'configFileTask.tsx',
  'hostTask.tsx',
  'influxdbTask.tsx',
  'ipmiTask.tsx',
  'ipTask.tsx',
  'k8sTask.tsx',
  'networkConfigFileTask.tsx',
  'pcTask.tsx',
  'platformApiTask.tsx',
  'snmpTask.tsx',
  'sqlTask.tsx',
  'vmTask.tsx',
  'winsphereTask.tsx',
];

for (const file of taskForms) {
  const source = readFileSync(resolve(componentDir, file), 'utf8');
  assert.ok(
    source.includes('useCollectionFormLayout'),
    `${file} 应复用通用横向表单布局`
  );
  assert.ok(
    !source.includes('layout="vertical"'),
    `${file} 不得使用纵向表单布局`
  );
}

const layoutHook = readFileSync(
  resolve(componentDir, '../hooks/useCollectionFormLayout.ts'),
  'utf8'
);
assert.ok(layoutHook.includes("layout: 'horizontal'"), '通用任务表单必须使用横向布局');
assert.ok(layoutHook.includes("locale === 'en' ? 6 : 5"), '通用布局应沿用中英文标签列宽');

const baseTask = readFileSync(resolve(componentDir, 'baseTask.tsx'), 'utf8');
assert.ok(baseTask.includes('className="ml-8 mb-6"'), 'IP/资产选择器应恢复旧版横向缩进');

console.log(`cmdb-collection-form-layout-test passed (${taskForms.length} forms)`);
