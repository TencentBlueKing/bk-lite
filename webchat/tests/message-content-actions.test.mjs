import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { buildSync } from 'esbuild';

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const sourcePath = path.join(
  rootDir,
  'packages/webchat-ui/src/messageContentActions.ts'
);
const outputDir = fs.mkdtempSync(path.join(os.tmpdir(), 'webchat-message-actions-'));
const outputPath = path.join(outputDir, 'messageContentActions.mjs');

buildSync({
  entryPoints: [sourcePath],
  bundle: true,
  platform: 'node',
  format: 'esm',
  outfile: outputPath,
});
process.on('exit', () => fs.rmSync(outputDir, { recursive: true, force: true }));

const { getMessageCopyText, planMessageRegeneration } = await import(
  pathToFileURL(outputPath)
);

function message(id, sender, content) {
  return { id, sender, content, type: 'multimodal', timestamp: 1 };
}

test('copy returns multimodal captions and text variants in source order', () => {
  assert.equal(
    getMessageCopyText([
      { type: 'message', message: 'caption' },
      { type: 'image_url', image_url: 'data:image/png;base64,abc' },
      { type: 'text', text: 'details' },
    ]),
    'caption\ndetails'
  );
});

test('caption regeneration truncates only after a non-empty replay plan exists', () => {
  const history = message('history', 'bot', 'older');
  const user = message('user', 'user', [
    { type: 'image_url', image_url: 'data:image/png;base64,abc' },
    { type: 'message', message: 'caption' },
  ]);
  const bot = message('bot', 'bot', 'answer');

  const plan = planMessageRegeneration([history, user, bot], 'bot');

  assert.deepEqual(plan, {
    preservedMessages: [history],
    contentToSend: 'caption',
  });
});

test('image-only regeneration keeps the original conversation intact', () => {
  const user = message('user', 'user', [
    { type: 'image_url', image_url: 'data:image/png;base64,abc' },
  ]);
  const bot = message('bot', 'bot', 'answer');
  const messages = [user, bot];

  assert.equal(planMessageRegeneration(messages, 'bot'), null);
  assert.deepEqual(messages, [user, bot]);
});

test('missing captions and unknown targets do not create destructive plans', () => {
  const user = message('user', 'user', [{ type: 'message' }]);
  const messages = [user];

  assert.equal(planMessageRegeneration(messages, 'user'), null);
  assert.equal(planMessageRegeneration(messages, 'missing'), null);
  assert.deepEqual(messages, [user]);
});

test('whitespace-only captions do not create destructive plans', () => {
  const user = message('user', 'user', [
    { type: 'message', message: '  \n ' },
  ]);
  const bot = message('bot', 'bot', 'answer');
  const messages = [user, bot];

  assert.equal(planMessageRegeneration(messages, 'bot'), null);
  assert.deepEqual(messages, [user, bot]);
});
