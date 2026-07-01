import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';

const root = process.cwd();
const read = (path) => readFileSync(join(root, path), 'utf8');
const exists = (path) => existsSync(join(root, path));

const registry = read('src/app/monitor/dashboards/registry.ts');
assert.match(registry, /StorageDashboard/);
assert.match(registry, /key:\s*'storage'/);
assert.match(registry, /objectName:\s*'Storage'/);
assert.match(registry, /groupKey:\s*'hardware'/);

const storageIntegration = read('src/app/monitor/hooks/integration/objects/hardwareDevice/storage.tsx');
assert.match(storageIntegration, /dashboardDisplay:\s*\[/);
assert.match(storageIntegration, /pure_array_capacity_bytes_gauge/);
assert.match(storageIntegration, /Pure:\s*'pure'/);
assert.match(storageIntegration, /InfiniBox:\s*'infinibox'/);

const commonUtils = read('src/app/monitor/utils/common.tsx');
assert.match(commonUtils, /\\bpure\\b[\s\S]*pure\\s\*storage[\s\S]*flasharray[\s\S]*icon:\s*'mm-purestorage_purestorage'/);
assert.match(commonUtils, /infinidat\|infinibox[\s\S]*icon:\s*'mm-infinidat_infinidat'/);

const pureMetrics = JSON.parse(read('../server/apps/monitor/support-files/plugins/Telegraf/pure/storage/metrics.json'));
const infiniBoxMetrics = JSON.parse(read('../server/apps/monitor/support-files/plugins/Telegraf/infinibox/storage/metrics.json'));
assert.equal(pureMetrics.icon, 'mm-storage_储存设备');
assert.equal(infiniBoxMetrics.icon, 'mm-storage_储存设备');

const configPath = 'src/app/monitor/dashboards/objects/storage/config.ts';
const dashboardPath = 'src/app/monitor/dashboards/objects/storage/dashboard.tsx';
const storyPath = 'src/stories/monitor/dashboards/storage.stories.tsx';
assert.equal(exists(configPath), true, `${configPath} should exist`);
assert.equal(exists(dashboardPath), true, `${dashboardPath} should exist`);
assert.equal(exists(storyPath), true, `${storyPath} should exist`);

const config = read(configPath);
for (const metricName of [
  'pure_array_used_bytes_gauge',
  'pure_volume_read_iops_gauge',
  'infinibox_pool_physical_capacity_bytes_gauge',
  'infinibox_volume_read_iops_gauge'
]) {
  assert.match(config, new RegExp(metricName));
}

const story = read(storyPath);
assert.match(story, /title:\s*'Monitor\/Dashboard\/Storage'/);
assert.match(story, /Pure FlashArray/);
assert.match(story, /InfiniBox/);
assert.match(story, /StorageDashboardPreview/);
assert.doesNotMatch(story, /export\s+(function|const)\s+StorageDashboardPreview/);

console.log('storage dashboard delivery tests passed');
