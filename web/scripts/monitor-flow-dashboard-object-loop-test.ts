import * as assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

interface FlowObjectLoadTicket {
  generation: number;
}

interface FlowObjectLoadCoordinator {
  begin: (isLoading: boolean) => FlowObjectLoadTicket | null;
  shouldApply: (ticket: FlowObjectLoadTicket) => boolean;
  shouldReloadForFetcherIdentity: (
    previousFetcher: unknown,
    nextFetcher: unknown,
  ) => boolean;
  invalidate: () => void;
}

const here = dirname(fileURLToPath(import.meta.url));
const helperPath = resolve(
  here,
  '../src/app/monitor/dashboards/objects/flow-common/flowObjectLoad.ts',
);
const pagePath = resolve(
  here,
  '../src/app/monitor/dashboards/objects/flow-common/flow-dashboard-page.tsx',
);

const REPRO_COPY = {
  menu: '视图',
  rowButton: '仪表盘',
  titles: ['NetFlow 流量分析', 'sFlow 流量分析'],
  sections: ['健康概览', '流量分析'],
  placeholder: '选择实例',
  kpis: ['总流量速率', '总包速率', '平均包大小', '有效采样率'],
} as const;

function pageReloadsOnFetcherIdentity(source: string): boolean {
  return /},\s*\[\s*getMonitorObject\s*,\s*isLoading\s*\]/.test(source);
}

async function simulatePageObjectLoad(options: {
  isLoading: boolean;
  reloadOnFetcherIdentity: boolean;
  invalidateBeforeApply?: boolean;
  maxRounds?: number;
}): Promise<{ requestCount: number; appliedCount: number }> {
  const maxRounds = options.maxRounds ?? 5;
  let requestCount = 0;
  let appliedCount = 0;
  let generation = 0;
  let latest = 0;

  const makeFetcher = () => {
    return async () => {
      requestCount += 1;
      return [{ id: requestCount }];
    };
  };

  let fetcher = makeFetcher();

  const runRound = async (round: number): Promise<void> => {
    if (options.isLoading || round > maxRounds) return;

    const ticketGeneration = ++generation;
    latest = ticketGeneration;
    const currentFetcher = fetcher;
    const data = await currentFetcher();

    if (options.invalidateBeforeApply) {
      latest += 1;
    }
    if (ticketGeneration !== latest) return;

    const nextObjects = data || [];
    assert.ok(Array.isArray(nextObjects), '成功路径必须写入对象数组');
    appliedCount += 1;

    const nextFetcher = makeFetcher();
    if (options.reloadOnFetcherIdentity && currentFetcher !== nextFetcher) {
      fetcher = nextFetcher;
      await runRound(round + 1);
    }
  };

  await runRound(1);
  return { requestCount, appliedCount };
}

async function loadCoordinator(): Promise<FlowObjectLoadCoordinator> {
  let loaded: {
    createFlowObjectLoadCoordinator?: unknown;
    shouldReloadFlowObjectsForFetcherIdentity?: unknown;
  } = {};
  try {
    loaded = await import(
      '../src/app/monitor/dashboards/objects/flow-common/flowObjectLoad.ts'
    );
  } catch {
    // RED：对象列表加载世代尚未抽出。
  }

  assert.equal(
    typeof loaded.createFlowObjectLoadCoordinator,
    'function',
    '应抽出 createFlowObjectLoadCoordinator',
  );
  assert.equal(
    typeof loaded.shouldReloadFlowObjectsForFetcherIdentity,
    'function',
    '应抽出 shouldReloadFlowObjectsForFetcherIdentity',
  );

  const coordinator = (
    loaded.createFlowObjectLoadCoordinator as () => FlowObjectLoadCoordinator
  )();
  assert.equal(typeof coordinator.begin, 'function', 'coordinator.begin 必须存在');
  assert.equal(typeof coordinator.shouldApply, 'function', 'coordinator.shouldApply 必须存在');
  coordinator.shouldReloadForFetcherIdentity =
    loaded.shouldReloadFlowObjectsForFetcherIdentity as FlowObjectLoadCoordinator['shouldReloadForFetcherIdentity'];
  return coordinator;
}

