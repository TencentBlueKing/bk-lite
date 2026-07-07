import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();

const buildRecordTab = fs.readFileSync(path.join(root, 'src/app/opspilot/components/wiki/BuildRecordTab.tsx'), 'utf8');
const wikiTypes = fs.readFileSync(path.join(root, 'src/app/opspilot/types/wiki.ts'), 'utf8');
const zh = JSON.parse(fs.readFileSync(path.join(root, 'src/app/opspilot/locales/zh.json'), 'utf8'));
const en = JSON.parse(fs.readFileSync(path.join(root, 'src/app/opspilot/locales/en.json'), 'utf8'));

assert.match(wikiTypes, /export interface BuildSourceMaterialTrace/);
assert.match(wikiTypes, /materials\?: BuildSourceMaterialTrace\[\]/);
assert.match(buildRecordTab, /renderSourceMaterialTrace/);
assert.match(buildRecordTab, /trace\?\.materials/);
assert.match(buildRecordTab, /sourceMaterials/);
assert.match(buildRecordTab, /sourceMaterial/);
assert.doesNotMatch(buildRecordTab, /const chunks = trace\?\.chunks \|\| \[\];\s*const pageActions = trace\?\.page_actions \|\| \[\];\s*if \(!chunks\.length && !pageActions\.length\)/);

for (const key of ['sourceMaterials', 'sourceMaterial']) {
  assert.ok(zh.wiki[key], `missing zh wiki.${key}`);
  assert.ok(en.wiki[key], `missing en wiki.${key}`);
}

console.log('wiki build record source trace validation passed');
