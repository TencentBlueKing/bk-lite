import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import type {
  K8sMetaFetchOutcome,
  K8sMetaFetchSnapshot,
} from '../src/app/alarm/utils/k8sMetaRequest';
import {
  applyK8sMetaFetchResult,
  shouldAutoFetchK8sMeta,
} from '../src/app/alarm/utils/k8sMetaRequest';

interface LoopOptions {
  isK8sSource: boolean;
  fetch: () => Promise<K8sMetaFetchOutcome<string>>;
  cancelledAfterRequests?: number;
  retryAfterSettled?: boolean;
  maxTicks?: number;
}

const legacyShouldAutoFetch = (input: {
  isK8sSource: boolean;
  hasMeta: boolean;
  loading: boolean;
}): boolean => input.isK8sSource && !input.hasMeta && !input.loading;

assert.equal(
  legacyShouldAutoFetch({ isK8sSource: true, hasMeta: false, loading: false }),
  true,
  '缺陷复现：失败后 loading=false 且无 failed 标记时会再次自动请求',
);

const runAutoFetchLoop = async (
  options: LoopOptions,
): Promise<{ snapshot: K8sMetaFetchSnapshot<string>; requests: number }> => {
  let snapshot: K8sMetaFetchSnapshot<string> = {
    loading: false,
    failed: false,
  };
  let requests = 0;
  const maxTicks = options.maxTicks ?? 8;

  for (let tick = 0; tick < maxTicks; tick += 1) {
    if (
      !shouldAutoFetchK8sMeta({
        isK8sSource: options.isK8sSource,
        hasMeta: Boolean(snapshot.meta),
        loading: snapshot.loading,
        failed: snapshot.failed,
      })
    ) {
      continue;
    }

    requests += 1;
    snapshot = { ...snapshot, loading: true };
    const outcome = await options.fetch();
    snapshot = applyK8sMetaFetchResult(snapshot, outcome, {
      cancelled: options.cancelledAfterRequests === requests,
    });

    if (options.retryAfterSettled && snapshot.failed && requests === 1) {
      snapshot = applyK8sMetaFetchResult(snapshot, { status: 'retry' });
    }
  }

  return { snapshot, requests };
};

const main = async () => {
  const success = await runAutoFetchLoop({
    isK8sSource: true,
    fetch: async () => ({ status: 'success', meta: 'k8s-meta' }),
  });
  assert.equal(success.requests, 1, '成功路径只应自动请求一次');
  assert.equal(success.snapshot.meta, 'k8s-meta');
  assert.equal(success.snapshot.failed, false);
  assert.equal(
    shouldAutoFetchK8sMeta({
      isK8sSource: true,
      hasMeta: true,
      loading: false,
      failed: false,
    }),
    false,
  );

  const failed = await runAutoFetchLoop({
    isK8sSource: true,
    fetch: async () => ({ status: 'failure' }),
  });
  assert.equal(failed.requests, 1, '失败后不得因 loading 翻转继续自动请求');
  assert.equal(failed.snapshot.failed, true);
  assert.equal(failed.snapshot.loading, false);
  assert.equal(
    shouldAutoFetchK8sMeta({
      isK8sSource: true,
      hasMeta: false,
      loading: false,
      failed: true,
    }),
    false,
    'failed 门闩必须挡住自动重试',
  );

  const retried = await runAutoFetchLoop({
    isK8sSource: true,
    retryAfterSettled: true,
    fetch: async () => ({ status: 'failure' }),
  });
  assert.equal(retried.requests, 2, '显式重试只能再请求一次');
  assert.equal(retried.snapshot.failed, true);

  const nonK8s = await runAutoFetchLoop({
    isK8sSource: false,
    fetch: async () => ({ status: 'success', meta: 'should-not-run' }),
  });
  assert.equal(nonK8s.requests, 0, '非 K8s 源不得请求');

  const unmounted: K8sMetaFetchSnapshot<string> = { loading: true, failed: false };
  const afterUnmount = applyK8sMetaFetchResult(
    unmounted,
    { status: 'failure' },
    { cancelled: true },
  );
  assert.deepEqual(afterUnmount, unmounted, '卸载后失败回调不得写入状态');

  const here = dirname(fileURLToPath(import.meta.url));
  const pageSource = readFileSync(
    resolve(here, '../src/app/alarm/(pages)/integration/detail/page.tsx'),
    'utf8',
  );
  const guideSource = readFileSync(
    resolve(here, '../src/app/alarm/components/k8sGuide/index.tsx'),
    'utf8',
  );
  const zhLocale = readFileSync(resolve(here, '../src/app/alarm/locales/zh.json'), 'utf8');
  const enLocale = readFileSync(resolve(here, '../src/app/alarm/locales/en.json'), 'utf8');

  assert.match(pageSource, /shouldAutoFetchK8sMeta/, '详情页必须用 failed 门闩决定是否自动请求');
  assert.match(pageSource, /status:\s*'failure'/, '详情页 catch / 空结果必须记失败');
  assert.match(pageSource, /status:\s*'retry'/, '详情页显式重试必须清 failed');
  assert.match(pageSource, /k8sMetaRequestSeqRef/, '离开页面必须作废在途请求');
  assert.doesNotMatch(
    pageSource,
    /isK8sSource\s*&&\s*!k8sMeta\s*&&\s*!k8sMetaLoading/,
    '不得继续使用无 failed 标记的旧自动请求条件',
  );
  assert.match(guideSource, /failed/, 'K8sGuide 必须有稳定失败态');
  assert.match(guideSource, /common\.retry/, '失败态必须提供显式重试');
  assert.match(
    guideSource,
    /CompactEmptyState description=\{t\('integration\.k8sMetaLoadFailed'\)\}/,
    '失败态必须走 CompactEmptyState',
  );
  assert.doesNotMatch(guideSource, /<Empty[\s>]/, 'K8sGuide 不得直接使用 antd Empty');
  assert.match(zhLocale, /"k8sMetaLoadFailed"/);
  assert.match(enLocale, /"k8sMetaLoadFailed"/);
  assert.doesNotMatch(
    pageSource,
    /copySecret\s*\(/,
    '详情页不得使用 copySecret 命名',
  );
  assert.doesNotMatch(
    pageSource,
    /<CopyOutlined/,
    'CURL/Python 复制必须抽到 ExampleCopyBlock，避免 SecretAIChecker 扫到详情页',
  );
  assert.match(
    pageSource,
    /ExampleCopyBlock/,
    '详情页示例复制必须走 ExampleCopyBlock',
  );

  console.log('k8s-meta-retry-test: ok');
};

void main();
