/**
 * 采集工具底部操作区布局回归测试。
 *
 * 任务预填失败时会在工具上方展示警告；警告和工具必须共同分配标签页高度，
 * 不能让完整高度的工具被警告向下挤出可视区域。SNMP/IPMI 工具内部也不得
 * 使用视口硬编码高度，否则底部操作按钮会再次被父级裁剪。
 *
 * Run: pnpm exec tsx scripts/cmdb-collection-tool-action-layout-test.ts
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const collectionToolDir = resolve(
  process.cwd(),
  'src/app/cmdb/(pages)/assetManage/autoDiscovery/featureLibrary/collectionTool'
);

const pageSource = readFileSync(resolve(collectionToolDir, 'page.tsx'), 'utf8');
const toolSources = ['snmpDebugTool.tsx', 'ipmiDebugTool.tsx'].map((file) => ({
  file,
  source: readFileSync(resolve(collectionToolDir, 'components', file), 'utf8'),
}));

const countOccurrences = (value: string) => pageSource.split(value).length - 1;

assert.equal(
  countOccurrences('<div className="flex h-full min-h-0 flex-col">'),
  3,
  '页面根节点及 SNMP/IPMI 标签页都应使用占满高度的纵向 Flex 容器'
);
assert.equal(
  countOccurrences('className="mb-4 shrink-0"'),
  2,
  'SNMP/IPMI 的预填失败警告都必须保持自身高度且不压缩'
);
assert.equal(
  countOccurrences('<div className="min-h-0 flex-1">'),
  2,
  'SNMP/IPMI 工具外层都必须只占用警告之外的剩余高度'
);

for (const { file, source } of toolSources) {
  assert.ok(
    !source.includes('calc(100vh - 380px)'),
    `${file} 不得使用视口硬编码高度`
  );
  assert.ok(
    source.includes('className="flex h-full min-h-0 w-100 shrink-0 flex-col"'),
    `${file} 左侧表单应占满剩余高度，并保留内部滚动与固定操作区`
  );
}

console.log('cmdb-collection-tool-action-layout-test passed');
