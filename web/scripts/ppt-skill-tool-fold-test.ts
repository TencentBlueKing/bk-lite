import assert from 'node:assert/strict';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { IntlProvider } from 'react-intl';

import { foldPptSkillToolCalls } from '../packages/chat-content/src/pptSkillToolFold';
import ToolCallGroup from '../src/app/opspilot/components/custom-chat-sse/ToolCallGroup';
import { renderAllToolCalls } from '../src/app/opspilot/components/custom-chat-sse/toolCallRenderer';

const copy = { name: 'PPT 技能', action: '写页面并导出' };

const commands = [
  'python /skills/ppt-master/scripts/project_manager.py init alarm-summary --quick',
  'python /skills/ppt-master/scripts/text_measure.py calibrate projects/alarm-summary',
  'python /skills/ppt-master/scripts/svg_quality_checker.py projects/alarm-summary',
  'ls ppt-workspace/projects/alarm-summary_20261123/svg_output',
  'ls ppt-workspace/projects/alarm-summary_20261123',
  'ls projects/alarm-summary_20261123',
  'ls projects/alarm-summary_20261123/svg_output',
  'ls -la /ppt-workspace/projects/alarm-summary_20261123/svg_output',
  'python /skills/ppt-master/scripts/svg_quality_checker.py /ppt-workspace/projects/alarm-summary',
  'python /skills/ppt-master/scripts/svg_to_pptx.py projects/alarm-summary_20261123',
];

const executes = commands.map((command, index) => ({
  id: `e${index}`,
  name: 'execute',
  args: JSON.stringify({ command }),
  status: 'completed' as const,
  result: command,
}));

const folded = foldPptSkillToolCalls(executes, copy);
assert.equal(folded.length, 1);
assert.equal(folded[0].name, 'PPT 技能');
assert.equal(JSON.parse(folded[0].args || '{}').action, '写页面并导出');
assert.equal(folded[0].result, undefined);
const packed = JSON.stringify(folded[0]);
for (const command of commands) {
  assert.equal(packed.includes(command), false);
}
assert.equal(packed.includes('project_manager.py'), false);
assert.equal(packed.includes('svg_to_pptx.py'), false);

const mixed = foldPptSkillToolCalls([
  { id: 'q', name: 'query_alerts', args: JSON.stringify({ query: 'active' }), status: 'completed' as const, result: '5' },
  executes[0],
  { id: 'w', name: 'write_file', args: JSON.stringify({ path: '/ppt-workspace/projects/demo/svg_output/01.svg' }), status: 'calling' as const },
  { id: 'other', name: 'execute', args: JSON.stringify({ command: 'ls /tmp' }), status: 'completed' as const, result: 'tmp' },
], copy);
assert.deepEqual(mixed.map((tool) => tool.name), ['query_alerts', 'PPT 技能']);
assert.equal(mixed[1].status, 'calling');
assert.equal(mixed[0].result, '5');
assert.equal(JSON.stringify(mixed).includes('ls /tmp'), false);

const alone = foldPptSkillToolCalls([
  { id: 'ls', name: 'execute', args: JSON.stringify({ command: 'ls /tmp' }), status: 'completed' as const },
], copy);
assert.equal(alone.length, 1);
assert.equal(alone[0].name, 'execute');

const failed = foldPptSkillToolCalls([
  executes[0],
  { id: 'bad', name: 'execute', args: JSON.stringify({ command: 'ls projects/alarm-summary_20261123' }), status: 'error' as const, result: '页面没有写出来' },
], copy);
assert.equal(failed.length, 1);
assert.equal(failed[0].status, 'error');
assert.equal(failed[0].result, '页面没有写出来');
assert.equal(JSON.stringify(failed[0]).includes('project_manager.py'), false);

const html = renderAllToolCalls(new Map(executes.map((tool) => [tool.id, tool])));
assert.equal(html.includes('已调用 1 个工具'), false);
assert.equal(html.includes('点击展开'), false);
assert.equal(html.includes('PPT 技能'), true);
assert.equal(html.includes('写页面并导出'), true);
assert.equal(html.includes('project_manager.py'), false);
assert.equal(html.includes('svg_to_pptx.py'), false);
assert.equal(html.includes('alarm-summary_20261123'), false);

const plain = renderAllToolCalls(new Map([
  ['1', { name: 'search', args: JSON.stringify({ query: 'nginx' }), status: 'completed' as const, result: '2' }],
  ['2', { name: 'analyze', args: JSON.stringify({ namespace: 'default' }), status: 'completed' as const, result: 'ok' }],
]));
assert.equal(plain.includes('已调用 2 个工具'), true);
assert.equal(plain.includes('search'), true);
assert.equal(plain.includes('PPT 技能'), false);

const markup = renderToStaticMarkup(
  React.createElement(
    IntlProvider,
    { locale: 'zh', messages: {} },
    React.createElement(ToolCallGroup, { toolCalls: executes, isStreaming: false }),
  ),
);
assert.equal(markup.includes('已调用 1 个工具'), false);
assert.equal(markup.includes('点击展开'), false);
assert.equal(markup.includes('PPT 技能 · 写页面并导出'), true);
assert.equal(markup.includes('project_manager.py'), false);
assert.equal(markup.includes('svg_to_pptx.py'), false);
assert.equal((markup.match(/PPT 技能/g) || []).length, 1);

console.log('ppt skill tool fold ok');
