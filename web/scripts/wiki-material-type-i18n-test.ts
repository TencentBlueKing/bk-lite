import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const materialTab = fs.readFileSync(path.join(root, 'src/app/opspilot/components/wiki/MaterialTab.tsx'), 'utf8');
const zh = JSON.parse(fs.readFileSync(path.join(root, 'src/app/opspilot/locales/zh.json'), 'utf8'));
const en = JSON.parse(fs.readFileSync(path.join(root, 'src/app/opspilot/locales/en.json'), 'utf8'));

for (const key of ['materialFile', 'materialText', 'materialWeb', 'downloadFile']) {
  assert.ok(zh.wiki[key], `missing zh wiki.${key}`);
  assert.ok(en.wiki[key], `missing en wiki.${key}`);
}

assert.match(materialTab, /const MATERIAL_TYPE_KEY/);
assert.match(materialTab, /file:\s*'wiki\.materialFile'/);
assert.match(materialTab, /text:\s*'wiki\.materialText'/);
assert.match(materialTab, /web:\s*'wiki\.materialWeb'/);
assert.match(materialTab, /render:\s*\(type:\s*MaterialType\)\s*=>\s*materialTypeLabel\(type\)/);
assert.match(materialTab, /\{materialTypeLabel\(detail\.material\.material_type\)\}/);
assert.doesNotMatch(materialTab, /\{detail\.material\.material_type\}<\/Descriptions\.Item>/);
assert.match(materialTab, /\{t\('wiki\.downloadFile'\)\}/);
assert.doesNotMatch(materialTab, /\{t\('wiki\.openFile'\)\}/);

console.log('wiki material type i18n validation passed');
