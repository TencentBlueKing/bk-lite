import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const wikiApi = fs.readFileSync(path.join(root, 'src/app/opspilot/api/wiki.ts'), 'utf8');
const wikiModifyModal = fs.readFileSync(path.join(root, 'src/app/opspilot/components/wiki/WikiModifyModal.tsx'), 'utf8');
const settingsTab = fs.readFileSync(path.join(root, 'src/app/opspilot/components/wiki/SettingsTab.tsx'), 'utf8');
const pageTable = fs.readFileSync(path.join(root, 'src/app/opspilot/components/wiki/WikiPageTable.tsx'), 'utf8');

assert.match(wikiApi, /fetchEmbedProviders,/);
assert.match(wikiApi, /reindexPage,/);

assert.match(wikiModifyModal, /fetchEmbedProviders/);
assert.match(wikiModifyModal, /label=\{t\("wiki\.embedProvider"\)\}/);
assert.match(wikiModifyModal, /name="embed_provider"/);
assert.match(wikiModifyModal, /embed_provider:\s*values\.embed_provider \?\? null/);

assert.match(settingsTab, /fetchEmbedProviders/);
assert.match(settingsTab, /label=\{t\("wiki\.embedProvider"\)\}/);
assert.match(settingsTab, /name="embed_provider"/);
assert.match(settingsTab, /embed_provider:\s*v\.embed_provider \?\? null/);
assert.doesNotMatch(settingsTab, /embed_provider:\s*prev\?\.embed_provider/);

assert.match(pageTable, /const SHOW_PAGE_REINDEX_ACTION = false/);
assert.match(pageTable, /SHOW_PAGE_REINDEX_ACTION && page\.status === "active"/);
assert.match(pageTable, /t\("wiki\.reindexPage"\)/);

console.log('wiki embed provider entry and hidden page reindex validation passed');
