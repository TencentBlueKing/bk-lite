import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const webRoot = join(dirname(fileURLToPath(import.meta.url)), '..');
const read = (path: string) => readFileSync(join(webRoot, path), 'utf8');

const events = read('src/app/apm/events/page.tsx');
const policies = read('src/app/apm/policies/page.tsx');

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
for (const range of ["'1h'", "'24h'", "'7d'"]) {
  assert.ok(events.includes(range), `告警页应支持原型中的时间范围 ${range}`);
}
assert.match(policies, /新建策略/);
assert.match(policies, /编辑/);
assert.match(policies, /title: '启停'/, '策略启停必须保留在列表中');

console.log('APM event workflow checks passed');
