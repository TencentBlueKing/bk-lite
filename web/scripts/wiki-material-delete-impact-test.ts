import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();

const materialTab = fs.readFileSync(path.join(root, 'src/app/opspilot/components/wiki/MaterialTab.tsx'), 'utf8');
const wikiApi = fs.readFileSync(path.join(root, 'src/app/opspilot/api/wiki.ts'), 'utf8');
const wikiTypes = fs.readFileSync(path.join(root, 'src/app/opspilot/types/wiki.ts'), 'utf8');
const zh = JSON.parse(fs.readFileSync(path.join(root, 'src/app/opspilot/locales/zh.json'), 'utf8'));
const en = JSON.parse(fs.readFileSync(path.join(root, 'src/app/opspilot/locales/en.json'), 'utf8'));

assert.match(wikiTypes, /export interface MaterialDeleteImpact/);
assert.match(wikiTypes, /will_be_source_invalid/);
assert.match(wikiTypes, /shared_source_protected/);

assert.match(wikiApi, /fetchMaterialDeleteImpact/);
assert.match(wikiApi, /delete_impact/);

assert.match(materialTab, /fetchMaterialDeleteImpact/);
assert.match(materialTab, /deleteImpact/);
assert.match(materialTab, /will_be_source_invalid/);
assert.match(materialTab, /shared_source_protected/);
assert.match(materialTab, /deleteImpactVisible/);

for (const key of [
  'deleteImpact',
  'deleteImpactTip',
  'affectedPages',
  'willLoseSource',
  'sharedSourceProtected',
  'noAffectedPages',
]) {
  assert.ok(zh.wiki[key], `missing zh wiki.${key}`);
  assert.ok(en.wiki[key], `missing en wiki.${key}`);
}

console.log('wiki material delete impact validation passed');
