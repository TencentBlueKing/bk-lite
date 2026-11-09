import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolveTableBodyScrollY } from '../src/app/ops-analysis/components/widgets/shared/useTableBodyScrollY';
import { resolveTableDimensions } from '../src/components/custom-table/tableHeight';

const runtimeTableSource = readFileSync(
  new URL('../src/app/ops-analysis/components/widgets/comTable.tsx', import.meta.url),
  'utf8',
);
const showcaseTableSource = readFileSync(
  new URL('../src/app/ops-analysis/components/ops-analysis-widgets/table.tsx', import.meta.url),
  'utf8',
);
const runtimeEventSource = readFileSync(
  new URL('../src/app/ops-analysis/components/widgets/eventTable/eventTable.tsx', import.meta.url),
  'utf8',
);
const showcaseEventSource = readFileSync(
  new URL('../src/app/ops-analysis/components/ops-analysis-widgets/event-table.tsx', import.meta.url),
  'utf8',
);
const scrollHookSource = readFileSync(
  new URL(
    '../src/app/ops-analysis/components/widgets/shared/useTableBodyScrollY.ts',
    import.meta.url,
  ),
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
  ['运行时事件表', runtimeEventSource],
  ['组件展示事件表', showcaseEventSource],
] as const) {
  assert.match(source, /useTableBodyScrollY\(/, `${name}要用槽位量到的表体高度`);
  assert.match(source, /y:\s*tableScrollY/, `${name}要把数字高度交给 CustomTable`);
  assert.doesNotMatch(
    source,
    /y:\s*tableScrollY\s*\*/,
    `${name}不能再把表体高度乘一次缩放`,
  );
  assert.doesNotMatch(
    source,
    /scroll=\{\{\s*x:\s*'max-content'\s*\}\}/,
    `${name}不能只声明横向滚动`,
  );
}

const scrollHookCode = scrollHookSource
  .replace(/\/\*[\s\S]*?\*\//g, '')
  .replace(/\/\/.*$/gm, '');
assert.doesNotMatch(
  scrollHookCode,
  /widgetUiScale|widgetScale/,
  '测高钩子不能读取或再乘 widgetUiScale',
);
assert.match(scrollHookCode, /offsetHeight/, '测高必须读取真实表头和分页高度');
assert.match(scrollHookCode, /ant-table-header/, '测高必须能读到拆分后的表头');
assert.match(scrollHookCode, /ant-pagination/, '测高必须能读到分页');
assert.match(scrollHookCode, /setContainer/, '槽位晚挂载时要重新测量');
assert.doesNotMatch(scrollHookCode, /\b47\b|\b56\b/, '不能再按固定 47/56 预留');
for (const [name, source] of [
  ['运行时表格', runtimeTableSource],
  ['组件展示表格', showcaseTableSource],
  ['运行时事件表', runtimeEventSource],
  ['组件展示事件表', showcaseEventSource],
] as const) {
  assert.match(source, /opsTableScroll/, `${name}的滚动口必须留在卡片 flex 槽里`);
}
const tableScrollStyle = readFileSync(
  new URL('../src/app/ops-analysis/components/widgets/comTable.module.scss', import.meta.url),
  'utf8',
);
const customTableStyle = readFileSync(
  new URL('../src/components/custom-table/index.module.scss', import.meta.url),
  'utf8',
);
assert.match(tableScrollStyle, /height:\s*auto\s*!important/, '表体不能被数字 y 的像素高度钉死');
assert.match(tableScrollStyle, /overflow-y:\s*auto\s*!important/, '卡片内表体要保留纵向滚动');
assert.match(tableScrollStyle, /overflow-x:\s*clip\s*!important/, '列未超出时要剪掉纵条占位造成的横向滚动');
assert.equal(
  tableScrollStyle.match(/\.ant-table-container\)\s*\{[^}]*transform:\s*translateZ\(0\)/g)?.length,
  2,
  '普通槽和大屏槽的表容器都要挡住到顶继续上滚时的文档高度闪动',
);
assert.doesNotMatch(
  tableScrollStyle,
  /overflow:\s*auto\s*!important/,
  '不能用 overflow 简写盖住列未溢出时的横向隐藏',
);
assert.match(
  customTableStyle,
  /\.noHorizontalScroll[^{]*\{[^}]*overflow-x:\s*hidden\s*!important/,
  '列未超出时仍由 noHorizontalScroll 关掉横向滚动',
);
assert.equal(
  resolveTableBodyScrollY({ containerHeight: 320, headerHeight: 39, paginationHeight: 0 }),
  281,
  '无分页表格应减去当时量到的表头',
);
assert.equal(
  resolveTableBodyScrollY({ containerHeight: 320, headerHeight: 39, paginationHeight: 72 }),
  209,
  '折成两行的分页按 72 预留，而不是 56',
);
assert.equal(
  resolveTableBodyScrollY({ containerHeight: 280, headerHeight: 57, paginationHeight: 72 }),
  151,
  '放大后的表头按 57 预留，且不再乘一次缩放',
);
assert.equal(
  resolveTableDimensions({
    scrollY: 100,
    viewportHeight: 900,
    parentHeight: 180,
    size: 'small',
    hasPagination: false,
  }).tableHeight,
  100,
  '数字 scroll.y 保持调用方量到的高度',
);
assert.equal(
  resolveTableDimensions({
    scrollY: undefined,
    viewportHeight: 900,
    parentHeight: 400,
    size: 'small',
    hasPagination: false,
  }).containerHeight,
  undefined,
  '省略 y 的无分页表格仍按内容撑高',
);
assert.match(
  dashboardCanvasSource,
  /className="widget-body flex-1 h-full min-h-0"/,
  'widget 内容区必须允许表格在 flex 布局中收缩',
);

console.log('ops analysis table height contract tests passed');
