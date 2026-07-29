import assert from 'node:assert/strict';
import test from 'node:test';

import { SSEHandler } from '../../packages/webchat-core/src/sse';
import type {
  Message,
  MessageEvent as WebChatMessageEvent,
} from '../../packages/webchat-core/src/types';

function streamResponse(chunks: string[]): Response {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(encoder.encode(chunk));
      }
      controller.close();
    },
  });

  return {
    body,
    ok: true,
    status: 200,
  } as Response;
}

test('parses split SSE data lines and ignores keep-alive comments', async () => {
  const originalFetch = globalThis.fetch;
  const messages: Message[] = [];

  globalThis.fetch = async (input, init) => {
    assert.equal(input, 'https://example.test/stream');
    assert.equal(init?.headers && 'Authorization' in init.headers, true);
    return streamResponse([
      'data: {"id":"message-1","content":"hel',
      'lo","sender":"bot"}\n: keep-alive\n',
      'data: plain text\n',
    ]);
  };

  const handler = new SSEHandler(0, 0);
  handler.on('message', (event: WebChatMessageEvent) => {
    messages.push(event.message);
  });

  try {
    await handler.connect('https://example.test/stream', {
      Authorization: 'Bearer placeholder',
    });
    assert.equal(messages.length, 2);
    assert.equal(messages[0].id, 'message-1');
    assert.equal(messages[0].content, 'hello');
    assert.equal(messages[1].content, 'plain text');
  } finally {
    handler.destroy();
    globalThis.fetch = originalFetch;
  }
});

test('retries a failed fetch connection once before succeeding', async () => {
  const originalFetch = globalThis.fetch;
  const originalError = console.error;
  let attempts = 0;
  let opens = 0;

  console.error = () => undefined;
  globalThis.fetch = async () => {
    attempts += 1;
    if (attempts === 1) {
      throw new Error('temporary connection failure');
    }
    return streamResponse([]);
  };

  const handler = new SSEHandler(1, 0);
  handler.on('open', () => {
    opens += 1;
  });

  try {
    await handler.connect('https://example.test/stream', {
      Authorization: 'Bearer placeholder',
    });
    assert.equal(attempts, 2);
    assert.equal(opens, 1);
  } finally {
    handler.destroy();
    console.error = originalError;
    globalThis.fetch = originalFetch;
  }
});
