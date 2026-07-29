import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath, pathToFileURL } from 'node:url';
import ts from 'typescript';

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const lifecyclePath = path.join(
  rootDir,
  'packages/webchat-ui/src/streamLifecycle.ts'
);
const chatPath = path.join(rootDir, 'packages/webchat-ui/src/Chat.tsx');
const outputDir = fs.mkdtempSync(path.join(os.tmpdir(), 'webchat-stream-lifecycle-'));
const outputPath = path.join(outputDir, 'streamLifecycle.mjs');
const compiled = ts.transpileModule(fs.readFileSync(lifecyclePath, 'utf8'), {
  compilerOptions: {
    module: ts.ModuleKind.ES2020,
    target: ts.ScriptTarget.ES2020,
  },
  fileName: lifecyclePath,
});
fs.writeFileSync(outputPath, compiled.outputText);
process.on('exit', () => fs.rmSync(outputDir, { recursive: true, force: true }));

const { isAbortError, runOwnedStream, StreamLifecycle, toError } =
  await import(pathToFileURL(outputPath));

class FakeReader {
  cancelled = [];
  releaseCount = 0;

  async read() {
    return { done: true, value: undefined };
  }

  async cancel(reason) {
    this.cancelled.push(reason);
  }

  releaseLock() {
    this.releaseCount += 1;
  }
}

function fakeAbortController() {
  return {
    signal: { aborted: false },
    abort() {
      this.signal.aborted = true;
    },
  };
}

test('Chat wires stream ownership into every lifecycle boundary', () => {
  const source = fs.readFileSync(chatPath, 'utf8');
  for (const fragment of [
    'runOwnedStream({',
    'request: (signal) =>',
    '...(signal ? { signal } : {})',
    'streamLifecycle?.dispose()',
    "cancel('session-cleared')",
    'onCancel={handleStopStreaming}',
  ]) {
    assert.ok(source.includes(fragment), `Chat is missing lifecycle wiring: ${fragment}`);
  }
});

test('normal completion keeps the active stream writable and releases its reader', async () => {
  const lifecycle = new StreamLifecycle(fakeAbortController);
  const encoder = new TextEncoder();
  const body = new ReadableStream({
    start(controller) {
      controller.enqueue(encoder.encode('normal-response'));
      controller.close();
    },
  });
  const chunks = [];
  const errors = [];
  let completed = 0;
  let receivedSignal;
  lifecycle.mount();

  const stream = lifecycle.begin();
  assert.ok(stream);
  await runOwnedStream({
    lifecycle,
    stream,
    request: async (signal) => {
      receivedSignal = signal;
      return new Response(body);
    },
    onChunk: (chunk) => chunks.push(new TextDecoder().decode(chunk)),
    onError: (error) => errors.push(error),
    onComplete: () => {
      completed += 1;
    },
  });

  assert.equal(receivedSignal, stream.signal);
  assert.deepEqual(chunks, ['normal-response']);
  assert.deepEqual(errors, []);
  assert.equal(completed, 1);
  assert.equal(lifecycle.isActive(stream), false);
  assert.doesNotThrow(() => {
    const nextReader = body.getReader();
    nextReader.releaseLock();
  });
});

test('unmount deactivates synchronously and cancels the active reader', async () => {
  const lifecycle = new StreamLifecycle(fakeAbortController);
  const reader = new FakeReader();
  lifecycle.mount();

  const stream = lifecycle.begin();
  assert.ok(stream);
  lifecycle.attachReader(stream, reader);
  const cleanup = lifecycle.dispose();

  assert.equal(lifecycle.isActive(stream), false);
  assert.equal(stream.signal.aborted, true);
  await cleanup;
  assert.deepEqual(reader.cancelled, ['component-unmounted']);
  assert.equal(reader.releaseCount, 1);
  assert.equal(lifecycle.begin(), null);
});

test('a pending ReadableStream cannot write after the component unmounts', async () => {
  const lifecycle = new StreamLifecycle();
  const encoder = new TextEncoder();
  const writes = [];
  let sourceController;
  let resolveFirstWrite;
  const firstWrite = new Promise((resolve) => {
    resolveFirstWrite = resolve;
  });
  const body = new ReadableStream({
    start(controller) {
      sourceController = controller;
    },
  });

  lifecycle.mount();
  const stream = lifecycle.begin();
  assert.ok(stream);
  const errors = [];
  let completed = 0;
  const consuming = runOwnedStream({
    lifecycle,
    stream,
    request: async () => new Response(body),
    onChunk: (value) => {
      writes.push(new TextDecoder().decode(value));
      resolveFirstWrite();
    },
    onError: (error) => errors.push(error),
    onComplete: () => {
      completed += 1;
    },
  });

  sourceController.enqueue(encoder.encode('first'));
  await firstWrite;
  await lifecycle.dispose();
  await consuming;

  assert.deepEqual(writes, ['first']);
  assert.deepEqual(errors, []);
  assert.equal(completed, 0);
  assert.doesNotThrow(() => {
    const nextReader = body.getReader();
    nextReader.releaseLock();
  });
});

