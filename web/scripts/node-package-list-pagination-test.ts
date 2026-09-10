import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { resolvePackageListPagination } from '../src/app/node-manager/components/sidecar/packageListPagination';

const pageTwo = { current: 2, total: 40, pageSize: 20 };
const pageTwoSuccess = resolvePackageListPagination(pageTwo, {
  count: 40,
  itemCount: 20,
});
assert.equal(pageTwoSuccess.current, 2, '第 2 页成功后 current 仍为 2');
assert.equal(pageTwoSuccess.total, 40, '成功响应只更新 total');
assert.equal(pageTwoSuccess.pageSize, 20);
assert.equal(pageTwo.current, 2, '不应就地修改原分页对象');

const pageSizeChanged = resolvePackageListPagination(
  { current: 3, total: 0, pageSize: 50 },
  { count: 100, itemCount: 50 }
);
assert.equal(
  pageSizeChanged.current,
  3,
  'pageSize 变化时保留传入的 current'
);
assert.equal(pageSizeChanged.pageSize, 50);
assert.equal(pageSizeChanged.total, 100);

const emptiedLastPage = resolvePackageListPagination(
  { current: 3, total: 41, pageSize: 20 },
  { count: 40, itemCount: 0 }
);
assert.equal(
  emptiedLastPage.current,
  2,
  '删空末页且 count>0 时应落到最后一页'
);
assert.equal(emptiedLastPage.total, 40);

const emptyCatalog = resolvePackageListPagination(
  { current: 1, total: 0, pageSize: 20 },
  { count: 0, itemCount: 0 }
);
assert.equal(emptyCatalog.current, 1);
assert.equal(emptyCatalog.total, 0);

const detailSource = readFileSync(
  resolve(process.cwd(), 'src/app/node-manager/components/sidecar/detail.tsx'),
  'utf8'
);
const getTableDataMatch = detailSource.match(
  /const getTableData = async \(\) => \{[\s\S]*?\n  \};/
);
assert.ok(getTableDataMatch, '找不到 getTableData');
assert.match(
  getTableDataMatch[0],
  /resolvePackageListPagination/,
  'getTableData 应使用抽出的分页函数'
);
assert.doesNotMatch(
  getTableDataMatch[0],
  /current:\s*1/,
  'getTableData 成功回调不应再写死 current:1'
);

console.log('node package list pagination tests passed');
