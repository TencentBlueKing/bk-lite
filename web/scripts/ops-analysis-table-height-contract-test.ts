import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolveTableBodyScrollY } from '../src/app/ops-analysis/components/widgets/shared/useTableBodyScrollY';

const runtimeTableSource = readFileSync(
  new URL('../src/app/ops-analysis/components/widgets/comTable.tsx', import.meta.url),
  'utf8',
);
const showcaseTableSource = readFileSync(
  new URL('../src/app/ops-analysis/components/ops-analysis-widgets/table.tsx', import.meta.url),
  'utf8',
);
const dashboardCanvasSource = readFileSync(
  new URL(
    '../src/app/ops-analysis/(pages)/view/dashBoard/components/dashboardCanvas.tsx',
    import.meta.url,
  ),
  'utf8',
);

for (const [name, source] of [
  ['运行时表格', runtimeTableSource],
  ['组件展示表格', showcaseTableSource],
] as const) {
  assert.match(source, /useTableBodyScrollY\(/, `${name}必须监听可用高度`);
  assert.match(
    source,
    /scroll=\{\{\s*x:\s*'max-content',\s*y:\s*tableScrollY\s*\}\}/,
    `${name}必须把计算后的高度交给表体滚动`,
  );
}

assert.equal(
  resolveTableBodyScrollY({ containerHeight: 320, hasPagination: false }),
  277,
  '无分页表格应使用 widget 剩余高度减去表头高度',
);
assert.equal(
  resolveTableBodyScrollY({ containerHeight: 320, hasPagination: true }),
  221,
  '有分页表格还应为分页栏预留高度',
);
assert.match(
  dashboardCanvasSource,
  /className="widget-body flex-1 h-full min-h-0"/,
  'widget 内容区必须允许表格在 flex 布局中收缩',
);

console.log('ops analysis table height contract tests passed');
