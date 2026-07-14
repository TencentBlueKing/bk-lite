import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import {
  ClipboardCopyError,
  copyText,
  fallbackCopyText,
} from '../src/app/node-manager/utils/clipboard.ts';
import {
  commandCopyInitialState,
  commandCopyReducer,
} from '../src/app/node-manager/hooks/useCommandCopyDialog.tsx';

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

const copying = commandCopyReducer(commandCopyInitialState, {
  type: 'copying',
  content: 'echo hello',
});
assert.equal(copying.open, false);
assert.equal(copying.copying, true);
assert.equal(copying.content, 'echo hello');

const success = commandCopyReducer(copying, { type: 'success' });
assert.equal(success.open, true);
assert.equal(success.status, 'success');
assert.equal(success.copying, false);

const failure = commandCopyReducer(copying, {
  type: 'failure',
  reason: 'failed',
});
assert.equal(failure.open, true);
assert.equal(failure.status, 'error');
assert.equal(failure.content, 'echo hello');
assert.equal(failure.reason, 'failed');

const emptyFailure = commandCopyReducer(commandCopyInitialState, {
  type: 'failure',
  reason: 'empty',
  content: '',
});
assert.equal(emptyFailure.open, true);
assert.equal(emptyFailure.reason, 'empty');

const closed = commandCopyReducer(failure, { type: 'close' });
assert.deepEqual(closed, commandCopyInitialState);

const locales = ['zh', 'en'].map((name) => ({
  name,
  locale: JSON.parse(
    readFileSync(
      new URL(
        `../src/app/node-manager/locales/${name}.json`,
        import.meta.url
      ),
      'utf8'
    )
  ),
}));
for (const { name, locale } of locales) {
  const node = locale['node-manager'].cloudregion.node;
  for (const key of [
    'commandCopySuccessTitle',
    'commandCopySuccessDesc',
    'commandCopyFailedTitle',
    'commandCopyFailedDesc',
    'commandCopyEmptyDesc',
    'copiedOriginal',
    'copyAgain',
    'retryCopy',
    'gotIt',
  ]) {
    assert.equal(typeof node[key], 'string', `${name}.${key}`);
  }
}

const readWebSource = (path: string) =>
  readFileSync(new URL(`../${path}`, import.meta.url), 'utf8');

const guidance = readWebSource(
  'src/app/node-manager/(pages)/cloudregion/node/controllerInstall/installing/operationGuidance.tsx'
);
assert.match(guidance, /useCommandCopyDialog/);
assert.match(guidance, /copyCommand\(nodeInfo\.installerSession/);
assert.match(guidance, /commandCopyDialog/);
assert.match(guidance, /handleCopy\(\{ value \}\)/);

const sections = readWebSource(
  'src/app/node-manager/(pages)/cloudregion/node/controllerInstall/installing/operationGuidanceSections.tsx'
);
assert.match(
  sections,
  /disabled=\{loading \|\| !installerSession\.trim\(\)\}/
);
assert.match(sections, /loading=\{copying\}/);

const progress = readWebSource(
  'src/app/node-manager/(pages)/cloudregion/node/operationProgress/index.tsx'
);
assert.match(progress, /await copyCommand\(installCommand\)/);
assert.doesNotMatch(
  progress,
  /notification\.success\(\{[\s\S]*?commandCopied/
);

console.log('node-manager command copy dialog tests passed');
};

run().catch((error) => {
  console.error(error);
  process.exit(1);
});
