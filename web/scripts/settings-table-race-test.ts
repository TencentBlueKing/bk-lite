import * as assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createLatestRequestGuard } from '../src/context/latestRequestGuard.ts';
import type { LatestRequestGuard } from '../src/context/latestRequestGuard.ts';

interface SettingsTableListPayload<T> {
  items?: T[] | null;
  count?: number | null;
}

interface SettingsTableListView<T> {
  dataList: T[];
  listCount: number;
  paginationTotal: number;
}

interface CommitFns {
  buildSettingsTableListView: <T>(payload: SettingsTableListPayload<T>) => SettingsTableListView<T>;
  commitSettingsTableListSuccess: <T>(
    guard: LatestRequestGuard,
    requestId: number,
    payload: SettingsTableListPayload<T>,
    apply: (next: SettingsTableListView<T>) => void,
  ) => boolean;
  commitSettingsTableListFailure: (
    guard: LatestRequestGuard,
    requestId: number,
    reportError: () => void,
  ) => boolean;
  commitSettingsTableListSettled: (
    guard: LatestRequestGuard,
    requestId: number,
    settle: () => void,
  ) => boolean;
}

interface Row {
  id: number;
  name: string;
}

interface ViewState {
  dataList: Row[];
  listCount: number;
  paginationTotal: number;
  tableLoading: boolean;
  error: string | null;
}

const here = dirname(fileURLToPath(import.meta.url));
const hookPath = resolve(here, '../src/app/alarm/hooks/useSettingsTable.ts');
const utilPath = resolve(here, '../src/app/alarm/utils/settingsTableRequest.ts');

async function loadCommitFns(): Promise<CommitFns> {
  let loaded: Partial<CommitFns> = {};
  try {
    loaded = await import('../src/app/alarm/utils/settingsTableRequest.ts');
  } catch {
    // RED：提交函数尚未抽出。
  }

  assert.equal(typeof loaded.buildSettingsTableListView, 'function', '应抽出 buildSettingsTableListView');
  assert.equal(typeof loaded.commitSettingsTableListSuccess, 'function', '应抽出 commitSettingsTableListSuccess');
  assert.equal(typeof loaded.commitSettingsTableListFailure, 'function', '应抽出 commitSettingsTableListFailure');
  assert.equal(typeof loaded.commitSettingsTableListSettled, 'function', '应抽出 commitSettingsTableListSettled');

  return loaded as CommitFns;
}

function createListSession(fns: CommitFns) {
  const guard = createLatestRequestGuard();
  let state: ViewState = {
    dataList: [],
    listCount: 0,
    paginationTotal: 0,
    tableLoading: false,
    error: null,
  };

  const start = () => {
    const requestId = guard.begin();
    state = { ...state, tableLoading: true };
    return requestId;
  };

  const succeed = (requestId: number, payload: SettingsTableListPayload<Row>) => {
    fns.commitSettingsTableListSuccess(guard, requestId, payload, (next) => {
      state = {
        ...state,
        dataList: next.dataList,
        listCount: next.listCount,
        paginationTotal: next.paginationTotal,
      };
    });
    fns.commitSettingsTableListSettled(guard, requestId, () => {
      state = { ...state, tableLoading: false };
    });
  };

  const fail = (requestId: number) => {
    fns.commitSettingsTableListFailure(guard, requestId, () => {
      state = { ...state, error: 'loadFailed' };
    });
    fns.commitSettingsTableListSettled(guard, requestId, () => {
      state = { ...state, tableLoading: false };
    });
  };

  return {
    getState: () => state,
    start,
    succeed,
    fail,
    unmount: () => guard.invalidate(),
  };
}

