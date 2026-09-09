import * as assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createLatestRequestGuard } from '../src/context/latestRequestGuard.ts';
import type { LatestRequestGuard } from '../src/context/latestRequestGuard.ts';
import type {
  CollectToolExecuteResponse,
  CollectToolResultResponse,
  CollectToolSubmitResponse,
  ExecStatus,
} from '../src/app/cmdb/types/collectTool.ts';

interface CollectToolCommitFns {
  commitCollectToolSubmit: (
    guard: LatestRequestGuard,
    requestId: number,
    apply: () => void,
  ) => boolean;
  commitCollectToolPoll: (
    guard: LatestRequestGuard,
    requestId: number,
    apply: () => void,
  ) => boolean;
  commitCollectToolFailure: (
    guard: LatestRequestGuard,
    requestId: number,
    apply: () => void,
  ) => boolean;
}

interface SessionState {
  execStatus: ExecStatus;
  result: CollectToolExecuteResponse | null;
  timerRunning: boolean;
  pollScheduled: boolean;
}

const here = dirname(fileURLToPath(import.meta.url));
const hookPath = resolve(
  here,
  '../src/app/cmdb/(pages)/assetManage/autoDiscovery/featureLibrary/collectionTool/hooks/useCollectTool.ts',
);
const utilPath = resolve(
  here,
  '../src/app/cmdb/(pages)/assetManage/autoDiscovery/featureLibrary/collectionTool/hooks/collectToolRequest.ts',
);
const localePath = resolve(here, '../src/app/cmdb/locales/zh.json');
const menuPath = resolve(here, '../src/app/cmdb/constants/menu.json');

const PAGE_COPY = {
  menuManage: '管理',
  menuAutoDiscovery: '自动发现',
  menuCollectTool: '采集工具',
  pageTitle: '采集工具',
  snmpTab: 'SNMP 工具',
  testConnection: '测试连通性',
  resultTitle: '采集结果',
  pause: '暂停',
};

async function loadCommitFns(): Promise<CollectToolCommitFns> {
  let loaded: Partial<CollectToolCommitFns> = {};
  try {
    loaded = await import(
      '../src/app/cmdb/(pages)/assetManage/autoDiscovery/featureLibrary/collectionTool/hooks/collectToolRequest.ts'
    );
  } catch {
    // RED：提交函数尚未抽出。
  }

  assert.equal(typeof loaded.commitCollectToolSubmit, 'function', '应抽出 commitCollectToolSubmit');
  assert.equal(typeof loaded.commitCollectToolPoll, 'function', '应抽出 commitCollectToolPoll');
  assert.equal(typeof loaded.commitCollectToolFailure, 'function', '应抽出 commitCollectToolFailure');

  return loaded as CollectToolCommitFns;
}

function makeResult(requestId: string, success: boolean): CollectToolExecuteResponse {
  return {
    request_id: requestId,
    protocol: 'snmp',
    action: 'test_connection',
    executor: 'stargazer',
    success,
    stage: success ? 'collect' : 'timeout',
    summary: success ? 'ok' : 'fail',
    raw_log: success ? 'ok-log' : 'fail-log',
    duration_ms: 12,
    meta: { target: '10.0.0.1', port: 161 },
  };
}

function submitPending(debugId: string): CollectToolSubmitResponse {
  return {
    debug_id: debugId,
    status: 'pending',
    poll_interval_ms: 2000,
  };
}

function pollPending(debugId: string): CollectToolResultResponse {
  return {
    debug_id: debugId,
    status: 'pending',
    poll_interval_ms: 2000,
  };
}

function pollRunning(debugId: string): CollectToolResultResponse {
  return {
    debug_id: debugId,
    status: 'running',
    poll_interval_ms: 2000,
  };
}

function pollSuccess(debugId: string): CollectToolResultResponse {
  return {
    debug_id: debugId,
    status: 'success',
    poll_interval_ms: 2000,
    result: makeResult(debugId, true),
  };
}

function applyFinal(
  state: SessionState,
  response: CollectToolExecuteResponse | undefined,
): void {
  state.timerRunning = false;
  state.pollScheduled = false;
  if (!response) {
    state.execStatus = 'error';
    return;
  }
  state.result = response;
  state.execStatus = response.success ? 'success' : 'error';
}

