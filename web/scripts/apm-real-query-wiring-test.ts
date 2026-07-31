import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const webRoot = join(dirname(fileURLToPath(import.meta.url)), '..');
const read = (path: string) => readFileSync(join(webRoot, path), 'utf8');

const api = read('src/app/apm/api/index.ts');
const serviceDetail = read('src/app/apm/services/[serviceId]/page.tsx');
const traceSearch = read('src/app/apm/traces/page.tsx');
const traceDetail = read('src/app/apm/traces/[traceId]/page.tsx');

assert.match(api, /\/apm\/services\/\$\{serviceId\}\/metrics\//, '服务详情必须调用真实 RED API');
assert.match(api, /\/apm\/traces\//, 'Trace 页面必须调用真实 Trace API');
assert.match(serviceDetail, /timeseries/, '服务详情必须读取真实 RED 时序');
assert.match(serviceDetail, /TimeSeriesComposedChart/, '服务详情必须呈现真实 RED 时序图');
assert.match(serviceDetail, /top_endpoints/, '服务详情必须呈现真实 Top endpoint');
assert.match(serviceDetail, /started_at:[\s\S]*ended_at:/, '服务到 Trace 跳转必须保留同一时间窗');
assert.match(traceSearch, /getTraces\(buildQuery\(cursor\)\)/, 'Trace 搜索必须使用受控筛选与游标');
assert.match(traceSearch, /page\.next_cursor/, '空授权页仍必须保留后续游标');
assert.match(traceDetail, /getTrace\(params\.traceId\)/, '瀑布详情必须读取真实 Trace API');

for (const source of [serviceDetail, traceSearch, traceDetail]) {
  assert.doesNotMatch(source, /(?:stories|fixtures?)\//i, 'APM 生产查询页面不得导入 Story/fixture');
}

console.log('APM real query wiring checks passed');
