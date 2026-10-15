import assert from 'node:assert/strict';
import test from 'node:test';

import {
  dispatchCompletedToolResult,
  registerToolResultHandler,
  resetToolResultHandlersForTests,
} from '../registry';

test('dispatches a completed tool result only to handlers of that tool', () => {
  resetToolResultHandlersForTests();
  const seen: string[] = [];
  const unsubscribe = registerToolResultHandler('prepare_dashboard_proposal', (result) => {
    seen.push(result.toolCallId);
  });
  registerToolResultHandler('search_data_sources', () => {
    seen.push('search');
  });

  dispatchCompletedToolResult({
    toolCallId: 'call-1',
    toolCallName: 'prepare_dashboard_proposal',
    content: '{}',
  });
  unsubscribe();
  dispatchCompletedToolResult({
    toolCallId: 'call-2',
    toolCallName: 'prepare_dashboard_proposal',
    content: '{}',
  });

  assert.deepEqual(seen, ['call-1']);
});
