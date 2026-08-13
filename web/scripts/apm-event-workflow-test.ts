import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const webRoot = join(dirname(fileURLToPath(import.meta.url)), '..');
const read = (path: string) => readFileSync(join(webRoot, path), 'utf8');

const events = read('src/app/apm/events/alerts/page.tsx');
const policies = read('src/app/apm/events/policies/page.tsx');
const legacyEvents = read('src/app/apm/events/page.tsx');
const legacyPolicies = read('src/app/apm/policies/page.tsx');

assert.match(events, /活跃告警/);
assert.match(events, /历史告警/);
assert.match(events, /event\.status === 'firing'/, '活跃告警必须来自 APM firing 状态');
assert.match(events, /event\.status === 'recovered'/, '历史告警必须来自 APM recovered 状态');
assert.match(events, /告警分布/, '告警页应提供与原型一致的时间分布概览');
assert.match(events, /搜索告警标题 \/ 服务 \/ 规则/, '告警页应支持原型中的快捷搜索');
assert.match(events, /Drawer/, '告警页必须提供详情抽屉');
assert.match(events, /openDrawer|setSelected/, '告警行必须可打开详情');
assert.match(events, /Timeline/, '告警详情必须提供事件时间线');
assert.match(events, /retryNotificationDelivery/, '告警详情必须保留投递失败重投');
assert.match(events, /searchParams\.get\('service'\)/, '告警页必须接受服务深链筛选');
assert.match(events, /environmentFilter/, '告警页必须支持环境筛选以便服务目录下钻');
assert.match(events, /title: '服务'/, '告警列表必须展示服务');
assert.match(events, /title: '端点'/, '告警列表必须展示端点');
assert.doesNotMatch(events, /title: '状态'|title: '值'/, '告警列表不得重复展示状态和值');
assert.match(events, /告警趋势/, '告警详情必须提供指标趋势视图');
for (const range of ["'1h'", "'24h'", "'7d'"]) {
  assert.ok(events.includes(range), `告警页应支持原型中的时间范围 ${range}`);
}
assert.match(policies, /新建策略/);
assert.match(policies, /编辑/);
assert.match(policies, /title: '启用状态'/, '策略启停必须保留在列表中');
assert.doesNotMatch(policies, /测试查询|title: '监控对象'/, '策略列表不得保留测试查询或监控对象列');
assert.match(policies, /openCreate/, '新建策略必须打开创建表单');
assert.doesNotMatch(policies, /events\/policies\/new/, '新建策略不得再跳转旧的独立页面');
assert.match(policies, /FilterToolbar/, '策略列表工具栏必须复用统一筛选布局');
assert.match(policies, /MoreActionsDropdown/, '策略行操作必须收敛到统一更多操作菜单');
assert.match(legacyEvents, /\/apm\/events\/alerts/, '旧 /apm/events 必须兼容跳转到告警列表');
assert.match(legacyPolicies, /\/apm\/events\/policies/, '旧 /apm/policies 必须兼容跳转到事件策略');

console.log('APM event workflow checks passed');
