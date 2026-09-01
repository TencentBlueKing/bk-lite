import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { build } from 'esbuild';

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const sourcePath = path.join(rootDir, 'packages/webchat-ui/src/Chat.tsx');
const outputDir = fs.mkdtempSync(path.join(rootDir, '.test-chat-boundaries-'));
const outputPath = path.join(outputDir, 'Chat.mjs');

const virtualModules = new Map([
  [
    '@webchat/core',
    `export class SessionManager {
      constructor(config) { this.config = config; this.session = null; globalThis.__chatTest.sessionManager = this; }
      initSession() { return this.session ||= { sessionId: 's', messages: [] }; }
      getSession() { return this.session; }
      addMessage(message) { this.session.messages.push(message); }
      saveSession() { this.saveCount = (this.saveCount || 0) + 1; this.saved = structuredClone(this.session); }
      clearSession() { this.session = null; }
    }
    export class StateMachine { on() { return () => {}; } transition() {} transitionToChatting() {} destroy() {} }
    export class SSEStreamParser { push() { return []; } }
    export const normalizeWebChatConfig = (config) => config;
    export const isSilentCustomEvent = () => false;
    export const parseLlmContextUsage = () => null;
    export const contextUsagePercent = () => 0;
    export const formatContextTokens = (tokens) => String(tokens);
    let nextId = 0;
    export const generateId = () => 'message-' + ++nextId;`,
  ],
  [
    '@ant-design/x',
    `import React from 'react';
    export const Bubble = () => React.createElement('div');
    export const Sender = (props) => React.createElement(
      React.Fragment,
      null,
      React.createElement('button', { 'data-test': 'stop', onClick: props.onCancel }, 'stop'),
      React.createElement('button', { 'data-test': 'submit', onClick: () => props.onSubmit('hi') }, 'submit')
    );`,
  ],
  [
    './agui',
    `export class AGUIHandler {
      constructor() { globalThis.__chatTest.agui = this; }
      getEventStream() { return { subscribe: (callback) => { this.callback = callback; return { unsubscribe() {} }; } }; }
      emit(event) { this.callback(event); }
      processSSEData() { return { type: 'ignored' }; }
      destroy() {}
    }`,
  ],
  [
    './components/MessageBubble',
    `import React from 'react'; export const MessageBubble = ({ message }) => React.createElement('div', { 'data-message': message.id }, String(message.content));`,
  ],
  [
    './components/ConfirmDialog',
    `import React from 'react'; export const ConfirmDialog = ({ isOpen, onConfirm }) => isOpen ? React.createElement('button', { 'data-test': 'confirm-clear', onClick: onConfirm }, 'confirm') : null;`,
  ],
  [
    './components/ContextUsageRing',
    `import React from 'react'; export default function ContextUsageRing() { return null; }`,
  ],
  [
    './components/PillComposer',
    `import React from 'react'; export const PillComposer = (props) => React.createElement(
      React.Fragment,
      null,
      React.createElement('button', { 'data-test': 'stop', onClick: props.onCancel }, 'stop'),
      React.createElement('button', { 'data-test': 'submit', onClick: () => props.onSubmit('hi') }, 'submit')
    );`,
  ],
  [
    './hooks/useMessageHandlers',
    `export const useMessageHandlers = () => ({ handleRegenerate() {}, handleCopy() {}, handleDelete() {} });`,
  ],
  [
    './streamLifecycle',
    `export class StreamLifecycle {
      mount() {}
      begin() { return {}; }
      cancel() { return Promise.resolve(); }
      dispose() { return Promise.resolve(); }
    }
    export const isAbortError = (error) => error?.name === 'AbortError';
    export const toError = (error) => error instanceof Error ? error : new Error(String(error));
    export const runOwnedStream = async (options) => { globalThis.__chatTest.streamRun = options; };`,
  ],
]);

await build({
  entryPoints: [sourcePath],
  bundle: true,
  platform: 'node',
  format: 'esm',
  outfile: outputPath,
  external: ['react'],
  plugins: [
    {
      name: 'chat-test-boundaries',
      setup(build) {
        build.onResolve({ filter: /\.css$/ }, () => ({ path: 'empty-css', namespace: 'test' }));
        build.onResolve({ filter: /.*/ }, (args) =>
          virtualModules.has(args.path) ? { path: args.path, namespace: 'test' } : null
        );
        build.onLoad({ filter: /.*/, namespace: 'test' }, (args) => ({
          contents: args.path === 'empty-css' ? '' : virtualModules.get(args.path),
          loader: 'js',
        }));
      },
    },
  ],
});
process.on('exit', () => fs.rmSync(outputDir, { recursive: true, force: true }));

