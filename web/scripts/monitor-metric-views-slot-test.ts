import assert from 'node:assert/strict';

import {
  MAX_CONCURRENT_METRIC_REQUESTS,
  canEnterMetricRequestSlot,
  executeMetricViewRequest,
  occupyMetricRequestSlot,
  releaseMetricRequestSlotIfCurrent,
} from '../src/app/monitor/components/metric-views/metricRequestSlot.ts';

const rejectPost = async (): Promise<never> => {
  throw new Error('query_by_metric_range rejected');
};

const abortPost = async (): Promise<never> => {
  const error = new Error('The user aborted a request.');
  error.name = 'AbortError';
  throw error;
};

const main = async () => {
  assert.equal(MAX_CONCURRENT_METRIC_REQUESTS, 4, '并发上限必须保持 4');

  const failedSlots = new Map<number, AbortController>();
  const failedIds = [11, 12, 13, 14];
  await Promise.all(
    failedIds.map((metricId) =>
      executeMetricViewRequest({
        slots: failedSlots,
        metricId,
        controller: new AbortController(),
        post: rejectPost,
      }),
    ),
  );

  assert.equal(
    failedSlots.size,
    0,
    'post 拒绝后必须释放槽位，activeRequestsRef.size 应回到 0',
  );
  assert.equal(
    canEnterMetricRequestSlot(failedSlots),
    true,
    '四个 post 失败后第五个指标仍应能占槽',
  );

  const fifthController = new AbortController();
  occupyMetricRequestSlot(failedSlots, 15, fifthController);
  assert.equal(failedSlots.size, 1, '第五个指标应成功占槽');
  assert.equal(
    releaseMetricRequestSlotIfCurrent(failedSlots, 15, fifthController),
    true,
  );
  assert.equal(failedSlots.size, 0);

  const replacedSlots = new Map<number, AbortController>();
  const oldController = new AbortController();
  const newController = new AbortController();
  occupyMetricRequestSlot(replacedSlots, 21, oldController);
  occupyMetricRequestSlot(replacedSlots, 21, newController);
  assert.equal(
    releaseMetricRequestSlotIfCurrent(replacedSlots, 21, oldController),
    false,
    '被替换的旧请求不得删除新槽',
  );
  assert.equal(replacedSlots.get(21), newController);
  assert.equal(
    releaseMetricRequestSlotIfCurrent(replacedSlots, 21, newController),
    true,
  );

  const abortSlots = new Map<number, AbortController>();
  const abortController = new AbortController();
  await executeMetricViewRequest({
    slots: abortSlots,
    metricId: 31,
    controller: abortController,
    post: abortPost,
  });
  assert.equal(abortSlots.size, 0, 'AbortError 也必须释放槽位');

  console.log('monitor metric-views slot helpers ok');
};

void main();
