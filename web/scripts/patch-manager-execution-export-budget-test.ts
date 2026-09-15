import assert from 'node:assert/strict';

import {
  EXECUTION_EXPORT_LIST_PAGE_SIZE,
  EXECUTION_EXPORT_MAX_RISK_DETAILS,
  EXECUTION_EXPORT_MAX_TASKS,
  EXECUTION_EXPORT_RISK_DETAIL_CONCURRENCY,
  collectPagedItems,
  mapWithConcurrency,
} from '../src/app/patch-manager/utils/execution-export-budget';

const delay = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

assert.ok(EXECUTION_EXPORT_LIST_PAGE_SIZE > 0 && EXECUTION_EXPORT_LIST_PAGE_SIZE < 10000);
assert.ok(EXECUTION_EXPORT_MAX_TASKS > 0);
assert.ok(EXECUTION_EXPORT_MAX_RISK_DETAILS > 0);
assert.ok(EXECUTION_EXPORT_RISK_DETAIL_CONCURRENCY > 0);

const main = async () => {
  const listRequests: Array<{ page: number; pageSize: number }> = [];
  const allPages = await collectPagedItems({
    fetchPage: async ({ page, pageSize }) => {
      listRequests.push({ page, pageSize });
      const start = (page - 1) * pageSize;
      const items = Array.from({ length: 7 }, (_, index) => index + 1).slice(start, start + pageSize);
      return { items, count: 7 };
    },
    pageSize: 3,
    maxItems: 500,
  });

  assert.deepEqual(
    listRequests.map((request) => request.pageSize),
    [3, 3, 3],
    '列表必须按固定 page_size 分页，直到没有下一页',
  );
  assert.ok(
    listRequests.every((request) => request.pageSize !== 10000),
    '导出全部不得请求 page_size=10000',
  );
  assert.deepEqual(allPages.items, [1, 2, 3, 4, 5, 6, 7]);
  assert.equal(allPages.truncated, false);

  const defaultPageSizes: number[] = [];
  await collectPagedItems({
    fetchPage: async ({ pageSize }) => {
      defaultPageSizes.push(pageSize);
      return { items: [1], count: 1 };
    },
  });
  assert.deepEqual(defaultPageSizes, [EXECUTION_EXPORT_LIST_PAGE_SIZE]);
  assert.notEqual(EXECUTION_EXPORT_LIST_PAGE_SIZE, 10000);

  const truncatedTaskRequests: number[] = [];
  const truncatedTasks = await collectPagedItems({
    fetchPage: async ({ page, pageSize }) => {
      truncatedTaskRequests.push(page);
      return {
        items: [page * 10, page * 10 + 1, page * 10 + 2].slice(0, pageSize),
        count: 20,
      };
    },
    pageSize: 3,
    maxItems: 4,
  });
  assert.equal(truncatedTasks.items.length, 4);
  assert.equal(truncatedTasks.truncated, true);
  assert.deepEqual(truncatedTaskRequests, [1, 2], '达到任务上限后必须停止继续请求列表页');

  let activeRequests = 0;
  let peakRequests = 0;
  let startedRequests = 0;
  const riskItems = Array.from({ length: 12 }, (_, index) => index + 1);
  const concurrent = await mapWithConcurrency({
    items: riskItems,
    concurrency: 3,
    mapper: async (item) => {
      startedRequests += 1;
      activeRequests += 1;
      peakRequests = Math.max(peakRequests, activeRequests);
      await delay(20);
      activeRequests -= 1;
      return item * 10;
    },
  });
  assert.deepEqual(concurrent.items, riskItems.map((item) => item * 10));
  assert.equal(concurrent.truncated, false);
  assert.equal(startedRequests, 12);
  assert.ok(peakRequests <= 3, `风险详情并发 ${peakRequests} 超过上限 3`);
  assert.equal(peakRequests, 3);

  let detailCalls = 0;
  const truncatedDetails = await mapWithConcurrency({
    items: ['a', 'b', 'c', 'd', 'e', 'f'],
    concurrency: 2,
    maxResults: 4,
    mapper: async (item) => {
      detailCalls += 1;
      await delay(5);
      return item;
    },
  });
  assert.deepEqual(truncatedDetails.items, ['a', 'b', 'c', 'd']);
  assert.equal(truncatedDetails.truncated, true);
  assert.equal(detailCalls, 4, '达到风险详情上限后必须停止继续请求');

  const defaultCap = await mapWithConcurrency({
    items: Array.from({ length: EXECUTION_EXPORT_MAX_RISK_DETAILS + 3 }, (_, index) => index),
    concurrency: EXECUTION_EXPORT_RISK_DETAIL_CONCURRENCY,
    mapper: async (item) => item,
  });
  assert.equal(defaultCap.items.length, EXECUTION_EXPORT_MAX_RISK_DETAILS);
  assert.equal(defaultCap.truncated, true);

  console.log('补丁执行记录导出预算约束通过');
};

void main();
