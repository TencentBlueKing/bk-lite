import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
function read(p: string) {
  return fs.readFileSync(path.join(root, p), 'utf8');
}

const settingsTab = read('src/app/opspilot/components/wiki/SettingsTab.tsx');
const zh = JSON.parse(read('src/app/opspilot/locales/zh.json'));
const en = JSON.parse(read('src/app/opspilot/locales/en.json'));

// 1. SectionKey 不再含 generation
assert.match(
  settingsTab,
  /type SectionKey = 'basic' \| 'purpose' \| 'danger';/
);
assert.doesNotMatch(settingsTab, /generation:\s*'wiki\./);

// 2. 危险区域使用灰色线(border-border-1),不再用红色 border-fail
assert.match(settingsTab, /border-\[var\(--color-border-1\)\]/);
assert.doesNotMatch(settingsTab, /border-\[var\(--color-fail\)\]/);
// 红框容器 + 两个分隔线共 3 处,全部走 var(--color-border-1)
const failBorderCount = (settingsTab.match(/border-\[var\(--color-fail\)\]/g) || []).length;
const grayBorderCount = (settingsTab.match(/border-\[var\(--color-border-1\)\]/g) || []).length;
assert.ok(failBorderCount === 0, `danger 区域仍残留 ${failBorderCount} 处红框,应改灰`);
assert.ok(grayBorderCount >= 3, `危险区域需要至少 3 处边框(容器 + 2 个分隔线),实际 ${grayBorderCount}`);

// 3. i18n key 已删除
assert.ok(!zh.wiki.settingsGeneration, 'zh.json: settingsGeneration 应删除');
assert.ok(!en.wiki.settingsGeneration, 'en.json: settingsGeneration 应删除');
assert.ok(!zh.wiki.helpGenerationDesc, 'zh.json: helpGenerationDesc 应删除');
assert.ok(!en.wiki.helpGenerationDesc, 'en.json: helpGenerationDesc 应删除');

// 4. 合并预览(generation 里的子功能)同步下线:UI、state、handler、Modal 都不再在 SettingsTab 中
assert.doesNotMatch(settingsTab, /previewMergeKnowledgeBase/);
assert.doesNotMatch(settingsTab, /previewMergeOpen/);
assert.doesNotMatch(settingsTab, /previewMergeLoading/);
assert.doesNotMatch(settingsTab, /openMergePreview/);
assert.doesNotMatch(settingsTab, /preview_merge/);
assert.doesNotMatch(settingsTab, /open=\{mergePreviewOpen\}/);
// 合并预览相关 i18n key 也可以同步下线
const previewMergeI18nKeys = [
  'previewMerge',
  'previewMergeTitle',
  'previewMergeGroups',
  'previewMergeActive',
  'previewMergeEmpty',
  'previewMergeFailed',
  'previewMergeRuleDuplicate',
  'previewMergeRuleAlias',
];
for (const k of previewMergeI18nKeys) {
  assert.ok(!zh.wiki[k], `zh.json: ${k} 应下线(generation Tab 一并移除)`);
  assert.ok(!zh.wiki[k], `en.json: ${k} 应下线(generation Tab 一并移除)`);
}

// 5. 同时清理不再用的 antd import:Modal/List/Empty/Alert/Tag
assert.doesNotMatch(settingsTab, /import\s+\{[^}]*\bModal\b[^}]*\}\s+from\s+'antd'/);
assert.doesNotMatch(settingsTab, /import\s+\{[^}]*\bList\b[^}]*\}\s+from\s+'antd'/);
assert.doesNotMatch(settingsTab, /import\s+\{[^}]*\bEmpty\b[^}]*\}\s+from\s+'antd'/);
assert.doesNotMatch(settingsTab, /import\s+\{[^}]*\bAlert\b[^}]*\}\s+from\s+'antd'/);
assert.doesNotMatch(settingsTab, /import\s+\{[^}]*\bTag\b[^}]*\}\s+from\s+'antd'/);

// 6. 仍保留基础 Tab + 危险 Tab
assert.match(settingsTab, /key:\s*'basic'/);
assert.match(settingsTab, /key:\s*'purpose'/);
assert.match(settingsTab, /key:\s*'danger'/);

// 7. 危险 Tab 标签仍标红(Warning 图标 + color-fail class)
assert.match(settingsTab, /text-\[var\(--color-fail\)\][^<]*<WarningOutlined/);

console.log('wiki settings tabs validation passed');
