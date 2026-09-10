import * as assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createLatestRequestGuard } from '../src/context/latestRequestGuard.ts';
import type { LatestRequestGuard } from '../src/context/latestRequestGuard.ts';
import type { ApmTopologyGraph } from '../src/app/apm/types.ts';

interface TopologyTimeRange {
  startedAt: string;
  endedAt: string;
}

interface TopologyLoadSuccessPayload {
  graph: ApmTopologyGraph;
  range: TopologyTimeRange;
}

interface TopologyLoadView {
  graph: ApmTopologyGraph;
  range: TopologyTimeRange;
  state: 'ready' | 'empty';
}

interface CommitFns {
  beginTopologyLoad: (guard: LatestRequestGuard) => number;
  commitTopologyLoadSuccess: (
    guard: LatestRequestGuard,
    requestId: number,
    payload: TopologyLoadSuccessPayload,
    apply: (next: TopologyLoadView) => void,
  ) => boolean;
  commitTopologyLoadFailure: (
    guard: LatestRequestGuard,
    requestId: number,
    reportError: () => void,
  ) => boolean;
}

interface ViewState {
  graph: ApmTopologyGraph;
  range: TopologyTimeRange | null;
  state: 'loading' | 'ready' | 'empty' | 'error';
}

const here = dirname(fileURLToPath(import.meta.url));
const pagePath = resolve(here, '../src/app/apm/services/topology/page.tsx');
const utilPath = resolve(here, '../src/app/apm/utils/topologyLoadRequest.ts');

const emptyGraph: ApmTopologyGraph = {
  nodes: [],
  edges: [],
  sampled_traces: 0,
  truncated: false,
  data_state: 'no_data',
};

function graphNamed(name: string): ApmTopologyGraph {
  return {
    nodes: [
      {
        id: name,
        service_namespace: 'default',
        service_name: name,
        environment: 'prod',
        health: 'healthy',
        sampled_spans: 1,
        error_spans: 0,
      },
    ],
    edges: [],
    sampled_traces: 1,
    truncated: false,
    data_state: 'available',
  };
}

async function loadCommitFns(): Promise<CommitFns> {
  let loaded: Partial<CommitFns> = {};
  try {
    loaded = await import('../src/app/apm/utils/topologyLoadRequest.ts');
  } catch {
    // RED：提交函数尚未抽出。
  }

  assert.equal(typeof loaded.beginTopologyLoad, 'function', '应抽出 beginTopologyLoad');
  assert.equal(typeof loaded.commitTopologyLoadSuccess, 'function', '应抽出 commitTopologyLoadSuccess');
  assert.equal(typeof loaded.commitTopologyLoadFailure, 'function', '应抽出 commitTopologyLoadFailure');

  return loaded as CommitFns;
}

