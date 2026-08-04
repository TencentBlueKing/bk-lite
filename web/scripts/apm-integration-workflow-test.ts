import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const webRoot = join(dirname(fileURLToPath(import.meta.url)), '..');
const read = (path: string) => readFileSync(join(webRoot, path), 'utf8');

const catalog = read('src/app/apm/integration/add/page.tsx');
const instances = read('src/app/apm/integration/instances/page.tsx');

for (const method of ['Node.js', 'Java', 'Python', '.NET', 'Go', 'OTel Collector', 'eBPF', 'Kubernetes']) {
  assert.ok(catalog.includes(method), `接入目录应包含 ${method}`);
}
assert.match(catalog, /规划中/, '尚未落地的接入方式必须明确标记为规划中');
assert.match(catalog, /当前 MVP 尚未开放此接入方式/, '不可用接入方式不能伪装为已落地能力');
assert.match(catalog, /createIngestSource\(/, '可用接入方式必须接入真实受控接入源流程');
assert.match(catalog, /getIngestSnippet\(/, '可用接入方式必须生成真实后端配置片段');
assert.match(instances, /title="接入列表"/, '接入实例页应使用产品术语“接入列表”');
for (const range of ["'15m'", "'1h'", "'4h'", "'1d'", "'7d'"]) {
  assert.ok(instances.includes(range), `接入列表应支持原型中的时间范围 ${range}`);
}
assert.match(instances, /全部接入方式/, '接入列表应支持按接入源筛选');
assert.match(instances, /全部环境/, '接入列表应支持按环境筛选');

for (const source of [catalog, instances]) {
  assert.doesNotMatch(source, /(?:stories|fixtures?)\//i, '接入生产页面不得导入 Story/fixture');
}

console.log('APM integration workflow checks passed');
