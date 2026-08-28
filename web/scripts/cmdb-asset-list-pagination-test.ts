import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { resetListPaginationToFirstPage } from '../src/app/cmdb/(pages)/assetData/listPagination';

const pageOne = { current: 1, pageSize: 20, total: 40 };
assert.equal(
  resetListPaginationToFirstPage(pageOne),
  pageOne,
  '已在第一页时不应新建分页对象，避免多余刷新'
);

const missingCurrent = { pageSize: 20, total: 40 };
assert.equal(
  resetListPaginationToFirstPage(missingCurrent),
  missingCurrent,
  '未设置 current 时视为第一页'
);

const pageTwo = { current: 2, pageSize: 20, total: 40 };
assert.deepEqual(
  resetListPaginationToFirstPage(pageTwo),
  { current: 1, pageSize: 20, total: 40 },
  '筛选变化后应从第二页回到第一页'
);
assert.equal(pageTwo.current, 2, '不应就地修改原分页对象');

const pageSource = readFileSync(
  resolve(process.cwd(), 'src/app/cmdb/(pages)/assetData/page.tsx'),
  'utf8'
);
assert.match(pageSource, /resetListPaginationToFirstPage/);
assert.match(
  pageSource,
  /setPagination\(\(prev\) => resetListPaginationToFirstPage\(prev\)\)/
);

console.log('cmdb asset list pagination tests passed');
