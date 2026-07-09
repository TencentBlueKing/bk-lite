import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const buildRecordTab = fs.readFileSync(path.join(root, 'src/app/opspilot/components/wiki/BuildRecordTab.tsx'), 'utf8');
const zh = JSON.parse(fs.readFileSync(path.join(root, 'src/app/opspilot/locales/zh.json'), 'utf8'));
const en = JSON.parse(fs.readFileSync(path.join(root, 'src/app/opspilot/locales/en.json'), 'utf8'));

assert.match(buildRecordTab, /statusFilter/);
assert.match(buildRecordTab, /status: statusFilter \|\| undefined/);
assert.match(buildRecordTab, /t\('wiki\.filterStatus'\)/);
assert.match(buildRecordTab, /t\('wiki\.buildRecordStatusAll'\)/);

for (const removedFilter of ['triggerFilter', 'maintenanceStatusFilter', 'maintenanceStageFilter', 'maintenanceStageStatusFilter']) {
  assert.doesNotMatch(buildRecordTab, new RegExp(removedFilter), `BuildRecordTab should not render ${removedFilter}`);
}

for (const removedParam of ['trigger:', 'maintenance_status:', 'maintenance_stage:', 'maintenance_stage_status:']) {
  assert.doesNotMatch(buildRecordTab, new RegExp(removedParam), `BuildRecordTab should not query by ${removedParam}`);
}

assert.ok(zh.wiki.buildRecordStatusAll, 'missing zh wiki.buildRecordStatusAll');
assert.ok(en.wiki.buildRecordStatusAll, 'missing en wiki.buildRecordStatusAll');

console.log('wiki build record filter validation passed');
