import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { buildSync } from 'esbuild';
import React from 'react';
import { act, create } from 'react-test-renderer';

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const sourcePath = path.join(
  rootDir,
  'packages/webchat-ui/src/components/MessageActions.tsx'
);
const outputDir = path.join(rootDir, '.test-dist', 'copy-feedback');
fs.mkdirSync(outputDir, { recursive: true });
const outputPath = path.join(outputDir, 'MessageActions.mjs');

buildSync({
  entryPoints: [sourcePath],
  bundle: true,
  platform: 'node',
  format: 'esm',
  jsx: 'automatic',
  outfile: outputPath,
  external: ['react', 'react/jsx-runtime', 'react-dom'],
  alias: {
    '@webchat/core': path.join(rootDir, 'packages/webchat-core/src/index.ts'),
  },
  loader: { '.css': 'empty' },
});
process.on('exit', () => {
  fs.rmSync(outputDir, { recursive: true, force: true });
});

const { COPY_SUCCESS_LABEL, MessageActions } = await import(
  pathToFileURL(outputPath)
);

const writes = [];
Object.defineProperty(globalThis, 'navigator', {
  configurable: true,
  value: {
    clipboard: {
      writeText: async (text) => {
        writes.push(text);
      },
    },
  },
});

const flush = async () => {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
};

test('copy shows clipboard success label and writes message text', async () => {
  writes.length = 0;
  let renderer;
  await act(() => {
    renderer = create(
      React.createElement(MessageActions, {
        messageId: 'm1',
        messageContent: '磁盘使用率 Top',
        isBot: true,
        showActions: true,
      })
    );
  });

  const copyBtn = renderer.root.findByProps({ 'aria-label': '复制' });
  assert.match(String(copyBtn.props.className), /hover:-translate-y-0\.5/);
  await act(async () => {
    copyBtn.props.onClick();
    await Promise.resolve();
    await Promise.resolve();
  });
  await flush();

  assert.deepEqual(writes, ['磁盘使用率 Top']);
  renderer.root.findByProps({ 'aria-label': COPY_SUCCESS_LABEL });
});
