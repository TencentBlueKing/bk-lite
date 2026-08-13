import assert from 'node:assert/strict';
import test from 'node:test';

import { normalizeWebChatConfig } from '../packages/webchat-core/src/config';
import type { WebChatConfig } from '../packages/webchat-core/src/types';
import { AGUIHandler } from '../packages/webchat-ui/src/agui';
import { createFloatingButtonChatCallbacks } from '../packages/webchat-ui/src/floatingButtonCallbacks';
import { parseLegacyMessage } from '../packages/webchat-ui/src/legacyMessage';

const typedConfig: WebChatConfig = {
  sseUrl: 'https://example.test/chat',
  socketUrl: 'https://legacy.example.test/chat',
  enableSSE: true,
  extensions: {
    pluginMode: 'compact',
  },
};
void typedConfig;

// @ts-expect-error Unknown integration options must be nested under extensions.
const invalidTopLevelConfig: WebChatConfig = { pluginMode: 'compact' };
void invalidTopLevelConfig;

// @ts-expect-error The normalization API must also reject unknown top-level options.
normalizeWebChatConfig({ sseUrl: 'https://example.test/chat', pluginMode: 'compact' });

test('normalizes the documented legacy socketUrl to the active SSE endpoint', () => {
  const legacyConfig: WebChatConfig = {
    socketUrl: 'https://legacy.example.test/chat',
    enableSSE: true,
    reconnectAttempts: 3,
  };

  const normalized = normalizeWebChatConfig(legacyConfig);

  assert.equal(normalized.sseUrl, 'https://legacy.example.test/chat');
  assert.equal('socketUrl' in normalized, false);
  assert.equal('enableSSE' in normalized, false);
  assert.equal('reconnectAttempts' in normalized, false);
  assert.equal(legacyConfig.socketUrl, 'https://legacy.example.test/chat');
});

test('prefers sseUrl and keeps named extensions isolated', () => {
  const normalized = normalizeWebChatConfig({
    sseUrl: 'https://example.test/chat',
    socketUrl: 'https://legacy.example.test/chat',
    extensions: {
      pluginMode: 'compact',
    },
  });

  assert.equal(normalized.sseUrl, 'https://example.test/chat');
  assert.deepEqual(normalized.extensions, {
    pluginMode: 'compact',
  });
  assert.equal('pluginMode' in normalized, false);
});

test('preserves unknown top-level keys passed by untyped JavaScript integrations', () => {
  const javascriptConfig = {
    socketUrl: 'https://legacy.example.test/chat',
    pluginMode: 'compact',
  } as WebChatConfig & { pluginMode: string };

  const normalized = normalizeWebChatConfig(javascriptConfig) as Record<string, unknown>;

  assert.equal(normalized.sseUrl, 'https://legacy.example.test/chat');
  assert.equal(normalized.pluginMode, 'compact');
});

test('forwards floating-button callbacks without hiding Chat callbacks', () => {
  const states: string[] = [];
  const closeOrder: string[] = [];
  const callbacks = createFloatingButtonChatCallbacks({
    onChatStateChange: (state) => states.push(`chat:${state}`),
    onStateChange: (state) => states.push(`fallback:${state}`),
    onClose: () => closeOrder.push('consumer'),
    close: () => closeOrder.push('floating-button'),
  });

  callbacks.onStateChange?.('chatting');
  callbacks.onClose?.();

  assert.deepEqual(states, ['chat:chatting']);
  assert.deepEqual(closeOrder, ['consumer', 'floating-button']);
});

test('falls back to Chat onStateChange when the floating alias is absent', () => {
  const states: string[] = [];
  const callbacks = createFloatingButtonChatCallbacks({
    onStateChange: (state) => states.push(state),
    close: () => undefined,
  });

  callbacks.onStateChange?.('connected');

  assert.deepEqual(states, ['connected']);
});

test('rejects malformed AG-UI payloads before they reach event subscribers', () => {
  const handler = new AGUIHandler();
  const events: unknown[] = [];
  const legacyMessages: unknown[] = [];
  const subscription = handler.getEventStream().subscribe((event) => events.push(event));
  const malformed = {
    type: 'TEXT_MESSAGE_CONTENT',
    messageId: 'message-1',
    delta: {},
    content: 'must not reach the legacy renderer',
  };

  const result = handler.processSSEData(malformed);
  if (result.type === 'legacy-message' && result.message) {
    legacyMessages.push(result.message);
  }

  assert.deepEqual(result, { type: 'ignored' });
  assert.deepEqual(events, []);
  assert.deepEqual(legacyMessages, []);
  subscription.unsubscribe();
  handler.destroy();
});

test('fails closed for future protocol events and malformed legacy metadata', () => {
  const handler = new AGUIHandler();
  const futureProtocolEvent = {
    type: 'TEXT_MESSAGE_FUTURE',
    content: 'must not reach the legacy renderer',
  };
  const malformedLegacyMessage = {
    type: 'text',
    content: 'unsafe chunks',
    metadata: { contentChunks: 'not-an-array' },
  };

  assert.deepEqual(handler.processSSEData(futureProtocolEvent), { type: 'ignored' });
  assert.deepEqual(handler.processSSEData(malformedLegacyMessage), { type: 'ignored' });
  assert.equal(parseLegacyMessage(futureProtocolEvent), null);
  assert.equal(parseLegacyMessage(malformedLegacyMessage), null);
  handler.destroy();
});

test('passes only validated legacy messages to the fallback renderer', () => {
  const handler = new AGUIHandler();
  const legacyMessage = {
    id: 'legacy-message-1',
    type: 'text',
    content: 'legacy content',
    metadata: {
      contentChunks: [{ type: 'text', content: 'legacy content' }],
    },
  };

  assert.deepEqual(handler.processSSEData(legacyMessage), {
    type: 'legacy-message',
    message: legacyMessage,
  });
  assert.deepEqual(parseLegacyMessage(legacyMessage), legacyMessage);
  handler.destroy();
});

test('accepts schema-valid content and chunk AG-UI events', () => {
  const handler = new AGUIHandler();
  const events: string[] = [];
  const subscription = handler.getEventStream().subscribe((event) => events.push(event.type));

  const contentResult = handler.processSSEData({
    type: 'TEXT_MESSAGE_CONTENT',
    messageId: 'message-1',
    delta: 'hello',
  });
  const chunkResult = handler.processSSEData({
    type: 'TEXT_MESSAGE_CHUNK',
    messageId: 'message-1',
    delta: ' world',
  });

  assert.equal(contentResult.type, 'agui-event');
  assert.equal(chunkResult.type, 'agui-event');
  assert.deepEqual(events, ['TEXT_MESSAGE_CONTENT', 'TEXT_MESSAGE_CHUNK']);
  subscription.unsubscribe();
  handler.destroy();
});

test('normalizes the documented legacy RUN_FINISHED event for typed consumers', () => {
  const handler = new AGUIHandler();
  const events: unknown[] = [];
  const subscription = handler.getEventStream().subscribe((event) => events.push(event));

  const result = handler.processSSEData({
    type: 'RUN_FINISHED',
    timestamp: 1234567890,
  });

  assert.equal(result.type, 'agui-event');
  assert.deepEqual(events, [
    {
      type: 'RUN_FINISHED',
      threadId: 'legacy',
      runId: 'legacy',
      timestamp: 1234567890,
    },
  ]);
  subscription.unsubscribe();
  handler.destroy();
});
