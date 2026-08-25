import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath, pathToFileURL } from 'node:url';

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const { buildSync } = createRequire(path.join(rootDir, 'packages/webchat-ui/package.json'))('esbuild');
const sourcePath = path.join(rootDir, 'packages/webchat-ui/src/aguiEventHandler.ts');
const outputDir = fs.mkdtempSync(path.join(os.tmpdir(), 'webchat-agui-events-'));
const outputPath = path.join(outputDir, 'aguiEventHandler.mjs');

buildSync({
  entryPoints: [sourcePath],
  bundle: true,
  platform: 'node',
  format: 'esm',
  outfile: outputPath,
  alias: {
    '@webchat/core': path.join(rootDir, 'packages/webchat-core/src/index.ts'),
  },
});
process.on('exit', () => fs.rmSync(outputDir, { recursive: true, force: true }));

const { createAGUIEventHandler, shouldShowTypingPlaceholder } = await import(pathToFileURL(outputPath));

function createHarness({ batching = true } = {}) {
  let nextFrameId = 0;
  const frames = new Map();
  let messages = [];
  let messageUpdates = 0;
  let saves = 0;
  let persistedSession = null;
  let isLoading = false;
  let isThinking = false;
  const streamingTextBatchingRef = { current: batching };
  const session = {
    sessionId: 'session-1',
    messages: [],
    startTime: 1,
    lastActivityTime: 1,
  };
  const sessionManager = {
    getSession: () => session,
    addMessage: (message) => session.messages.push(message),
    saveSession: () => {
      saves += 1;
      persistedSession = structuredClone(session);
    },
  };
  const setMessages = (next) => {
    messageUpdates += 1;
    messages = typeof next === 'function' ? next(messages) : next;
  };
  const dispatch = createAGUIEventHandler({
    currentMessageIdRef: { current: null },
    streamingContentRef: { current: '' },
    sessionManagerRef: { current: sessionManager },
    stateMachineRef: { current: { transitionToChatting() {}, transition() {} } },
    onMessageReceivedRef: { current: undefined },
    setMessages,
    setIsLoading(next) {
      isLoading = typeof next === 'function' ? next(isLoading) : next;
    },
    setIsThinking(next) {
      isThinking = typeof next === 'function' ? next(isThinking) : next;
    },
    addMessage(message) {
      setMessages((current) => [...current, message]);
      sessionManager.addMessage(message);
    },
    frameScheduler: {
      schedule(callback) {
        const id = ++nextFrameId;
        frames.set(id, callback);
        return id;
      },
      cancel(id) {
        frames.delete(id);
      },
    },
    streamingTextBatchingRef,
  });
  return {
    dispatch,
    runFrame() {
      const queued = [...frames.values()];
      frames.clear();
      queued.forEach((callback) => callback());
    },
    get messages() {
      return messages;
    },
    get session() {
      return session;
    },
    get messageUpdates() {
      return messageUpdates;
    },
    get saves() {
      return saves;
    },
    get persistedSession() {
      return persistedSession;
    },
    setBatching(enabled) {
      streamingTextBatchingRef.current = enabled;
    },
    get isLoading() {
      return isLoading;
    },
    get isThinking() {
      return isThinking;
    },
  };
}

test('AG-UI content events coalesce and END persists the complete text', () => {
  const harness = createHarness();
  harness.dispatch({ type: 'TEXT_MESSAGE_START', role: 'assistant' });
  const updatesAfterStart = harness.messageUpdates;

  for (let index = 0; index < 200; index += 1) {
    harness.dispatch({ type: 'TEXT_MESSAGE_CONTENT', delta: String(index) });
  }

  assert.equal(harness.messageUpdates, updatesAfterStart);
  harness.dispatch({ type: 'TEXT_MESSAGE_END' });
  assert.equal(harness.messageUpdates, updatesAfterStart + 1);
  assert.equal(harness.messages[0].content, Array.from({ length: 200 }, (_, i) => String(i)).join(''));
  assert.equal(harness.session.messages[0].content, harness.messages[0].content);
  assert.equal(harness.saves, 1);
  harness.runFrame();
  assert.equal(harness.messageUpdates, updatesAfterStart + 1);
});

test('tool start flushes text before appending the tool chunk', () => {
  const harness = createHarness();
  harness.dispatch({ type: 'TEXT_MESSAGE_START', role: 'assistant' });
  harness.dispatch({ type: 'TEXT_MESSAGE_CONTENT', delta: 'before tool' });
  harness.dispatch({ type: 'TOOL_CALL_START', toolCallId: 'tool-1', toolCallName: 'search' });

  assert.deepEqual(
    harness.messages[0].metadata.contentChunks.map((chunk) => chunk.type),
    ['text', 'toolCalls']
  );
  assert.deepEqual(
    harness.session.messages[0].metadata.contentChunks.map((chunk) => chunk.type),
    ['text', 'toolCalls']
  );
});

