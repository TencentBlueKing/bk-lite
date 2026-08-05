import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const webRoot = join(dirname(fileURLToPath(import.meta.url)), '..');
const readPage = (path: string) => readFileSync(join(webRoot, 'src/app/apm', path, 'page.tsx'), 'utf8');

const servicesPage = readPage('services');
const topologyPage = readPage('topology');
const sloPage = readPage('slo');

assert.match(servicesPage, /ServicePerspective = 'application' \| 'service'/, '服务目录必须支持应用与服务两种视角');
assert.match(servicesPage, /getServiceRed/, '应用视角指标必须来自真实 RED 查询');
assert.match(servicesPage, /getApplications/, '应用视角必须以应用目录为事实来源，不能只从已有服务反推应用');
assert.match(servicesPage, /applicationSummaries/, '服务必须按 namespace 聚合为应用卡片');
assert.match(servicesPage, /已归档/, '服务工具栏必须保留已归档入口');
assert.match(servicesPage, /metricFailureKeys/, '服务目录必须单独记录 RED 查询失败，不能把故障伪装成无数据');
assert.match(servicesPage, /RED 指标查询失败/, '服务目录必须明确提示 RED 指标降级');
assert.match(servicesPage, /setMetricRefreshKey/, 'RED 指标降级状态必须提供可操作的重试入口');

assert.match(topologyPage, /title="服务拓扑"/, '服务拓扑页面标题缺失');
assert.match(topologyPage, /options=\{\['15m', '1h', '4h', '1d', '7d'\]\}/, '拓扑必须提供时间窗切换');
assert.match(topologyPage, /只看异常/, '拓扑必须支持异常筛选');
assert.match(topologyPage, /getTopology/, '拓扑必须来自服务端的真实 Trace 聚合');
assert.match(topologyPage, /overflow-x-auto/, '窄屏下拓扑画布必须在页面内可滚动，不能静默裁切节点');
assert.match(topologyPage, /tabIndex=\{0\}/, '拓扑滚动区域必须支持键盘聚焦');
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
assert.doesNotMatch(sloPage, /本地预览|设计预览/, '服务端已支持的 SLO 不得再标成静态预览');

for (const page of [servicesPage, topologyPage, sloPage]) {
  assert.doesNotMatch(page, /src\/stories|@\/stories/, '生产页面不得依赖 Storybook 实现');
}

console.log('APM service workflow checks passed');