function createSession(fns: CollectToolCommitFns) {
  const guard = createLatestRequestGuard();
  const state: SessionState = {
    execStatus: 'idle',
    result: null,
    timerRunning: false,
    pollScheduled: false,
  };

  const beginExecute = () => {
    const requestId = guard.begin();
    state.execStatus = 'submitting';
    state.result = null;
    state.timerRunning = true;
    state.pollScheduled = false;
    return requestId;
  };

  const pause = () => {
    guard.invalidate();
    state.timerRunning = false;
    state.pollScheduled = false;
    if (state.execStatus === 'running' || state.execStatus === 'submitting') {
      state.execStatus = 'idle';
    }
  };

  const unmount = () => {
    guard.invalidate();
    state.timerRunning = false;
    state.pollScheduled = false;
  };

  const applySubmit = (requestId: number, response: CollectToolSubmitResponse) => {
    return fns.commitCollectToolSubmit(guard, requestId, () => {
      if (response.status === 'error' && response.result) {
        applyFinal(state, response.result);
        return;
      }
      state.execStatus = 'running';
      state.pollScheduled = true;
    });
  };

  const applyPoll = (requestId: number, response: CollectToolResultResponse) => {
    return fns.commitCollectToolPoll(guard, requestId, () => {
      if (response.status === 'pending' || response.status === 'running') {
        state.execStatus = 'running';
        state.pollScheduled = true;
        return;
      }
      if (response.status === 'success' || response.status === 'error') {
        applyFinal(state, response.result);
        return;
      }
      state.timerRunning = false;
      state.pollScheduled = false;
      state.execStatus = 'error';
    });
  };

  const applyFailure = (requestId: number, errorResult: CollectToolExecuteResponse) => {
    return fns.commitCollectToolFailure(guard, requestId, () => {
      state.timerRunning = false;
      state.pollScheduled = false;
      state.result = errorResult;
      state.execStatus = 'error';
    });
  };

  return {
    getState: () => state,
    beginExecute,
    pause,
    unmount,
    applySubmit,
    applyPoll,
    applyFailure,
  };
}

