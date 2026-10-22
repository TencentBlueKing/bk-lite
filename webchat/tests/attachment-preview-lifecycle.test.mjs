import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import React from 'react';
import { act, create } from 'react-test-renderer';
import { buildSync } from 'esbuild';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const output = path.join(root, '.test-dist', 'attachment-preview');
fs.mkdirSync(output, { recursive: true });
process.on('exit', () => {
  if (!process.env.NODE_V8_COVERAGE) fs.rmSync(output, { recursive: true, force: true });
});
buildSync({
  entryPoints: [path.join(root, 'packages/webchat-ui/src/components/MessageBubble.tsx')],
  bundle: true,
  platform: 'node',
  format: 'cjs',
  sourcemap: 'inline',
  external: ['react', 'react-dom'],
  alias: { '@webchat/core': path.join(root, 'packages/webchat-core/src/index.ts') },
  loader: { '.css': 'empty' },
  outfile: path.join(output, 'component.cjs'),
});
const { MessageBubble } = createRequire(import.meta.url)(path.join(output, 'component.cjs'));


const active = new Set();
let renderer;
const createUrl = URL.createObjectURL.bind(URL);
const revokeUrl = URL.revokeObjectURL.bind(URL);
test.beforeEach(() => {
  URL.createObjectURL = (blob) => { const url = createUrl(blob); active.add(url); return url; };
  URL.revokeObjectURL = (url) => { active.delete(url); revokeUrl(url); };
});
test.afterEach(async () => {
  await act(async () => renderer?.unmount());
  renderer = undefined;
  active.forEach(revokeUrl);
  active.clear();
  URL.createObjectURL = createUrl;
  URL.revokeObjectURL = revokeUrl;
});
const attachment = { id: 1, name: 'fixture.png', mime: 'image/png', size: 7, status: 'ready' };
const message = { id: 'fixture', sender: 'user', content: 'fixture', timestamp: 1, metadata: { attachments: [attachment] } };
const loadAttachment = async () => new Blob(['fixture'], { type: 'image/png' });
const bubble = (attachments = [attachment], load = loadAttachment) => React.createElement(MessageBubble, {
  message: { ...message, metadata: { attachments } }, loadAttachment: load,
});
const mount = async (element = bubble()) => { await act(async () => { renderer = create(element); }); };
const unmount = async () => { await act(async () => renderer.unmount()); renderer = undefined; };

test('历史图片显示期间有效，重复渲染复用，卸载后释放', async () => {
  await mount();
  const url = renderer.root.findByType('img').props.src;
  assert.ok(active.has(url));
  await act(async () => renderer.update(bubble()));
  assert.equal(renderer.root.findByType('img').props.src, url);
  assert.equal(active.size, 1);
  await unmount();
  assert.equal(active.size, 0);
});

test('替换和移除附件会注销旧 URL', async () => {
  await mount();
  const oldUrl = renderer.root.findByType('img').props.src;
  await act(async () => renderer.update(bubble([{ ...attachment, id: 2, name: 'next.png' }])));
  assert.equal(active.has(oldUrl), false);
  assert.equal(active.size, 1);
  assert.equal(renderer.root.findByType('img').props.alt, 'next.png');
  await act(async () => renderer.update(bubble([])));
  assert.equal(active.size, 0);
  assert.equal(renderer.root.findAllByType('img').length, 0);
});

test('挂起下载在卸载后完成不会登记 URL', async () => {
  let release;
  await mount(bubble([attachment], () => new Promise((resolve) => { release = resolve; })));
  assert.equal(active.size, 0);
  await unmount();
  await act(async () => release(new Blob(['late'])));
  assert.equal(active.size, 0);
});

test('同 ID 移除后重入，迟到的旧下载不能覆盖新预览', async () => {
  let release;
  let calls = 0;
  const load = async () => {
    calls += 1;
    if (calls === 1) return new Promise((resolve) => { release = resolve; });
    return new Blob(['current']);
  };
  await mount(bubble([attachment], load));
  await act(async () => renderer.update(bubble([], load)));
  await act(async () => renderer.update(bubble([attachment], load)));
  const current = renderer.root.findByType('img').props.src;
  await act(async () => release(new Blob(['obsolete'])));
  assert.equal(renderer.root.findByType('img').props.src, current);
  assert.equal(active.size, 1);
});

test('下载拒绝或没有下载能力不会创建 URL，保留文件按钮', async () => {
  for (const load of [async () => { throw new Error('fixture failure'); }, null]) {
    await mount(bubble([attachment], load));
    assert.equal(active.size, 0);
    assert.equal(renderer.root.findAllByType('img').length, 0);
    assert.ok(renderer.root.findAllByType('button').length > 0);
    await unmount();
  }
});

test('非图片下载仍在点击后创建并注销 URL', async () => {
  const previousDocument = globalThis.document;
  let clicked = 0;
  globalThis.document = { createElement: () => ({ click: () => { clicked += 1; } }) };
  try {
    await mount(bubble([{ ...attachment, mime: 'text/plain', name: 'fixture.txt' }]));
    const button = renderer.root.findByProps({ title: '点击下载' });
    await act(async () => button.props.onClick());
    assert.equal(clicked, 1);
    assert.equal(active.size, 0);
  } finally { globalThis.document = previousDocument; }
});

test('重复生命周期与 StrictMode 不保留 Blob URL', async () => {
  for (let cycle = 0; cycle < 10; cycle += 1) {
    await mount(React.createElement(React.StrictMode, null, bubble()));
    assert.equal(active.size, 1);
    await unmount();
    assert.equal(active.size, 0);
  }
});
