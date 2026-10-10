import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const read = (file: string) => fs.readFileSync(path.join(root, file), 'utf8');

const pageTab = read('src/app/opspilot/components/wiki/PageTab.tsx');
const modal = read('src/app/opspilot/components/wiki/WikiMarkdownImportModal.tsx');
const editor = read('src/app/opspilot/components/wiki/WikiPageEditorDrawer.tsx');
const zh = JSON.parse(read('src/app/opspilot/locales/zh.json'));
const en = JSON.parse(read('src/app/opspilot/locales/en.json'));

assert.match(pageTab, /t\(["']wiki\.importOkf["']\)/);
assert.doesNotMatch(pageTab, /wiki\.exportMarkdown/);
assert.doesNotMatch(pageTab, /wiki\.importMarkdown/);
assert.doesNotMatch(pageTab, /markdownImportOpen/);
assert.doesNotMatch(pageTab, /importFormat/);
assert.doesNotMatch(modal, /importFormat/);
assert.doesNotMatch(modal, /restoreStructure/);
assert.doesNotMatch(modal, /restore_structure/);
assert.doesNotMatch(modal, /path_mappings/);
assert.doesNotMatch(modal, /markdownImportArchiveMarkdown/);
assert.match(modal, /okfImportAlignmentTitle/);
assert.match(modal, /options\.import_format = ["']okf["']/);
assert.match(
  editor,
  /!\[\"other\", \"source\"\]\.includes\(key\)/,
  "new page type select must not offer source",
);

for (const key of ['importOkf', 'okfImportAlignmentTitle', 'materialsRootEmpty', 'introductionRequired']) {
  assert.ok(zh.wiki[key], `missing zh wiki.${key}`);
  assert.ok(en.wiki[key], `missing en wiki.${key}`);
}
for (const gone of [
  'importMarkdown',
  'markdownImportTitle',
  'markdownImportDropHint',
  'markdownImportFileTypeInvalid',
  'markdownImportArchiveMarkdown',
  'markdownImportRestoreStructure',
]) {
  assert.equal(zh.wiki[gone], undefined, `zh wiki.${gone} should be removed`);
  assert.equal(en.wiki[gone], undefined, `en wiki.${gone} should be removed`);
}
assert.equal(zh.wiki.importOkf, '导入 OKF');
assert.equal(en.wiki.importOkf, 'Import OKF');
assert.equal(zh.wiki.triggerMarkdownImport, '导入 OKF');
assert.equal(en.wiki.triggerMarkdownImport, 'Import OKF');
assert.doesNotMatch(zh.wiki.triggerMarkdownImport, /Markdown/);
assert.doesNotMatch(en.wiki.triggerMarkdownImport, /Markdown/);
assert.doesNotMatch(zh.wiki.importOkf, /Markdown/);
assert.doesNotMatch(en.wiki.importOkf, /Markdown/);

console.log('wiki OKF-only import validation passed');