class TestElement {
  constructor(tagName = 'div') {
    this.tagName = tagName.toUpperCase();
    this.nodeName = this.tagName;
    this.nodeType = 1;
    this.childNodes = [];
    this.style = {};
    this.attributes = {};
    this.listeners = new Map();
    this.ownerDocument = globalThis.document;
  }
  appendChild(child) { this.childNodes.push(child); child.parentNode = this; return child; }
  insertBefore(child, before) {
    if (!before) return this.appendChild(child);
    this.childNodes.splice(this.childNodes.indexOf(before), 0, child);
    child.parentNode = this;
    return child;
  }
  removeChild(child) { this.childNodes.splice(this.childNodes.indexOf(child), 1); }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  removeAttribute(name) { delete this.attributes[name]; }
  addEventListener(name, listener) { this.listeners.set(name, listener); }
  removeEventListener() {}
  focus() {}
  scrollIntoView() { globalThis.__chatTest.scrolls += 1; }
  get firstChild() { return this.childNodes[0] || null; }
  get lastChild() { return this.childNodes.at(-1) || null; }
}

function find(root, predicate) {
  if (predicate(root)) return root;
  for (const child of root.childNodes || []) {
    const match = find(child, predicate);
    if (match) return match;
  }
  return null;
}

const document = {
  createElement: (tagName) => new TestElement(tagName),
  createElementNS: (_namespace, tagName) => new TestElement(tagName),
  createTextNode: (text) => ({ nodeType: 3, nodeValue: text, ownerDocument: document }),
  addEventListener() {},
  removeEventListener() {},
  activeElement: null,
};
globalThis.document = document;
document.body = new TestElement('body');
document.documentElement = new TestElement('html');
globalThis.window = {
  document,
  HTMLElement: TestElement,
  HTMLIFrameElement: class extends TestElement {},
  getSelection: () => null,
};
document.defaultView = window;
globalThis.HTMLElement = TestElement;
globalThis.Node = { ELEMENT_NODE: 1 };
Object.defineProperty(globalThis, 'navigator', {
  configurable: true,
  value: { userAgent: 'node' },
});
globalThis.__chatTest = { scrolls: 0 };
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const ReactModule = await import('react');
const React = ReactModule.default;
const { act } = ReactModule;
const { Simulate } = await import('react-dom/test-utils');
const { createRoot } = await import('react-dom/client');
const { Chat } = await import(pathToFileURL(outputPath));

async function mountChat(props = {}) {
  const container = new TestElement('div');
  const root = createRoot(container);
  await act(async () => root.render(React.createElement(Chat, props)));
  return { container, root };
}

async function emit(event) {
  await act(async () => globalThis.__chatTest.agui.emit(event));
}

test('mounted Chat wires stop to flush and persist pending text', async () => {
  const { container, root } = await mountChat();
  await emit({ type: 'TEXT_MESSAGE_START', role: 'assistant' });
  await emit({ type: 'TEXT_MESSAGE_CONTENT', delta: 'partial' });
  const stop = find(container, (node) => node.attributes?.['data-test'] === 'stop');

  await act(async () => Simulate.click(stop));

  const sessionManager = globalThis.__chatTest.sessionManager;
  assert.equal(sessionManager.saved.messages[0].content, 'partial');
  await act(async () => root.unmount());
});

