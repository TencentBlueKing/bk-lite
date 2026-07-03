import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const pageTab = fs.readFileSync(path.join(root, 'src/app/opspilot/components/wiki/PageTab.tsx'), 'utf8');
const wikiApi = fs.readFileSync(path.join(root, 'src/app/opspilot/api/wiki.ts'), 'utf8');
const zh = JSON.parse(fs.readFileSync(path.join(root, 'src/app/opspilot/locales/zh.json'), 'utf8'));
const en = JSON.parse(fs.readFileSync(path.join(root, 'src/app/opspilot/locales/en.json'), 'utf8'));

for (const key of [
  'filterName',
  'filterNamePlaceholder',
  'filterStatus',
  'filterType',
  'pageTypeAll',
  'batchDeletePages',
  'batchDeletePagesConfirm',
  'batchDeleteDone',
]) {
  assert.ok(zh.wiki[key], `missing zh wiki.${key}`);
  assert.ok(en.wiki[key], `missing en wiki.${key}`);
}

assert.match(wikiApi, /const batchDeletePages = \(/);
assert.match(wikiApi, /post\(`\$\{BASE\}\/page\/batch_delete\/`, \{ knowledge_base: kbId, ids \}\)/);
assert.match(pageTab, /const \[nameFilter, setNameFilter\]/);
assert.match(pageTab, /const \[typeFilter, setTypeFilter\]/);
assert.match(pageTab, /const \[filterPageTypes, setFilterPageTypes\]/);
assert.match(pageTab, /const \[statusFilter, setStatusFilter\] = useState\('active'\)/);
assert.match(pageTab, /fetchPages\(kbId,\s*\{[^}]*status:\s*statusFilter/);
assert.doesNotMatch(pageTab, /status:\s*statusFilter \|\| undefined/);
assert.match(pageTab, /title:\s*nameFilter\.trim\(\) \|\| undefined/);
assert.match(pageTab, /page_type:\s*typeFilter\.trim\(\) \|\| undefined/);
assert.match(pageTab, /handleNameFilterSearch/);
assert.match(pageTab, /handleTypeFilterChange/);
assert.match(pageTab, /setFilterPageTypes\(\(current\) =>/);
assert.match(pageTab, /new Set\(\[\.\.\.current,\s*\.\.\.nextTypes\]\)/);
assert.match(pageTab, /filterTypeOptions/);
assert.match(pageTab, /filterPageTypes\.map\(\(value\) => \(\{ value, label: value \}\)\)/);
assert.match(pageTab, /<Select[\s\S]*placeholder=\{t\('wiki\.pageTypeAll'\)\}[\s\S]*onChange=\{handleTypeFilterChange\}/);
assert.doesNotMatch(pageTab, /<AutoComplete[\s\S]*placeholder=\{t\('wiki\.pageTypeAll'\)\}/);
assert.match(pageTab, /rowSelection=\{\{/);
assert.match(pageTab, /batchDeletePages\(kbId, selectedPageIds\)/);
assert.match(pageTab, /t\('wiki\.batchDeletePages'\)/);
assert.match(pageTab, /t\('wiki\.batchDeletePagesConfirm'\)/);
assert.match(pageTab, /t\('wiki\.filterName'\)/);
assert.match(pageTab, /t\('wiki\.filterNamePlaceholder'\)/);
assert.match(pageTab, /t\('wiki\.filterStatus'\)/);
assert.match(pageTab, /t\('wiki\.filterType'\)/);
assert.match(pageTab, /t\('wiki\.pageTypeAll'\)/);
assert.doesNotMatch(pageTab, /pageStatusWorking/);
assert.doesNotMatch(pageTab, /pageStatusAll/);
assert.doesNotMatch(pageTab, /value:\s*''[^,]*,\s*label:\s*t\('wiki\.pageStatus/);
assert.match(pageTab, /value: 'active'/);
assert.match(pageTab, /value: 'source_invalid'/);

console.log('wiki page batch delete validation passed');
