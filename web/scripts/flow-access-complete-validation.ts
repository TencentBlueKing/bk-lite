import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(scriptDir, '..');
const accessCompletePath = path.join(
  repoRoot,
  'src/app/monitor/(pages)/integration/list/detail/configure/flow/accessComplete.tsx'
);
const zhLocalePath = path.join(repoRoot, 'src/app/monitor/locales/zh.json');
const enLocalePath = path.join(repoRoot, 'src/app/monitor/locales/en.json');

const accessCompleteSource = fs.readFileSync(accessCompletePath, 'utf8');
const zhLocale = JSON.parse(fs.readFileSync(zhLocalePath, 'utf8'));
const enLocale = JSON.parse(fs.readFileSync(enLocalePath, 'utf8'));

assert.match(accessCompleteSource, /router\.push\(`\/monitor\/view`\)/);
assert.doesNotMatch(
  accessCompleteSource,
  /router\.push\(`\/monitor\/integration\/asset\?objId=\$\{objectId\}`\)/
);
assert.equal(
  zhLocale.monitor.integrations.flow.viewAssetList,
  '查看监控视图'
);
assert.equal(
  enLocale.monitor.integrations.flow.viewAssetList,
  'View Monitoring View'
);

console.log('flow access complete validation passed');
