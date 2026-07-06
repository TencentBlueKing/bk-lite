import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const wikiApi = fs.readFileSync(path.join(root, 'src/app/opspilot/api/wiki.ts'), 'utf8');
const materialTab = fs.readFileSync(path.join(root, 'src/app/opspilot/components/wiki/MaterialTab.tsx'), 'utf8');
const zh = JSON.parse(fs.readFileSync(path.join(root, 'src/app/opspilot/locales/zh.json'), 'utf8'));
const en = JSON.parse(fs.readFileSync(path.join(root, 'src/app/opspilot/locales/en.json'), 'utf8'));

for (const key of ['reindexPage', 'reindexPageDone']) {
  assert.ok(zh.wiki[key], `missing zh wiki.${key}`);
  assert.ok(en.wiki[key], `missing en wiki.${key}`);
}

assert.match(wikiApi, /const reindexMaterial = \(id: number\): Promise<BuildRecord> =>/);
assert.match(wikiApi, /\/material\/\$\{id\}\/reindex\//);
assert.match(wikiApi, /reindexMaterial,/);
assert.match(materialTab, /reindexMaterial,/);
assert.match(materialTab, /reindexingMaterialId/);
assert.match(materialTab, /handleReindexMaterial/);
assert.match(materialTab, /t\('wiki\.reindexPage'\)/);

// 重跑索引按钮需用纯文字,与其他操作风格一致(都无 icon)
assert.match(materialTab, /<Button\s+type="link"\s+size="small"[\s\S]*?t\('wiki\.reindexPage'\)/);

console.log('wiki material reindex validation passed');
