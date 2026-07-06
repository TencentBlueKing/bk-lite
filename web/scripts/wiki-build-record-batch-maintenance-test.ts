import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const buildRecordTab = fs.readFileSync(path.join(root, 'src/app/opspilot/components/wiki/BuildRecordTab.tsx'), 'utf8');
const wikiApi = fs.readFileSync(path.join(root, 'src/app/opspilot/api/wiki.ts'), 'utf8');
const wikiTypes = fs.readFileSync(path.join(root, 'src/app/opspilot/types/wiki.ts'), 'utf8');
const zh = JSON.parse(fs.readFileSync(path.join(root, 'src/app/opspilot/locales/zh.json'), 'utf8'));
const en = JSON.parse(fs.readFileSync(path.join(root, 'src/app/opspilot/locales/en.json'), 'utf8'));

assert.match(wikiTypes, /export interface BuildMaintenanceBatchRetryResult/);
assert.match(wikiApi, /batchRetryBuildMaintenance/);
assert.match(wikiApi, /batch_retry_maintenance/);
assert.match(wikiApi, /knowledge_base: kbId/);
assert.match(wikiApi, /ids/);
assert.match(buildRecordTab, /batchRetryBuildMaintenance/);
assert.match(buildRecordTab, /selectedRowKeys/);
assert.match(buildRecordTab, /rowSelection/);
assert.match(buildRecordTab, /handleBatchMaintenanceRetry/);
assert.match(buildRecordTab, /maintenanceStageFilter \? \[maintenanceStageFilter\] : undefined/);

for (const key of ['batchRetryMaintenance', 'batchRetryMaintenanceConfirm']) {
  assert.ok(zh.wiki[key], `missing zh wiki.${key}`);
  assert.ok(en.wiki[key], `missing en wiki.${key}`);
}

console.log('wiki build record batch maintenance validation passed');
