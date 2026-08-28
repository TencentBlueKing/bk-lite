import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const webRoot = join(dirname(fileURLToPath(import.meta.url)), '..');
const read = (path: string) => readFileSync(join(webRoot, path), 'utf8');

const traces = read('src/app/apm/explore/traces/page.tsx');
const endpoints = read('src/app/apm/explore/endpoints/page.tsx');
const errors = read('src/app/apm/explore/errors/page.tsx');
const traceDetail = read('src/app/apm/explore/traces/[traceId]/page.tsx');
const legacyTraces = read('src/app/apm/traces/page.tsx');

assert.match(traces, /调用链/, 'Trace 搜索页应使用产品术语“调用链”');
assert.match(traces, /TraceDistribution/, '调用链页应提供与原型一致的耗时分布视图');
assert.match(traces, /快速筛选/, '调用链页应提供真实数据驱动的快速筛选');
assert.match(traces, /matchesResultFacets/, '快速筛选必须在当前命中样本上收窄，而不是重新查询填满 limit');
assert.match(traces, /ResultMode = 'detail' \| 'aggregate'/, '调用链页必须支持明细与聚合切换');
assert.match(traces, /buildAggregate/, '聚合视图必须基于当前命中样本计算');
assert.match(traces, /traces\/s/, '调用链页必须展示命中速率');
assert.match(traces, /按 key:value 过滤/, '调用链页搜索框应对齐 Storybook 的 key:value 形态');
assert.match(traces, /value: 'spans', label: 'Spans'/, '调用链页必须开放 Spans 视角');
assert.match(traces, /getSpans\(/, 'Spans 视角必须调用受控 Span 检索 API');
assert.doesNotMatch(traces, /Spans 检索将在数据能力就绪后开放/, 'Spans 能力就绪后不得再展示禁用提示');
assert.doesNotMatch(traces, /应用 namespace/, '调用链页不得使用表单网格堆砌筛选字段');
assert.match(traces, /\/apm\/explore\/traces/, '调用链页站内导航必须使用目录化路径');
assert.match(traces, /apm.explore.traceDetail/, 'Traces 必须提供显式详情入口');
assert.doesNotMatch(traces, /onRow/, 'Span 与 Trace 列表不得整行跳转详情');
assert.match(traceDetail, /span_id/, 'Trace 详情必须支持从 URL 选中指定 Span');
assert.match(endpoints, /getServices\(\)/, '端点列表必须来自真实服务目录');
assert.match(endpoints, /getServiceRed\(/, '端点列表必须来自真实 RED 指标');
assert.match(endpoints, /top_endpoints/, '端点列表必须使用服务 RED 的端点聚合结果');
assert.match(endpoints, /'7d'/, '端点页应支持原型中的 7 天时间范围');
assert.match(endpoints, /metricFailureCount/, '端点列表必须显式记录部分 RED 查询失败');
assert.match(endpoints, /部分服务的端点指标查询失败/, '端点列表不能静默隐藏查询失败的服务');
assert.match(endpoints, /Drawer/, '端点列表必须提供详情抽屉下钻');
assert.match(endpoints, /样本调用链/, '端点详情必须提供样本 Trace');
assert.match(errors, /getIssues\(/, '错误页必须来自真实 Issue 查询');
assert.match(errors, /sample_traces/, '错误页必须展示样本调用链');
assert.doesNotMatch(errors, /Issue 自动聚类将在数据能力就绪后接入|当前版本按错误调用链展示/, '错误页不得堆叠能力规划说明');
assert.match(errors, /完整堆栈与分布/, '错误页应保留完整堆栈与分布折叠区');
assert.doesNotMatch(errors, /justify-between/, '样本调用链耗时必须紧挨名称，不得拉到行尾');
assert.match(traceDetail, /跳到首个错误/, 'Trace 详情必须支持跳到首个错误 Span');
assert.match(traceDetail, /服务耗时分解/, 'Trace 详情必须展示服务耗时分解');
assert.match(traceDetail, /跨度列表/, 'Trace 详情必须支持跨度列表视图');
assert.match(traceDetail, /火焰图/, 'Trace 详情必须支持火焰图视图');
assert.match(legacyTraces, /\/apm\/explore\/traces/, '旧 /apm/traces 必须兼容跳转到探索目录');

for (const source of [endpoints, errors, traces, traceDetail]) {
  assert.doesNotMatch(source, /(?:stories|fixtures?)\//i, '探索生产页面不得导入 Story/fixture');
}

console.log('APM explore workflow checks passed');
