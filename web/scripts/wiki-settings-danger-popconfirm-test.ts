import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const settingsTab = fs.readFileSync(
  path.join(root, 'src/app/opspilot/components/wiki/SettingsTab.tsx'),
  'utf8'
);

assert.match(settingsTab, /const \[rebuildConfirmOpen,\s*setRebuildConfirmOpen\]/);
assert.match(settingsTab, /const \[hasRunningBuild,\s*setHasRunningBuild\]/);
assert.match(settingsTab, /fetchBuildRecords,/);
assert.match(settingsTab, /fetchBuildRecords\(kbId,\s*\{\s*status:\s*'running',\s*page_size:\s*1\s*\}\)/);
assert.match(settingsTab, /setHasRunningBuild\(\(records\.items \|\| \[\]\)\.length > 0\);/);
assert.match(settingsTab, /const dangerDisabled = busy \|\| hasRunningBuild;/);
assert.match(settingsTab, /const rebuildButtonClass = /);
assert.match(settingsTab, /min-w-\[108px\]/);
assert.doesNotMatch(settingsTab, /ant-btn-loading-icon/);
assert.match(settingsTab, /const handleRebuildConfirm = \(\) => \{/);
assert.match(settingsTab, /setRebuildConfirmOpen\(false\);/);
assert.match(settingsTab, /setHasRunningBuild\(true\);/);
assert.match(settingsTab, /void runDanger\(\(\) => rebuildKnowledgeBase\(kbId\)\);/);
assert.match(settingsTab, /LoadingOutlined/);
assert.match(settingsTab, /const rebuildButtonIcon = dangerDisabled \? <LoadingOutlined spin \/> : undefined;/);
assert.doesNotMatch(
  settingsTab,
  /onConfirm=\{\(\) => runDanger\(\(\) => rebuildKnowledgeBase\(kbId\)\)\}/,
  'rebuild Popconfirm must not return the rebuild promise'
);
assert.match(settingsTab, /open=\{rebuildConfirmOpen\}/);
assert.match(settingsTab, /onOpenChange=\{setRebuildConfirmOpen\}/);
assert.match(settingsTab, /onConfirm=\{handleRebuildConfirm\}/);
assert.doesNotMatch(settingsTab, /loading=\{dangerDisabled\}/);
assert.match(settingsTab, /icon=\{rebuildButtonIcon\}/);
assert.match(settingsTab, /disabled=\{dangerDisabled\}/);
assert.match(settingsTab, /className=\{rebuildButtonClass\}/);
assert.match(settingsTab, /danger disabled=\{dangerDisabled\}/);

console.log('wiki settings danger popconfirm behavior OK');
