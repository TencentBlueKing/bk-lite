import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const webRoot = join(dirname(fileURLToPath(import.meta.url)), '..');
const read = (path: string) => readFileSync(join(webRoot, path), 'utf8');

const catalog = read('src/app/apm/integration/add/page.tsx');
const apmApi = read('src/app/apm/api/index.ts');
const request = read('src/utils/request.ts');
const applications = read('src/app/apm/integration/applications/page.tsx');
const instances = read('src/app/apm/integration/instances/page.tsx');
const integrationStories = read('src/stories/apm-integration-pages.components.tsx');

for (const method of ['Node.js', 'Java', 'Python', '.NET', 'Go', 'OTel Collector', 'eBPF', 'Kubernetes']) {
  assert.ok(catalog.includes(method), `接入目录应包含 ${method}`);
}
assert.match(catalog, /规划中/, '尚未落地的接入方式必须明确标记为规划中');
assert.match(catalog, /当前 MVP 尚未开放此接入方式/, '不可用接入方式不能伪装为已落地能力');
assert.match(catalog, /getIngestSnippet\(/, '可用接入方式必须生成真实后端配置片段');
assert.match(catalog, /getApplications\(/, '接入配置必须选择已持久化应用');
assert.match(catalog, /getCloudRegions\(/, '接入配置必须从服务端加载受信云区域');
assert.match(catalog, /name="application_id"/, '应用 ID 必须映射到 service.namespace');
assert.match(catalog, /name="cloud_region_id"/, '接入配置必须选择云区域');
assert.match(catalog, /name="service_name"/, '接入配置必须收集 service.name');
assert.match(catalog, /name="service_version"/, '接入配置必须收集 service.version');
assert.doesNotMatch(catalog, /接入配置不会保存|APM Token/, '页面不应使用全局警示解释内部存储或鉴权实现');
assert.match(catalog, /生成临时配置/, '临时性应在生成动作附近以用户语言表达');
assert.match(catalog, /仅在本窗口保留/, '生成结果附近必须说明临时性');
assert.doesNotMatch(catalog, /Token 仅在本窗口显示一次|credential|createIngestSource/, '接入配置不得创建接入源或签发 Token');
assert.match(catalog, /suppressErrorNotification: true/, '页面内错误态存在时，目录请求必须禁止重复全局 toast');
assert.match(apmApi, /RequestConfig/, 'APM API 必须允许调用方声明页面内错误呈现策略');
assert.match(apmApi, /getIngestSnippet[\s\S]*?suppressErrorNotification: true/, '生成配置失败由表单内错误态呈现，不应重复显示全局 toast');
assert.match(request, /error\.config\?\.suppressErrorNotification/, '请求拦截器必须尊重调用方的局部错误呈现策略');
assert.match(catalog, /云区域暂不可用/, '云区域目录失败必须显示与失败来源一致的页面内标题');
assert.match(catalog, /重新加载/, '目录失败必须提供明确的恢复操作');
assert.match(catalog, /role="alert"/, '页面内目录错误必须可被辅助技术感知');
assert.match(catalog, /上报端点/, 'SDK 接入向导应先展示平台分配的上报端点');
assert.match(catalog, /接入配置/, 'SDK 接入向导应明确分组接入配置');
assert.match(catalog, /Docker 运行/, 'SDK 接入向导应支持 Docker 环境变量注入模式');
assert.match(catalog, /自动探针|Java Agent|Go SDK/, 'SDK 接入向导应提供语言对应的原生接入模式');
assert.match(catalog, /Segmented/, 'SDK 接入模式应使用可切换的分段控件');
assert.doesNotMatch(catalog, /name="endpoint"/, '平台分配的 OTLP 端点不应再要求用户手工填写');
assert.doesNotMatch(catalog, /window\.location|publicOtlpEndpoint/, '浏览器不得根据当前 hostname 拼接 APM 端点');
assert.match(catalog, /snippet\.http_endpoint/, '页面应展示服务端解析的 OTLP\/HTTP 端点');
assert.match(catalog, /snippet\.grpc_endpoint/, '页面应展示服务端解析的 OTLP\/gRPC 端点');
assert.match(catalog, /generationError/, '生成失败必须保留明确的页面内错误态');
assert.match(catalog, /复制失败/, '复制操作必须反馈失败');
assert.match(instances, /title="接入实例"/, '接入实例页应使用产品术语“接入实例”');
for (const range of ["'15m'", "'1h'", "'4h'", "'1d'", "'7d'"]) {
  assert.ok(instances.includes(range), `接入列表应支持原型中的时间范围 ${range}`);
}
assert.match(instances, /全部应用/, '接入实例应支持按应用筛选');
assert.match(instances, /全部环境/, '接入列表应支持按环境筛选');
assert.match(applications, /createApplication\(/, '应用管理必须支持创建应用');
assert.match(applications, /updateApplication\(/, '应用管理必须支持编辑应用');
assert.match(applications, /name="application_id"/, '应用管理必须维护稳定的应用 ID');
assert.match(applications, /item\.is_builtin/, '应用管理必须识别内置应用');
assert.match(applications, /内置/, '内置应用必须有文字标识，不能只依赖颜色');
assert.match(applications, /系统维护/, '内置应用必须呈现明确的只读状态');
assert.doesNotMatch(applications, /允许发现新服务|name="is_enabled"|<Switch/, '应用管理不应暴露多余的启用开关');
assert.match(catalog, /!item\.is_builtin/, '内置未归类应用不能用于生成普通接入配置');
assert.doesNotMatch(catalog, /item\.is_enabled|创建并启用/, '接入页不应依赖已移除的应用启用状态');
assert.doesNotMatch(integrationStories, /OTEL_SERVICE_NAMESPACE=default/, 'eBPF 示例不应伪造默认 namespace');

for (const source of [catalog, applications, instances]) {
  assert.doesNotMatch(source, /(?:stories|fixtures?)\//i, '接入生产页面不得导入 Story/fixture');
}

console.log('APM integration workflow checks passed');
