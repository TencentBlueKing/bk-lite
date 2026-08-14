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
assert.match(events, /getAlerts\(query\)/, '告警列表必须读取 APM Alert 聚合接口');
assert.match(events, /getAlertDistribution/, '告警页应提供真实事件分布概览');
assert.match(events, /搜索标题、策略、服务或端点/, '告警页应支持原型中的快捷搜索');
assert.match(events, /Drawer/, '告警页必须提供详情抽屉');
assert.match(events, /openDrawer|setSelected/, '告警行必须可打开详情');
assert.match(events, /Timeline/, '告警详情必须提供事件时间线');
assert.match(events, /getNotificationDeliveries/, '通知投递必须作为独立记录读取');
assert.match(events, /getAlertSnapshots\(alert\.id, event\.event_id\)/, '趋势必须绑定所选 event_id 的持久化快照');
assert.doesNotMatch(events, /getServiceRed/, '告警详情不得重查当前 RED 冒充历史快照');
assert.match(events, /Service \/ Endpoint/, '告警列表必须展示服务和端点身份');
assert.match(events, /当时阈值/, '告警详情必须展示事件发生时阈值线');
assert.match(events, /事件发生点/, '告警详情必须展示事件发生点');
assert.match(events, /width=\{880\}/, '详情抽屉必须使用 880px 宽度');
for (const range of ["'1h'", "'24h'", "'7d'"]) {
  assert.ok(events.includes(range), `告警页应支持原型中的时间范围 ${range}`);
}
assert.match(policies, /新建策略/);
assert.match(policies, /编辑/);
assert.match(policies, /setPolicyEnabled/, '策略启停必须保留在列表中');
assert.doesNotMatch(policies, /测试查询|title: '监控对象'/, '策略列表不得保留测试查询或监控对象列');
assert.match(policies, /events\/policies\/new/, '新建策略必须进入独立四步页面');
assert.match(policies, /events\/policies\/\$\{item\.id\}/, '编辑策略必须进入独立编辑页面');
assert.doesNotMatch(policies, /MoreActionsDropdown/, '策略的编辑与删除必须直接可见，不应收进更多菜单');
assert.match(policies, /fixed: 'right'/, '策略操作列必须固定在表格右侧');
assert.match(legacyEvents, /\/apm\/events\/alerts/, '旧 /apm/events 必须兼容跳转到告警列表');
assert.match(legacyPolicies, /\/apm\/events\/policies/, '旧 /apm/policies 必须兼容跳转到事件策略');

console.log('APM event workflow checks passed');
