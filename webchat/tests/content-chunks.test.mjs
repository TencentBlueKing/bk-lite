import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath, pathToFileURL } from 'node:url';
import ts from 'typescript';

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const sourcePath = path.join(rootDir, 'packages/webchat-ui/src/contentChunks.ts');
const outputDir = fs.mkdtempSync(path.join(os.tmpdir(), 'webchat-content-chunks-'));
const outputPath = path.join(outputDir, 'contentChunks.mjs');

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

const {
  appendToolCallChunk,
  mapMessageChunks,
  patchToolCall,
  syncSessionChunks,
  upsertTextChunk,
} = await import(pathToFileURL(outputPath));

test('upsertTextChunk updates the trailing text chunk', () => {
  const chunks = [{ type: 'text', content: 'hel' }];
  assert.deepEqual(upsertTextChunk(chunks, 'hello'), [
    { type: 'text', content: 'hello' },
  ]);
});

test('upsertTextChunk appends after a tool-call chunk', () => {
  const chunks = [
    { type: 'toolCalls', toolCalls: [{ id: 't1', name: 'search', status: 'running' }] },
  ];
  assert.deepEqual(upsertTextChunk(chunks, 'result'), [
    chunks[0],
    { type: 'text', content: 'result' },
  ]);
});

test('appendToolCallChunk rejects duplicates', () => {
  const tool = { id: 't1', name: 'search', status: 'running' };
  const chunks = [{ type: 'toolCalls', toolCalls: [tool] }];
  assert.equal(appendToolCallChunk(chunks, tool), null);
});

test('patchToolCall updates args and status', () => {
  const chunks = [
    {
      type: 'toolCalls',
      toolCalls: [{ id: 't1', name: 'search', status: 'running' }],
    },
  ];
  const patched = patchToolCall(chunks, 't1', {
    args: '{"q":"x"}',
    status: 'completed',
  });
  assert.deepEqual(patched[0], {
    type: 'toolCalls',
    toolCalls: [
      { id: 't1', name: 'search', status: 'completed', args: '{"q":"x"}' },
    ],
  });
});

test('mapMessageChunks and syncSessionChunks stay aligned', () => {
  const message = {
    id: 'm1',
    type: 'text',
    content: '',
    sender: 'bot',
    timestamp: 1,
    metadata: { contentChunks: [] },
  };
  const session = {
    sessionId: 's1',
    messages: [{ ...message, metadata: { contentChunks: [] } }],
    startTime: 1,
    lastActivityTime: 1,
  };

  const nextMessages = mapMessageChunks(
    [message],
    'm1',
    (chunks) => upsertTextChunk(chunks, 'hi'),
    'hi'
  );
  syncSessionChunks(session, 'm1', (chunks) => upsertTextChunk(chunks, 'hi'), 'hi');

  assert.equal(nextMessages[0].content, 'hi');
  assert.equal(session.messages[0].content, 'hi');
  assert.deepEqual(nextMessages[0].metadata.contentChunks, [
    { type: 'text', content: 'hi' },
  ]);
  assert.deepEqual(session.messages[0].metadata.contentChunks, [
    { type: 'text', content: 'hi' },
  ]);
});
