import assert from 'node:assert/strict';

import { finalizePendingToolCalls } from '../src/app/opspilot/components/custom-chat-sse/aguiMessageHandler';
import { ToolCallInfo } from '../src/app/opspilot/components/custom-chat-sse/toolCallRenderer';

const calls = new Map<string, ToolCallInfo>([
  ['tool-a', { name: 'execute', args: '{"command":"echo ok"}', status: 'calling' }],
  ['tool-b', { name: 'agent_browser_inspect', args: '{}', status: 'completed', result: 'ok' }],
]);

const changed = finalizePendingToolCalls(calls, '工具调用已结束，但未收到结果事件。');

assert.equal(changed, true, 'finalization should report when pending calls were changed');
assert.equal(calls.get('tool-a')?.status, 'completed', 'pending tool call should be finalized');
assert.match(calls.get('tool-a')?.result || '', /未收到结果事件/, 'finalized tool should explain why no result is shown');
assert.equal(calls.get('tool-b')?.result, 'ok', 'completed tool result should be preserved');

const changedAgain = finalizePendingToolCalls(calls, 'unused');
assert.equal(changedAgain, false, 'already finalized calls should not report another change');
