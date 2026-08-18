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
const zhLocale = JSON.parse(read('src/app/apm/locales/zh.json'));
const enLocale = JSON.parse(read('src/app/apm/locales/en.json'));

assert.match(events, /活跃告警/);
assert.match(events, /历史告警/);
assert.match(events, /getAlerts\(query\)/, '告警列表必须读取 APM Alert 聚合接口');
assert.match(events, /getAlertDistribution/, '告警页应提供真实事件分布概览');
assert.match(events, /搜索告警标题 \/ 服务 \/ 规则/, '告警页应支持原型中的快捷搜索');
assert.match(events, /Drawer/, '告警页必须提供详情抽屉');
assert.match(events, /openDrawer|setSelected/, '告警行必须可打开详情');
assert.match(events, /Timeline/, '告警详情必须提供事件时间线');
assert.match(events, /getNotificationDeliveries/, '通知投递必须作为独立记录读取');
assert.match(events, /getAlertSnapshots\(alert\.id, event\.event_id\)/, '趋势必须绑定所选 event_id 的持久化快照');
assert.doesNotMatch(events, /getServiceRed/, '告警详情不得重查当前 RED 冒充历史快照');
assert.match(events, /服务 \/ 端点/, '告警列表必须展示服务和端点身份');
assert.match(events, /当时阈值/, '告警详情必须展示事件发生时阈值线');
assert.match(events, /事件发生点/, '告警详情必须展示事件发生点');
assert.match(events, /width=\{880\}/, '详情抽屉必须使用 880px 宽度');
assert.match(events, /TimeSelector/, '历史告警应复用 Monitor/Log 的时间范围下拉框');
assert.match(events, /onlyTimeSelect/, '历史告警的时间控件不应重复展示刷新周期');
assert.match(events, /selectValue: 10080/, '历史告警默认查询最近 7 天');
assert.doesNotMatch(events, /refreshInterval|自动刷新/, '告警页不应暴露独立的自动刷新周期配置');
assert.match(policies, /新建策略/);
assert.match(policies, /编辑/);
assert.match(policies, /setPolicyEnabled/, '策略启停必须保留在列表中');
assert.doesNotMatch(policies, /测试查询|title: '监控对象'/, '策略列表不得保留测试查询或监控对象列');
assert.match(policies, /events\/policies\/new/, '新建策略必须进入独立四步页面');
assert.match(policies, /events\/policies\/\$\{item\.id\}/, '编辑策略必须进入独立编辑页面');
assert.doesNotMatch(policies, /MoreActionsDropdown/, '策略的编辑与删除必须直接可见，不应收进更多菜单');
assert.match(policies, /fixed: 'right'/, '策略操作列必须固定在表格右侧');
for (const key of ['scope', 'condition', 'status']) {
  assert.ok(zhLocale.apm.policies[key], `APM 策略中文 locale 缺少 ${key}`);
  assert.ok(enLocale.apm.policies[key], `APM 策略英文 locale 缺少 ${key}`);
}
assert.match(policies, /apm\.common\.operation/, '策略列表必须复用 APM 公共操作文案');
assert.match(legacyEvents, /\/apm\/events\/alerts/, '旧 /apm/events 必须兼容跳转到告警列表');
assert.match(legacyPolicies, /\/apm\/events\/policies/, '旧 /apm/policies 必须兼容跳转到事件策略');

console.log('APM event workflow checks passed');
