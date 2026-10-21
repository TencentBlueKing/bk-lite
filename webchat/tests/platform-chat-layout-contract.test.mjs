import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import React from 'react';
import { act, create } from 'react-test-renderer';
import { build } from 'esbuild';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const output = path.join(root, '.test-dist', 'platform-chat-layout');
fs.mkdirSync(output, { recursive: true });
process.on('exit', () => {
  if (!process.env.NODE_V8_COVERAGE) fs.rmSync(output, { recursive: true, force: true });
});

await build({
  entryPoints: [path.join(root, 'packages/webchat-ui/src/PlatformChat.tsx')],
  bundle: true,
  platform: 'node',
  format: 'cjs',
  sourcemap: 'inline',
  external: ['react', 'react-dom'],
  alias: { '@webchat/core': path.join(root, 'packages/webchat-core/src/index.ts') },
  loader: { '.css': 'empty' },
  outfile: path.join(output, 'component.cjs'),
  plugins: [
    {
      name: 'stub-chat-panel',
      setup(build) {
        build.onResolve({ filter: /^\.\/Chat$/ }, (args) => {
          if (args.kind !== 'dynamic-import') return null;
          return { path: 'chat-panel-stub', namespace: 'layout-contract' };
        });
        build.onLoad({ filter: /.*/, namespace: 'layout-contract' }, () => ({
          contents: `const React = require('react');
            exports.Chat = function ChatStub() {
              return React.createElement('div', { 'data-test': 'chat-panel' }, 'chat');
            };`,
          loader: 'js',
        }));
      },
    },
  ],
});

const { PlatformChat } = createRequire(import.meta.url)(path.join(output, 'component.cjs'));

function hostClass(node) {
  return typeof node?.props?.className === 'string' ? node.props.className : '';
}

function walk(node, visit) {
  visit(node);
  for (const child of node?.children || []) {
    if (child && typeof child === 'object') walk(child, visit);
  }
}

function findHost(node, predicate) {
  let found = null;
  walk(node, (current) => {
    if (!found && predicate(current)) found = current;
  });
  return found;
}

function ancestorWithClass(node, pattern) {
  let current = node;
  while (current) {
    if (pattern.test(hostClass(current))) return current;
    current = current.parent;
  }
  return null;
}

function containsText(node, text) {
  let found = false;
  walk(node, (current) => {
    if (found) return;
    for (const child of current.children || []) {
      if (typeof child === 'string' && child.includes(text)) found = true;
    }
  });
  return found;
}

function classDump(node) {
  const classes = [];
  walk(node, (current) => {
    const className = hostClass(current);
    if (className) classes.push(className);
  });
  return classes.join(' | ');
}

function assertPinnedDock(renderer, sidebarLabel) {
  const tree = renderer.root;
  const shell = findHost(
    tree,
    (node) => /\bfixed\b/.test(hostClass(node)) && /\bbottom-0\b/.test(hostClass(node)) && /\btop-0\b/.test(hostClass(node))
  );
  assert.ok(shell, `dock 外壳缺失：${classDump(tree)}`);
  assert.match(hostClass(shell), /\bright-0\b/);
  assert.doesNotMatch(hostClass(shell), /\bfixed inset-0\b/);

  const rail = findHost(tree, (node) => {
    const className = hostClass(node);
    return /\bself-stretch\b/.test(className) && /\bflex-shrink-0\b/.test(className) && !/\brelative\b/.test(className);
  });
  assert.ok(rail, `${sidebarLabel}缺少 self-stretch：${classDump(tree)}`);
  assert.match(hostClass(rail), /\boverflow-hidden\b/);
  assert.match(hostClass(rail), /\bmin-h-0\b/);
  assert.doesNotMatch(hostClass(rail), /\bh-full\b/);

  const row = ancestorWithClass(rail, /\bitems-stretch\b/);
  assert.ok(row, `${sidebarLabel}不在横向拉伸行里`);
  assert.match(hostClass(row), /\boverflow-hidden\b/);
  assert.match(hostClass(row), /\bmin-h-0\b/);

  const column = findHost(
    row,
    (node) => /\brelative\b/.test(hostClass(node)) && /\bself-stretch\b/.test(hostClass(node)) && /\bflex-1\b/.test(hostClass(node))
  );
  assert.ok(column, `对话列缺少 relative + self-stretch：${classDump(row)}`);
  assert.doesNotMatch(hostClass(column), /\bh-full\b/);

  const inner = findHost(
    column,
    (node) => /\babsolute\b/.test(hostClass(node)) && /\binset-0\b/.test(hostClass(node))
  );
  assert.ok(inner, `对话列缺少 absolute inset-0：${classDump(column)}`);
  assert.match(hostClass(inner), /\bflex\b/);
  assert.match(hostClass(inner), /\bmin-h-0\b/);
  assert.match(hostClass(inner), /\bflex-col\b/);
  assert.match(hostClass(inner), /\boverflow-hidden\b/);
  assert.doesNotMatch(hostClass(inner), /\bh-full\b/);
  return { rail, column, inner };
}

