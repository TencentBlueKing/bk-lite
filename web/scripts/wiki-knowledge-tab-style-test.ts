import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const knowledgeTab = fs.readFileSync(path.join(root, 'src/app/opspilot/components/wiki/KnowledgeTab.tsx'), 'utf8');

assert.match(knowledgeTab, /import \{ Tabs \} from 'antd';/, 'KnowledgeTab should use Ant Design Tabs');
assert.doesNotMatch(knowledgeTab, /Segmented/, 'KnowledgeTab should not use segmented button tabs');
assert.match(knowledgeTab, /FileTextOutlined/, 'Knowledge page tab should use an icon');
assert.match(knowledgeTab, /ApartmentOutlined/, 'Graph tab should use an icon');
assert.match(knowledgeTab, /activeKey=\{view\}/, 'Tabs should be controlled by the current view');
assert.match(knowledgeTab, /items=\{\[/, 'Tabs should define tab items');
assert.match(knowledgeTab, /\[&_\.ant-tabs-content-holder\]:flex-1/, 'Tabs content holder should fill the workspace height');
assert.match(knowledgeTab, /\[&_\.ant-tabs-tabpane\]:h-full/, 'Tab pane should preserve graph full-height layout');

console.log('wiki knowledge tab style validation passed');