function assertHookUsesGeneration(source: string) {
  assert.match(
    source,
    /from ['"]@\/context\/latestRequestGuard['"]/,
    'hook 必须复用 @/context/latestRequestGuard，不得复制新 guard',
  );
  assert.match(source, /createLatestRequestGuard/, 'hook 必须创建 latest request guard');
  assert.match(source, /requestGuard\.begin\(\)/, 'getTableList 必须按单调序号 begin');
  assert.match(
    source,
    /from ['"]@\/app\/alarm\/utils\/settingsTableRequest['"]/,
    'hook 必须调用抽出的 settingsTableRequest',
  );
  assert.match(source, /commitSettingsTableListSuccess\(/, '成功响应必须经 commitSettingsTableListSuccess 提交');
  assert.match(source, /commitSettingsTableListFailure\(/, '失败必须经 commitSettingsTableListFailure 提交');
  assert.match(source, /commitSettingsTableListSettled\(/, '结束 loading 必须经 commitSettingsTableListSettled 提交');
  assert.match(source, /requestGuard\.invalidate\(\)/, '卸载后必须 invalidate，迟到响应不得写回');
  assert.match(
    source,
    /current:\s*pagination\.current\s*-\s*1/,
    '删除最后一行后的 current-1 刷新路径必须保留',
  );
  assert.doesNotMatch(
    source,
    /setDataList\(\s*data\.items/,
    'getTableList 不得在 await 后无条件写 dataList',
  );
  assert.doesNotMatch(
    source,
    /function createLatestRequestGuard|const createLatestRequestGuard\s*=/,
    '不得在 hook 内复制一套序号 guard',
  );
}

async function main() {
  const fns = await loadCommitFns();

  const built = fns.buildSettingsTableListView({ items: [{ id: 1, name: 'a' }], count: 3 });
  assert.deepEqual(built, {
    dataList: [{ id: 1, name: 'a' }],
    listCount: 1,
    paginationTotal: 3,
  });

  const search = createListSession(fns);
  const staleSearch = search.start();
  const latestSearch = search.start();
  search.succeed(latestSearch, { items: [{ id: 2, name: 'bar' }], count: 1 });
  search.succeed(staleSearch, { items: [{ id: 1, name: 'foo' }], count: 5 });
  assert.deepEqual(search.getState().dataList, [{ id: 2, name: 'bar' }], '搜索乱序：较旧响应不得覆盖较新搜索结果');
  assert.equal(search.getState().paginationTotal, 1, '搜索乱序：total 必须属于最新查询');
  assert.equal(search.getState().tableLoading, false);

  const cleared = createListSession(fns);
  const staleFilter = cleared.start();
  const latestClear = cleared.start();
  cleared.succeed(latestClear, {
    items: [
      { id: 1, name: 'all-1' },
      { id: 2, name: 'all-2' },
    ],
    count: 2,
  });
  cleared.succeed(staleFilter, { items: [{ id: 9, name: 'filtered' }], count: 1 });
  assert.deepEqual(
    cleared.getState().dataList.map((row) => row.name),
    ['all-1', 'all-2'],
    '清空乱序：较旧搜索结果不得覆盖清空后的全量列表',
  );
  assert.equal(cleared.getState().paginationTotal, 2);

  const paging = createListSession(fns);
  const pageOne = paging.start();
  const pageTwo = paging.start();
  paging.succeed(pageTwo, { items: [{ id: 20, name: 'page-2' }], count: 40 });
  paging.succeed(pageOne, { items: [{ id: 10, name: 'page-1' }], count: 40 });
  assert.deepEqual(paging.getState().dataList, [{ id: 20, name: 'page-2' }], '翻页乱序：较旧页不得覆盖较新页');
  assert.equal(paging.getState().listCount, 1);

  const latestFailed = createListSession(fns);
  const staleSuccess = latestFailed.start();
  const failedLatest = latestFailed.start();
  latestFailed.fail(failedLatest);
  latestFailed.succeed(staleSuccess, { items: [{ id: 3, name: 'stale-ok' }], count: 8 });
  assert.equal(latestFailed.getState().error, 'loadFailed', '最新失败必须可报错');
  assert.deepEqual(latestFailed.getState().dataList, [], '旧成功不能在最新失败之后写回列表');
  assert.equal(latestFailed.getState().paginationTotal, 0);
  assert.equal(latestFailed.getState().tableLoading, false);

  const inflight = createListSession(fns);
  const staleFail = inflight.start();
  inflight.start();
  inflight.fail(staleFail);
  assert.equal(inflight.getState().tableLoading, true, '旧失败不得把仍在途的最新请求 loading 清掉');
  assert.equal(inflight.getState().error, null, '旧失败不得展示为当前错误');

  const unmounted = createListSession(fns);
  const lateId = unmounted.start();
  unmounted.unmount();
  unmounted.succeed(lateId, { items: [{ id: 4, name: 'late' }], count: 1 });
  unmounted.fail(lateId);
  assert.deepEqual(unmounted.getState().dataList, [], '卸载后迟到成功不得写回');
  assert.equal(unmounted.getState().paginationTotal, 0);
  assert.equal(unmounted.getState().error, null, '卸载后迟到失败不得写回');
  assert.equal(unmounted.getState().tableLoading, true, '卸载后不得用迟到 finally 收口仍有效的会话状态');

  const afterDelete = createListSession(fns);
  const pageTwoBeforeDelete = afterDelete.start();
  afterDelete.succeed(pageTwoBeforeDelete, { items: [{ id: 21, name: 'last-row' }], count: 21 });
  const pageAfterDelete = afterDelete.start();
  afterDelete.succeed(pageAfterDelete, { items: [{ id: 11, name: 'prev-page' }], count: 20 });
  assert.deepEqual(
    afterDelete.getState().dataList,
    [{ id: 11, name: 'prev-page' }],
    '删除最后一行后的 current-1 刷新必须仍能提交',
  );
  assert.equal(afterDelete.getState().paginationTotal, 20);

  const hookSource = readFileSync(hookPath, 'utf8');
  const utilSource = readFileSync(utilPath, 'utf8');
  assertHookUsesGeneration(hookSource);
  assert.doesNotMatch(
    utilSource,
    /createLatestRequestGuard\s*=|function createLatestRequestGuard/,
    'settingsTableRequest 不得复制一套序号 guard',
  );
  assert.match(
    hookSource,
    /patchItem/,
    '开关 patch 刷新入口必须保留',
  );

  console.log('settings table race test passed');
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
