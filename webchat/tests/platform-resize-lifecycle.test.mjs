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
const output = path.join(root, '.test-dist', 'platform-resize');
fs.mkdirSync(output, { recursive: true });
process.on('exit', () => {
  if (!process.env.NODE_V8_COVERAGE) fs.rmSync(output, { recursive: true, force: true });
});
buildSync({
  entryPoints: [path.join(root, 'packages/webchat-ui/src/PlatformChat.tsx')],
  bundle: true,
  platform: 'node',
  format: 'cjs',
  sourcemap: 'inline',
  external: ['react', 'react-dom'],
  alias: { '@webchat/core': path.join(root, 'packages/webchat-core/src/index.ts') },
  loader: { '.css': 'empty' },
  outfile: path.join(output, 'component.cjs'),
});
const { PlatformChat } = createRequire(import.meta.url)(path.join(output, 'component.cjs'));

class WindowTarget extends EventTarget {
  listeners = new Map(['pointermove', 'pointerup', 'pointercancel'].map((name) => [name, new Set()]));
  innerWidth = 1200;
  innerHeight = 800;
  localStorage = { getItem: () => null, setItem: () => {} };
  addEventListener(name, listener, options) {
    this.listeners.get(name)?.add(listener);
    super.addEventListener(name, listener, options);
  }
  removeEventListener(name, listener, options) {
    this.listeners.get(name)?.delete(listener);
    super.removeEventListener(name, listener, options);
  }
  retained() {
    return [...this.listeners.values()].reduce((sum, listeners) => sum + listeners.size, 0);
  }
}

async function fixture(run, { saveFails = false, savePending = false } = {}) {
  const previous = { window: globalThis.window, document: globalThis.document, fetch: globalThis.fetch };
  const window = new WindowTarget();
  const document = Object.assign(new EventTarget(), {
    body: { style: { cursor: 'crosshair' } },
    querySelector: () => null,
    documentElement: { style: { setProperty() {} } },
  });
  const saves = [];
  let releaseSave;
  globalThis.window = window;
  globalThis.document = document;
  globalThis.fetch = async (_url, options) => {
    if (options.method === 'POST') {
      saves.push(JSON.parse(options.body));
      if (saveFails) throw new Error('fixture save failed');
      if (savePending) await new Promise((resolve) => { releaseSave = resolve; });
    }
    return { ok: true, status: 200, headers: { get: () => 'application/json' }, json: async () => ({ data: [] }) };
  };
  const platform = { applicationsUrl: '/fixture/apps', sessionsUrl: '/fixture/sessions', messagesUrl: '/fixture/messages', chatUrlTemplate: '/fixture/chat' };
  let renderer;
  const mount = async () => {
    await act(async () => { renderer = create(React.createElement(PlatformChat, { platform, canManageAgents: true })); });
    await act(async () => { renderer.root.findByProps({ 'aria-label': '打开对话' }).props.onClick({ preventDefault() {} }); });
  };
  const start = async (button = 0) => {
    await act(async () => { renderer.root.findByProps({ role: 'separator' }).props.onPointerDown({ button, clientX: 100, preventDefault() {}, stopPropagation() {} }); });
  };
  const dispatch = async (name, clientX = 60) => {
    const event = Object.assign(new Event(name), { clientX });
    await act(async () => { window.dispatchEvent(event); });
  };
  const unmount = async () => { await act(async () => { renderer?.unmount(); }); renderer = undefined; };
  try { await run({ window, document, saves, mount, start, dispatch, unmount, width: () => renderer.root.findByProps({ role: 'separator' }).props['aria-valuenow'] }); }
  finally {
    await unmount();
    await dispatch('pointercancel');
    releaseSave?.();
    await Promise.resolve();
    Object.assign(globalThis, previous);
  }
}

test('拖拽中卸载会回收监听器与原光标，迟到事件不保存宽度', () => fixture(async ({ window, document, saves, mount, start, dispatch, unmount }) => {
  await mount();
  await start();
  assert.equal(window.retained(), 3);
  await unmount();
  assert.equal(window.retained(), 0);
  assert.equal(document.body.style.cursor, 'crosshair');
  await dispatch('pointermove');
  await dispatch('pointerup');
  assert.equal(saves.length, 0);
}));

for (const end of ['pointerup', 'pointercancel']) {
  test(`${end} 保持宽度保存和幂等清理`, () => fixture(async ({ window, document, saves, mount, start, dispatch, unmount, width }) => {
    await mount();
    await start();
    await dispatch('pointermove');
    assert.equal(width(), 420);
    await dispatch(end);
    assert.equal(window.retained(), 0);
    assert.equal(document.body.style.cursor, 'crosshair');
    assert.equal(saves.length, 1);
    assert.deepEqual(saves, [{ width: 420 }]);
    await dispatch(end);
    await unmount();
    assert.equal(saves.length, 1);
  }));
}

test('重复开始替换上次拖拽，重复卸载不留下回调', () => fixture(async ({ window, document, saves, mount, start, unmount }) => {
  for (let cycle = 0; cycle < 10; cycle += 1) {
    await mount();
    await start(2);
    assert.equal(window.retained(), 0);
    await start();
    await start();
    assert.equal(window.retained(), 3);
    await unmount();
    await unmount();
    assert.equal(window.retained(), 0);
    assert.equal(document.body.style.cursor, 'crosshair');
  }
  assert.equal(saves.length, 0);
}));


test('宽度保存失败不影响已完成的资源清理', () => fixture(async ({ window, document, saves, mount, start, dispatch, unmount }) => {
  await mount();
  await start();
  await dispatch('pointerup');
  await unmount();
  assert.equal(window.retained(), 0);
  assert.equal(document.body.style.cursor, 'crosshair');
  assert.equal(saves.length, 1);
}, { saveFails: true }));


test('宽度保存长时间等待不延长拖拽资源生命周期', () => fixture(async ({ window, document, saves, mount, start, dispatch, unmount }) => {
  await mount();
  await start();
  await dispatch('pointerup');
  await unmount();
  await new Promise((resolve) => setTimeout(resolve, 20));
  assert.equal(window.retained(), 0);
  assert.equal(document.body.style.cursor, 'crosshair');
  assert.deepEqual(saves, [{ width: 420 }]);
}, { savePending: true }));