function assertHookUsesGeneration(source: string) {
  assert.match(
    source,
    /from ['"]@\/context\/latestRequestGuard['"]/,
    'hook 必须复用 @/context/latestRequestGuard，不得复制新 guard',
  );
  assert.match(source, /createLatestRequestGuard/, 'hook 必须创建 latest request guard');
  assert.match(
    source,
    /from ['"]\.\/collectToolRequest['"]/,
    'hook 必须调用抽出的 collectToolRequest',
  );
  assert.match(source, /requestGuard\.begin\(\)/, 'execute 开始时必须 begin 新代次');
  assert.match(source, /commitCollectToolSubmit\(/, '提交响应必须经 commitCollectToolSubmit 提交');
  assert.match(source, /commitCollectToolPoll\(/, '轮询响应必须经 commitCollectToolPoll 提交');
  assert.match(source, /commitCollectToolFailure\(/, 'catch 必须经 commitCollectToolFailure 提交');
  assert.match(source, /requestGuard\.invalidate\(\)/, 'pause 与卸载必须 invalidate');

  const invalidates = source.match(/requestGuard\.invalidate\(\)/g);
  assert.ok(
    invalidates && invalidates.length >= 2,
    'pause 与 effect cleanup 都必须 invalidate',
  );

  const pollFn = source.match(/const pollResult[\s\S]*?(?=\n  const execute)/)?.[0] || '';
  assert.ok(pollFn.includes('const pollResult'), '必须能定位 pollResult');
  assert.doesNotMatch(pollFn, /requestGuard\.begin\(\)/, '同一 execute 的后续 poll 不得再次 begin');
  assert.match(pollFn, /commitCollectToolPoll\(/, 'poll await 后必须按代次提交');
  assert.match(pollFn, /commitCollectToolFailure\(/, 'poll catch 必须按代次提交');

  const executeFn = source.match(/const execute[\s\S]*?(?=\n  const pause)/)?.[0] || '';
  assert.ok(executeFn.includes('const execute'), '必须能定位 execute');
  assert.match(executeFn, /requestGuard\.begin\(\)/, 'execute 必须 begin');
  assert.match(executeFn, /commitCollectToolSubmit\(/, 'execute await 后必须按代次提交');
  assert.match(executeFn, /commitCollectToolFailure\(/, 'execute catch 必须按代次提交');

  assert.doesNotMatch(
    source,
    /function createLatestRequestGuard|const createLatestRequestGuard\s*=/,
    '不得在 hook 内复制一套序号 guard',
  );
  assert.doesNotMatch(
    source,
    /取消任务|已取消|abortCollect|cancelCollect/,
    '暂停仍只停本地跟踪，不得暗示服务端已取消',
  );
}

async function main() {
  const locale = readFileSync(localePath, 'utf8');
  const menu = readFileSync(menuPath, 'utf8');
  assert.match(menu, new RegExp(`"title": "${PAGE_COPY.menuManage}"`));
  assert.match(menu, new RegExp(`"title": "${PAGE_COPY.menuAutoDiscovery}"`));
  assert.match(menu, new RegExp(`"title": "${PAGE_COPY.menuCollectTool}"`));
  assert.match(locale, new RegExp(`"pageTitle": "${PAGE_COPY.pageTitle}"`));
  assert.match(locale, new RegExp(`"snmpTool": "${PAGE_COPY.snmpTab}"`));
  assert.match(locale, new RegExp(`"testConnection": "${PAGE_COPY.testConnection}"`));
  assert.match(locale, new RegExp(`"resultTitle": "${PAGE_COPY.resultTitle}"`));
  assert.match(locale, new RegExp(`"pause": "${PAGE_COPY.pause}"`));

  const fns = await loadCommitFns();

  const pausedDuringSubmit = createSession(fns);
  const submitGen = pausedDuringSubmit.beginExecute();
  pausedDuringSubmit.pause();
  const submitApplied = pausedDuringSubmit.applySubmit(submitGen, submitPending('debug-submit'));
  assert.equal(submitApplied, false, '提交中暂停后旧 pending 不得提交');
  assert.equal(pausedDuringSubmit.getState().execStatus, 'idle', '提交中暂停后不得恢复运行中');
  assert.equal(pausedDuringSubmit.getState().pollScheduled, false, '提交中暂停后不得安排新 timeout');
  assert.equal(pausedDuringSubmit.getState().timerRunning, false);

  const pausedDuringPoll = createSession(fns);
  const pollGen = pausedDuringPoll.beginExecute();
  pausedDuringPoll.applySubmit(pollGen, submitPending('debug-poll'));
  assert.equal(pausedDuringPoll.getState().execStatus, 'running');
  pausedDuringPoll.pause();
  const pollApplied = pausedDuringPoll.applyPoll(pollGen, pollRunning('debug-poll'));
  assert.equal(pollApplied, false, '轮询中暂停后旧 running 不得提交');
  assert.equal(pausedDuringPoll.getState().execStatus, 'idle', '轮询中暂停后不得恢复运行中');
  assert.equal(pausedDuringPoll.getState().pollScheduled, false, '轮询中暂停后不得再 setTimeout');
  const latePollError = pausedDuringPoll.applyFailure(pollGen, makeResult('debug-poll', false));
  assert.equal(latePollError, false, '暂停后迟到失败不得写状态');
  assert.equal(pausedDuringPoll.getState().execStatus, 'idle');
  assert.equal(pausedDuringPoll.getState().result, null);

  const unmounted = createSession(fns);
  const unmountGen = unmounted.beginExecute();
  unmounted.unmount();
  assert.equal(unmounted.applySubmit(unmountGen, submitPending('debug-unmount')), false);
  assert.equal(unmounted.applyPoll(unmountGen, pollSuccess('debug-unmount')), false);
  assert.equal(unmounted.applyFailure(unmountGen, makeResult('debug-unmount', false)), false);
  assert.equal(unmounted.getState().result, null, '卸载后迟到响应不得写结果');
  assert.equal(unmounted.getState().pollScheduled, false, '卸载后不得再安排轮询');
  assert.notEqual(unmounted.getState().execStatus, 'running', '卸载后不得写回运行中');
  assert.notEqual(unmounted.getState().execStatus, 'success', '卸载后迟到终态不得写成功');

  const sequential = createSession(fns);
  const genA = sequential.beginExecute();
  sequential.applySubmit(genA, submitPending('debug-A'));
  const genB = sequential.beginExecute();
  assert.equal(sequential.getState().timerRunning, true, 'execute B 必须启动新计时器');
  assert.equal(sequential.getState().result, null);
  const staleSuccess = sequential.applyPoll(genA, pollSuccess('debug-A'));
  assert.equal(staleSuccess, false, 'A 在途时 execute B，A 的 success 不得提交');
  assert.equal(sequential.getState().result, null, 'A 的 success 不得覆盖 B 的 request_id');
  assert.equal(sequential.getState().timerRunning, true, 'A 的终态不得 stopTimer 停掉 B 的计时器');
  sequential.applySubmit(genB, submitPending('debug-B'));
  sequential.applyPoll(genB, pollPending('debug-B'));
  sequential.applyPoll(genB, pollSuccess('debug-B'));
  assert.equal(sequential.getState().result?.request_id, 'debug-B', '迟到终态只属于当前代次');
  assert.equal(sequential.getState().execStatus, 'success');
  assert.equal(sequential.getState().timerRunning, false);
  const lateAAfterB = sequential.applyPoll(genA, pollSuccess('debug-A-late'));
  assert.equal(lateAAfterB, false, 'B 完成后 A 的迟到终态仍不得覆盖');
  assert.equal(sequential.getState().result?.request_id, 'debug-B');

  const currentOk = createSession(fns);
  const currentGen = currentOk.beginExecute();
  currentOk.applySubmit(currentGen, submitPending('debug-current'));
  currentOk.applyPoll(currentGen, pollSuccess('debug-current'));
  assert.equal(currentOk.getState().result?.request_id, 'debug-current', '当前代次终态必须可写');
  assert.equal(currentOk.getState().execStatus, 'success');

  const hookSource = readFileSync(hookPath, 'utf8');
  const utilSource = readFileSync(utilPath, 'utf8');
  assertHookUsesGeneration(hookSource);
  assert.match(
    utilSource,
    /from ['"]@\/context\/latestRequestGuard['"]/,
    'collectToolRequest 必须复用 LatestRequestGuard 类型',
  );
  assert.doesNotMatch(
    utilSource,
    /createLatestRequestGuard\s*=|function createLatestRequestGuard/,
    'collectToolRequest 不得复制一套序号 guard',
  );
  assert.match(utilSource, /commitIfCurrent/, '抽出模块必须经 commitIfCurrent 提交');

  console.log('collect tool pause race test passed');
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
