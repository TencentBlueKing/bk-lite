import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';


// 仅验证 decision-only API 与生产组件接线；scope/race/reset 行为由 wiki-decision-center-test.ts 执行。
const root = process.cwd();
const checkTab = fs.readFileSync(path.join(root, 'src/app/opspilot/components/wiki/CheckTab.tsx'), 'utf8');
const wikiApi = fs.readFileSync(path.join(root, 'src/app/opspilot/api/wiki.ts'), 'utf8');

assert.match(checkTab, /fetchDecisionItems/);
assert.match(checkTab, /buildDecisionLoadPlan/);
assert.match(checkTab, /Promise\.all/);
assert.match(checkTab, /filterDecisionItems/);
assert.match(checkTab, /items:\s*filterDecisionItems\(primary\.items\)/);
assert.match(wikiApi, /fetchCheckItems\(kbId,\s*\{[\s\S]*decision_only:\s*true,[\s\S]*view/);
assert.doesNotMatch(checkTab, /<Select|checkTypeFilter|statusFilter|statusOptions|checkTypeOptions/);
assert.doesNotMatch(checkTab, /CustomTable|Drawer|handleScan|scanConfirm/);
assert.doesNotMatch(checkTab, /acceptCheck|rejectCheck|batchAcceptChecks|batchRejectChecks/);

console.log('wiki decision-only pending/processed filter validation passed');
