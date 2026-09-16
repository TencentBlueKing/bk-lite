import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import { resolveTableDimensions } from '../src/components/custom-table/tableHeight';

const featureLibraryPages = [
  'src/app/cmdb/(pages)/assetManage/autoDiscovery/featureLibrary/soid/page.tsx',
  'src/app/cmdb/(pages)/assetManage/autoDiscovery/featureLibrary/port/page.tsx',
];
const layoutSource = readFileSync(
  'src/app/cmdb/(pages)/assetManage/autoDiscovery/featureLibrary/layout.tsx',
  'utf8'
);

assert.match(
  layoutSource,
  /flex min-h-0 flex-1 flex-col overflow-hidden/,
  '特征库内容区必须是纵向 flex，SOID / 端口指纹才能吃到剩余高度'
);

for (const pagePath of featureLibraryPages) {
  const source = readFileSync(pagePath, 'utf8');
  assert.equal(
    /scroll=\{\{\s*y:\s*['"]calc\(100vh/.test(source),
    false,
    `${pagePath} 不得用 100vh 估算表格高度：特征库 Tab 会把表格和翻页裁出 overflow-hidden 容器`
  );
  assert.match(
    source,
    /flex h-full min-h-0 flex-1 flex-col overflow-hidden/,
    `${pagePath} 必须作为特征库 flex 子项占满剩余高度`
  );
  assert.match(
    source,
    /min-h-0 h-full flex-1 overflow-hidden[\s\S]*<CustomTable/,
    `${pagePath} 必须把 CustomTable 放进有明确高度的剩余空间`
  );
}

const parentHeight = 400;
const fitted = resolveTableDimensions({
  scrollY: undefined,
  viewportHeight: 800,
  parentHeight,
  size: 'middle',
  hasPagination: true,
});

assert.equal(fitted.containerHeight, parentHeight);
assert.ok(
  (fitted.tableHeight ?? 0) < parentHeight,
  '自适应高度必须给表头和翻页留出空间'
);

const unmeasured = resolveTableDimensions({
  scrollY: undefined,
  viewportHeight: 800,
  parentHeight: 0,
  size: 'middle',
  hasPagination: true,
});
assert.equal(unmeasured.containerHeight, undefined);
assert.equal(unmeasured.tableHeight, undefined);

const shortParent = resolveTableDimensions({
  scrollY: undefined,
  viewportHeight: 800,
  parentHeight: 80,
  size: 'middle',
  hasPagination: true,
});
assert.equal(shortParent.containerHeight, 80);
assert.ok(
  (shortParent.containerHeight ?? 0) <= 80,
  '父容器较矮时不得再按最小表体撑破，否则翻页会被裁掉'
);

const legacyVh = resolveTableDimensions({
  scrollY: 'calc(100vh - 456px)',
  viewportHeight: 800,
  parentHeight,
  size: 'middle',
  hasPagination: true,
});

assert.ok(
  (legacyVh.containerHeight ?? 0) > parentHeight,
  '旧 100vh 算法会超出父容器，回归时用来对照裁切原因'
);

console.log(
  `特征库表格按父容器 ${parentHeight}px 自适应：表体 ${fitted.tableHeight}px，容器 ${fitted.containerHeight}px`
);
