import * as assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createLatestRequestGuard } from '../src/context/latestRequestGuard.ts';
import {
  commitIntegrationEventListSettled,
  commitIntegrationEventListSuccess,
} from '../src/app/alarm/(pages)/integration/detail/integrationEventListRequest.ts';

interface EventRow {
  id: number;
  title: string;
}

interface ViewState {
  eventList: EventRow[];
  total: number;
  eventLoading: boolean;
  error: string | null;
}

const here = dirname(fileURLToPath(import.meta.url));
const pagePath = resolve(here, '../src/app/alarm/(pages)/integration/detail/page.tsx');
const utilPath = resolve(
  here,
  '../src/app/alarm/(pages)/integration/detail/integrationEventListRequest.ts',
);

function createEventListSession() {
  const guard = createLatestRequestGuard();
  let state: ViewState = {
    eventList: [],
    total: 0,
    eventLoading: false,
    error: null,
  };

  const start = () => {
    const requestId = guard.begin();
    state = { ...state, eventLoading: true };
    return requestId;
  };

  const succeed = (requestId: number, items: EventRow[], total: number) => {
    commitIntegrationEventListSuccess(guard, requestId, () => {
      state = {
        ...state,
        eventList: items,
        total,
        error: null,
      };
    });
    commitIntegrationEventListSettled(guard, requestId, () => {
      state = { ...state, eventLoading: false };
    });
  };

  const fail = (requestId: number) => {
    commitIntegrationEventListSettled(guard, requestId, () => {
      state = { ...state, error: 'loadFailed', eventLoading: false };
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

function assertPageUsesGeneration(source: string) {
  assert.match(
    source,
    /from ['"]@\/context\/latestRequestGuard['"]/,
    'page 必须复用 @/context/latestRequestGuard，不得复制新 guard',
  );
  assert.match(source, /createLatestRequestGuard/, 'page 必须创建 latest request guard');
  assert.match(source, /\.begin\(\)/, 'fetchEventList 必须按单调序号 begin');
  assert.match(
    source,
    /from ['"]\.\/integrationEventListRequest['"]/,
    'page 必须调用抽出的 integrationEventListRequest',
  );
  assert.match(source, /commitIntegrationEventListSuccess\(/, '成功响应必须经 commitIntegrationEventListSuccess 提交');
  assert.match(source, /commitIntegrationEventListSettled\(/, '结束 loading 必须经 commitIntegrationEventListSettled 提交');
  assert.match(source, /\.invalidate\(\)/, '筛选、页码、源变化和卸载必须 invalidate');
  assert.match(source, /k8sMetaRequestSeqRef/, 'K8s 元数据请求序号必须保留');
  assert.doesNotMatch(
    source,
    /setEventList\(\s*res\.items/,
    'fetchEventList 不得手写无序号的 setEventList(res.items)',
  );
  assert.doesNotMatch(
    source,
    /function createLatestRequestGuard|const createLatestRequestGuard\s*=/,
    '不得在 page 内复制一套序号 guard',
  );
}

function assertHelperAcceptsGuard(source: string) {
  assert.match(source, /LatestRequestGuard/, '抽出函数必须接受 LatestRequestGuard');
  assert.match(source, /requestId/, '抽出函数必须接受 requestId');
  assert.doesNotMatch(
    source,
    /createLatestRequestGuard\s*=|function createLatestRequestGuard/,
    'integrationEventListRequest 不得复制一套序号 guard',
  );
}

async function main() {
  assert.equal(typeof createLatestRequestGuard, 'function', '必须 import createLatestRequestGuard');
  assert.equal(typeof commitIntegrationEventListSuccess, 'function', '必须 import commitIntegrationEventListSuccess');
  assert.equal(typeof commitIntegrationEventListSettled, 'function', '必须 import commitIntegrationEventListSettled');

  const search = createEventListSession();
  const staleSearch = search.start();
  const latestSearch = search.start();
  search.succeed(latestSearch, [{ id: 2, title: 'new-title' }], 1);
  search.succeed(staleSearch, [{ id: 1, title: 'old-title' }], 9);
  assert.deepEqual(
    search.getState().eventList,
    [{ id: 2, title: 'new-title' }],
    'old 晚于 new 返回时列表必须保持 new',
  );
  assert.equal(search.getState().total, 1, 'old 晚于 new 返回时 total 必须保持 new');
  assert.equal(search.getState().eventLoading, false);

  const latestFailed = createEventListSession();
  const staleSuccess = latestFailed.start();
  const failedLatest = latestFailed.start();
  latestFailed.fail(failedLatest);
  latestFailed.succeed(staleSuccess, [{ id: 3, title: 'stale-ok' }], 8);
  assert.equal(latestFailed.getState().error, 'loadFailed', '当前请求失败仍可提交错误可见态');
  assert.deepEqual(latestFailed.getState().eventList, [], '旧成功不能在最新失败之后写回列表');
  assert.equal(latestFailed.getState().total, 0);
  assert.equal(latestFailed.getState().eventLoading, false, 'loading 必须由当前请求结束');

  const inflight = createEventListSession();
  const staleFail = inflight.start();
  inflight.start();
  inflight.fail(staleFail);
  assert.equal(inflight.getState().eventLoading, true, '旧失败不得把仍在途的最新请求 loading 清掉');
  assert.equal(inflight.getState().error, null, '旧失败不得展示为当前错误');

  const unmounted = createEventListSession();
  const lateId = unmounted.start();
  unmounted.unmount();
  unmounted.succeed(lateId, [{ id: 4, title: 'late' }], 1);
  unmounted.fail(lateId);
  assert.deepEqual(unmounted.getState().eventList, [], '卸载/invalidate 后旧成功不得写回');
  assert.equal(unmounted.getState().total, 0);
  assert.equal(unmounted.getState().error, null, '卸载后迟到失败不得写回');
  assert.equal(unmounted.getState().eventLoading, true, '卸载后不得用迟到 finally 收口仍有效的会话状态');

  const pageSource = readFileSync(pagePath, 'utf8');
  const utilSource = readFileSync(utilPath, 'utf8');
  assertPageUsesGeneration(pageSource);
  assertHelperAcceptsGuard(utilSource);

  console.log('alarm integration event list stale test passed');
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
