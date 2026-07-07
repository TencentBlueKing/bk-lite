import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const read = (file: string) => fs.readFileSync(path.join(root, file), 'utf8');

const wikiApi = read('src/app/opspilot/api/wiki.ts');
const wikiTypes = read('src/app/opspilot/types/wiki.ts');
const pageTab = read('src/app/opspilot/components/wiki/PageTab.tsx');
const zh = JSON.parse(read('src/app/opspilot/locales/zh.json'));
const en = JSON.parse(read('src/app/opspilot/locales/en.json'));

assert.match(wikiTypes, /export interface MarkdownImportResult/);
assert.match(wikiTypes, /created: number/);
assert.match(wikiTypes, /updated: number/);
assert.match(wikiTypes, /skipped: number/);

assert.match(wikiApi, /const importKnowledgeBaseMarkdown = \(id: number, file: File\): Promise<MarkdownImportResult> =>/);
assert.match(wikiApi, /new FormData\(\)/);
assert.match(wikiApi, /fd\.append\('file', file\)/);
assert.match(wikiApi, /\/knowledge_base\/\$\{id\}\/import_markdown\//);
assert.match(wikiApi, /importKnowledgeBaseMarkdown,/);

assert.match(pageTab, /UploadOutlined/);
assert.match(pageTab, /importKnowledgeBaseMarkdown/);
assert.match(pageTab, /handleImportMarkdown/);
assert.match(pageTab, /accept="\.md,\.markdown,\.zip"/);
assert.match(pageTab, /showUploadList=\{false\}/);
assert.match(pageTab, /beforeUpload=\{\(file\) =>/);
assert.match(pageTab, /t\('wiki\.importMarkdown'\)/);
assert.match(pageTab, /t\('wiki\.importMarkdownDone'\)/);

for (const key of ['importMarkdown', 'importMarkdownDone', 'importMarkdownFailed']) {
  assert.ok(zh.wiki[key], `missing zh wiki.${key}`);
  assert.ok(en.wiki[key], `missing en wiki.${key}`);
}

console.log('wiki markdown import validation passed');