test('a new send owns state and prevents the replaced stream from completing it', async () => {
  const lifecycle = new StreamLifecycle(fakeAbortController);
  const oldReader = new FakeReader();
  lifecycle.mount();

  const oldStream = lifecycle.begin();
  assert.ok(oldStream);
  lifecycle.attachReader(oldStream, oldReader);
  const newStream = lifecycle.begin();
  assert.ok(newStream);

  assert.equal(lifecycle.isActive(oldStream), false);
  assert.equal(lifecycle.isActive(newStream), true);
  assert.equal(lifecycle.complete(oldStream), false);
  await Promise.resolve();
  assert.deepEqual(oldReader.cancelled, ['replaced-by-new-stream']);
});

test('clearing a session or pressing stop cancels without producing an error', async () => {
  for (const reason of ['session-cleared', 'user-stopped']) {
    const lifecycle = new StreamLifecycle(fakeAbortController);
    const reader = new FakeReader();
    lifecycle.mount();

    const stream = lifecycle.begin();
    assert.ok(stream);
    lifecycle.attachReader(stream, reader);
    await lifecycle.cancel(reason);

    assert.equal(lifecycle.isActive(stream), false);
    assert.deepEqual(reader.cancelled, [reason]);
    assert.equal(reader.releaseCount, 1);
  }
});

test('AbortError stays silent while ordinary request errors reach the UI contract', async () => {
  const abortLifecycle = new StreamLifecycle(fakeAbortController);
  const abortErrors = [];
  let abortCompleted = 0;
  abortLifecycle.mount();
  const abortStream = abortLifecycle.begin();
  assert.ok(abortStream);

  await runOwnedStream({
    lifecycle: abortLifecycle,
    stream: abortStream,
    request: async () => {
      throw { name: 'AbortError' };
    },
    onChunk: () => undefined,
    onError: (error) => abortErrors.push(error),
    onComplete: () => {
      abortCompleted += 1;
    },
  });

  assert.deepEqual(abortErrors, []);
  assert.equal(abortCompleted, 1);

  const failedLifecycle = new StreamLifecycle(fakeAbortController);
  const failedErrors = [];
  let failedCompleted = 0;
  failedLifecycle.mount();
  const failedStream = failedLifecycle.begin();
  assert.ok(failedStream);

  await runOwnedStream({
    lifecycle: failedLifecycle,
    stream: failedStream,
    request: async () => {
      throw 'network failed';
    },
    onChunk: () => undefined,
    onError: (error) => failedErrors.push(error.message),
    onComplete: () => {
      failedCompleted += 1;
    },
  });

  assert.deepEqual(failedErrors, ['network failed']);
  assert.equal(failedCompleted, 1);
  assert.equal(isAbortError({ name: 'AbortError' }), true);
  assert.equal(isAbortError(new Error('network failed')), false);
  assert.equal(toError({ code: 'E_STREAM' }).message, 'Unknown stream error');
});

test('runtimes without AbortController still enforce ownership and reader cleanup', async () => {
  const lifecycle = new StreamLifecycle(() => null);
  const reader = new FakeReader();
  lifecycle.mount();

  const stream = lifecycle.begin();
  assert.ok(stream);
  assert.equal(stream.signal, undefined);
  lifecycle.attachReader(stream, reader);
  await lifecycle.cancel('user-stopped');

  assert.equal(lifecycle.isActive(stream), false);
  assert.equal(reader.releaseCount, 1);
});

test('a reader arriving after its lease was cancelled is cleaned up immediately', async () => {
  const lifecycle = new StreamLifecycle(fakeAbortController);
  const reader = new FakeReader();
  lifecycle.mount();

  const stream = lifecycle.begin();
  assert.ok(stream);
  await lifecycle.cancel('session-cleared');

  assert.equal(lifecycle.attachReader(stream, reader), false);
  await Promise.resolve();
  assert.deepEqual(reader.cancelled, ['stale-stream']);
  assert.equal(reader.releaseCount, 1);
});
