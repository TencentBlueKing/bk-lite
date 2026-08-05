import assert from 'node:assert/strict';
import test from 'node:test';

import { normalizeWebChatConfig } from '../packages/webchat-core/src/config';
import type { WebChatConfig } from '../packages/webchat-core/src/types';
import type { FloatingButtonProps } from '../packages/webchat-ui/src/FloatingButton';
import { createFloatingButtonChatCallbacks } from '../packages/webchat-ui/src/floatingButtonCallbacks';

const typedConfig: WebChatConfig = {
  sseUrl: 'https://example.test/chat',
  socketUrl: 'https://legacy.example.test/chat',
  enableSSE: true,
  extensions: {
    pluginMode: 'compact',
  },
};
void typedConfig;

const floatingButtonConfig: FloatingButtonProps = {
  sseUrl: 'https://example.test/chat',
  apiKey: 'placeholder',
  onMessageReceived: () => undefined,
};
void floatingButtonConfig;

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