test('text after a tool starts a new chunk without repeating the prior segment', () => {
  const harness = createHarness();
  harness.dispatch({ type: 'TEXT_MESSAGE_START', role: 'assistant' });
  harness.dispatch({ type: 'TEXT_MESSAGE_CONTENT', delta: 'before' });
  harness.dispatch({ type: 'TOOL_CALL_START', toolCallId: 'tool-1', toolCallName: 'search' });
  harness.dispatch({ type: 'TOOL_CALL_ARGS', toolCallId: 'tool-1', delta: '{"q":"x"}' });
  harness.dispatch({ type: 'TOOL_CALL_END', toolCallId: 'tool-1' });
  harness.dispatch({ type: 'TOOL_CALL_RESULT', toolCallId: 'tool-1', content: 'found' });
  harness.dispatch({ type: 'TEXT_MESSAGE_CONTENT', delta: 'after' });
  harness.dispatch({ type: 'TEXT_MESSAGE_END' });

  const expectedChunks = [
    { type: 'text', content: 'before' },
    {
      type: 'toolCalls',
      toolCalls: [
        {
          id: 'tool-1',
          name: 'search',
          args: '{"q":"x"}',
          result: 'found',
          status: 'completed',
        },
      ],
    },
    { type: 'text', content: 'after' },
  ];
  assert.deepEqual(harness.messages[0].metadata.contentChunks, expectedChunks);
  assert.deepEqual(harness.session.messages[0].metadata.contentChunks, expectedChunks);
  assert.equal(harness.messages[0].content, 'beforeafter');
  assert.equal(harness.session.messages[0].content, 'beforeafter');
});

test('a new run preserves the partial response equally in both modes', () => {
  const replay = (batching) => {
    const harness = createHarness({ batching });
    harness.dispatch({ type: 'TEXT_MESSAGE_START', role: 'assistant' });
    harness.dispatch({ type: 'TEXT_MESSAGE_CONTENT', delta: 'partial' });
    harness.dispatch({ type: 'RUN_STARTED' });
    const updatesAtBoundary = harness.messageUpdates;
    harness.runFrame();
    return {
      message: harness.messages[0].content,
      session: harness.session.messages[0].content,
      updatesAtBoundary,
      updatesAfterLateFrame: harness.messageUpdates,
    };
  };

  assert.deepEqual(replay(true), replay(false));
});

test('RUN_ERROR flushes the complete error text before persisting', () => {
  const harness = createHarness();
  harness.dispatch({ type: 'TEXT_MESSAGE_START', role: 'assistant' });
  harness.dispatch({ type: 'TEXT_MESSAGE_CONTENT', delta: 'partial' });
  harness.dispatch({ type: 'RUN_ERROR', message: 'network failed' });

  assert.equal(
    harness.messages[0].content,
    'partial\n\n❌ **错误**: network failed'
  );
  assert.equal(harness.session.messages[0].content, harness.messages[0].content);
  assert.equal(harness.saves, 1);
});

test('TEXT_MESSAGE_CHUNK uses the same frame and persistence contract', () => {
  const harness = createHarness();
  harness.dispatch({ type: 'TEXT_MESSAGE_CHUNK', role: 'assistant', delta: 'a' });
  harness.dispatch({ type: 'TEXT_MESSAGE_CHUNK', role: 'assistant', delta: 'b' });

  assert.equal(harness.messages[0].content, '');
  harness.dispatch({ type: 'RUN_FINISHED' });

  assert.equal(harness.messages[0].content, 'ab');
  assert.equal(harness.session.messages[0].content, 'ab');
  assert.equal(harness.saves, 1);
});

test('Chat stop or network-error flush persists pending text before a late frame', () => {
  const harness = createHarness();
  harness.dispatch({ type: 'TEXT_MESSAGE_START', role: 'assistant' });
  harness.dispatch({ type: 'TEXT_MESSAGE_CONTENT', delta: 'partial' });

  harness.dispatch.flushPendingText();
  harness.runFrame();

  assert.equal(harness.messages[0].content, 'partial');
  assert.equal(harness.session.messages[0].content, 'partial');
  assert.equal(harness.saves, 1);
  assert.equal(harness.persistedSession.messages[0].content, 'partial');
});