function createLoadSession(fns: CommitFns) {
  const guard = createLatestRequestGuard();
  let state: ViewState = {
    graph: emptyGraph,
    range: null,
    state: 'loading',
  };

  const start = () => {
    const requestId = fns.beginTopologyLoad(guard);
    state = { ...state, state: state.state === 'ready' || state.state === 'empty' ? state.state : 'loading' };
    return requestId;
  };

  const succeed = (requestId: number, payload: TopologyLoadSuccessPayload) => {
    fns.commitTopologyLoadSuccess(guard, requestId, payload, (next) => {
      state = {
        graph: next.graph,
        range: next.range,
        state: next.state,
      };
    });
  };

  const fail = (requestId: number) => {
    fns.commitTopologyLoadFailure(guard, requestId, () => {
      state = { ...state, state: 'error' };
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
  assert.match(
    source,
    /from ['"]@\/app\/apm\/utils\/topologyLoadRequest['"]/,
    'page 必须调用抽出的 topologyLoadRequest',
  );
  assert.match(source, /beginTopologyLoad\(/, 'load 必须按单调序号 begin');
  assert.match(source, /commitTopologyLoadSuccess\(/, '成功响应必须经 commitTopologyLoadSuccess 提交');
  assert.match(source, /commitTopologyLoadFailure\(/, '失败必须经 commitTopologyLoadFailure 提交');
  assert.match(source, /requestGuard\.invalidate\(\)/, '切换筛选或卸载后必须 invalidate，迟到响应不得写回');
  assert.match(source, /include_inferred:\s*false/, 'getTopology 必须保持 include_inferred=false');
  assert.match(source, /只看异常/, '只看异常语义必须保留');
  assert.match(source, /定位节点/, '定位节点语义必须保留');
  assert.match(source, /title=\{t\('apm\.topology\.title', '服务拓扑'\)\}/, '页头必须仍是服务拓扑');
  assert.match(source, /aria-label=\{t\('apm\.topology\.window', '拓扑时间窗口'\)\}/, '时间窗控件 aria 必须是拓扑时间窗口');
  assert.match(source, /options=\{\['15m', '1h', '4h', '1d', '7d'\]\}/, '时间窗选项必须仍是 15m/1h/4h/1d/7d');
  assert.match(source, /aria-label=\{t\('apm\.topology\.filterEnvironment', '按环境筛选拓扑'\)\}/, '环境筛选 aria 必须保留');
  assert.match(source, /placeholder=\{t\('apm\.common\.allEnvironments', '全部环境'\)\}/, '环境筛选占位必须是全部环境');
  assert.match(source, /aria-label=\{t\('apm\.topology\.refresh', '刷新拓扑'\)\}/, '刷新按钮 aria 必须是刷新拓扑');
  assert.doesNotMatch(source, /setGraph\(\s*result\s*\)/, 'load 不得在 await 后无条件写 graph');
  assert.doesNotMatch(source, /setRange\(\s*nextRange\s*\)/, '不得在请求开始时单独更新 range');
  assert.doesNotMatch(
    source,
    /function createLatestRequestGuard|const createLatestRequestGuard\s*=/,
    '不得在 page 内复制一套序号 guard',
  );
  assert.doesNotMatch(
    source,
    /<Segmented[\s\S]{0,200}disabled=/,
    '不得把禁用时间窗 Segmented 当唯一修复',
  );
  assert.doesNotMatch(
    source,
    /<Select[\s\S]{0,240}disabled=/,
    '不得把禁用环境 Select 当唯一修复',
  );
}

async function main() {
  const fns = await loadCommitFns();

  const windowRace = createLoadSession(fns);
  const staleWindow = windowRace.start();
  const latestWindow = windowRace.start();
  const latestWindowRange = { startedAt: '2026-09-09T01:00:00.000Z', endedAt: '2026-09-09T02:00:00.000Z' };
  const staleWindowRange = { startedAt: '2026-09-09T01:45:00.000Z', endedAt: '2026-09-09T02:00:00.000Z' };
  windowRace.succeed(latestWindow, { graph: graphNamed('window-1h'), range: latestWindowRange });
  windowRace.succeed(staleWindow, { graph: graphNamed('window-15m'), range: staleWindowRange });
  assert.equal(windowRace.getState().graph.nodes[0]?.id, 'window-1h', '时间窗乱序：后发先至的旧图不得覆盖新图');
  assert.deepEqual(windowRace.getState().range, latestWindowRange, '时间窗乱序：graph 与该次 nextRange 必须同代次提交');
  assert.equal(windowRace.getState().state, 'ready');

  const envRace = createLoadSession(fns);
  const staleEnv = envRace.start();
  const latestEnv = envRace.start();
  const prodRange = { startedAt: '2026-09-09T03:00:00.000Z', endedAt: '2026-09-09T04:00:00.000Z' };
  const stagingRange = { startedAt: '2026-09-09T03:00:01.000Z', endedAt: '2026-09-09T04:00:01.000Z' };
  envRace.succeed(latestEnv, { graph: graphNamed('env-staging'), range: stagingRange });
  envRace.succeed(staleEnv, { graph: graphNamed('env-prod'), range: prodRange });
  assert.equal(envRace.getState().graph.nodes[0]?.id, 'env-staging', '环境乱序：旧环境图不得覆盖当前环境');
  assert.deepEqual(envRace.getState().range, stagingRange, '环境乱序：range 必须属于当前环境请求');

  const durationRace = createLoadSession(fns);
  const staleDuration = durationRace.start();
  const latestDuration = durationRace.start();
  const slicedRange = { startedAt: '2026-09-09T05:00:00.000Z', endedAt: '2026-09-09T06:00:00.000Z' };
  const unslicedRange = { startedAt: '2026-09-09T05:00:02.000Z', endedAt: '2026-09-09T06:00:02.000Z' };
  durationRace.succeed(latestDuration, { graph: graphNamed('duration-500'), range: slicedRange });
  durationRace.succeed(staleDuration, { graph: graphNamed('duration-none'), range: unslicedRange });
  assert.equal(durationRace.getState().graph.nodes[0]?.id, 'duration-500', '耗时下限乱序：旧切片图不得覆盖当前切片');
  assert.deepEqual(durationRace.getState().range, slicedRange);

  const refreshRace = createLoadSession(fns);
  const staleRefresh = refreshRace.start();
  const latestRefresh = refreshRace.start();
  const refreshRange = { startedAt: '2026-09-09T07:00:00.000Z', endedAt: '2026-09-09T08:00:00.000Z' };
  const staleRefreshRange = { startedAt: '2026-09-09T06:59:00.000Z', endedAt: '2026-09-09T07:59:00.000Z' };
  refreshRace.succeed(latestRefresh, { graph: graphNamed('refresh-new'), range: refreshRange });
  refreshRace.succeed(staleRefresh, { graph: graphNamed('refresh-old'), range: staleRefreshRange });
  assert.equal(refreshRace.getState().graph.nodes[0]?.id, 'refresh-new', '手动刷新乱序：旧刷新结果不得覆盖新图');
  assert.deepEqual(refreshRace.getState().range, refreshRange);

  const staleError = createLoadSession(fns);
  const lateError = staleError.start();
  const latestOk = staleError.start();
  const okRange = { startedAt: '2026-09-09T09:00:00.000Z', endedAt: '2026-09-09T10:00:00.000Z' };
  staleError.succeed(latestOk, { graph: graphNamed('current-ok'), range: okRange });
  staleError.fail(lateError);
  assert.equal(staleError.getState().graph.nodes[0]?.id, 'current-ok', '旧错误晚到不得覆盖当前图');
  assert.equal(staleError.getState().state, 'ready', '旧错误晚到不得把当前成功改成失败');
  assert.deepEqual(staleError.getState().range, okRange);

  const unmounted = createLoadSession(fns);
  const lateSuccess = unmounted.start();
  unmounted.unmount();
  unmounted.succeed(lateSuccess, {
    graph: graphNamed('after-unmount'),
    range: { startedAt: '2026-09-09T11:00:00.000Z', endedAt: '2026-09-09T12:00:00.000Z' },
  });
  unmounted.fail(lateSuccess);
  assert.deepEqual(unmounted.getState().graph, emptyGraph, '卸载后迟到成功不得写回 graph');
  assert.equal(unmounted.getState().range, null, '卸载后迟到成功不得写回 range');
  assert.equal(unmounted.getState().state, 'loading', '卸载后迟到失败不得写回 state');

  const pageSource = readFileSync(pagePath, 'utf8');
  const utilSource = readFileSync(utilPath, 'utf8');
  assertPageUsesGeneration(pageSource);
  assert.doesNotMatch(
    utilSource,
    /createLatestRequestGuard\s*=|function createLatestRequestGuard/,
    'topologyLoadRequest 不得复制一套序号 guard',
  );
  assert.match(
    pageSource,
    /commitTopologyLoadSuccess\([\s\S]*setGraph\([\s\S]*setRange\([\s\S]*setState\(/,
    'page 必须按序号同代次提交 graph/range/state',
  );

  console.log('apm topology load race test passed');
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
