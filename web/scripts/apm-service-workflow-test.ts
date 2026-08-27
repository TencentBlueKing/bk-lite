import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const webRoot = join(dirname(fileURLToPath(import.meta.url)), '..');
const readPage = (path: string) => readFileSync(join(webRoot, 'src/app/apm', path, 'page.tsx'), 'utf8');

const servicesPage = readPage('services');
const topologyPage = readPage('services/topology');
const topologyCanvas = readFileSync(join(webRoot, 'src/app/apm/services/topology/topology-canvas.tsx'), 'utf8');
const topologyInspectPanel = readFileSync(join(webRoot, 'src/app/apm/services/topology/topology-inspect-panel.tsx'), 'utf8');
const serviceLanguageIcon = readFileSync(join(webRoot, 'src/app/apm/components/service-language-icon.tsx'), 'utf8');
const topologyObjectIcon = readFileSync(join(webRoot, 'src/app/apm/components/topology-object-icon.ts'), 'utf8');
const serviceCatalogTable = readFileSync(join(webRoot, 'src/app/apm/components/service-catalog-table.tsx'), 'utf8');
const applicationObservability = readFileSync(join(webRoot, 'src/app/apm/components/application-observability.tsx'), 'utf8');
const sloPage = readPage('services/slo');

assert.match(servicesPage, /ServicePerspective = 'application' \| 'service'/, '服务目录必须支持应用与服务两种视角');
assert.match(servicesPage, /getServiceRed/, '应用视角指标必须来自真实 RED 查询');
assert.match(servicesPage, /getApplications/, '应用视角必须以应用目录为事实来源，不能只从已有服务反推应用');
assert.match(servicesPage, /applicationSummaries/, '服务必须按 namespace 聚合为应用卡片');
assert.match(servicesPage, /perspective === 'service'[\s\S]*已归档/, '已归档入口只挂在服务视角，不出现在应用卡片页');
assert.match(servicesPage, /已归档服务/, '已归档入口必须打开归档抽屉而不是仅切换列表筛选');
assert.match(servicesPage, /Drawer/, '已归档服务必须使用 Drawer 承载');
assert.match(servicesPage, /\/apm\/services\/applications\//, '应用卡详情必须留在服务菜单，不得跳到集成');
assert.match(serviceCatalogTable, /吞吐量\(\/s\)/, '服务表必须展示吞吐 RED 列');
assert.match(serviceCatalogTable, /错误率/, '服务表必须展示错误率 RED 列');
assert.match(serviceCatalogTable, /P99/, '服务表必须展示 P99 RED 列');
assert.match(serviceCatalogTable, /MiniTrend/, '服务表必须展示趋势列');
assert.match(servicesPage, /getEvents\(\{ limit: 100 \}\)/, '服务目录事件查询 limit 不得超过后端上限 100');
assert.match(servicesPage, /getSlos/, '服务目录 SLO 列必须来自真实 SLO 查询');
assert.match(servicesPage, /metricFailureKeys/, '服务目录必须单独记录 RED 查询失败，不能把故障伪装成无数据');
assert.match(servicesPage, /RED 指标查询失败/, '服务目录必须明确提示 RED 指标降级');
assert.match(servicesPage, /setMetricRefreshKey/, 'RED 指标降级状态必须提供可操作的重试入口');
assert.match(serviceCatalogTable, /ServiceLanguage/, '服务名称前必须展示遥测 SDK 语言标识');
assert.match(serviceCatalogTable, /apm\.common\.status/, '服务表必须单独展示最高活跃告警状态');
assert.match(serviceCatalogTable, /最高活跃告警/, '状态必须以最高活跃告警级别解释，不能继续使用健康度口径');
assert.match(serviceCatalogTable, /MetricValue/, 'RED 空态必须区分无数据与查询失败');
assert.match(servicesPage, /router\.replace/, '服务目录筛选与视角必须写入 URL 以便深链');
assert.match(servicesPage, /\/apm\/events\/alerts\?service=/, '活跃告警必须下钻到告警页并携带服务筛选');

const serviceDetail = readFileSync(join(webRoot, 'src/app/apm/services/[serviceId]/page.tsx'), 'utf8');
assert.match(serviceDetail, /activeKey=\{activeTab\}/, '服务详情 Tabs 必须真正切换内容而不是仅跳转');
assert.match(serviceDetail, /key: 'traces'/, '服务详情必须内嵌调用链 Tab');
assert.match(serviceDetail, /key: 'errors'/, '服务详情必须内嵌错误 Tab');
assert.match(serviceDetail, /getTraces/, '服务详情调用链 Tab 必须读取真实 Trace');
assert.match(serviceDetail, /getTopology/, '服务详情依赖关系必须读取真实拓扑');
assert.match(serviceDetail, /getDeployments/, '服务详情部署 Tab 必须读取物化部署事件');
assert.doesNotMatch(serviceDetail, /部署事件将在发布埋点接入后展示/, '部署 Tab 不得继续使用埋点占位文案');
assert.match(serviceDetail, /跳到首个错误|依赖关系/, '服务详情概览必须提供依赖或错误下钻能力');
assert.doesNotMatch(serviceDetail, /color:\s*'var\(--/, 'Canvas 图表不得直接使用 CSS 变量颜色');

assert.match(topologyPage, /服务拓扑/, '服务拓扑页面标题缺失');
assert.match(topologyPage, /options=\{\['15m', '1h', '4h', '1d', '7d'\]\}/, '拓扑必须提供时间窗切换');
assert.match(topologyPage, /只看异常/, '拓扑必须支持异常筛选');
assert.match(topologyPage, /getTopology/, '拓扑必须来自服务端的真实 Trace 聚合');
assert.match(topologyPage, /TopologyLayoutMode/, '拓扑必须提供层次与力导向布局');
assert.match(topologyPage, /t\('apm.topology.layered', '层次'\)/, '拓扑布局切换必须包含层次');
assert.match(topologyPage, /t\('apm.topology.force', '力导向'\)/, '拓扑布局切换必须包含力导向');
assert.doesNotMatch(topologyPage, /type ViewMode = 'graph' \| 'list'/, '拓扑不得再按图形/列表切换');
assert.match(topologyCanvas, /viewBox=\{`0 0 \$\{TOPOLOGY_CANVAS_SIZE\.width\} \$\{TOPOLOGY_CANVAS_SIZE\.height\}`\}/, '图形视图必须使用响应式 viewBox');
assert.match(topologyCanvas, /tabIndex=\{onSelect \|\| onNodeClick \? 0 : undefined\}/, '可点击拓扑节点必须支持键盘聚焦');
assert.match(topologyCanvas, /event\.key === 'Enter' \|\| event\.key === ' '/, '拓扑节点必须支持 Enter 与 Space 下钻');
assert.match(topologyCanvas, /sampled_spans/, '拓扑节点大小必须编码采样吞吐');
assert.match(topologyCanvas, /TopologyServiceIcon/, '拓扑节点必须按语言或推断系统选择图标');
assert.match(topologyCanvas, /truncateTopologyNodeLabel/, '拓扑节点长名称必须截断，避免和角标挤变形');
assert.match(topologyObjectIcon, /cc-redis_REDIS/, '推断 redis 必须使用对象库 Redis 图标');
assert.match(topologyObjectIcon, /cc-postgresql_PostgreSQL/, '推断 postgresql 必须使用对象库 PostgreSQL 图标');
assert.match(topologyObjectIcon, /gateway\|kong\|apisix/, '名称含 gateway 的推断节点必须识别为网关图标');
assert.match(serviceLanguageIcon, /data-service-icon=\{kind\}/, '未知语言必须可被识别为默认服务图标');
assert.match(serviceLanguageIcon, /UnknownIcon[\s\S]*'default'/, '未知语言必须回退到默认服务图标');
assert.doesNotMatch(serviceLanguageIcon, /ui-monospace/, '未知语言不得用空代码符号占位');
assert.match(topologyCanvas, /formatTopologyEdgeMetrics/, '连线必须展示观测调用量');
assert.match(topologyCanvas, /onWheel/, '拓扑必须支持滚轮缩放');
assert.match(topologyPage, /onSelect/, '拓扑节点必须可点选并停在图上调查');
assert.match(topologyPage, /TopologyInspectPanel/, '拓扑必须提供右侧调查栏');
assert.match(topologyPage, /getTraces/, '调查栏样本 Trace 必须来自真实调用链查询');
assert.match(topologyPage, /isolateTopologyNeighborhood/, '拓扑必须支持一跳隔离');
assert.match(topologyPage, /totalCalls/, '拓扑摘要必须展示总调用数而不是观测 Trace');
assert.match(topologyPage, /include_inferred: true/, '服务拓扑必须请求推断下游');
assert.match(topologyPage, /errorRequestsOnly/, '拓扑必须提供仅错误请求切片，且与只看异常分开');
assert.match(topologyPage, /anomalyOnly/, '拓扑必须保留按节点健康度的只看异常');
assert.match(topologyPage, /clearSlice/, '拓扑必须能清空请求切片并回到时间窗全图');
assert.match(topologyCanvas, /inferredBadge/, '推断节点必须展示推断角标');
assert.match(topologyCanvas, /data-node-kind/, '推断节点必须可被画布按 kind 识别');
assert.match(topologyInspectPanel, /peerAddress/, '推断节点调查栏必须展示 Client Span 中的地址');
assert.match(topologyInspectPanel, /dbName/, '推断节点调查栏必须单独展示库名而不是用库名冒充 host');
assert.doesNotMatch(applicationObservability, /include_inferred:\s*true/, '应用详情子拓扑第一版不得请求推断下游');
assert.doesNotMatch(serviceDetail, /include_inferred:\s*true/, '服务详情不得打开推断查询');
assert.doesNotMatch(topologyPage, /min-w-\[960px\]|scroll=\{\{ x:/, '拓扑不得通过固定宽度撑开整页');
assert.doesNotMatch(topologyPage, /设计预览|Storybook 示例数据/, '已有后端契约时不得继续展示示例拓扑');
assert.match(applicationObservability, /关键信息/, '应用详情必须使用关键信息而不是应用 KPI');
assert.match(applicationObservability, /focusNamespace/, '应用拓扑必须区分本应用与上下游');
assert.match(applicationObservability, /ServiceCatalogTable/, '应用内服务列表必须复用服务目录表格');

assert.match(sloPage, /编辑 SLO/, 'SLO 必须支持新建和编辑');
assert.match(sloPage, /onFinish=\{submit\}/, 'SLO 保存必须通过 Ant Design Form 校验后提交');
assert.match(sloPage, /Popconfirm/, 'SLO 删除必须二次确认');
assert.match(sloPage, /错误预算/, 'SLO 列表必须展示错误预算');
assert.match(sloPage, /getSlos/, 'SLO 列表必须来自服务端');
assert.match(sloPage, /createSlo/, 'SLO 新建必须写入服务端');
assert.match(sloPage, /updateSlo/, 'SLO 编辑必须写入服务端');
assert.match(sloPage, /setSloEnabled/, 'SLO 启停必须写入服务端');
assert.match(sloPage, /deleteSlo/, 'SLO 删除必须写入服务端');
assert.doesNotMatch(sloPage, /name="is_enabled"/, 'SLO 启用状态不得出现在新建或编辑表单');
assert.doesNotMatch(sloPage, /本地预览|设计预览/, '服务端已支持的 SLO 不得再标成静态预览');

const deploymentsPage = readPage('services/deployments');
assert.match(deploymentsPage, /\bredirect\(/, '独立部署列表暂不展示，旧路由必须重定向');
assert.doesNotMatch(deploymentsPage, /ApmDataTable|getDeployments/, '独立部署列表页不得继续渲染事件表');

for (const page of [servicesPage, serviceDetail, topologyPage, topologyCanvas, serviceCatalogTable, applicationObservability, sloPage]) {
  assert.doesNotMatch(page, /src\/stories|@\/stories/, '生产页面不得依赖 Storybook 实现');
}

console.log('APM service workflow checks passed');
