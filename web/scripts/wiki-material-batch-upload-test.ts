import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const read = (file: string) => fs.readFileSync(path.join(root, file), 'utf8');

const materialTab = read('src/app/opspilot/components/wiki/MaterialTab.tsx');
const wikiApi = read('src/app/opspilot/api/wiki.ts');
const wikiTypes = read('src/app/opspilot/types/wiki.ts');
const zh = JSON.parse(read('src/app/opspilot/locales/zh.json'));
const en = JSON.parse(read('src/app/opspilot/locales/en.json'));

// MaterialTab:文件选择→批量提交
assert.match(materialTab, /const files = fileList/);
assert.match(materialTab, /multiple/);
assert.doesNotMatch(materialTab, /maxCount=\{1\}/);
assert.match(materialTab, /setFileList\(fl\)/);

// 多文件分支:走 batchCreateMaterials 后端,失败汇总到 toast
assert.match(materialTab, /batchCreateMaterials/);
assert.match(materialTab, /result\?\.errors/);
assert.match(materialTab, /t\('wiki\.batchAddMaterialPartial'\)/);
assert.match(materialTab, /t\('wiki\.batchAddMaterialDone'\)/);
assert.doesNotMatch(materialTab, /files\.map\(\(file\)\s*=>\s*createMaterialFile/);

// API 层提供 batchCreateMaterials
assert.match(wikiApi, /const batchCreateMaterials\s*=/);
assert.match(wikiApi, /fd\.append\('files'/);
assert.match(wikiApi, /material\/batch_create\//);

// 类型层提供 MaterialBatchCreateResult
assert.match(wikiTypes, /interface MaterialBatchCreateResult/);
assert.match(wikiTypes, /items:\s*Material\[\]/);
assert.match(wikiTypes, /errors:\s*Array<\{\s*name:\s*string;\s*error:\s*string\s*\}>/);

for (const key of ['batchAddMaterialDone', 'batchAddMaterialPartial', 'selectedFiles']) {
  assert.ok(zh.wiki[key], `missing zh wiki.${key}`);
  assert.ok(en.wiki[key], `missing en wiki.${key}`);
}

console.log('wiki material batch upload validation passed');