function assertPageUsesCoordinator(source: string) {
  assert.match(
    source,
    /from ['"]\.\/flowObjectLoad['"]/,
    'FlowDashboardPage 必须复用抽出的 flowObjectLoad',
  );
  assert.match(source, /getMonitorObjectRef/, '必须用 ref 稳定 getMonitorObject');
  assert.match(source, /\.begin\(\s*isLoading\s*\)/, '认证未就绪时必须走 begin(isLoading)');
  assert.match(source, /\.shouldApply\(/, '迟到响应必须经 shouldApply 再写回');
  assert.match(source, /\.invalidate\(\)/, '卸载必须作废在途世代');
  assert.doesNotMatch(
    source,
    /},\s*\[\s*getMonitorObject\s*,\s*isLoading\s*\]/,
    'effect 不得因 getMonitorObject 函数身份重载',
  );
}

async function main() {
  assert.equal(REPRO_COPY.menu, '视图');
  assert.equal(REPRO_COPY.rowButton, '仪表盘');
  assert.deepEqual(REPRO_COPY.titles, ['NetFlow 流量分析', 'sFlow 流量分析']);
  assert.deepEqual(REPRO_COPY.sections, ['健康概览', '流量分析']);
  assert.equal(REPRO_COPY.placeholder, '选择实例');
  assert.deepEqual(REPRO_COPY.kpis, [
    '总流量速率',
    '总包速率',
    '平均包大小',
    '有效采样率',
  ]);

  const pageSource = readFileSync(pagePath, 'utf8');
  const reloadOnFetcherIdentity = pageReloadsOnFetcherIdentity(pageSource);
  const loop = await simulatePageObjectLoad({
    isLoading: false,
    reloadOnFetcherIdentity,
  });

  assert.equal(
    loop.requestCount,
    1,
    `isLoading=false 且函数身份变化 + setObjects 新数组后应只请求 1 次，实际 ${loop.requestCount} 次`,
  );
  assert.equal(loop.appliedCount, 1, '成功写回新数组不得触发下一轮对象列表请求');

  const authBlocked = await simulatePageObjectLoad({
    isLoading: true,
    reloadOnFetcherIdentity: true,
  });
  assert.equal(authBlocked.requestCount, 0, 'isLoading=true 时不得请求 monitor_object');

  const stale = await simulatePageObjectLoad({
    isLoading: false,
    reloadOnFetcherIdentity: false,
    invalidateBeforeApply: true,
  });
  assert.equal(stale.requestCount, 1, '卸载后仍允许在途请求结束');
  assert.equal(stale.appliedCount, 0, '过期世代不得写回 objects');

  const coordinator = await loadCoordinator();
  const firstFetcher = async () => [];
  const nextFetcher = async () => [];
  assert.equal(
    coordinator.shouldReloadForFetcherIdentity(firstFetcher, nextFetcher),
    false,
    '函数身份变化不得视为需要重载对象列表',
  );

  assert.equal(coordinator.begin(true), null, '认证未就绪时 begin 不得开世代');

  const ticket = coordinator.begin(false);
  assert.ok(ticket, '认证就绪后 begin 必须开世代');
  assert.equal(coordinator.shouldApply(ticket!), true, '当前世代响应应可写回');
  coordinator.invalidate();
  assert.equal(coordinator.shouldApply(ticket!), false, '卸载后迟到响应必须忽略');

  const nextTicket = coordinator.begin(false);
  assert.ok(nextTicket, '作废后再次就绪应开新世代');
  assert.notEqual(nextTicket!.generation, ticket!.generation);
  assert.equal(coordinator.shouldApply(nextTicket!), true);
  assert.equal(coordinator.shouldApply(ticket!), false);

  assertPageUsesCoordinator(pageSource);

  const helperSource = readFileSync(helperPath, 'utf8');
  assert.match(helperSource, /export function createFlowObjectLoadCoordinator/);
  assert.match(helperSource, /export function shouldReloadFlowObjectsForFetcherIdentity/);

  console.log('monitor-flow-dashboard-object-loop-test: ok');
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
