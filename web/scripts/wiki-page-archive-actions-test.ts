import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const pageTab = fs.readFileSync(path.join(root, 'src/app/opspilot/components/wiki/PageTab.tsx'), 'utf8');
const wikiApi = fs.readFileSync(path.join(root, 'src/app/opspilot/api/wiki.ts'), 'utf8');
const zh = JSON.parse(fs.readFileSync(path.join(root, 'src/app/opspilot/locales/zh.json'), 'utf8'));
const en = JSON.parse(fs.readFileSync(path.join(root, 'src/app/opspilot/locales/en.json'), 'utf8'));

for (const key of [
  'viewPage',
  'restoreArchive',
  'restoreArchiveConfirm',
  'archivedReadOnlyTip',
]) {
  assert.ok(zh.wiki[key], `missing zh wiki.${key}`);
  assert.ok(en.wiki[key], `missing en wiki.${key}`);
}

assert.match(wikiApi, /const restorePageFromArchive = \(id: number\): Promise<KnowledgePage> =>/);
assert.match(wikiApi, /post\(`\$\{BASE\}\/page\/\$\{id\}\/restore_from_archive\/`, \{\}\)/);
assert.match(pageTab, /const isArchivedPage = \(record: KnowledgePage\) => record\.status === 'archived'/);
assert.match(pageTab, /const \[statusFilter, setStatusFilter\] = useState\('active'\)/);
assert.match(pageTab, /const isReadOnlyPage = !!editing && isArchivedPage\(editing\)/);
assert.match(pageTab, /const openView = async \(record: KnowledgePage\) =>/);
assert.match(pageTab, /const handleRestoreFromArchive = async \(record: KnowledgePage\) =>/);
assert.match(pageTab, /restorePageFromArchive\(record\.id\)/);
assert.doesNotMatch(pageTab, /pageStatusWorking/);
assert.doesNotMatch(pageTab, /value:\s*''[^,]*,\s*label:\s*t\('wiki\.pageStatus/);
assert.match(pageTab, /isArchivedPage\(record\) \?/);
assert.match(pageTab, /t\('wiki\.viewPage'\)/);
assert.match(pageTab, /t\('wiki\.restoreArchive'\)/);
assert.match(pageTab, /t\('wiki\.restoreArchiveConfirm'\)/);
assert.match(pageTab, /t\('wiki\.archivedReadOnlyTip'\)/);
assert.match(pageTab, /disabled=\{isReadOnlyPage\}/);
assert.match(pageTab, /extra=\{isReadOnlyPage \? null :/);
assert.doesNotMatch(pageTab, /isArchivedPage\(record\)[\s\S]{0,500}t\('common\.edit'\)/);

console.log('wiki page archive actions validation passed');
