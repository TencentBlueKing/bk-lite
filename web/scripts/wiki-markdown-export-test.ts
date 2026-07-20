import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const read = (file: string) => fs.readFileSync(path.join(root, file), 'utf8');

const wikiApi = read('src/app/opspilot/api/wiki.ts');
const pageTab = read('src/app/opspilot/components/wiki/PageTab.tsx');
const zh = JSON.parse(read('src/app/opspilot/locales/zh.json'));
const en = JSON.parse(read('src/app/opspilot/locales/en.json'));

assert.match(wikiApi, /const exportKnowledgeBaseMarkdown = \(id: number\): Promise<Blob> =>/);
assert.match(wikiApi, /\/knowledge_base\/\$\{id\}\/export_markdown\//);
assert.match(wikiApi, /responseType: 'blob'/);
assert.match(wikiApi, /exportKnowledgeBaseMarkdown,/);

assert.match(pageTab, /DownloadOutlined/);
assert.match(pageTab, /exportKnowledgeBaseMarkdown/);
assert.match(pageTab, /handleExportMarkdown/);
assert.match(pageTab, /URL\.createObjectURL/);
assert.match(pageTab, /wiki-kb-\$\{kbId\}-markdown\.zip/);
assert.match(pageTab, /t\('wiki\.exportMarkdown'\)/);
assert.match(pageTab, /t\('wiki\.exportMarkdownDone'\)/);

for (const key of ['exportMarkdown', 'exportMarkdownDone', 'exportMarkdownFailed']) {
  assert.ok(zh.wiki[key], `missing zh wiki.${key}`);
  assert.ok(en.wiki[key], `missing en wiki.${key}`);
}

console.log('wiki markdown export validation passed');
