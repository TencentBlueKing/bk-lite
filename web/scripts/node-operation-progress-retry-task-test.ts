import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  mergeCollectorRetryRows,
  readCollectorRetryTaskId,
} from '../src/app/node-manager/(pages)/cloudregion/node/operationProgress/collectorRetryTaskState.ts';

const here = dirname(fileURLToPath(import.meta.url));
const pagePath = resolve(
  here,
  '../src/app/node-manager/(pages)/cloudregion/node/operationProgress/index.tsx',
);

interface ProgressRow {
  node_id: string;
  status: string;
  result?: { steps?: Array<{ action: string }> };
}

function applyCollectorRetry(
  currentRows: ProgressRow[],
  payload: unknown,
  retryRows: ProgressRow[],
): ProgressRow[] {
  const retryTaskId = readCollectorRetryTaskId(payload);
  if (!retryTaskId) {
    return currentRows;
  }
  return mergeCollectorRetryRows(currentRows, retryRows);
}

function assertPageWiresCollectorRetry(pageSource: string) {
  assert.match(
    pageSource,
    /from ['"]\.\/collectorRetryTaskState['"]/,
    'index 必须 import 抽出的 collectorRetryTaskState',
  );
  assert.match(
    pageSource,
    /readCollectorRetryTaskId\(/,
    'handleCollectorRetry 必须读取返回的 task_id',
  );
  assert.match(
    pageSource,
    /mergeCollectorRetryRows\(/,
    'getNodeList 必须按节点合并新任务行',
  );
  assert.match(
    pageSource,
    /const\s+\w+\s*=\s*await\s+installCollector\(/,
    '安装组件重试必须保存 installCollector 返回值',
  );
  assert.match(
    pageSource,
    /const\s+\w+\s*=\s*await\s+batchOperationCollector\(/,
    '启动/停止/重启重试必须保存 batchOperationCollector 返回值',
  );
  assert.match(
    pageSource,
    /getCollectorNodes\(\{\s*taskId:\s*taskIds[\s\S]*?page:[\s\S]*?page_size:/,
    '安装进度仍须查询旧 taskIds（可带当前页 page/page_size）',
  );
  assert.match(
    pageSource,
    /getCollectorOperationNodes\(\{\s*taskId:\s*taskIds[\s\S]*?page:[\s\S]*?page_size:/,
    '启停重启进度仍须查询旧 taskIds（可带当前页 page/page_size）',
  );
  assert.match(
    pageSource,
    /createOperationProgressRequestGuard/,
    '必须保留 requestGuard',
  );
  assert.doesNotMatch(
    pageSource,
    /AbortController|\.abort\(/,
    '不得 abort 后端请求',
  );
  assert.doesNotMatch(
    pageSource,
    /import \{\s*import \{/,
    'index 不得出现重复 import {',
  );
}

async function main() {
  const originalRows: ProgressRow[] = [
    {
      node_id: 'node-failed',
      status: 'error',
      result: { steps: [{ action: 'old-error' }] },
    },
    {
      node_id: 'node-ok',
      status: 'success',
      result: { steps: [{ action: 'old-success' }] },
    },
  ];
  const retryRunningRows: ProgressRow[] = [
    {
      node_id: 'node-failed',
      status: 'running',
      result: { steps: [{ action: 'retry-running' }] },
    },
  ];

  assert.equal(
    readCollectorRetryTaskId({ task_id: 101 }),
    '101',
    '安装组件重试必须读到新 task_id',
  );
  assert.equal(
    readCollectorRetryTaskId({ task_id: 'action-7' }),
    'action-7',
    '启动/停止/重启重试必须读到新 task_id',
  );
  assert.equal(
    readCollectorRetryTaskId({ task_id: 'restart-9' }),
    'restart-9',
    '重启组件重试必须读到新 task_id',
  );

  const mergedInstall = applyCollectorRetry(
    originalRows,
    { task_id: 101 },
    retryRunningRows,
  );
  const retriedInstall = mergedInstall.find((row) => row.node_id === 'node-failed');
  const siblingInstall = mergedInstall.find((row) => row.node_id === 'node-ok');
  assert.equal(retriedInstall?.status, 'running', '被重试行应变为新任务状态');
  assert.equal(
    retriedInstall?.result?.steps?.[0]?.action,
    'retry-running',
    '被重试行日志必须跟随新任务',
  );
  assert.equal(siblingInstall?.status, 'success', '同批其他节点仍保留旧任务状态');
  assert.equal(
    siblingInstall?.result?.steps?.[0]?.action,
    'old-success',
    '同批其他节点日志不得被新任务替换',
  );
  assert.deepEqual(
    mergedInstall.map((row) => row.node_id),
    ['node-failed', 'node-ok'],
    '合并不得隐藏同批其他节点',
  );

  const mergedAction = applyCollectorRetry(
    originalRows,
    { task_id: 'action-7' },
    retryRunningRows,
  );
  assert.equal(
    mergedAction.find((row) => row.node_id === 'node-failed')?.status,
    'running',
    '启停重启重试后被重试行也必须合并新状态',
  );
  assert.equal(
    mergedAction.find((row) => row.node_id === 'node-ok')?.status,
    'success',
    '启停重启重试后其他节点仍保留旧状态',
  );

  const missingPayloads: unknown[] = [undefined, null, {}, { task_id: '' }];
  for (const payload of missingPayloads) {
    const mergedMissing = applyCollectorRetry(
      originalRows,
      payload,
      retryRunningRows,
    );
    assert.equal(
      mergedMissing.find((row) => row.node_id === 'node-failed')?.status,
      'error',
      '缺少 task_id 时不得覆盖旧行',
    );
    assert.equal(
      mergedMissing.find((row) => row.node_id === 'node-ok')?.status,
      'success',
      '缺少 task_id 时其他节点保持不变',
    );
  }

  const pageSource = readFileSync(pagePath, 'utf8');
  assertPageWiresCollectorRetry(pageSource);

  console.log('node operation progress retry task test passed');
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
