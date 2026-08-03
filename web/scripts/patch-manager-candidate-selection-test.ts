import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import {
  createCandidateSelection,
  reconcileCandidatePageSelection,
  removeCandidateFromSelection,
} from '../src/app/patch-manager/components/candidate-selection';
import type { CandidateItem } from '../src/app/patch-manager/types';

const candidate = (key: string, name: string): CandidateItem => ({
  key,
  name,
  title: name,
  arch: 'x86_64',
  added: false,
});

const page52Item = candidate('page-52', 'page-52-package');
const searchItem = candidate('search-result', 'searched-package');

let selection = createCandidateSelection();
selection = reconcileCandidatePageSelection(selection, [page52Item], [page52Item.key]);

// 回到第一页后，当前页没有该记录，但右侧已选明细仍应保留完整记录。
selection = reconcileCandidatePageSelection(
  selection,
  [candidate('page-1', 'page-1-package')],
  [],
);
assert.deepEqual(selection.keys, [page52Item.key]);
assert.deepEqual(selection.items.map((item) => item.key), [page52Item.key]);

// 搜索后勾选新记录只应合并当前结果，不得覆盖之前页面的选择。
selection = reconcileCandidatePageSelection(selection, [searchItem], [searchItem.key]);
assert.deepEqual(selection.keys, [page52Item.key, searchItem.key]);
assert.deepEqual(selection.items.map((item) => item.key), [page52Item.key, searchItem.key]);

// 回到原页取消勾选时，只移除当前页记录。
selection = reconcileCandidatePageSelection(selection, [page52Item], []);
assert.deepEqual(selection.keys, [searchItem.key]);
assert.deepEqual(selection.items.map((item) => item.key), [searchItem.key]);

// 右侧明细的单项删除必须同时更新 key 和记录缓存。
selection = removeCandidateFromSelection(selection, searchItem.key);
assert.deepEqual(selection, createCandidateSelection());

const libraryPage = readFileSync(
  resolve(process.cwd(), 'src/app/patch-manager/(pages)/library/page.tsx'),
  'utf8',
);
const openDrawerHandler = libraryPage.match(
  /const handleImportSearch = \(\) => \{([\s\S]*?)\n  \};/,
)?.[1] || '';
const candidateColumns = libraryPage.match(
  /const candidateColumns:[\s\S]*?= \[([\s\S]*?)\n  \];/,
)?.[1] || '';
const displayFailures = [
  !/setCandidatePagination\(\{ current: 1, pageSize: 20, total: 0 \}\)/.test(openDrawerHandler)
    ? '同步入库抽屉默认每页应为 20 条'
    : null,
  /patchManager\.advisoryId/.test(candidateColumns)
    ? 'Linux 候选表不应在包版本可区分时额外展示公告编号'
    : null,
  !/patchManager\.pkgVersion/.test(candidateColumns)
    ? 'Linux 同名包必须展示包版本以便区分候选项'
    : null,
].filter(Boolean);
assert.deepEqual(displayFailures, []);

assert.match(libraryPage, /reconcileCandidatePageSelection/);
assert.match(libraryPage, /preserveSelectedRowKeys:\s*true/);
assert.doesNotMatch(
  libraryPage,
  /const selectedItems = candidateData\.filter/,
  '右侧已选明细不得只从当前页数据中取值',
);

console.log('补丁同步入库跨分页与搜索选择状态回归通过');