test('mounted Chat clear and unmount cancel pending writes', async () => {
  const scheduled = new Map();
  let nextFrameId = 0;
  const originalRequestAnimationFrame = globalThis.requestAnimationFrame;
  const originalCancelAnimationFrame = globalThis.cancelAnimationFrame;
  globalThis.requestAnimationFrame = (callback) => {
    const id = ++nextFrameId;
    scheduled.set(id, callback);
    return id;
  };
  globalThis.cancelAnimationFrame = (id) => scheduled.delete(id);
  const { container, root } = await mountChat({
    showClearButton: true,
  });
  await emit({ type: 'TEXT_MESSAGE_START', role: 'assistant' });
  await emit({ type: 'TEXT_MESSAGE_CONTENT', delta: 'stale' });
  assert.equal(scheduled.size, 1);
  const clear = find(container, (node) => node.attributes?.title === '清除对话');
  await act(async () => Simulate.click(clear));
  const confirm = find(container, (node) => node.attributes?.['data-test'] === 'confirm-clear');
  await act(async () => Simulate.click(confirm));
  assert.equal(scheduled.size, 0);
  assert.equal(find(container, (node) => node.attributes?.['data-message']), null);
  const clearedSession = globalThis.__chatTest.sessionManager.getSession();
  const clearSaveCount = globalThis.__chatTest.sessionManager.saveCount || 0;
  await new Promise((resolve) => setTimeout(resolve, 20));
  assert.deepEqual(clearedSession.messages, []);
  assert.equal(globalThis.__chatTest.sessionManager.saveCount || 0, clearSaveCount);

  await emit({ type: 'TEXT_MESSAGE_START', role: 'assistant' });
  await emit({ type: 'TEXT_MESSAGE_CONTENT', delta: 'unmounted' });
  assert.equal(scheduled.size, 1);
  const unmountedSession = globalThis.__chatTest.sessionManager.getSession();
  const unmountSaveCount = globalThis.__chatTest.sessionManager.saveCount || 0;
  await act(async () => root.unmount());
  assert.equal(scheduled.size, 0);
  await new Promise((resolve) => setTimeout(resolve, 20));
  assert.equal(container.childNodes.length, 0);
  assert.equal(unmountedSession.messages[0].content, '');
  assert.equal(globalThis.__chatTest.sessionManager.saveCount || 0, unmountSaveCount);
  globalThis.requestAnimationFrame = originalRequestAnimationFrame;
  globalThis.cancelAnimationFrame = originalCancelAnimationFrame;
});

test('mounted Chat honors the rollback prop and auto-scrolls every immediate delta', async () => {
  globalThis.__chatTest.scrolls = 0;
  const { root } = await mountChat({ streamingTextBatching: false });
  const scrollsAfterMount = globalThis.__chatTest.scrolls;
  await emit({ type: 'TEXT_MESSAGE_START', role: 'assistant' });
  await emit({ type: 'TEXT_MESSAGE_CONTENT', delta: 'a' });
  await emit({ type: 'TEXT_MESSAGE_CONTENT', delta: 'b' });

  const sessionManager = globalThis.__chatTest.sessionManager;
  assert.equal(sessionManager.getSession().messages[0].content, 'ab');
  assert.ok(globalThis.__chatTest.scrolls >= scrollsAfterMount + 2);
  await act(async () => root.unmount());
});

test('mounted Chat auto-scrolls only after the default batched frame commits', async () => {
  globalThis.__chatTest.scrolls = 0;
  const { root } = await mountChat();
  await emit({ type: 'TEXT_MESSAGE_START', role: 'assistant' });
  const scrollsAfterStart = globalThis.__chatTest.scrolls;
  await emit({ type: 'TEXT_MESSAGE_CONTENT', delta: 'batched' });

  assert.equal(globalThis.__chatTest.scrolls, scrollsAfterStart);
  await act(async () => new Promise((resolve) => setTimeout(resolve, 20)));
  assert.equal(globalThis.__chatTest.sessionManager.getSession().messages[0].content, 'batched');
  assert.equal(globalThis.__chatTest.scrolls, scrollsAfterStart + 1);
  await act(async () => root.unmount());
});

test('mounted Chat network-error and completion callbacks flush pending text', async () => {
  const errors = [];
  const { container, root } = await mountChat({
    sseUrl: 'https://example.test/chat',
    onError: (error) => errors.push(error.message),
  });
  const submit = find(container, (node) => node.attributes?.['data-test'] === 'submit');
  await act(async () => Simulate.click(submit));
  await emit({ type: 'TEXT_MESSAGE_START', role: 'assistant' });
  await emit({ type: 'TEXT_MESSAGE_CONTENT', delta: 'partial' });

  const originalConsoleError = console.error;
  console.error = () => {};
  try {
    await act(async () => globalThis.__chatTest.streamRun.onError(new Error('network')));
  } finally {
    console.error = originalConsoleError;
  }
  assert.deepEqual(errors, ['network']);
  assert.equal(globalThis.__chatTest.sessionManager.saved.messages[1].content, 'partial');

  await emit({ type: 'TEXT_MESSAGE_CONTENT', delta: '-complete' });
  await act(async () => globalThis.__chatTest.streamRun.onComplete());
  assert.equal(
    globalThis.__chatTest.sessionManager.saved.messages[1].content,
    'partial-complete'
  );
  await act(async () => root.unmount());
});
