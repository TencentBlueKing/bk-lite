import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath, pathToFileURL } from 'node:url';
import ts from 'typescript';

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const sourcePath = path.join(
  rootDir,
  'packages/webchat-ui/src/streamingFrameBatcher.ts'
);
const outputDir = fs.mkdtempSync(path.join(os.tmpdir(), 'webchat-frame-batcher-'));
const outputPath = path.join(outputDir, 'streamingFrameBatcher.mjs');
const source = fs.readFileSync(sourcePath, 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.ES2020,
    target: ts.ScriptTarget.ES2020,
  },
  fileName: sourcePath,
});

fs.writeFileSync(outputPath, compiled.outputText);
process.on('exit', () => fs.rmSync(outputDir, { recursive: true, force: true }));

const { createStreamingFrameBatcher } = await import(pathToFileURL(outputPath));

function createManualFrameScheduler() {
  let nextId = 0;
  const callbacks = new Map();
  return {
    scheduler: {
      schedule(callback) {
        const id = ++nextId;
        callbacks.set(id, callback);
        return id;
      },
      cancel(id) {
        callbacks.delete(id);
      },
    },
    runFrame() {
      const queued = [...callbacks.values()];
      callbacks.clear();
      queued.forEach((callback) => callback());
    },
    get size() {
      return callbacks.size;
    },
  };
}

test('many deltas commit only the latest text once per frame', () => {
  const frames = createManualFrameScheduler();
  const commits = [];
  const batcher = createStreamingFrameBatcher((text) => commits.push(text), frames.scheduler);

  for (let index = 1; index <= 500; index += 1) {
    batcher.schedule(`delta-${index}`);
  }

  assert.equal(frames.size, 1);
  assert.deepEqual(commits, []);
  frames.runFrame();
  assert.deepEqual(commits, ['delta-500']);
});

test('flush commits pending text synchronously and cancels the frame', () => {
  const frames = createManualFrameScheduler();
  const commits = [];
  const batcher = createStreamingFrameBatcher((text) => commits.push(text), frames.scheduler);

  batcher.schedule('before tool');
  batcher.flush();

  assert.deepEqual(commits, ['before tool']);
  assert.equal(frames.size, 0);
  frames.runFrame();
  assert.deepEqual(commits, ['before tool']);
});

test('cancel drops pending work without a late commit', () => {
  const frames = createManualFrameScheduler();
  const commits = [];
  const batcher = createStreamingFrameBatcher((text) => commits.push(text), frames.scheduler);

  batcher.schedule('stale response');
  batcher.cancel();
  frames.runFrame();

  assert.deepEqual(commits, []);
});

test('disabled batching commits every update immediately and schedules no frame', () => {
  const frames = createManualFrameScheduler();
  const commits = [];
  const batcher = createStreamingFrameBatcher(
    (text) => commits.push(text),
    frames.scheduler,
    () => false
  );

  batcher.schedule('a');
  batcher.schedule('ab');

  assert.deepEqual(commits, ['a', 'ab']);
  assert.equal(frames.size, 0);
});

test('disabling batching cancels a queued frame and commits the newest text immediately', () => {
  const frames = createManualFrameScheduler();
  const commits = [];
  let batching = true;
  const batcher = createStreamingFrameBatcher(
    (text) => commits.push(text),
    frames.scheduler,
    () => batching
  );

  batcher.schedule('a');
  batching = false;
  batcher.schedule('ab');
  frames.runFrame();

  assert.deepEqual(commits, ['ab']);
  assert.equal(frames.size, 0);
});
