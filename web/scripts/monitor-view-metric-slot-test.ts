import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  MAX_CONCURRENT_REQUESTS,
  occupyMetricRequestSlot,
  releaseMetricRequestSlot,
  runMetricRangeQuery,
  waitForAvailableMetricSlot,
} from '../src/app/monitor/(pages)/view/metricRequestSlot.ts';

const here = dirname(fileURLToPath(import.meta.url));
const monitorViewPath = resolve(
  here,
  '../src/app/monitor/(pages)/view/monitorView.tsx'
);
const metricViewsPath = resolve(
  here,
  '../src/app/monitor/components/metric-views/index.tsx'
);

function rejectAs(name: string, message: string): Promise<never> {
  const error = new Error(message);
  error.name = name;
  return Promise.reject(error);
}

async function assertPostRejectReleasesSlot() {
  const slots = new Map<number, AbortController>();
  const outcome = await runMetricRangeQuery({
    slots,
    metricId: 11,
    controller: new AbortController(),
    postQuery: () => rejectAs('Error', 'query failed'),
  });

  assert.equal(outcome, 'failed');
  assert.equal(
    slots.size,
    0,
    'post 拒绝后必须释放该指标槽，不能让 activeRequestsRef 继续占用'
  );
}

async function assertFourFailuresAllowFifth() {
  const slots = new Map<number, AbortController>();
  await Promise.all(
    [1, 2, 3, 4].map((metricId) =>
      runMetricRangeQuery({
        slots,
        metricId,
        controller: new AbortController(),
        postQuery: () => rejectAs('Error', `metric ${metricId} failed`),
      })
    )
  );

  assert.equal(
    slots.size,
    0,
    '四次 post 拒绝后槽位数必须回到 0，否则第五个指标会卡在 while 等待'
  );

  const fifthController = new AbortController();
  let fifthOccupied = false;
  const waitFifth = (async () => {
    const ready = await waitForAvailableMetricSlot(slots, () => true, {
      intervalMs: 5,
    });
    if (ready) {
      occupyMetricRequestSlot(slots, 5, fifthController);
      fifthOccupied = true;
    }
  })();

  let timedOut = false;
  await Promise.race([
    waitFifth,
    new Promise<void>((resolve) => {
      setTimeout(() => {
        timedOut = true;
        resolve();
      }, 80);
    }),
  ]);

  assert.equal(timedOut, false, '四个失败后第五个必须能立刻占槽，不能继续排队');
  assert.equal(fifthOccupied, true, '四个失败后第五个指标仍可请求');
  assert.equal(slots.get(5), fifthController);
}

async function assertAbortReleasesSlot() {
  const slots = new Map<number, AbortController>();
  const controller = new AbortController();
  const outcome = await runMetricRangeQuery({
    slots,
    metricId: 21,
    controller,
    postQuery: () => {
      controller.abort();
      return rejectAs('AbortError', 'aborted');
    },
  });

  assert.equal(outcome, 'aborted');
  assert.equal(slots.size, 0, 'Abort 后必须释放槽');
}

async function assertOldRequestDoesNotDropReplacement() {
  const slots = new Map<number, AbortController>();
  const oldController = new AbortController();
  const newController = new AbortController();
  let rejectOld: ((error: unknown) => void) | undefined;

  const oldDone = runMetricRangeQuery({
    slots,
    metricId: 31,
    controller: oldController,
    postQuery: () =>
      new Promise<never>((_, reject) => {
        rejectOld = reject;
      }),
  });

  assert.equal(slots.get(31), oldController);
  occupyMetricRequestSlot(slots, 31, newController);
  assert.equal(slots.get(31), newController);

  const abortError = new Error('replaced');
  abortError.name = 'AbortError';
  rejectOld?.(abortError);
  const outcome = await oldDone;

  assert.equal(outcome, 'aborted');
  assert.equal(slots.get(31), newController, '旧请求结束不得删替代的新槽');
  assert.equal(slots.size, 1);
  assert.equal(releaseMetricRequestSlot(slots, 31, oldController), false);
  assert.equal(slots.get(31), newController);
}

function assertMonitorViewWiresSlotHelpers() {
  const source = readFileSync(monitorViewPath, 'utf8');
  const metricViews = readFileSync(metricViewsPath, 'utf8');

  assert.match(
    source,
    /from ['"]\.\/metricRequestSlot['"]/,
    'monitorView 必须使用抽出的 metricRequestSlot'
  );
  assert.match(
    source,
    /MAX_CONCURRENT_REQUESTS/,
    '并发上限必须继续来自 MAX_CONCURRENT_REQUESTS'
  );
  assert.match(
    source,
    /query_by_metric_range/,
    '查询 URL 不得改动'
  );
  assert.match(
    source,
    /suppressErrorNotification:\s*true/,
    '失败仍须 suppressErrorNotification'
  );
  assert.match(
    source,
    /runMetricRangeQuery|releaseMetricRequestSlot/,
    'post 与释放必须走抽出的槽位契约'
  );
  assert.match(
    source,
    /waitForAvailableMetricSlot|generation !== requestGenerationRef/,
    '代际变化在占槽前退出时必须能结束 loading'
  );

  assert.match(
    metricViews,
    /activeRequestsRef\.current\.set\(metric\.id, abortController\)/,
    '#5254 metric-views 本轮不得改动'
  );
  assert.match(
    metricViews,
    /if \(error\.name === 'AbortError'\) \{\s*return;/,
    'metric-views 仍保持原 post catch 早退，留给 #5254'
  );
}

async function main() {
  assert.equal(MAX_CONCURRENT_REQUESTS, 4, '不得改并发上限');
  await assertPostRejectReleasesSlot();
  await assertFourFailuresAllowFifth();
  await assertAbortReleasesSlot();
  await assertOldRequestDoesNotDropReplacement();
  assertMonitorViewWiresSlotHelpers();
  console.log('monitor view metric slot ok');
}

main().catch((error: unknown) => {
  console.error(error);
  process.exitCode = 1;
});
