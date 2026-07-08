import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const wikiApi = fs.readFileSync(path.join(root, 'src/app/opspilot/api/wiki.ts'), 'utf8');
const wikiModifyModal = fs.readFileSync(path.join(root, 'src/app/opspilot/components/wiki/WikiModifyModal.tsx'), 'utf8');
const settingsTab = fs.readFileSync(path.join(root, 'src/app/opspilot/components/wiki/SettingsTab.tsx'), 'utf8');
const pageTab = fs.readFileSync(path.join(root, 'src/app/opspilot/components/wiki/PageTab.tsx'), 'utf8');

assert.match(wikiApi, /fetchEmbedProviders,/);
assert.match(wikiApi, /reindexPage,/);

assert.doesNotMatch(wikiModifyModal, /label=\{t\('wiki\.embedProvider'\)\}/);
assert.doesNotMatch(wikiModifyModal, /name="embed_provider"/);

assert.doesNotMatch(settingsTab, /label=\{t\('wiki\.embedProvider'\)\}/);
assert.doesNotMatch(settingsTab, /name="embed_provider"/);
assert.match(settingsTab, /embed_provider:\s*prev\?\.embed_provider/);

assert.match(pageTab, /const SHOW_PAGE_REINDEX_ACTION = false/);
assert.match(pageTab, /reindexPage,/);
assert.match(pageTab, /handleReindexPage/);
assert.match(pageTab, /SHOW_PAGE_REINDEX_ACTION && record\.status === 'active'/);
assert.match(pageTab, /onClick=\{\(\) => handleReindexPage\(record\)\}/);
assert.match(pageTab, /t\('wiki\.reindexPage'\)/);

console.log('wiki hidden embed and page reindex entry validation passed');
