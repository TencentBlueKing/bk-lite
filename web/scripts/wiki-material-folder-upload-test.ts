import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const read = (file: string) => fs.readFileSync(path.join(root, file), 'utf8');

const materialTab = read('src/app/opspilot/components/wiki/MaterialTab.tsx');
const zh = JSON.parse(read('src/app/opspilot/locales/zh.json'));
const en = JSON.parse(read('src/app/opspilot/locales/en.json'));

assert.match(materialTab, /const \[folderImport, setFolderImport\] = useState\(false\)/);
assert.match(materialTab, /setFolderImport\(false\)/);
assert.match(materialTab, /directory=\{folderImport\}/);
assert.match(materialTab, /onChange=\{\(checked\) => setFolderImport\(checked\)\}/);
assert.match(materialTab, /t\('wiki\.folderImport'\)/);
assert.match(materialTab, /t\('wiki\.folderImportTip'\)/);

for (const key of ['folderImport', 'folderImportTip']) {
  assert.ok(zh.wiki[key], `missing zh wiki.${key}`);
  assert.ok(en.wiki[key], `missing en wiki.${key}`);
}

console.log('wiki material folder upload validation passed');
