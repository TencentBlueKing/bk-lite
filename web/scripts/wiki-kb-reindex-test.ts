import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const wikiApi = fs.readFileSync(path.join(root, 'src/app/opspilot/api/wiki.ts'), 'utf8');
const settingsTab = fs.readFileSync(path.join(root, 'src/app/opspilot/components/wiki/SettingsTab.tsx'), 'utf8');
const zh = JSON.parse(fs.readFileSync(path.join(root, 'src/app/opspilot/locales/zh.json'), 'utf8'));
const en = JSON.parse(fs.readFileSync(path.join(root, 'src/app/opspilot/locales/en.json'), 'utf8'));

for (const key of ['reindexKnowledgeBase', 'reindexKnowledgeBaseTip', 'reindexKnowledgeBaseConfirm', 'reindexKnowledgeBaseDone']) {
  assert.ok(zh.wiki[key], `missing zh wiki.${key}`);
  assert.ok(en.wiki[key], `missing en wiki.${key}`);
}

assert.match(wikiApi, /const reindexKnowledgeBase = \(id: number\): Promise<BuildRecord> =>/);
assert.match(wikiApi, /\/knowledge_base\/\$\{id\}\/reindex\//);
assert.match(wikiApi, /reindexKnowledgeBase,/);

assert.match(settingsTab, /reindexKnowledgeBase,/);
assert.match(settingsTab, /const \[reindexConfirmOpen,\s*setReindexConfirmOpen\]/);
assert.match(settingsTab, /const handleReindexConfirm = \(\) => \{/);
assert.match(settingsTab, /runDanger\(\(\) => reindexKnowledgeBase\(kbId\),\s*\(\) => refreshRunningBuildState\(\)\)/);
assert.match(settingsTab, /title=\{t\('wiki\.reindexKnowledgeBaseConfirm'\)\}/);
assert.match(settingsTab, /open=\{reindexConfirmOpen\}/);
assert.match(settingsTab, /onOpenChange=\{setReindexConfirmOpen\}/);
assert.match(settingsTab, /onConfirm=\{handleReindexConfirm\}/);
assert.match(settingsTab, /t\('wiki\.reindexKnowledgeBase'\)/);
assert.match(settingsTab, /t\('wiki\.reindexKnowledgeBaseTip'\)/);

console.log('wiki knowledge base reindex validation passed');
