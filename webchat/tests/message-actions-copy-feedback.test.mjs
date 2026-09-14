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
  external: ['react', 'react/jsx-runtime'],
  alias: {
    '@webchat/core': path.join(rootDir, 'packages/webchat-core/src/index.ts'),
    'react-dom': path.join(rootDir, 'tests/react-dom.portal-capture.stub.mjs'),
  },
  loader: { '.css': 'empty' },
});
process.on('exit', () => {
  fs.rmSync(outputDir, { recursive: true, force: true });
});

const {
  COPY_SUCCESS_LABEL,
  WEBCHAT_ROOT_ID,
  MessageActions,
  resolveWebchatPortalTarget,
} = await import(pathToFileURL(outputPath));

assert.equal(COPY_SUCCESS_LABEL, '已复制到剪贴板');

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

const COPY_BTN_RECT = {
  top: 120,
  left: 200,
  width: 24,
  height: 24,
  bottom: 144,
  right: 224,
  x: 200,
  y: 120,
  toJSON() {
    return this;
  },
};

const installDocument = ({ withRoot = true } = {}) => {
  const webchatRoot = { id: WEBCHAT_ROOT_ID };
  const body = { id: '' };
  globalThis.document = {
    body,
    getElementById: (id) => (withRoot && id === WEBCHAT_ROOT_ID ? webchatRoot : null),
  };
  globalThis.__webchatPortalTargets = [];
  return { webchatRoot, body };
};

const renderActions = async () => {
  let renderer;
  await act(() => {
    renderer = create(
      React.createElement(MessageActions, {
        messageId: 'm1',
        messageContent: '磁盘使用率 Top',
        isBot: true,
        showActions: true,
      }),
      {
        createNodeMock: (element) => {
          if (element.type === 'button' && element.props['aria-label'] === '复制') {
            return {
              getBoundingClientRect: () => COPY_BTN_RECT,
              closest: (selector) =>
                selector === `#${WEBCHAT_ROOT_ID}`
                  ? globalThis.document.getElementById(WEBCHAT_ROOT_ID)
                  : null,
            };
          }
          return {};
        },
      }
    );
  });
  return renderer;
};

test('copy shows clipboard success label and writes message text', async () => {
  writes.length = 0;
  installDocument();
  const renderer = await renderActions();

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

test('resolveWebchatPortalTarget prefers #webchat-root over document.body', () => {
  const { webchatRoot, body } = installDocument();
  const fromId = resolveWebchatPortalTarget(null);
  assert.equal(fromId, webchatRoot);
  assert.notEqual(fromId, body);

  installDocument({ withRoot: false });
  const closestRoot = { id: WEBCHAT_ROOT_ID };
  const fromClosest = resolveWebchatPortalTarget({
    closest: (selector) => (selector === `#${WEBCHAT_ROOT_ID}` ? closestRoot : null),
  });
  assert.equal(fromClosest, closestRoot);

  installDocument({ withRoot: false });
  assert.equal(resolveWebchatPortalTarget(null), null);
});

test('copy success tip portals into #webchat-root with inline fixed positioning', async () => {
  writes.length = 0;
  const { webchatRoot, body } = installDocument();
  const renderer = await renderActions();

  const copyBtn = renderer.root.findByProps({ 'aria-label': '复制' });
  await act(async () => {
    copyBtn.props.onClick();
    await Promise.resolve();
    await Promise.resolve();
  });
  await flush();

  assert.equal(globalThis.__webchatPortalTargets.length, 1);
  assert.equal(globalThis.__webchatPortalTargets[0], webchatRoot);
  assert.notEqual(globalThis.__webchatPortalTargets[0], body);

  const portal = renderer.root.findByProps({ 'data-testid': 'webchat-portal' });
  assert.equal(portal.props['data-portal-target-id'], WEBCHAT_ROOT_ID);

  const tip = renderer.root.findByProps({ role: 'status' });
  assert.equal(tip.children[0], COPY_SUCCESS_LABEL);
  assert.equal(tip.props.style.position, 'fixed');
  assert.equal(tip.props.style.transform, 'translate(-50%, -100%)');
  assert.equal(tip.props.style.zIndex, 2100);
  assert.equal(tip.props.style.top, COPY_BTN_RECT.top - 8);
  assert.equal(tip.props.style.left, COPY_BTN_RECT.left + COPY_BTN_RECT.width / 2);
  assert.equal(tip.props.className, undefined);
});

test('copy tip source does not portal onto document.body', () => {
  const source = fs.readFileSync(sourcePath, 'utf8');
  assert.match(source, /resolveWebchatPortalTarget/);
  assert.doesNotMatch(source, /createPortal\([\s\S]*document\.body/);
  assert.doesNotMatch(source, /,\s*document\.body\s*\)/);
});
