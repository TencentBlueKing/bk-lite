import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { buildSync } from 'esbuild';

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const sourcePath = path.join(rootDir, 'packages/webchat-ui/src/aguiEventHandler.ts');
const outputDir = fs.mkdtempSync(path.join(os.tmpdir(), 'webchat-agui-events-'));
const outputPath = path.join(outputDir, 'aguiEventHandler.mjs');

buildSync({
  entryPoints: [sourcePath],
  bundle: true,
  platform: 'node',
  format: 'esm',
  outfile: outputPath,
});
process.on('exit', () => fs.rmSync(outputDir, { recursive: true, force: true }));

const { createAGUIEventHandler } = await import(pathToFileURL(outputPath));

function createHarness() {
  let nextFrameId = 0;
  const frames = new Map();
  let messages = [];
  let messageUpdates = 0;
  let saves = 0;
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
    setIsLoading() {},
    setIsThinking() {},
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

test('a new run cancels stale pending text from the previous run', () => {
  const harness = createHarness();
  harness.dispatch({ type: 'TEXT_MESSAGE_START', role: 'assistant' });
  harness.dispatch({ type: 'TEXT_MESSAGE_CONTENT', delta: 'stale' });
  harness.dispatch({ type: 'RUN_STARTED' });
  harness.runFrame();

  assert.equal(harness.messages[0].content, '');
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
