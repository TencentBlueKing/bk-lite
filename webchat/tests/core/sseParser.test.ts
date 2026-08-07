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

test('reset clears the incomplete-line buffer', () => {
  const parser = new SSEStreamParser();
  parser.push('data: {"partial":');
  parser.reset();
  assert.deepEqual(parser.push('data: {"ok":true}\n'), [{ ok: true }]);
});
