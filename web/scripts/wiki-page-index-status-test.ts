import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const wikiApi = fs.readFileSync(path.join(root, 'src/app/opspilot/api/wiki.ts'), 'utf8');
const pageTab = fs.readFileSync(path.join(root, 'src/app/opspilot/components/wiki/PageTab.tsx'), 'utf8');
const wikiFormat = fs.readFileSync(path.join(root, 'src/app/opspilot/components/wiki/wikiFormat.ts'), 'utf8');
const wikiTypes = fs.readFileSync(path.join(root, 'src/app/opspilot/types/wiki.ts'), 'utf8');
const zh = JSON.parse(fs.readFileSync(path.join(root, 'src/app/opspilot/locales/zh.json'), 'utf8'));
const en = JSON.parse(fs.readFileSync(path.join(root, 'src/app/opspilot/locales/en.json'), 'utf8'));

for (const key of [
  'indexStatus',
  'pageIndex',
  'chunkIndex',
  'indexStatusIndexed',
  'indexStatusNotIndexed',
  'indexStatusFailed',
  'indexStatusSkipped',
  'indexReasonNoEmbedProvider',
  'indexReasonNoCurrentVersion',
  'indexReasonEmptyBody',
  'reindexPage',
  'reindexPageDone',
]) {
  assert.ok(zh.wiki[key], `missing zh wiki.${key}`);
  assert.ok(en.wiki[key], `missing en wiki.${key}`);
}

assert.match(wikiTypes, /export interface WikiIndexStageDetail/);
assert.match(wikiTypes, /index_status\?: string/);
assert.match(wikiTypes, /chunk_index_status\?: string/);
assert.match(wikiTypes, /index_detail\?: WikiIndexDetail/);
assert.match(wikiFormat, /export const INDEX_STATUS_LABEL/);
assert.match(wikiFormat, /export const INDEX_REASON_LABEL/);
assert.match(wikiApi, /const reindexPage = \(id: number\): Promise<BuildRecord> =>/);
assert.match(wikiApi, /\/page\/\$\{id\}\/reindex\//);
assert.match(wikiApi, /reindexPage,/);
assert.match(pageTab, /INDEX_STATUS_COLOR/);
assert.match(pageTab, /reindexPage,/);
assert.match(pageTab, /handleReindexPage/);
assert.match(pageTab, /reindexingPageId/);
assert.match(pageTab, /renderIndexStatus/);
assert.match(pageTab, /record\.index_detail\?\.page_embedding/);
assert.match(pageTab, /record\.index_detail\?\.chunk_embedding/);
assert.match(pageTab, /title:\s*t\('wiki\.indexStatus'\)/);
assert.match(pageTab, /Tooltip title=\{tip\}/);
assert.match(pageTab, /t\('wiki\.reindexPage'\)/);
assert.doesNotMatch(pageTab, /\{record\.index_status\}/);
assert.doesNotMatch(pageTab, /\{record\.chunk_index_status\}/);

// 重跑索引按钮需用纯文字,与其他操作风格一致(都无 icon)
assert.match(
  pageTab,
  /<Button\s+type="link"\s+size="small"[\s\S]*?t\('wiki\.reindexPage'\)/
);
assert.doesNotMatch(pageTab, /icon=\{<ReloadOutlined\s*\/>\}/);

console.log('wiki page index status validation passed');
