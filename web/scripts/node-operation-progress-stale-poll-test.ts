import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { createOperationProgressRequestGuard } from '../src/app/node-manager/(pages)/cloudregion/node/operationProgress/operationProgressRequestGuard.ts';

const here = dirname(fileURLToPath(import.meta.url));
const pagePath = resolve(
  here,
  '../src/app/node-manager/(pages)/cloudregion/node/operationProgress/index.tsx',
);

const AUTO_ADVANCE_DELAY = 5000;

interface ProgressRow {
  status: string;
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function createFakeTimers() {
  let nextId = 1;
  const intervals = new Map<number, { callback: () => void; ms: number }>();
  const timeouts = new Map<number, { callback: () => void; ms: number }>();

  return {
    intervals,
    timeouts,
    setInterval(callback: () => void, ms: number) {
      const id = nextId++;
      intervals.set(id, { callback, ms });
      return id;
    },
    clearInterval(id: unknown) {
      intervals.delete(id as number);
    },
    setTimeout(callback: () => void, ms: number) {
      const id = nextId++;
      timeouts.set(id, { callback, ms });
      return id;
    },
    clearTimeout(id: unknown) {
      timeouts.delete(id as number);
    },
    fireTimeouts() {
      for (const [id, timer] of [...timeouts]) {
        timeouts.delete(id);
        timer.callback();
      }
    },
  };
}

function createProgressSession() {
  const guard = createOperationProgressRequestGuard();
  const timers = createFakeTimers();
  const state = {
    tableData: [] as ProgressRow[],
    intervalSchedules: 0,
    onNextCount: 0,
    fetchCount: 0,
  };
  let intervalId: number | null = null;
  let autoAdvanceId: number | null = null;
  let currentGeneration = 0;

  const clearIntervalTimer = () => {
    if (intervalId != null) {
      timers.clearInterval(intervalId);
      intervalId = null;
    }
  };

  const clearAutoAdvanceTimer = () => {
    if (autoAdvanceId != null) {
      timers.clearTimeout(autoAdvanceId);
      autoAdvanceId = null;
    }
  };

  const stopProgressRequests = () => {
    guard.invalidate();
    clearIntervalTimer();
    clearAutoAdvanceTimer();
  };

  const schedulePolling = (generation: number) => {
    if (!guard.shouldContinue(generation)) {
      return;
    }
    clearIntervalTimer();
    state.intervalSchedules += 1;
    intervalId = timers.setInterval(() => {
      if (!guard.shouldContinue(generation)) {
        return;
      }
      state.fetchCount += 1;
    }, 5000);
  };

  const scheduleAutoAdvance = (generation: number) => {
    if (!guard.shouldContinue(generation)) {
      return;
    }
    clearAutoAdvanceTimer();
    autoAdvanceId = timers.setTimeout(() => {
      autoAdvanceId = null;
      if (!guard.shouldContinue(generation)) {
        return;
      }
      state.onNextCount += 1;
    }, AUTO_ADVANCE_DELAY);
  };

  const getNodeList = async (
    generation: number,
    fetchFn: () => Promise<ProgressRow[]>,
    options?: { autoAdvance?: boolean },
  ) => {
    const rows = await fetchFn();
    if (!guard.shouldContinue(generation)) {
      return;
    }
    state.tableData = rows;
    schedulePolling(generation);
    if (options?.autoAdvance) {
      scheduleAutoAdvance(generation);
    }
  };

  return {
    state,
    timers,
    guard,
    begin() {
      currentGeneration = guard.begin();
      return currentGeneration;
    },
    unmount: stopProgressRequests,
    finish: stopProgressRequests,
    getNodeList,
    schedulePolling,
    generation: () => currentGeneration,
  };
}

function assertPageWiresGuard(pageSource: string) {
  assert.match(
    pageSource,
    /from ['"]\.\/operationProgressRequestGuard['"]/,
    'index 必须 import 抽出的 operationProgressRequestGuard',
  );
  assert.match(pageSource, /createOperationProgressRequestGuard/, '必须创建 request guard');
  assert.match(pageSource, /\.begin\(\)/, 'effect 启动必须 begin');
  assert.match(pageSource, /\.invalidate\(\)/, '卸载与结束操作必须 invalidate');
  assert.match(pageSource, /shouldContinue\(/, 'await 后必须检查 shouldContinue');
  assert.match(pageSource, /autoAdvanceTimerRef/, '必须保存 auto-advance timeout');
  assert.match(
    pageSource,
    /clearTimeout\(autoAdvanceTimerRef/,
    '卸载必须清 auto-advance timeout',
  );
  assert.match(
    pageSource,
    /getNodeList\('timer',\s*currentGeneration\)/,
    'schedulePolling 回调必须携带 generation',
  );
  assert.doesNotMatch(
    pageSource,
    /AbortController|\.abort\(/,
    '不得 abort 后端请求',
  );
}

async function main() {
  const lateInterval = createProgressSession();
  const lateIntervalFetch = deferred<ProgressRow[]>();
  const lateIntervalGeneration = lateInterval.begin();
  lateInterval.schedulePolling(lateIntervalGeneration);
  const lateIntervalPending = lateInterval.getNodeList(
    lateIntervalGeneration,
    () => lateIntervalFetch.promise,
  );
  lateInterval.unmount();
  const intervalSchedulesAfterUnmount = lateInterval.state.intervalSchedules;
  lateIntervalFetch.resolve([{ status: 'running' }]);
  await lateIntervalPending;
  assert.equal(
    lateInterval.timers.intervals.size,
    0,
    '卸载后迟到状态不得重建 interval',
  );
  assert.equal(
    lateInterval.state.intervalSchedules,
    intervalSchedulesAfterUnmount,
    '卸载后迟到状态不得再次 schedulePolling',
  );

  const lateSuccess = createProgressSession();
  const lateSuccessFetch = deferred<ProgressRow[]>();
  const lateSuccessGeneration = lateSuccess.begin();
  const lateSuccessPending = lateSuccess.getNodeList(
    lateSuccessGeneration,
    () => lateSuccessFetch.promise,
    { autoAdvance: true },
  );
  lateSuccess.unmount();
  lateSuccessFetch.resolve([{ status: 'success' }]);
  await lateSuccessPending;
  lateSuccess.timers.fireTimeouts();
  assert.equal(lateSuccess.state.onNextCount, 0, '卸载后迟到成功不得 onNext');
  assert.equal(lateSuccess.timers.timeouts.size, 0, '卸载后迟到成功不得再挂 auto-advance');

  const clearAdvance = createProgressSession();
  const clearAdvanceGeneration = clearAdvance.begin();
  await clearAdvance.getNodeList(
    clearAdvanceGeneration,
    async () => [{ status: 'success' }],
    { autoAdvance: true },
  );
  assert.equal(clearAdvance.timers.timeouts.size, 1, '成功后应挂起 auto-advance timeout');
  clearAdvance.unmount();
  assert.equal(clearAdvance.timers.timeouts.size, 0, '卸载必须清 auto-advance timeout');
  clearAdvance.timers.fireTimeouts();
  assert.equal(clearAdvance.state.onNextCount, 0, '已卸载的 auto-advance 不得 onNext');

  const replaced = createProgressSession();
  const staleFetch = deferred<ProgressRow[]>();
  const staleGeneration = replaced.begin();
  const stalePending = replaced.getNodeList(staleGeneration, () => staleFetch.promise, {
    autoAdvance: true,
  });
  const latestFetch = deferred<ProgressRow[]>();
  const latestGeneration = replaced.begin();
  const latestPending = replaced.getNodeList(
    latestGeneration,
    () => latestFetch.promise,
    { autoAdvance: true },
  );
  staleFetch.resolve([{ status: 'success' }]);
  await stalePending;
  assert.equal(replaced.state.onNextCount, 0, '旧 generation 迟到成功不得 onNext');
  latestFetch.resolve([{ status: 'success' }]);
  await latestPending;
  replaced.timers.fireTimeouts();
  assert.equal(replaced.state.onNextCount, 1, '新 generation 成功仍可自动下一步');
  assert.equal(replaced.timers.intervals.size, 1, '新 generation 仍可轮询');

  const alive = createProgressSession();
  const aliveGeneration = alive.begin();
  await alive.getNodeList(
    aliveGeneration,
    async () => [{ status: 'success' }],
    { autoAdvance: true },
  );
  assert.equal(alive.timers.intervals.size, 1, '有效 generation 仍可轮询');
  alive.timers.fireTimeouts();
  assert.equal(alive.state.onNextCount, 1, '有效 generation 仍可自动下一步');

  const pageSource = readFileSync(pagePath, 'utf8');
  assertPageWiresGuard(pageSource);

  console.log('node operation progress stale poll test passed');
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
