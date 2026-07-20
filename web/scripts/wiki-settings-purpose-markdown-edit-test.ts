import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const settingsTab = fs.readFileSync(path.join(root, 'src/app/opspilot/components/wiki/SettingsTab.tsx'), 'utf8');

assert.match(settingsTab, /import MarkdownRenderer from '@\/components\/markdown'/, 'SettingsTab should render purpose/schema as markdown');
assert.match(settingsTab, /EditOutlined/, 'SettingsTab should expose edit icon for purpose/schema markdown');
assert.match(settingsTab, /Tooltip/, 'Edit icon should have a tooltip');
assert.match(settingsTab, /const \[purposeEditing,\s*setPurposeEditing\] = useState\(false\)/, 'Purpose/schema tab should default to read mode');
assert.match(settingsTab, /const \[purposePreview,\s*setPurposePreview\] = useState\(''\)/, 'Read mode should use loaded purpose snapshot');
assert.match(settingsTab, /const \[schemaPreview,\s*setSchemaPreview\] = useState\(''\)/, 'Read mode should use loaded schema snapshot');
assert.doesNotMatch(settingsTab, /Form\.useWatch\('purpose_md', form\)/, 'Read mode must not depend on unmounted purpose form item');
assert.doesNotMatch(settingsTab, /Form\.useWatch\('schema_md', form\)/, 'Read mode must not depend on unmounted schema form item');
assert.match(settingsTab, /setPurposePreview\(kb\.purpose_md \|\| ''\)/, 'Load should fill purpose markdown preview');
assert.match(settingsTab, /setSchemaPreview\(kb\.schema_md \|\| ''\)/, 'Load should fill schema markdown preview');
assert.match(settingsTab, /const handleCancelPurposeEdit = \(\) => \{/, 'Edit mode should support cancel');
assert.match(settingsTab, /purpose_md: purposePreview/, 'Cancel should restore purpose form field');
assert.match(settingsTab, /schema_md: schemaPreview/, 'Cancel should restore schema form field');
assert.match(settingsTab, /setPurposeEditing\(false\)/, 'Save or cancel should return to read mode');
assert.match(settingsTab, /<MarkdownRenderer content=\{content\} \/>/, 'Read mode should use MarkdownRenderer');
assert.match(settingsTab, /purposeEditing \? \(/, 'Purpose/schema pane should switch between edit and read mode');
assert.match(settingsTab, /setPurposeEditing\(true\)/, 'Edit icon should switch to edit mode');
assert.match(settingsTab, /active !== 'danger' && \(active !== 'purpose' \|\| purposeEditing\)/, 'Save button should only show in purpose tab while editing');
assert.match(settingsTab, /onClick=\{handleCancelPurposeEdit\}/, 'Edit mode should render cancel action');
assert.match(settingsTab, /t\('common\.cancel'\)/, 'Cancel action should use i18n text');
assert.match(settingsTab, /name="purpose_md"[\s\S]*<Input\.TextArea autoSize=\{\{ minRows: 18, maxRows: 28 \}\}/, 'Edit mode should keep large purpose textarea');
assert.match(settingsTab, /name="schema_md"[\s\S]*<Input\.TextArea autoSize=\{\{ minRows: 18, maxRows: 28 \}\}/, 'Edit mode should keep large schema textarea');

console.log('wiki settings purpose markdown edit validation passed');