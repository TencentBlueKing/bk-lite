import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const webRoot = join(dirname(fileURLToPath(import.meta.url)), '..');
const read = (path: string) => readFileSync(join(webRoot, path), 'utf8');

const traces = read('src/app/apm/traces/page.tsx');
const endpoints = read('src/app/apm/endpoints/page.tsx');
const errors = read('src/app/apm/errors/page.tsx');

assert.match(traces, /title="调用链"/, 'Trace 搜索页应使用产品术语“调用链”');
assert.match(traces, /TraceDistribution/, '调用链页应提供与原型一致的耗时分布视图');
assert.match(traces, /分面筛选/, '调用链页应提供真实数据驱动的分面筛选');
assert.match(endpoints, /getServices\(\)/, '端点列表必须来自真实服务目录');
assert.match(endpoints, /getServiceRed\(/, '端点列表必须来自真实 RED 指标');
assert.match(endpoints, /top_endpoints/, '端点列表必须使用服务 RED 的端点聚合结果');
assert.match(endpoints, /'7d'/, '端点页应支持原型中的 7 天时间范围');
assert.match(errors, /getTraces\(/, '错误页必须来自真实 Trace 查询');
assert.match(errors, /item\.status === 'error'/, '错误页只展示真实错误 Trace');
assert.match(errors, /Issue 自动聚类将在数据能力就绪后接入/, 'MVP 必须明确 Issue 聚类尚未接入');
assert.match(errors, /当前版本按错误调用链展示/, 'MVP 必须清晰说明当前错误页的数据口径');
assert.match(errors, /查看样本 Trace/, '错误页应保留原型中的样本 Trace 下钻入口');

for (const source of [endpoints, errors]) {
  assert.doesNotMatch(source, /(?:stories|fixtures?)\//i, '探索生产页面不得导入 Story/fixture');
}

console.log('APM explore workflow checks passed');
