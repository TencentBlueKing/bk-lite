import assert from 'node:assert/strict';

import {
  buildRequestDedupKey,
  dedupeInFlightRequest,
} from '../src/app/ops-analysis/api/requestDedup';

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

async function main() {
  const keyA = buildRequestDedupKey(7, {
    page: 1,
    filters: {
      keyword: 'cpu',
      time_range: ['2026-05-07 00:00:00', '2026-05-07 01:00:00'],
    },
  });
  const keyB = buildRequestDedupKey(7, {
    filters: {
      time_range: ['2026-05-07 00:00:00', '2026-05-07 01:00:00'],
      keyword: 'cpu',
    },
    page: 1,
  });
  assert.equal(keyA, keyB, '相同参数不同键顺序必须命中同一个去重 key');

  let requestCount = 0;
  const factory = async () => {
    requestCount += 1;
    await sleep(20);
    return { ok: true, requestCount };
  };

  const [resultA, resultB] = await Promise.all([
    dedupeInFlightRequest(keyA, factory),
    dedupeInFlightRequest(keyB, factory),
  ]);
  assert.equal(requestCount, 1, '并发相同请求只应下发一次');
  assert.deepEqual(resultA, resultB, '并发去重后的结果必须一致');

  await dedupeInFlightRequest(keyA, factory);
  assert.equal(requestCount, 2, '请求完成后不应缓存结果，后续刷新应重新下发');
}

void main();
