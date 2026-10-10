import assert from 'node:assert/strict';
import test from 'node:test';

import { completedToolResult, rememberToolCall } from '../packages/webchat-ui/src/toolResultForward.ts';

test('forwards a finished tool result with the name from tool start', () => {
  const names = new Map();
  rememberToolCall(names, 'call-1', 'prepare_dashboard_proposal');
  assert.deepEqual(completedToolResult(names, 'call-1', '{"success":true}'), {
    toolCallId: 'call-1',
    toolCallName: 'prepare_dashboard_proposal',
    content: '{"success":true}',
  });
});

test('ignores a result whose tool name was never recorded', () => {
  assert.equal(completedToolResult(new Map(), 'call-2', '{}'), null);
});
