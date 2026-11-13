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
const output = fs.mkdtempSync(path.join(root, '.test-session-isolation-'));
process.on('exit', () => fs.rmSync(output, { recursive: true, force: true }));
const stubs = new Map([
  ['./components/MessageBubble', `const React = require('react'); exports.MessageBubble = ({message}) => React.createElement('div', {'data-message': message.id}, String(message.content));`],
  ['./components/PillComposer', `const React = require('react'); exports.PillComposer = (props) => React.createElement('button', {'data-send': true, disabled: props.loading, onClick: () => props.onSubmit('run')}, 'send');`],
  ['@ant-design/x', `exports.Bubble = () => null; exports.Sender = () => null;`],
]);
await build({
  entryPoints: [path.join(root, 'packages/webchat-ui/src/PlatformChat.tsx')],
  bundle: true,
  platform: 'node',
  format: 'cjs',
  external: ['react', 'react-dom'],
  alias: { '@webchat/core': path.join(root, 'packages/webchat-core/src/index.ts') },
  loader: { '.css': 'empty' },
  outfile: path.join(output, 'component.cjs'),
  plugins: [{
    name: 'visual-only-stubs',
    setup(build) {
      build.onResolve({filter: /.*/}, args => stubs.has(args.path) ? {path: args.path, namespace: 'stub'} : null);
      build.onLoad({filter: /.*/, namespace: 'stub'}, args => ({contents: stubs.get(args.path), loader: 'js'}));
    },
  }],
});
const { PlatformChat } = createRequire(import.meta.url)(path.join(output, 'component.cjs'));

function visible(node) {
  for (let current = node; current; current = current.parent) {
    if (current.props?.hidden || (current.props?.className || '').split(/\s+/).includes('hidden') || current.props?.style?.display === 'none') return false;
  }
  return true;
}

function visibleText(renderer) {
  return renderer.root.findAll(node => node.type === 'div' && node.props['data-message'] && visible(node))
    .map(node => node.children.join('')).join('\n');
}

const settle = () => new Promise(resolve => setTimeout(resolve, 0));

async function openDock() {
  const previous = { window: globalThis.window, document: globalThis.document, fetch: globalThis.fetch };
  globalThis.window = {
    innerWidth: 1280, innerHeight: 800,
    localStorage: {getItem: () => null, setItem() {}, removeItem() {}},
    addEventListener() {}, removeEventListener() {},
  };
  globalThis.document = {
    body: {style: {}}, documentElement: {style: {setProperty() {}}},
    visibilityState: 'visible', addEventListener() {}, removeEventListener() {}, querySelector: () => null,
  };
  const streams = new Map();
  const historyReads = [];
  const json = data => new Response(JSON.stringify({result: true, data}), {headers: {'content-type': 'application/json'}});
  globalThis.fetch = async (url, init = {}) => {
    const target = String(url);
    if (target.includes('/fixture/apps')) return json([{id: 'app-1', channel_id: 'channel-1', name: '助手'}]);
    if (target.includes('/fixture/sessions')) return json([
      {session_id: 'session-a', title: '对话 A'}, {session_id: 'session-b', title: '对话 B'},
    ]);
    if (target.includes('/fixture/messages')) {
      historyReads.push(target);
      return json([]);
    }
    if (target.includes('/fixture/delete')) return json({});
    if (target.includes('/fixture/chat')) {
      const {session_id} = JSON.parse(init.body);
      let controller;
      const body = new ReadableStream({start(value) {controller = value;}});
      streams.set(session_id, {controller, signal: init.signal});
      return new Response(body, {headers: {'content-type': 'text/event-stream'}});
    }
    throw new Error(`Unexpected fetch: ${target}`);
  };
  const platform = {
    applicationsUrl: '/fixture/apps', sessionsUrl: '/fixture/sessions?channel_id={channelId}',
    messagesUrl: '/fixture/messages?session_id={sessionId}', chatUrlTemplate: '/fixture/chat/{channelId}',
    deleteSessionUrl: '/fixture/delete/{sessionId}',
  };
  let renderer;
  await act(async () => { renderer = create(React.createElement(PlatformChat, {platform, streamingTextBatching: false})); });
  await act(async () => {
    renderer.root.findByProps({'aria-label': '打开对话'}).props.onClick({preventDefault() {}});
    await settle();
  });
  return {
    renderer, streams, historyReads,
    async select(title) {
      if (!renderer.root.findAllByType('aside').length) {
        await act(async () => renderer.root.findByProps({'aria-label': '历史会话'}).props.onClick());
      }
      const item = renderer.root.findAll(node => node.type === 'button' && node.props['aria-label'] === title)[0];
      assert.ok(item, `Missing session: ${title}`);
      await act(async () => {item.props.onClick(); await settle();});
    },
    async send() {
      await act(async () => {
        renderer.root.findAll(node => node.type === 'button' && node.props['data-send'] && visible(node))[0].props.onClick();
        await settle();
      });
    },
    async emit(sessionId, ...events) {
      await act(async () => {
        const stream = streams.get(sessionId);
        for (const event of events) stream.controller.enqueue(new TextEncoder().encode(`data: ${JSON.stringify(event)}\n\n`));
        await settle();
      });
    },
    async finish(sessionId) {
      await act(async () => { streams.get(sessionId).controller.close(); await settle(); });
    },
    async close() {
      await act(async () => renderer.unmount());
      Object.assign(globalThis, previous);
    },
  };
}