function jsonResponse(body) {
  return {
    ok: true,
    status: 200,
    headers: { get: () => 'application/json' },
    json: async () => body,
  };
}

async function openDock() {
  const previous = {
    window: globalThis.window,
    document: globalThis.document,
    fetch: globalThis.fetch,
  };
  globalThis.window = {
    innerWidth: 1280,
    innerHeight: 800,
    localStorage: { getItem: () => null, setItem: () => {} },
    addEventListener() {},
    removeEventListener() {},
  };
  globalThis.document = {
    body: { style: {} },
    documentElement: { style: { setProperty() {} } },
    visibilityState: 'visible',
    addEventListener() {},
    removeEventListener() {},
    querySelector: () => null,
  };
  globalThis.fetch = async (url) => {
    const target = String(url);
    if (target.includes('/fixture/apps')) {
      return jsonResponse({
        result: true,
        data: [{ id: 'app-1', channel_id: 'channel-1', name: '平台助手' }],
        webchat_width: 460,
      });
    }
    if (target.includes('/fixture/sessions')) {
      return jsonResponse({
        result: true,
        data: [{ session_id: 'session-1', title: '昨天的对话' }],
      });
    }
    return jsonResponse({ result: true, data: [] });
  };

  const platform = {
    applicationsUrl: '/fixture/apps',
    sessionsUrl: '/fixture/sessions?channel_id={channelId}',
    messagesUrl: '/fixture/messages?session_id={sessionId}',
    chatUrlTemplate: '/fixture/chat/{channelId}',
  };
  let renderer;
  const restore = () => {
    globalThis.window = previous.window;
    globalThis.document = previous.document;
    globalThis.fetch = previous.fetch;
  };

  await act(async () => {
    renderer = create(React.createElement(PlatformChat, { platform, canManageAgents: true }));
  });
  await act(async () => {
    renderer.root.findByProps({ 'aria-label': '打开对话' }).props.onClick({ preventDefault() {} });
  });
  await act(async () => {
    await Promise.resolve();
  });
  return { renderer, restore };
}

test('dock 模式打开历史或文件侧栏时，对话列用 inset 高度，侧栏用 self-stretch', async () => {
  const { renderer, restore } = await openDock();
  try {
    await act(async () => {
      renderer.root.findByProps({ 'aria-label': '历史会话' }).props.onClick();
    });
    const history = assertPinnedDock(renderer, '历史侧栏');
    assert.equal(history.rail.props['aria-label'], '历史会话');
    assert.equal(history.rail.type, 'aside');
    assert.equal(renderer.root.findAllByProps({ 'aria-label': '收起历史' }).length, 1);

    await act(async () => {
      renderer.root.findByProps({ 'aria-label': '已生成文件' }).props.onClick();
    });
    const files = assertPinnedDock(renderer, '文件侧栏');
    assert.notEqual(files.rail.type, 'aside');
    assert.equal(renderer.root.findAllByType('aside').length, 0);
    assert.equal(renderer.root.findAllByProps({ 'aria-label': '收起文件' }).length, 1);
    assert.equal(containsText(files.rail, '已生成文件'), true);
  } finally {
    await act(async () => {
      renderer.unmount();
    });
    restore();
  }
});
