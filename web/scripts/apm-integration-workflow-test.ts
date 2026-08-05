import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const webRoot = join(dirname(fileURLToPath(import.meta.url)), '..');
const read = (path: string) => readFileSync(join(webRoot, path), 'utf8');

const catalog = read('src/app/apm/integration/add/page.tsx');
const applications = read('src/app/apm/integration/applications/page.tsx');
const instances = read('src/app/apm/integration/instances/page.tsx');

for (const method of ['Node.js', 'Java', 'Python', '.NET', 'Go', 'OTel Collector', 'eBPF', 'Kubernetes']) {
  assert.ok(catalog.includes(method), `接入目录应包含 ${method}`);
}
assert.match(catalog, /规划中/, '尚未落地的接入方式必须明确标记为规划中');
assert.match(catalog, /当前 MVP 尚未开放此接入方式/, '不可用接入方式不能伪装为已落地能力');
assert.match(catalog, /getIngestSnippet\(/, '可用接入方式必须生成真实后端配置片段');
assert.match(catalog, /getApplications\(/, '接入配置必须选择已持久化应用');
assert.match(catalog, /name="application_id"/, '应用 ID 必须映射到 service.namespace');
assert.match(catalog, /name="service_name"/, '接入配置必须收集 service.name');
assert.match(catalog, /name="service_version"/, '接入配置必须收集 service.version');
assert.match(catalog, /接入配置不会保存/, '接入页面必须说明配置是临时结果');
assert.doesNotMatch(catalog, /Token 仅在本窗口显示一次|credential|createIngestSource/, '接入配置不得创建接入源或签发 Token');
assert.match(catalog, /上报端点/, 'SDK 接入向导应先展示平台分配的上报端点');
assert.match(catalog, /接入配置/, 'SDK 接入向导应明确分组接入配置');
assert.match(catalog, /Docker 运行/, 'SDK 接入向导应支持 Docker 环境变量注入模式');
assert.match(catalog, /自动探针|Java Agent|Go SDK/, 'SDK 接入向导应提供语言对应的原生接入模式');
assert.match(catalog, /Segmented/, 'SDK 接入模式应使用可切换的分段控件');
assert.doesNotMatch(catalog, /name="endpoint"/, '平台分配的 OTLP 端点不应再要求用户手工填写');
assert.match(instances, /title="接入实例"/, '接入实例页应使用产品术语“接入实例”');
for (const range of ["'15m'", "'1h'", "'4h'", "'1d'", "'7d'"]) {
  assert.ok(instances.includes(range), `接入列表应支持原型中的时间范围 ${range}`);
}
assert.match(instances, /全部应用/, '接入实例应支持按应用筛选');
assert.match(instances, /全部环境/, '接入列表应支持按环境筛选');
assert.match(applications, /createApplication\(/, '应用管理必须支持创建应用');
assert.match(applications, /updateApplication\(/, '应用管理必须支持编辑应用');
assert.match(applications, /name="application_id"/, '应用管理必须维护稳定的应用 ID');

for (const source of [catalog, applications, instances]) {
  assert.doesNotMatch(source, /(?:stories|fixtures?)\//i, '接入生产页面不得导入 Story/fixture');
}

console.log('APM integration workflow checks passed');
