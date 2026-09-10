import * as assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

interface CollectionListPayload<T> {
  items?: T[] | null;
  count?: number | null;
}

interface CollectionListView<T> {
  items: T[];
  listCount: number;
  total: number;
}

interface CollectionListTimerApi {
  setTimeoutFn: (callback: () => void, ms: number) => unknown;
  clearTimeoutFn: (id: unknown) => void;
}

interface CollectionListRequest {
  begin: () => number;
  commitSuccess: <T>(
    requestId: number,
    payload: CollectionListPayload<T>,
    apply: (view: CollectionListView<T>) => void,
  ) => boolean;
  commitSettled: (requestId: number, settle: () => void) => boolean;
  resetTimer: (onTick: () => void) => void;
  unmount: () => void;
  clearTimer: () => void;
}

interface CollectTaskRow {
  id: number;
  name: string;
}

interface SessionState {
  tableData: CollectTaskRow[];
  tableCount: number;
  paginationTotal: number;
  tableLoading: boolean;
  fetchCount: number;
}

interface LoadedModule {
  COLLECTION_LIST_POLL_INTERVAL_MS?: number;
  createCollectionListRequest?: (
    timers?: Partial<CollectionListTimerApi>,
  ) => CollectionListRequest;
}

const here = dirname(fileURLToPath(import.meta.url));
const pagePath = resolve(
  here,
  '../src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/page.tsx',
);
const utilPath = resolve(
  here,
  '../src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/collectionListRequest.ts',
);
const menuPath = resolve(here, '../src/app/cmdb/constants/menu.json');
const zhPath = resolve(here, '../src/app/cmdb/locales/zh.json');

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

async function loadModule(): Promise<LoadedModule> {
  try {
    return (await import(
      '../src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/collectionListRequest.ts'
    )) as LoadedModule;
  } catch {
    return {};
  }
}

function createFakeTimers() {
  let nextId = 1;
  const timers = new Map<number, { callback: () => void; ms: number }>();
  return {
    timers,
    api: {
      setTimeoutFn: (callback: () => void, ms: number) => {
        const id = nextId++;
        timers.set(id, { callback, ms });
        return id;
      },
      clearTimeoutFn: (id: unknown) => {
        timers.delete(id as number);
      },
    },
  };
}

function createSession(request: CollectionListRequest) {
  const state: SessionState = {
    tableData: [],
    tableCount: 0,
    paginationTotal: 0,
    tableLoading: false,
    fetchCount: 0,
  };

  const fetchData = async (
    showLoading: boolean,
    listFn: () => Promise<CollectionListPayload<CollectTaskRow>>,
  ) => {
    const requestId = request.begin();
    state.fetchCount += 1;
    if (showLoading) {
      state.tableLoading = true;
    }
    try {
      const data = await listFn();
      request.commitSuccess(requestId, data, (view) => {
        state.tableData = view.items;
        state.tableCount = view.listCount;
        state.paginationTotal = view.total;
      });
    } catch (error: unknown) {
      void error;
    } finally {
      request.commitSettled(requestId, () => {
        if (showLoading) {
          state.tableLoading = false;
        }
        request.resetTimer(() => {
          void fetchData(false, listFn);
        });
      });
    }
  };

  return {
    state,
    fetchData,
    unmount: () => request.unmount(),
  };
}