test('Chat clear or unmount cancellation prevents stale pending writes', () => {
  const harness = createHarness();
  harness.dispatch({ type: 'TEXT_MESSAGE_START', role: 'assistant' });
  harness.dispatch({ type: 'TEXT_MESSAGE_CONTENT', delta: 'stale' });

  harness.dispatch.cancelPendingText();
  harness.session.messages.length = 0;
  harness.runFrame();

  assert.equal(harness.messages[0].content, '');
  assert.deepEqual(harness.session.messages, []);
  assert.equal(harness.saves, 0);
});

test('runtime rollback restores immediate commits while preserving final text', () => {
  const harness = createHarness();
  harness.dispatch({ type: 'TEXT_MESSAGE_START', role: 'assistant' });
  const updatesAfterStart = harness.messageUpdates;
  harness.dispatch({ type: 'TEXT_MESSAGE_CONTENT', delta: 'a' });
  harness.setBatching(false);
  harness.dispatch({ type: 'TEXT_MESSAGE_CONTENT', delta: 'b' });

  assert.equal(harness.messageUpdates, updatesAfterStart + 1);
  assert.equal(harness.messages[0].content, 'ab');
  assert.equal(harness.session.messages[0].content, 'ab');
  harness.runFrame();
  assert.equal(harness.messageUpdates, updatesAfterStart + 1);
});

test('BK-Lite THINKING deltas accumulate on the bot message instead of being dropped', () => {
  const harness = createHarness();
  harness.dispatch({ type: 'RUN_STARTED' });
  harness.dispatch({ type: 'THINKING', delta: 'Guang' });
  harness.dispatch({ type: 'THINKING', delta: 'zhou' });

  assert.equal(harness.isThinking, true);
  assert.equal(harness.messages[0].sender, 'bot');
  assert.equal(harness.messages[0].metadata.thinking, 'Guangzhou');
  assert.equal(harness.messages[0].metadata.isThinking, true);
  assert.equal(harness.session.messages[0].metadata.thinking, 'Guangzhou');
});

test('answer tokens keep thinking text but stop the typing placeholder', () => {
  const harness = createHarness();
  harness.dispatch({ type: 'RUN_STARTED' });
  harness.dispatch({ type: 'THINKING', delta: 'plan the answer' });
  assert.equal(shouldShowTypingPlaceholder(harness.isLoading, harness.isThinking, harness.messages), false);

  harness.dispatch({ type: 'TEXT_MESSAGE_START', role: 'assistant' });
  harness.dispatch({ type: 'TEXT_MESSAGE_CONTENT', delta: '广州是广东省省会' });
  harness.runFrame();
  harness.dispatch({ type: 'RUN_FINISHED' });

  assert.equal(harness.isThinking, false);
  assert.equal(harness.isLoading, false);
  assert.equal(harness.messages[0].content, '广州是广东省省会');
  assert.equal(harness.messages[0].metadata.thinking, 'plan the answer');
  assert.equal(harness.messages[0].metadata.isThinking, false);
  assert.equal(shouldShowTypingPlaceholder(harness.isLoading, harness.isThinking, harness.messages), false);
});

test('typing placeholder only shows while waiting for the first bot message', () => {
  assert.equal(shouldShowTypingPlaceholder(true, false, [{ sender: 'user' }]), true);
  assert.equal(shouldShowTypingPlaceholder(true, true, [{ sender: 'user' }]), true);
  assert.equal(
    shouldShowTypingPlaceholder(true, false, [{ sender: 'user' }, { sender: 'bot' }]),
    false
  );
  assert.equal(shouldShowTypingPlaceholder(false, false, [{ sender: 'user' }]), false);
});

test('batched and immediate modes produce the same final message and session', () => {
  const replay = (batching) => {
    const harness = createHarness({ batching });
    harness.dispatch({ type: 'TEXT_MESSAGE_START', role: 'assistant' });
    harness.dispatch({ type: 'TEXT_MESSAGE_CONTENT', delta: 'before' });
    harness.dispatch({
      type: 'TOOL_CALL_START',
      toolCallId: 'tool-1',
      toolCallName: 'search',
    });
    harness.dispatch({ type: 'TOOL_CALL_END', toolCallId: 'tool-1' });
    harness.dispatch({ type: 'TEXT_MESSAGE_CHUNK', role: 'assistant', delta: 'after' });
    harness.dispatch({ type: 'RUN_FINISHED' });
    const withoutRuntimeFields = ({ id: _id, timestamp: _timestamp, ...message }) => message;
    return {
      messages: harness.messages.map(withoutRuntimeFields),
      sessionMessages: harness.session.messages.map(withoutRuntimeFields),
    };
  };

  assert.deepEqual(replay(true), replay(false));
});
