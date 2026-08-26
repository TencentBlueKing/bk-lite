import assert from 'node:assert';
import { test } from 'node:test';
import { extractMessageText } from '../../packages/webchat-core/src/messageContent';

test('extractMessageText preserves plain string content', () => {
  assert.strictEqual(extractMessageText('hello'), 'hello');
});

test('extractMessageText reads text and caption variants in source order', () => {
  assert.strictEqual(
    extractMessageText([
      { type: 'text', text: 'first' },
      { type: 'image_url', image_url: 'data:image/png;base64,abc' },
      { type: 'message', message: 'caption' },
      { type: 'text', text: 'last' },
    ]),
    'first\ncaption\nlast'
  );
});

test('extractMessageText ignores images and absent text fields', () => {
  assert.strictEqual(
    extractMessageText([
      { type: 'image_url', image_url: 'https://example.com/image.png' },
      { type: 'message' },
      { type: 'text' },
    ]),
    ''
  );
});

test('extractMessageText skips empty fields without adding blank lines', () => {
  assert.strictEqual(
    extractMessageText([
      { type: 'text', text: '' },
      { type: 'message', message: 'caption' },
      { type: 'text', text: '' },
    ]),
    'caption'
  );
});

test('extractMessageText preserves whitespace inside non-empty fields', () => {
  assert.strictEqual(
    extractMessageText([
      { type: 'text', text: ' first\n' },
      { type: 'message', message: ' second ' },
    ]),
    ' first\n\n second '
  );
});
