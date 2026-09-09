import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const webRoot = join(dirname(fileURLToPath(import.meta.url)), '..');
const endpointsPage = readFileSync(join(webRoot, 'src/app/apm/explore/endpoints/page.tsx'), 'utf8');
const redLoadUtilPath = join(webRoot, 'src/app/apm/utils/endpointRedLoad.ts');

assert.doesNotMatch(
  endpointsPage,
  /Promise\.allSettled/,
  '端点页不得对可见服务做无界 Promise.allSettled',
);
assert.match(
  endpointsPage,
  /selectServicesForEndpointRed/,
  '端点页必须按服务筛选收窄 RED 请求目标',
);
assert.match(
  endpointsPage,
  /runEndpointRedSettled/,
  '端点页必须走带并发上限的 settled 队列',
);
assert.match(
  endpointsPage,
  /ENDPOINT_RED_CONCURRENCY/,
  '端点页必须使用固定 RED 并发常量',
);
assert.match(
  endpointsPage,
  /getServices\(\)/,
  '端点页必须继续拉取当前环境全部可见服务，不得改成第一页',
);
assert.doesNotMatch(
  endpointsPage,
  /getServices\(\s*\{[^}]*page_size/,
  'getServices 不得传 page_size，以免静默漏项',
);
assert.doesNotMatch(
  endpointsPage,
  /monitor\/dashboards\/shared\/utils\/concurrency/,
  '端点 RED 队列不得跨模块 import monitor runWithConcurrency',
);
assert.equal(existsSync(redLoadUtilPath), true, '必须抽出 apm/utils/endpointRedLoad.ts');
const redLoadUtil = readFileSync(redLoadUtilPath, 'utf8');
assert.doesNotMatch(
  redLoadUtil,
  /monitor\/dashboards\/shared\/utils\/concurrency/,
  'apm/utils 必须自建 settled 队列，不得复用 monitor 并发工具',
);
assert.match(
  endpointsPage,
  /\[authLoading, environment, getServiceRed, getServices, serviceId, timeRange\]/,
  'load 必须把服务筛选纳入请求目标依赖',
);
assert.match(endpointsPage, /t\('apm\.common\.service', '服务'\)/, '筛选文案必须保留「服务」');
assert.match(endpointsPage, /t\('apm\.common\.allServices', '全部服务'\)/, '筛选文案必须保留「全部服务」');
assert.match(endpointsPage, /t\('apm\.common\.environment', '环境'\)/, '筛选文案必须保留「环境」');
assert.match(endpointsPage, /t\('apm\.common\.timeRange', '时间范围'\)/, '筛选文案必须保留「时间范围」');
assert.match(endpointsPage, /t\('apm\.explore\.refreshEndpoints', '刷新端点'\)/, '筛选文案必须保留「刷新端点」');
assert.match(endpointsPage, /metricFailureCount/, '部分失败计数不得被关掉');
assert.match(endpointsPage, /catalogErrorKind\(error\)/, '空结果/无权限路径必须继续走 CatalogState');

interface FakeService {
  id: string;
}

const makeServices = (count: number): FakeService[] => (
  Array.from({ length: count }, (_, index) => ({ id: `svc-${index}` }))
);

const delay = () => new Promise<void>((resolve) => setImmediate(resolve));

const main = async () => {
  const {
    ENDPOINT_RED_CONCURRENCY,
    runEndpointRedSettled,
    selectServicesForEndpointRed,
  } = await import('../src/app/apm/utils/endpointRedLoad.ts');

  assert.equal(ENDPOINT_RED_CONCURRENCY, 6, '全服务视图必须使用固定并发上限 6');

  assert.deepEqual(
    selectServicesForEndpointRed(makeServices(0), 'all').map((service) => service.id),
    [],
    '0 个服务时请求目标应为空',
  );
  assert.deepEqual(
    selectServicesForEndpointRed(makeServices(1), 'all').map((service) => service.id),
    ['svc-0'],
    '1 个服务的全部服务视图只覆盖该服务',
  );
  assert.equal(
    selectServicesForEndpointRed(makeServices(200), 'all').length,
    200,
    '全部服务视图必须覆盖当前环境全部可见服务，不得只取第一页',
  );
  assert.deepEqual(
    selectServicesForEndpointRed(makeServices(200), 'svc-17').map((service) => service.id),
    ['svc-17'],
    '单服务筛选只请求选中 id',
  );

  const runTracked = async (
    services: FakeService[],
    options: {
      failIds?: Set<string>;
      isCancelled?: () => boolean;
      onFulfilled?: (value: { id: string }) => void;
      hangUntil?: (id: string) => Promise<void>;
    } = {},
  ) => {
    let active = 0;
    let peak = 0;
    let started = 0;
    const requestedIds: string[] = [];
    const results = await runEndpointRedSettled(
      services,
      async (service) => {
        started += 1;
        active += 1;
        peak = Math.max(peak, active);
        requestedIds.push(service.id);
        await (options.hangUntil ? options.hangUntil(service.id) : delay());
        active -= 1;
        if (options.failIds?.has(service.id)) {
          throw new Error(`red-failed:${service.id}`);
        }
        return { id: service.id };
      },
      {
        concurrency: ENDPOINT_RED_CONCURRENCY,
        isCancelled: options.isCancelled,
        onFulfilled: options.onFulfilled,
      },
    );
    return { active, peak, started, requestedIds, results };
  };

  const emptyRun = await runTracked([]);
  assert.equal(emptyRun.started, 0, '0 个服务不得发出 RED 请求');
  assert.equal(emptyRun.results.length, 0, '0 个服务应得到空 settled 结果');

  const singleRun = await runTracked(makeServices(1));
  assert.equal(singleRun.started, 1, '1 个服务只发出 1 次 RED');
  assert.equal(singleRun.peak, 1, '1 个服务的在途请求不得超过 1');
  assert.deepEqual(singleRun.requestedIds, ['svc-0']);

  const largeRun = await runTracked(makeServices(200));
  assert.equal(largeRun.started, 200, '200 个服务最终必须发出 200 次 RED');
  assert.ok(
    largeRun.peak <= ENDPOINT_RED_CONCURRENCY,
    `200 个服务的最大在途必须 <= ${ENDPOINT_RED_CONCURRENCY}，实际 ${largeRun.peak}`,
  );
  assert.equal(largeRun.peak, ENDPOINT_RED_CONCURRENCY, '满负荷批次应打到并发上限');
  assert.equal(
    largeRun.results.filter((result) => result.status === 'fulfilled').length,
    200,
    '全部成功时最终结果数应等于可见服务全集',
  );

  const selected = selectServicesForEndpointRed(makeServices(200), 'svc-42');
  const filteredRun = await runTracked(selected);
  assert.deepEqual(filteredRun.requestedIds, ['svc-42'], '单服务筛选不得请求其他服务');
  assert.equal(filteredRun.started, 1, '单服务筛选只请求该 id');

  const failIds = new Set(['svc-3', 'svc-8', 'svc-19']);
  const partialRun = await runTracked(makeServices(20), { failIds });
  const partialSuccess = partialRun.results.flatMap((result) => (
    result.status === 'fulfilled' ? [result.value.id] : []
  ));
  const partialFailures = partialRun.results.filter((result) => result.status === 'rejected');
  assert.equal(partialRun.started, 20, '部分失败不得中断剩余 RED 请求');
  assert.equal(partialSuccess.length, 17, '部分失败必须保留成功行');
  assert.equal(partialFailures.length, 3, '部分失败必须计数失败项');
  assert.equal(partialSuccess.includes('svc-3'), false, '失败服务不得混入成功行');

  let generation = 1;
  const staleFulfilled: string[] = [];
  const staleRun = await runTracked(makeServices(20), {
    isCancelled: () => generation !== 1,
    onFulfilled: (value) => staleFulfilled.push(value.id),
    hangUntil: async () => {
      generation = 2;
      await delay();
    },
  });
  assert.ok(staleRun.started <= ENDPOINT_RED_CONCURRENCY, '过期批次必须停止继续排队');
  assert.equal(staleFulfilled.length, 0, '过期批次不得把成功结果写回当前列表');
  assert.ok(
    staleRun.results.every((result) => result.status === 'fulfilled' || result.status === 'rejected'),
    '已启动的过期请求仍应 settled，但不能写回',
  );

  const writes: Array<{ range: string; ids: string[] }> = [];
  let releaseStale: () => void = () => undefined;
  const staleGate = new Promise<void>((resolve) => {
    releaseStale = resolve;
  });
  const loadByRange = async (
    range: string,
    batchId: number,
    current: { id: number },
    waitFor?: Promise<void>,
  ) => {
    const collected: string[] = [];
    await runEndpointRedSettled(
      makeServices(12),
      async (service) => {
        if (waitFor) await waitFor;
        await delay();
        return { id: service.id, range };
      },
      {
        concurrency: ENDPOINT_RED_CONCURRENCY,
        isCancelled: () => current.id !== batchId,
        onFulfilled: (value) => {
          if (current.id !== batchId) return;
          collected.push(value.id);
          writes.push({ range, ids: [...collected] });
        },
      },
    );
    if (current.id !== batchId) return;
    writes.push({ range, ids: [...collected] });
  };

  const currentBatch = { id: 1 };
  const firstLoad = loadByRange('1h', 1, currentBatch, staleGate);
  await delay();
  currentBatch.id = 2;
  const currentLoad = loadByRange('15m', 2, currentBatch);
  releaseStale();
  await Promise.all([firstLoad, currentLoad]);
  assert.equal(
    writes.every((entry) => entry.range === '15m'),
    true,
    '切换时间窗后过期批次不得覆盖当前列表',
  );
  assert.ok(writes.length > 0, '当前时间窗批次必须能写回');
  assert.equal(writes.at(-1)?.ids.length, 12, '最终写回必须覆盖当前批次已取回全集');

  console.log(JSON.stringify({
    ok: true,
    concurrency: ENDPOINT_RED_CONCURRENCY,
    cases: {
      empty: emptyRun.started,
      single: singleRun.started,
      large: { started: largeRun.started, peak: largeRun.peak },
      filtered: filteredRun.requestedIds,
      partialFailures: partialFailures.length,
      staleStarted: staleRun.started,
      timeRangeWrites: writes.at(-1)?.range,
    },
  }));
};

void main();
