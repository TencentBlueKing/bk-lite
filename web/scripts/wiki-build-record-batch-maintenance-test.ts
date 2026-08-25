import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const buildRecordTab = fs.readFileSync(
  path.join(root, 'src/app/opspilot/components/wiki/BuildRecordTab.tsx'),
  'utf8',
);
const wikiApi = fs.readFileSync(path.join(root, 'src/app/opspilot/api/wiki.ts'), 'utf8');
const wikiTypes = fs.readFileSync(path.join(root, 'src/app/opspilot/types/wiki.ts'), 'utf8');
const zh = JSON.parse(fs.readFileSync(path.join(root, 'src/app/opspilot/locales/zh.json'), 'utf8'));
const en = JSON.parse(fs.readFileSync(path.join(root, 'src/app/opspilot/locales/en.json'), 'utf8'));

assert.doesNotMatch(wikiTypes, /BuildMaintenanceBatchRetryResult/);
assert.doesNotMatch(wikiApi, /batchRetryBuildMaintenance/);
assert.doesNotMatch(wikiApi, /batch_retry_maintenance/);
assert.doesNotMatch(buildRecordTab, /batchRetryBuildMaintenance/);
assert.doesNotMatch(buildRecordTab, /handleBatchMaintenanceRetry/);
assert.doesNotMatch(buildRecordTab, /rowSelection/);
assert.doesNotMatch(buildRecordTab, /selectedRowKeys/);
assert.match(buildRecordTab, /retryBuildMaintenance/);
assert.match(buildRecordTab, /canRetryMaintenance/);
assert.doesNotMatch(buildRecordTab, /handleTriggerFilterChange/, 'BuildRecordTab should not render trigger filter');
assert.doesNotMatch(
  buildRecordTab,
  /handleMaintenanceStatusFilterChange/,
  'BuildRecordTab should not render maintenance result filter',
);

for (const key of ['batchRetryMaintenance', 'batchRetryMaintenanceConfirm']) {
  assert.equal(zh.wiki[key], undefined, `zh wiki.${key} should be removed`);
  assert.equal(en.wiki[key], undefined, `en wiki.${key} should be removed`);
}

console.log('wiki build record batch maintenance removal validation passed');
