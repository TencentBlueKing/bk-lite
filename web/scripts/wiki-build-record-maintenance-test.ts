import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();

const buildRecordTab = fs.readFileSync(path.join(root, 'src/app/opspilot/components/wiki/BuildRecordTab.tsx'), 'utf8');
const wikiApi = fs.readFileSync(path.join(root, 'src/app/opspilot/api/wiki.ts'), 'utf8');
const wikiTypes = fs.readFileSync(path.join(root, 'src/app/opspilot/types/wiki.ts'), 'utf8');
const zh = JSON.parse(fs.readFileSync(path.join(root, 'src/app/opspilot/locales/zh.json'), 'utf8'));
const en = JSON.parse(fs.readFileSync(path.join(root, 'src/app/opspilot/locales/en.json'), 'utf8'));

assert.match(wikiTypes, /export interface BuildMaintenanceStage/);
assert.match(wikiTypes, /export interface BuildMaintenance/);
assert.match(wikiTypes, /maintenance\?: BuildMaintenance/);

assert.match(buildRecordTab, /MAINTENANCE_STAGE_LABEL/);
assert.match(buildRecordTab, /renderMaintenance/);
assert.match(buildRecordTab, /detail\.maintenance/);
assert.match(buildRecordTab, /maintenanceDeletedPagePrune/);
assert.match(wikiApi, /retryBuildMaintenance/);
assert.match(wikiApi, /retry_maintenance/);
assert.match(wikiApi, /retryBuildMaintenance\s*=\s*\(id: number, stages\?: string\[\]\)/);
assert.match(wikiApi, /stages \? \{ stages \} : \{\}/);
assert.match(buildRecordTab, /retryBuildMaintenance/);
assert.match(buildRecordTab, /maintenanceRetry/);
assert.match(buildRecordTab, /handleMaintenanceRetry\s*=\s*async \(id: number, stages\?: string\[\]\)/);
assert.match(buildRecordTab, /retryBuildMaintenance\(id, stages\)/);
assert.match(buildRecordTab, /handleMaintenanceRetry\(detail\.id, \[stageKey\]\)/);
assert.match(buildRecordTab, /stage\.status === 'failed'/);

for (const key of [
  'maintenanceResult',
  'maintenanceRetry',
  'maintenanceRetryStage',
  'maintenanceRetryDone',
  'maintenanceSuccess',
  'maintenancePartial',
  'maintenanceFailed',
  'maintenanceSkipped',
  'maintenanceRelations',
  'maintenancePageEmbedding',
  'maintenanceChunkEmbedding',
  'maintenanceCheckSweep',
  'maintenanceDeletedPagePrune',
  'maintenancePruneDisabled',
]) {
  assert.ok(zh.wiki[key], `missing zh wiki.${key}`);
  assert.ok(en.wiki[key], `missing en wiki.${key}`);
}

console.log('wiki build record maintenance validation passed');
