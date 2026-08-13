import assert from 'node:assert/strict';
import test from 'node:test';

import { SSEHandler } from '../../packages/webchat-core/src/sse';
import type {
  Message,
  MessageEvent as WebChatMessageEvent,
} from '../../packages/webchat-core/src/types';

/** Build a streaming fetch response from the supplied text chunks. */
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

class FakeEventSource {
  static instances: FakeEventSource[] = [];

  public onopen: (() => void) | null = null;
  public onmessage: ((event: { data: string }) => void) | null = null;
  public onerror: ((error: unknown) => void) | null = null;
  public closed = false;

  constructor(public readonly url: string) {
    FakeEventSource.instances.push(this);
  }

  close(): void {
    this.closed = true;
  }

  static reset(): void {
    FakeEventSource.instances = [];
  }
}

function installFakeEventSource(): () => void {
  const originalEventSource = globalThis.EventSource;
  FakeEventSource.reset();
  globalThis.EventSource = FakeEventSource as unknown as typeof EventSource;
  return () => {
    globalThis.EventSource = originalEventSource;
  };
}

function wait(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
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

test('fetch reconnect respects its retry budget and resets it only after opening', async () => {
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
    if (attempts === 2) {
      const body = new ReadableStream<Uint8Array>({
        start(controller) {
          controller.error(new Error('stream disconnected after opening'));
        },
      });
      return { body, ok: true, status: 200 } as Response;
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
    assert.equal(attempts, 3);
    assert.equal(opens, 2);

    let terminalAttempts = 0;
    globalThis.fetch = async () => {
      terminalAttempts += 1;
      throw new Error('persistent connection failure');
    };
    await handler.connect('https://example.test/stream', {
      Authorization: 'Bearer placeholder',
    });
    assert.equal(terminalAttempts, 2);
  } finally {
    handler.destroy();
    console.error = originalError;
    globalThis.fetch = originalFetch;
  }
});

test('disconnect cancels a queued EventSource reconnect', async () => {
  const restoreEventSource = installFakeEventSource();
  const originalError = console.error;
  const originalLog = console.log;
  const originalClearTimeout = globalThis.clearTimeout;
  let clearedReconnectTimers = 0;
  console.error = () => undefined;
  console.log = () => undefined;
  globalThis.clearTimeout = ((timer: ReturnType<typeof setTimeout>) => {
    clearedReconnectTimers += 1;
    originalClearTimeout(timer);
  }) as typeof clearTimeout;
  const handler = new SSEHandler(1, 10);

  try {
    void handler.connect('https://example.test/stream');
    assert.equal(FakeEventSource.instances.length, 1);

    FakeEventSource.instances[0].onerror?.(new Error('temporary connection failure'));
    handler.disconnect();
    await wait(30);

    assert.equal(FakeEventSource.instances.length, 1);
    assert.equal(clearedReconnectTimers, 1);
  } finally {
    handler.destroy();
    restoreEventSource();
    console.error = originalError;
    console.log = originalLog;
    globalThis.clearTimeout = originalClearTimeout;
  }
});

test('disconnect cancels a queued fetch reconnect', async () => {
  const originalFetch = globalThis.fetch;
  const originalError = console.error;
  const originalClearTimeout = globalThis.clearTimeout;
  let attempts = 0;
  let clearedReconnectTimers = 0;
  console.error = () => undefined;
  globalThis.fetch = async () => {
    attempts += 1;
    throw new Error('temporary connection failure');
  };
  globalThis.clearTimeout = ((timer: ReturnType<typeof setTimeout>) => {
    clearedReconnectTimers += 1;
    originalClearTimeout(timer);
  }) as typeof clearTimeout;
  const handler = new SSEHandler(1, 10);

  try {
    const connecting = handler.connect('https://example.test/stream', {
      Authorization: 'Bearer placeholder',
    });
    await wait(0);
    handler.disconnect();
    await connecting;
    await wait(20);

    assert.equal(attempts, 1);
    assert.equal(clearedReconnectTimers, 1);

    const signals: AbortSignal[] = [];
    const resolveResponses: Array<(response: Response) => void> = [];
    const messages: Message[] = [];
    handler.on('message', (event: WebChatMessageEvent) => messages.push(event.message));
    globalThis.fetch = async (_input, init) => {
      signals.push(init?.signal as AbortSignal);
      return new Promise<Response>((resolve) => resolveResponses.push(resolve));
    };
    void handler.connect('https://example.test/first', { Authorization: 'first' });
    void handler.connect('https://example.test/second', { Authorization: 'second' });
    assert.equal(signals[0].aborted, true);
    assert.equal(signals[1].aborted, false);
    resolveResponses[0](streamResponse(['data: stale response\n']));
    await wait(0);
    assert.equal(messages.length, 0);
  } finally {
    handler.destroy();
    globalThis.fetch = originalFetch;
    console.error = originalError;
    globalThis.clearTimeout = originalClearTimeout;
  }
});

test('EventSource reconnect closes and isolates the superseded connection', async () => {
  const restoreEventSource = installFakeEventSource();
  const originalError = console.error;
  const originalLog = console.log;
  console.error = () => undefined;
  console.log = () => undefined;
  const handler = new SSEHandler(1, 0);
  const messages: Message[] = [];
  let opens = 0;
  handler.on('message', (event: WebChatMessageEvent) => {
    messages.push(event.message);
  });
  handler.on('open', () => {
    opens += 1;
  });

  try {
    void handler.connect('https://example.test/stream');
    const firstSource = FakeEventSource.instances[0];
    void handler.connect('https://example.test/replacement');
    const secondSource = FakeEventSource.instances[1];

    assert.equal(firstSource.closed, true);
    assert.equal(FakeEventSource.instances.length, 2);

    firstSource.onopen?.();
    firstSource.onmessage?.({ data: 'stale message' });
    secondSource.onmessage?.({ data: 'current message' });

    assert.equal(opens, 0);
    assert.deepEqual(
      messages.map((message) => message.content),
      ['current message']
    );

    secondSource.onerror?.(new Error('temporary connection failure'));
    await wait(0);
    assert.equal(FakeEventSource.instances.length, 3);

    secondSource.onopen?.();
    FakeEventSource.instances[2].onerror?.(new Error('retry budget exhausted'));
    await wait(0);
    assert.equal(FakeEventSource.instances.length, 3);

    void handler.connect('https://example.test/stream');
    FakeEventSource.instances[3].onerror?.(new Error('temporary connection failure'));
    await wait(0);
    FakeEventSource.instances[4].onopen?.();
    FakeEventSource.instances[4].onerror?.(new Error('failure after successful reconnect'));
    await wait(0);

    assert.equal(opens, 1);
    assert.equal(FakeEventSource.instances.length, 6);
  } finally {
    handler.destroy();
    restoreEventSource();
    console.error = originalError;
    console.log = originalLog;
  }
});
