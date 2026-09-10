import * as assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createLatestRequestGuard } from '../src/context/latestRequestGuard.ts';
import type { LatestRequestGuard } from '../src/context/latestRequestGuard.ts';

interface SearchItem {
  id: string;
}

interface CommitFns {
  beginTraceSearchRequest: (
    guard: LatestRequestGuard,
    currentRequestId: number,
    cursor?: string,
  ) => number;
  commitTraceSearchSuccess: (
    guard: LatestRequestGuard,
    requestId: number,
    apply: () => void,
  ) => boolean;
  commitTraceSearchFailure: (
    guard: LatestRequestGuard,
    requestId: number,
    reportError: () => void,
  ) => boolean;
  commitTraceSearchSettled: (
    guard: LatestRequestGuard,
    requestId: number,
    settle: () => void,
  ) => boolean;
}

interface SearchState {
  spanItems: SearchItem[];
  traceItems: SearchItem[];
  searching: boolean;
  pageState: 'idle' | 'loading' | 'ready' | 'empty' | 'error';
}

const here = dirname(fileURLToPath(import.meta.url));
const pagePath = resolve(here, '../src/app/apm/explore/traces/page.tsx');
const utilPath = resolve(here, '../src/app/apm/utils/traceSearchRequest.ts');
const guardPath = resolve(here, '../src/context/latestRequestGuard.ts');

async function loadCommitFns(): Promise<CommitFns> {
  let loaded: Partial<CommitFns> = {};
  try {
    loaded = await import('../src/app/apm/utils/traceSearchRequest.ts');
  } catch {
    // RED：提交函数尚未抽出。
  }

  assert.equal(typeof loaded.beginTraceSearchRequest, 'function', '应抽出 beginTraceSearchRequest');
  assert.equal(typeof loaded.commitTraceSearchSuccess, 'function', '应抽出 commitTraceSearchSuccess');
  assert.equal(typeof loaded.commitTraceSearchFailure, 'function', '应抽出 commitTraceSearchFailure');
  assert.equal(typeof loaded.commitTraceSearchSettled, 'function', '应抽出 commitTraceSearchSettled');

  return loaded as CommitFns;
}

function createSearchSession(fns: CommitFns) {
  const guard = createLatestRequestGuard();
  let currentRequestId = 0;
  let state: SearchState = {
    spanItems: [],
    traceItems: [],
    searching: false,
    pageState: 'idle',
  };

  const start = (cursor?: string) => {
    const requestId = fns.beginTraceSearchRequest(guard, currentRequestId, cursor);
    if (!cursor) {
      currentRequestId = requestId;
      state = { ...state, searching: true, pageState: 'loading' };
    } else {
      state = { ...state, searching: true };
    }
    return requestId;
  };

  const succeedSpans = (requestId: number, items: SearchItem[], cursor?: string) => {
    fns.commitTraceSearchSuccess(guard, requestId, () => {
      state = {
        ...state,
        spanItems: cursor ? [...state.spanItems, ...items] : items,
        traceItems: [],
        pageState: items.length === 0 && !cursor ? 'empty' : 'ready',
      };
    });
    fns.commitTraceSearchSettled(guard, requestId, () => {
      state = { ...state, searching: false };
    });
  };

  const succeedTraces = (requestId: number, items: SearchItem[], cursor?: string) => {
    fns.commitTraceSearchSuccess(guard, requestId, () => {
      state = {
        ...state,
        traceItems: cursor ? [...state.traceItems, ...items] : items,
        spanItems: [],
        pageState: items.length === 0 && !cursor ? 'empty' : 'ready',
      };
    });
    fns.commitTraceSearchSettled(guard, requestId, () => {
      state = { ...state, searching: false };
    });
  };

  const fail = (requestId: number) => {
    fns.commitTraceSearchFailure(guard, requestId, () => {
      state = { ...state, pageState: 'error' };
    });
    fns.commitTraceSearchSettled(guard, requestId, () => {
      state = { ...state, searching: false };
    });
  };

  return {
    getState: () => state,
    getCurrentRequestId: () => currentRequestId,
    start,
    succeedSpans,
    succeedTraces,
    fail,
    invalidate: () => guard.invalidate(),
  };
}

