import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();

const materialTab = fs.readFileSync(path.join(root, 'src/app/opspilot/components/wiki/MaterialTab.tsx'), 'utf8');
const wikiApi = fs.readFileSync(path.join(root, 'src/app/opspilot/api/wiki.ts'), 'utf8');
const wikiTypes = fs.readFileSync(path.join(root, 'src/app/opspilot/types/wiki.ts'), 'utf8');
const zh = JSON.parse(fs.readFileSync(path.join(root, 'src/app/opspilot/locales/zh.json'), 'utf8'));
const en = JSON.parse(fs.readFileSync(path.join(root, 'src/app/opspilot/locales/en.json'), 'utf8'));

assert.match(wikiTypes, /export interface MaterialUpdateImpact/);
assert.match(wikiTypes, /pending_review_pages/);
assert.match(wikiTypes, /content_changed/);

assert.match(wikiApi, /fetchMaterialUpdateImpact/);
assert.match(wikiApi, /update_impact/);
assert.match(wikiApi, /proposeUpdate/);

assert.match(materialTab, /fetchMaterialUpdateImpact/);
assert.match(materialTab, /proposeUpdate/);
assert.match(materialTab, /updateImpactVisible/);
assert.match(materialTab, /pending_review_pages/);
assert.match(materialTab, /status\s*===\s*'updated'/);

for (const key of [
  'updateImpact',
  'updateImpactTip',
  'updateImpactLoading',
  'pendingReviewPages',
  'contentChanged',
  'latestVersion',
  'previousVersion',
  'proposeUpdate',
  'proposeUpdateDone',
]) {
  assert.ok(zh.wiki[key], `missing zh wiki.${key}`);
  assert.ok(en.wiki[key], `missing en wiki.${key}`);
}

console.log('wiki material update impact validation passed');
