/**
 * 顶部用户菜单中的组织选择窗布局契约。
 *
 * 运行：pnpm exec tsx scripts/user-info-organization-panel-layout-test.ts
 */

import fs from 'node:fs';
import path from 'node:path';

const sourcePath = path.resolve(
  process.cwd(),
  'src/app/(core)/components/top-menu/user-info/index.tsx',
);
const source = fs.readFileSync(sourcePath, 'utf8');

let failed = 0;

const assert = (condition: boolean, message: string) => {
  if (condition) {
    console.log(`✓ ${message}`);
  } else {
    failed += 1;
    console.error(`✗ ${message}`);
  }
};

assert(
  /<span className="max-w-\[120px\] truncate text-xs text-\[var\(--color-text-4\)\]">\s*\{selectedGroup\?\.name\}/s.test(source),
  '长组织名称在用户菜单中应截断，不能撑宽菜单',
);

assert(
  !source.includes('handleGroupPanelToggle'),
  '组织菜单只负责名称截断，不额外引入动态定位逻辑',
);

if (failed > 0) {
  process.exit(1);
}
