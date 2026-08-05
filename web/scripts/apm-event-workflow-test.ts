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
for (const range of ["'1h'", "'24h'", "'7d'"]) {
  assert.ok(events.includes(range), `告警页应支持原型中的时间范围 ${range}`);
}
assert.match(policies, /新建策略/);
assert.match(policies, /编辑/);
assert.match(policies, /title: '启停'/, '策略启停必须保留在列表中');

console.log('APM event workflow checks passed');
