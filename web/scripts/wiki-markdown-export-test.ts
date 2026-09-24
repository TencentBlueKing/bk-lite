import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const read = (file: string) => fs.readFileSync(path.join(root, file), 'utf8');

const wikiApi = read('src/app/opspilot/api/wiki.ts');
const pageTab = read('src/app/opspilot/components/wiki/PageTab.tsx');
const zh = JSON.parse(read('src/app/opspilot/locales/zh.json'));
const en = JSON.parse(read('src/app/opspilot/locales/en.json'));

assert.match(wikiApi, /const exportKnowledgeBaseOkf = \(id: number\): Promise<Blob> =>/);
assert.match(wikiApi, /\/knowledge_base\/\$\{id\}\/export_okf\//);
assert.match(wikiApi, /exportKnowledgeBaseOkf,/);

assert.match(pageTab, /exportKnowledgeBaseOkf/);
assert.match(pageTab, /handleExportOkf/);
assert.match(pageTab, /t\(["']wiki\.exportOkf["']\)/);
assert.doesNotMatch(
  wikiApi,
  /exportKnowledgeBaseMarkdown|export_markdown/,
  'knowledge interchange export must be OKF only',
);
assert.doesNotMatch(
  pageTab,
  /exportKnowledgeBaseMarkdown|handleExportMarkdown|wiki\.exportMarkdown/,
  'knowledge interchange export must be OKF only',
);
assert.doesNotMatch(pageTab, /DownloadOutlined/);

assert.equal(zh.wiki.exportMarkdown, undefined, 'zh wiki.exportMarkdown should be removed');
assert.equal(en.wiki.exportMarkdown, undefined, 'en wiki.exportMarkdown should be removed');
assert.equal(zh.wiki.exportMarkdownDone, undefined);
assert.equal(en.wiki.exportMarkdownDone, undefined);
assert.equal(zh.wiki.exportMarkdownFailed, undefined);
assert.equal(en.wiki.exportMarkdownFailed, undefined);
assert.ok(zh.wiki.exportOkf, 'missing zh wiki.exportOkf');
assert.ok(en.wiki.exportOkf, 'missing en wiki.exportOkf');

console.log('wiki OKF-only export validation passed');
