import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const buildRecordTab = fs.readFileSync(path.join(root, 'src/app/opspilot/components/wiki/BuildRecordTab.tsx'), 'utf8');
const zh = JSON.parse(fs.readFileSync(path.join(root, 'src/app/opspilot/locales/zh.json'), 'utf8'));
const en = JSON.parse(fs.readFileSync(path.join(root, 'src/app/opspilot/locales/en.json'), 'utf8'));

assert.match(buildRecordTab, /statusFilter/);
assert.match(buildRecordTab, /triggerFilter/);
assert.match(buildRecordTab, /maintenanceStatusFilter/);
assert.match(buildRecordTab, /maintenanceStageFilter/);
assert.match(buildRecordTab, /maintenanceStageStatusFilter/);

for (const param of ['status', 'trigger', 'maintenance_status', 'maintenance_stage', 'maintenance_stage_status']) {
  assert.match(buildRecordTab, new RegExp(`${param}:`), `missing build record query param ${param}`);
}

for (const key of [
  'buildRecordStatusAll',
  'buildRecordTriggerAll',
  'maintenanceStatusAll',
  'maintenanceStageAll',
  'maintenanceStageStatusAll',
]) {
  assert.ok(zh.wiki[key], `missing zh wiki.${key}`);
  assert.ok(en.wiki[key], `missing en wiki.${key}`);
}

console.log('wiki build record filter validation passed');
