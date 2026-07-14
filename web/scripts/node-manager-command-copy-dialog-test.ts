import assert from 'node:assert/strict';
import {
  ClipboardCopyError,
  copyText,
  fallbackCopyText,
} from '../src/app/node-manager/utils/clipboard.ts';

const run = async () => {
let written = '';
await copyText('echo hello', {
  writeText: async (value) => {
    written = value;
  },
});
assert.equal(written, 'echo hello');

await assert.rejects(
  copyText('echo denied', {
    writeText: async () => {
      throw new Error('denied');
    },
  }),
  (error: unknown) =>
    error instanceof ClipboardCopyError && error.reason === 'failed'
);

let fallbackValue = '';
await copyText('echo fallback', {
  fallbackCopy: (value) => {
    fallbackValue = value;
    return true;
  },
});
assert.equal(fallbackValue, 'echo fallback');

await assert.rejects(
  copyText('echo false', { fallbackCopy: () => false }),
  (error: unknown) =>
    error instanceof ClipboardCopyError && error.reason === 'failed'
);

await assert.rejects(
  copyText('echo unavailable', {}),
  (error: unknown) =>
    error instanceof ClipboardCopyError && error.reason === 'unavailable'
);

let attemptedEmptyCopy = false;
await assert.rejects(
  copyText('   ', {
    fallbackCopy: () => {
      attemptedEmptyCopy = true;
      return true;
    },
  }),
  (error: unknown) =>
    error instanceof ClipboardCopyError && error.reason === 'empty'
);
assert.equal(attemptedEmptyCopy, false);

const appended: unknown[] = [];
const removed: unknown[] = [];
let selected = false;
const textarea = {
  value: '',
  style: {} as Record<string, string>,
  setAttribute: () => undefined,
  select: () => {
    selected = true;
  },
};
const fakeDocument = {
  createElement: (tagName: string) => {
    assert.equal(tagName, 'textarea');
    return textarea;
  },
  body: {
    appendChild: (element: unknown) => appended.push(element),
    removeChild: (element: unknown) => removed.push(element),
  },
  execCommand: (command: string) => {
    assert.equal(command, 'copy');
    return true;
  },
};

assert.equal(fallbackCopyText('echo cleanup', fakeDocument), true);
assert.equal(textarea.value, 'echo cleanup');
assert.equal(selected, true);
assert.deepEqual(appended, [textarea]);
assert.deepEqual(removed, [textarea]);

fakeDocument.execCommand = () => {
  throw new Error('copy failed');
};
assert.throws(() => fallbackCopyText('echo cleanup failure', fakeDocument));
assert.deepEqual(removed, [textarea, textarea]);

console.log('node-manager command copy dialog tests passed');
};

run().catch((error) => {
  console.error(error);
  process.exit(1);
});