test('切换对话后旧 SSE 结果留在原对话，两条流互不覆盖', async () => {
  const dock = await openDock();
  try {
    await dock.select('对话 A');
    await dock.send();
    await dock.emit('session-a', {type: 'TEXT_MESSAGE_START', messageId: 'a', role: 'assistant'}, {type: 'TEXT_MESSAGE_CONTENT', messageId: 'a', delta: 'A 开始'});
    assert.match(visibleText(dock.renderer), /A 开始/);
    await dock.select('对话 B');
    await dock.emit('session-a', {type: 'TEXT_MESSAGE_CONTENT', messageId: 'a', delta: '，A 完成'});
    assert.doesNotMatch(visibleText(dock.renderer), /A 完成/);
    assert.equal(dock.streams.get('session-a').signal.aborted, false, '切换对话不得中止原执行');
    await dock.send();
    await dock.emit('session-b', {type: 'TEXT_MESSAGE_START', messageId: 'b', role: 'assistant'}, {type: 'TEXT_MESSAGE_CONTENT', messageId: 'b', delta: 'B 结果'});
    await dock.emit('session-a', {type: 'TEXT_MESSAGE_END', messageId: 'a'}, {type: 'RUN_FINISHED', threadId: 'a', runId: 'a'});
    await dock.finish('session-a');
    const activeSend = dock.renderer.root.findAll(node => node.type === 'button' && node.props['data-send'] && visible(node))[0];
    assert.equal(activeSend.props.disabled, true, 'A 请求结束不能解除 B 的执行中状态');
    assert.match(visibleText(dock.renderer), /B 结果/);
    assert.doesNotMatch(visibleText(dock.renderer), /A 完成/);
    await dock.select('对话 A');
    assert.match(visibleText(dock.renderer), /A 开始，A 完成/);
    assert.doesNotMatch(visibleText(dock.renderer), /B 结果/);
    assert.equal(dock.historyReads.filter(url => url.includes('session-a')).length, 1, '返回运行中的对话不得用历史快照覆盖流式状态');
  } finally { await dock.close(); }
});

test('后台对话生成的文件不进入当前对话文件列表', async () => {
  const dock = await openDock();
  try {
    await dock.select('对话 A');
    await dock.send();
    await dock.select('对话 B');
    await dock.emit('session-a',
      {type: 'TOOL_CALL_START', toolCallId: 'export-a', toolCallName: 'generate_attachment_file'},
      {type: 'TOOL_CALL_RESULT', messageId: 'result-a', toolCallId: 'export-a', content: JSON.stringify({filename: 'A-report.xlsx', file_url: '/api/proxy/opspilot/download/a/'})},
    );
    await act(async () => dock.renderer.root.findByProps({'aria-label': '已生成文件'}).props.onClick());
    assert.equal(dock.renderer.root.findAllByProps({title: 'A-report.xlsx'}).length, 0);
    await dock.select('对话 A');
    await act(async () => dock.renderer.root.findByProps({'aria-label': '已生成文件'}).props.onClick());
    assert.equal(dock.renderer.root.findAllByProps({title: 'A-report.xlsx'}).length, 1);
  } finally { await dock.close(); }
});

test('新对话执行期间切走后仍可从历史栏返回，结果不丢失', async () => {
  const dock = await openDock();
  try {
    await act(async () => {
      dock.renderer.root.findByProps({'aria-label': '新对话'}).props.onClick();
      await settle();
    });
    await dock.send();
    const draftId = [...dock.streams.keys()][0];
    await dock.select('对话 B');
    await dock.emit(draftId, {type: 'TEXT_MESSAGE_START', messageId: 'draft', role: 'assistant'}, {type: 'TEXT_MESSAGE_CONTENT', messageId: 'draft', delta: 'draft result'});
    assert.doesNotMatch(visibleText(dock.renderer), /draft result/);
    await dock.select('run');
    assert.match(visibleText(dock.renderer), /draft result/);
    assert.equal(dock.streams.get(draftId).signal.aborted, false);
  } finally { await dock.close(); }
});

test('删除后台对话只回收该对话的流，当前对话继续执行', async () => {
  const dock = await openDock();
  try {
    await dock.select('对话 A');
    await dock.send();
    await dock.select('对话 B');
    await dock.send();
    const row = dock.renderer.root.findByProps({'aria-label': '对话 A'}).parent;
    await act(async () => row.findByProps({'aria-label': '删除会话'}).props.onClick());
    await act(async () => {
      row.findAll(node => node.type === 'button' && node.children.includes('删除'))[0].props.onClick();
      await settle();
    });
    assert.equal(dock.streams.get('session-a').signal.aborted, true);
    assert.equal(dock.streams.get('session-b').signal.aborted, false);
    await dock.emit('session-b', {type: 'TEXT_MESSAGE_START', messageId: 'b', role: 'assistant'}, {type: 'TEXT_MESSAGE_CONTENT', messageId: 'b', delta: 'B still running'});
    assert.match(visibleText(dock.renderer), /B still running/);
  } finally { await dock.close(); }
});