function assertPageUsesGeneration(pageSource: string, utilSource: string) {
  assert.match(
    utilSource,
    /from ['"]@\/context\/latestRequestGuard['"]/,
    'collectionListRequest 必须复用 @/context/latestRequestGuard，不得复制新 guard',
  );
  assert.match(utilSource, /createLatestRequestGuard/, '必须调用 createLatestRequestGuard');
  assert.doesNotMatch(
    utilSource,
    /function createLatestRequestGuard|const createLatestRequestGuard\s*=/,
    '不得在 collectionListRequest 内复制一套序号 guard',
  );
  assert.match(
    pageSource,
    /from ['"]\.\/collectionListRequest['"]/,
    'page 必须调用抽出的 collectionListRequest',
  );
  assert.match(pageSource, /createCollectionListRequest/, 'page 必须创建 collection list request');
  assert.match(pageSource, /\.begin\(\)/, 'fetchData 必须按代次 begin');
  assert.match(pageSource, /\.commitSuccess\(/, '写列表必须经 commitSuccess 按代次提交');
  assert.match(pageSource, /\.commitSettled\(/, 'finally 必须经 commitSettled 按代次提交');
  assert.match(pageSource, /\.unmount\(\)/, '卸载必须 invalidate 并清 timer');
  assert.doesNotMatch(
    pageSource,
    /^      resetTimer\(pluginId\);$/m,
    'page 源码 finally 不得无条件 resetTimer',
  );
  assert.match(pageSource, /30 \* 1000/, '页面存活时必须保持 30 秒刷新间隔');
  assert.match(
    pageSource,
    /collectApi\.getCollectList\(params\)/,
    '不得改 getCollectList 参数形态',
  );
  assert.match(
    pageSource,
    /page:\s*stateRef\.current\.pagination\.current/,
    '搜索分页参数必须保留',
  );
  assert.match(pageSource, /name:\s*stateRef\.current\.searchText/, '搜索 name 必须保留');
  assert.match(pageSource, /requiredPermissions=\{?\['Add'\]\}?/, '新增任务权限必须保留');
  assert.match(pageSource, /placeholder:\s*t\('Collection\.inputTaskPlaceholder'\)/, '搜索框文案 key 必须保留');
  assert.match(pageSource, /t\('Collection\.addTaskTitle'\)/, '新增任务按钮文案 key 必须保留');
  assert.match(pageSource, /name:\s*'全部'/, '分类名「全部」必须保留');
}

function assertRealCopy() {
  const menuSource = readFileSync(menuPath, 'utf8');
  const zhSource = readFileSync(zhPath, 'utf8');
  assert.match(menuSource, /"title": "管理"/, '菜单必须含「管理」');
  assert.match(menuSource, /"title": "自动发现"/, '菜单必须含「自动发现」');
  assert.match(menuSource, /"title": "采集"/, '菜单必须含「采集」');
  assert.match(zhSource, /"inputTaskPlaceholder": "请输入任务名称"/, '搜索框必须是「请输入任务名称」');
  assert.match(zhSource, /"addTaskTitle": "新增任务"/, '按钮必须是「新增任务」');
}

async function main() {
  const pageSource = readFileSync(pagePath, 'utf8');
  assert.doesNotMatch(
    pageSource,
    /^      resetTimer\(pluginId\);$/m,
    'page 源码 finally 不得无条件 resetTimer',
  );

  const loaded = await loadModule();
  assert.equal(typeof loaded.createCollectionListRequest, 'function', '应抽出 createCollectionListRequest');
  assert.equal(
    loaded.COLLECTION_LIST_POLL_INTERVAL_MS,
    30 * 1000,
    '轮询间隔必须是 30 * 1000',
  );

  const createCollectionListRequest = loaded.createCollectionListRequest!;

  const unmountSuccessTimers = createFakeTimers();
  const unmountSuccessRequest = createCollectionListRequest(unmountSuccessTimers.api);
  const unmountSuccess = createSession(unmountSuccessRequest);
  const successDeferred = deferred<CollectionListPayload<CollectTaskRow>>();
  const unmountSuccessPending = unmountSuccess.fetchData(true, () => successDeferred.promise);
  unmountSuccess.unmount();
  successDeferred.resolve({ items: [{ id: 1, name: 'late-ok' }], count: 1 });
  await unmountSuccessPending;
  assert.deepEqual(unmountSuccess.state.tableData, [], '卸载后迟到成功不得 setTableData');
  assert.equal(unmountSuccess.state.paginationTotal, 0, '卸载后迟到成功不得写 total');
  assert.equal(unmountSuccessTimers.timers.size, 0, '卸载后成功 finally 不得再 schedule 30s fetchData');
  assert.equal(unmountSuccess.state.fetchCount, 1, '卸载后成功不得再发起下一轮 fetchData');

  const unmountFailTimers = createFakeTimers();
  const unmountFailRequest = createCollectionListRequest(unmountFailTimers.api);
  const unmountFail = createSession(unmountFailRequest);
  const failDeferred = deferred<CollectionListPayload<CollectTaskRow>>();
  const unmountFailPending = unmountFail.fetchData(true, () => failDeferred.promise);
  unmountFail.unmount();
  failDeferred.reject(new Error('late-fail'));
  await unmountFailPending;
  assert.deepEqual(unmountFail.state.tableData, [], '卸载后迟到失败不得写列表');
  assert.equal(unmountFailTimers.timers.size, 0, '卸载后失败 finally 不得再 schedule 30s fetchData');
  assert.equal(unmountFail.state.fetchCount, 1, '卸载后失败不得再发起下一轮 fetchData');

  const aliveSuccessTimers = createFakeTimers();
  const aliveSuccessRequest = createCollectionListRequest(aliveSuccessTimers.api);
  const aliveSuccess = createSession(aliveSuccessRequest);
  await aliveSuccess.fetchData(true, async () => ({ items: [{ id: 2, name: 'alive' }], count: 4 }));
  assert.deepEqual(aliveSuccess.state.tableData, [{ id: 2, name: 'alive' }], '存活页成功必须写列表');
  assert.equal(aliveSuccess.state.paginationTotal, 4);
  assert.equal(aliveSuccess.state.tableLoading, false, '存活页成功必须收口 loading');
  assert.equal(aliveSuccessTimers.timers.size, 1, '存活页成功仍必须 schedule 下一轮');
  const aliveSuccessTimer = [...aliveSuccessTimers.timers.values()][0];
  assert.equal(aliveSuccessTimer.ms, 30 * 1000, '存活页刷新间隔必须是 30 秒');

  const aliveFailTimers = createFakeTimers();
  const aliveFailRequest = createCollectionListRequest(aliveFailTimers.api);
  const aliveFail = createSession(aliveFailRequest);
  await aliveFail.fetchData(true, async () => {
    throw new Error('alive-fail');
  });
  assert.deepEqual(aliveFail.state.tableData, [], '存活页失败不得写脏数据');
  assert.equal(aliveFailTimers.timers.size, 1, '存活页失败后仍必须重试 schedule');
  const aliveFailTimer = [...aliveFailTimers.timers.values()][0];
  assert.equal(aliveFailTimer.ms, 30 * 1000, '失败重试间隔必须是 30 秒');
  aliveFailTimer.callback();
  assert.equal(aliveFail.state.fetchCount, 2, '存活页失败后的 timer 必须再次调用 fetchData');

  const reopenTimers = createFakeTimers();
  const reopenRequest = createCollectionListRequest(reopenTimers.api);
  const reopen = createSession(reopenRequest);
  await reopen.fetchData(true, async () => ({ items: [{ id: 3, name: 'first' }], count: 1 }));
  assert.equal(reopenTimers.timers.size, 1, '首次打开应只有一条轮询链');
  reopen.unmount();
  assert.equal(reopenTimers.timers.size, 0, '卸载必须清掉已有 timer');
  await reopen.fetchData(true, async () => ({ items: [{ id: 4, name: 'second' }], count: 1 }));
  assert.equal(reopenTimers.timers.size, 1, '再次打开只保留一条链');
  assert.deepEqual(reopen.state.tableData, [{ id: 4, name: 'second' }], '再次打开必须提交当前代次列表');

  const strictTimers = createFakeTimers();
  const strictRequest = createCollectionListRequest(strictTimers.api);
  const strict = createSession(strictRequest);
  const firstMount = deferred<CollectionListPayload<CollectTaskRow>>();
  const firstPending = strict.fetchData(true, () => firstMount.promise);
  strict.unmount();
  const secondMount = deferred<CollectionListPayload<CollectTaskRow>>();
  const secondPending = strict.fetchData(true, () => secondMount.promise);
  firstMount.resolve({ items: [{ id: 8, name: 'stale-mount' }], count: 8 });
  secondMount.resolve({ items: [{ id: 9, name: 'latest-mount' }], count: 9 });
  await firstPending;
  await secondPending;
  assert.deepEqual(strict.state.tableData, [{ id: 9, name: 'latest-mount' }], 'StrictMode 双挂载不得用首次挂载写回');
  assert.equal(strictTimers.timers.size, 1, 'StrictMode 双挂载不得叠两条后台链');

  const utilSource = readFileSync(utilPath, 'utf8');
  assertPageUsesGeneration(pageSource, utilSource);
  assertRealCopy();

  console.log('profess collection unmount poll test passed');
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
