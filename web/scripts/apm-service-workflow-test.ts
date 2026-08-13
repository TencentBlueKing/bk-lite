import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const webRoot = join(dirname(fileURLToPath(import.meta.url)), '..');
const readPage = (path: string) => readFileSync(join(webRoot, 'src/app/apm', path, 'page.tsx'), 'utf8');

const servicesPage = readPage('services');
const topologyPage = readPage('services/topology');
const sloPage = readPage('services/slo');

assert.match(servicesPage, /ServicePerspective = 'application' \| 'service'/, '服务目录必须支持应用与服务两种视角');
assert.match(servicesPage, /getServiceRed/, '应用视角指标必须来自真实 RED 查询');
assert.match(servicesPage, /getApplications/, '应用视角必须以应用目录为事实来源，不能只从已有服务反推应用');
assert.match(servicesPage, /applicationSummaries/, '服务必须按 namespace 聚合为应用卡片');
assert.match(servicesPage, /已归档/, '服务工具栏必须保留已归档入口');
assert.match(servicesPage, /已归档服务/, '已归档入口必须打开归档抽屉而不是仅切换列表筛选');
assert.match(servicesPage, /Drawer/, '已归档服务必须使用 Drawer 承载');
assert.match(servicesPage, /title: '吞吐量\(\/s\)'/, '服务表必须展示吞吐 RED 列');
assert.match(servicesPage, /title: '错误率'/, '服务表必须展示错误率 RED 列');
assert.match(servicesPage, /title: 'P99'/, '服务表必须展示 P99 RED 列');
assert.match(servicesPage, /MiniTrend/, '服务表必须展示趋势列');
assert.match(servicesPage, /getEvents\(\{ limit: 100 \}\)/, '服务目录事件查询 limit 不得超过后端上限 100');
assert.match(servicesPage, /getSlos/, '服务目录 SLO 列必须来自真实 SLO 查询');
assert.match(servicesPage, /metricFailureKeys/, '服务目录必须单独记录 RED 查询失败，不能把故障伪装成无数据');
assert.match(servicesPage, /RED 指标查询失败/, '服务目录必须明确提示 RED 指标降级');
assert.match(servicesPage, /setMetricRefreshKey/, 'RED 指标降级状态必须提供可操作的重试入口');
assert.match(servicesPage, /ServiceLanguage/, '服务名称前必须展示遥测 SDK 语言标识');
assert.match(servicesPage, /title: '状态'/, '服务表必须单独展示最高活跃告警状态');
assert.match(servicesPage, /最高活跃告警/, '状态必须以最高活跃告警级别解释，不能继续使用健康度口径');
assert.match(servicesPage, /MetricValue/, 'RED 空态必须区分无数据与查询失败');
assert.match(servicesPage, /router\.replace/, '服务目录筛选与视角必须写入 URL 以便深链');
assert.match(servicesPage, /\/apm\/events\/alerts\?service=/, '活跃告警必须下钻到告警页并携带服务筛选');

const serviceDetail = readFileSync(join(webRoot, 'src/app/apm/services/[serviceId]/page.tsx'), 'utf8');
assert.match(serviceDetail, /activeKey=\{activeTab\}/, '服务详情 Tabs 必须真正切换内容而不是仅跳转');
assert.match(serviceDetail, /key: 'traces'/, '服务详情必须内嵌调用链 Tab');
assert.match(serviceDetail, /key: 'errors'/, '服务详情必须内嵌错误 Tab');
assert.match(serviceDetail, /getTraces/, '服务详情调用链 Tab 必须读取真实 Trace');
assert.match(serviceDetail, /getTopology/, '服务详情依赖关系必须读取真实拓扑');
assert.match(serviceDetail, /跳到首个错误|依赖关系/, '服务详情概览必须提供依赖或错误下钻能力');
assert.doesNotMatch(serviceDetail, /color:\s*'var\(--/, 'Canvas 图表不得直接使用 CSS 变量颜色');

assert.match(topologyPage, /title="服务拓扑"/, '服务拓扑页面标题缺失');
assert.match(topologyPage, /options=\{\['15m', '1h', '4h', '1d', '7d'\]\}/, '拓扑必须提供时间窗切换');
assert.match(topologyPage, /只看异常/, '拓扑必须支持异常筛选');
assert.match(topologyPage, /getTopology/, '拓扑必须来自服务端的真实 Trace 聚合');
assert.match(topologyPage, /type ViewMode = 'graph' \| 'list'/, '拓扑必须提供图形与依赖列表双视图');
assert.match(topologyPage, /screens\.md === false[\s\S]*setViewMode\('list'\)/, '窄屏必须默认使用依赖列表，避免图形撑宽页面');
assert.match(topologyPage, /viewBox="0 0 1030 520"/, '图形视图必须使用响应式 viewBox');
assert.doesNotMatch(topologyPage, /min-w-\[960px\]|scroll=\{\{ x:/, '拓扑不得通过固定宽度撑开整页');
assert.match(topologyPage, /columns=\{dependencyColumns\}/, '图形必须提供可访问的依赖表格替代视图');
assert.match(topologyPage, /tabIndex=\{onNodeClick \? 0 : undefined\}/, '可点击拓扑节点必须支持键盘聚焦');
assert.match(topologyPage, /event\.key === 'Enter' \|\| event\.key === ' '/, '拓扑节点必须支持 Enter 与 Space 下钻');
assert.match(topologyPage, /sampled_spans/, '拓扑节点大小必须编码采样吞吐');
assert.match(topologyPage, /onNodeClick/, '拓扑节点必须可下钻到服务详情');
assert.doesNotMatch(topologyPage, /设计预览|Storybook 示例数据/, '已有后端契约时不得继续展示示例拓扑');

assert.match(sloPage, /title=\{editingId \? '编辑 SLO' : '新建 SLO'\}/, 'SLO 必须支持新建和编辑');
assert.match(sloPage, /onFinish=\{submit\}/, 'SLO 保存必须通过 Ant Design Form 校验后提交');
assert.match(sloPage, /Popconfirm/, 'SLO 删除必须二次确认');
assert.match(sloPage, /错误预算剩余/, 'SLO 列表必须展示错误预算');
assert.match(sloPage, /getSlos/, 'SLO 列表必须来自服务端');
assert.match(sloPage, /createSlo/, 'SLO 新建必须写入服务端');
assert.match(sloPage, /updateSlo/, 'SLO 编辑必须写入服务端');
assert.match(sloPage, /setSloEnabled/, 'SLO 启停必须写入服务端');
assert.match(sloPage, /deleteSlo/, 'SLO 删除必须写入服务端');
assert.doesNotMatch(sloPage, /name="is_enabled"/, 'SLO 启用状态不得出现在新建或编辑表单');
assert.doesNotMatch(sloPage, /本地预览|设计预览/, '服务端已支持的 SLO 不得再标成静态预览');

for (const page of [servicesPage, serviceDetail, topologyPage, sloPage]) {
  assert.doesNotMatch(page, /src\/stories|@\/stories/, '生产页面不得依赖 Storybook 实现');
}

console.log('APM service workflow checks passed');
