import assert from 'node:assert/strict';
import test from 'node:test';

import { SSEStreamParser } from '../../packages/webchat-core/src/sseParser';

test('buffers incomplete SSE data lines across chunks', () => {
  const parser = new SSEStreamParser();

  assert.deepEqual(parser.push('data: {"id":"1","content":"hel'), []);
  assert.deepEqual(parser.push('lo"}\n: keep-alive\ndata: plain text\n'), [
    { id: '1', content: 'hello' },
    'plain text',
  ]);
});

test('preserves split AG-UI text, tool, and run-finished events', () => {
  const parser = new SSEStreamParser();

  assert.deepEqual(parser.push('data: {"type":"TEXT_MESSAGE_CONTENT","delta":"hel'), []);
  assert.deepEqual(
    parser.push(
      'lo"}\ndata: {"type":"TOOL_CALL_START","toolCallId":"tool-1"}\ndata: {"type":"RUN_FIN'
    ),
    [
      { type: 'TEXT_MESSAGE_CONTENT', delta: 'hello' },
      { type: 'TOOL_CALL_START', toolCallId: 'tool-1' },
    ]
  );
  assert.deepEqual(parser.push('ISHED","threadId":"thread-1"}\n'), [
    { type: 'RUN_FINISHED', threadId: 'thread-1' },
  ]);
});

test('reset clears the incomplete-line buffer', () => {
  const parser = new SSEStreamParser();
  parser.push('data: {"partial":');
  parser.reset();
  assert.deepEqual(parser.push('data: {"ok":true}\n'), [{ ok: true }]);
});