function assertPageUsesGeneration(source: string) {
  assert.match(
    source,
    /from ['"]@\/context\/latestRequestGuard['"]/,
    'page 必须复用 @/context/latestRequestGuard，不得复制新 guard',
  );
  assert.match(source, /createLatestRequestGuard/, 'page 必须创建 latest request guard');
  assert.match(
    source,
    /from ['"]@\/app\/apm\/utils\/traceSearchRequest['"]/,
    'page 必须调用抽出的 traceSearchRequest',
  );
  assert.match(source, /beginTraceSearchRequest\(/, 'search 无 cursor 时必须 begin，有 cursor 时复用当前代次');
  assert.match(source, /commitTraceSearchSuccess\(/, '成功响应必须经 commitTraceSearchSuccess 提交');
  assert.match(source, /commitTraceSearchFailure\(/, '失败必须经 commitTraceSearchFailure 提交');
  assert.match(source, /commitTraceSearchSettled\(/, '结束 searching 必须经 commitTraceSearchSettled 提交');
  assert.match(source, /requestGuard\.invalidate\(\)/, '切换粒度、时间窗、清空、卸载必须 invalidate');
  assert.match(source, /limit:\s*50/, '查询 limit 必须仍为 50');
  assert.match(
    source,
    /searchParams\.get\('entity'\) === 'traces' \? 'traces' : 'spans'/,
    '默认粒度必须仍为 Spans',
  );
  assert.doesNotMatch(
    source,
    /function createLatestRequestGuard|const createLatestRequestGuard\s*=/,
    '不得在 page 内复制一套序号 guard',
  );
  assert.doesNotMatch(
    source,
    /getSpans\(query\)\s*\.then\(\s*\(page\)\s*=>\s*\{/,
    'Span then 不得无条件写 items',
  );
  assert.doesNotMatch(
    source,
    /getTraces\(query\)\s*\.then\(\s*\(page\)\s*=>\s*\{/,
    'Trace then 不得无条件写 items',
  );
  assert.doesNotMatch(
    source,
    /disabled=\{searching\}/,
    '不得把禁用 Segmented 当作唯一修复',
  );
}

async function main() {
  const fns = await loadCommitFns();
  const guardSource = readFileSync(guardPath, 'utf8');
  assert.match(guardSource, /export const createLatestRequestGuard/, '必须复用已有 latestRequestGuard');

  const spanThenTrace = createSearchSession(fns);
  const spanRequest = spanThenTrace.start();
  const traceRequest = spanThenTrace.start();
  assert.notEqual(spanRequest, traceRequest, '无 cursor 的新查询必须分配新代次');
  spanThenTrace.succeedTraces(traceRequest, [{ id: 'trace-latest' }]);
  spanThenTrace.succeedSpans(spanRequest, [{ id: 'span-stale' }]);
  assert.deepEqual(
    spanThenTrace.getState().traceItems,
    [{ id: 'trace-latest' }],
    'Span→Trace 逆序：旧 Span 后到不得清空最新 Trace 结果',
  );
  assert.deepEqual(spanThenTrace.getState().spanItems, [], 'Span→Trace 逆序：旧 Span 不得写回 spanItems');
  assert.equal(spanThenTrace.getState().pageState, 'ready');
  assert.equal(spanThenTrace.getState().searching, false);

  const timeWindow = createSearchSession(fns);
  const hourWindow = timeWindow.start();
  const quarterWindow = timeWindow.start();
  timeWindow.succeedSpans(quarterWindow, [{ id: 'span-15m' }]);
  timeWindow.succeedSpans(hourWindow, [{ id: 'span-1h' }]);
  assert.deepEqual(
    timeWindow.getState().spanItems,
    [{ id: 'span-15m' }],
    '同粒度换时间窗：旧查询不得覆盖新结果',
  );
  assert.deepEqual(timeWindow.getState().traceItems, []);
  assert.equal(timeWindow.getState().searching, false);

  const cleared = createSearchSession(fns);
  const staleBeforeClear = cleared.start();
  cleared.succeedSpans(staleBeforeClear, [{ id: 'span-before-clear' }]);
  const inflightAfterClear = cleared.start();
  cleared.invalidate();
  cleared.succeedSpans(inflightAfterClear, [{ id: 'span-after-clear' }]);
  assert.deepEqual(
    cleared.getState().spanItems,
    [{ id: 'span-before-clear' }],
    '清空后旧响应不得写回新结果',
  );
  assert.equal(cleared.getState().searching, true, '清空后旧 finally 不得收口仍有效会话');

  const staleError = createSearchSession(fns);
  const failedOld = staleError.start();
  staleError.start();
  staleError.fail(failedOld);
  assert.equal(staleError.getState().pageState, 'loading', '旧错误晚到不得覆盖最新 loading');
  assert.equal(staleError.getState().searching, true, '旧错误晚到不得把最新 searching 清掉');

  const staleFinally = createSearchSession(fns);
  const oldInflight = staleFinally.start();
  staleFinally.start();
  staleFinally.succeedSpans(oldInflight, [{ id: 'span-old-finally' }]);
  assert.equal(staleFinally.getState().searching, true, '旧 finally 不得清掉最新 searching');
  assert.deepEqual(staleFinally.getState().spanItems, [], '旧成功不得在最新请求仍在途时写回');

  const loadMore = createSearchSession(fns);
  const firstPage = loadMore.start();
  loadMore.succeedSpans(firstPage, [{ id: 'span-page-1' }]);
  const morePage = loadMore.start('cursor-2');
  assert.equal(morePage, firstPage, '加载更多必须复用当前代次，不得作废首屏');
  loadMore.succeedSpans(morePage, [{ id: 'span-page-2' }], 'cursor-2');
  assert.deepEqual(
    loadMore.getState().spanItems.map((item) => item.id),
    ['span-page-1', 'span-page-2'],
    '加载更多必须追加当前代次结果',
  );

  const pageSource = readFileSync(pagePath, 'utf8');
  const utilSource = readFileSync(utilPath, 'utf8');
  assertPageUsesGeneration(pageSource);
  assert.match(
    utilSource,
    /from ['"]@\/context\/latestRequestGuard['"]/,
    'traceSearchRequest 必须复用 LatestRequestGuard 类型',
  );
  assert.doesNotMatch(
    utilSource,
    /createLatestRequestGuard\s*=|function createLatestRequestGuard/,
    'traceSearchRequest 不得复制一套序号 guard',
  );
  assert.match(pageSource, /getSpans\(/, '不得改掉 getSpans 查询入口');
  assert.match(pageSource, /getTraces\(/, '不得改掉 getTraces 查询入口');

  console.log('apm trace search race test passed');
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
