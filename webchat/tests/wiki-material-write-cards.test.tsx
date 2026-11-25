import assert from 'node:assert/strict';
import test from 'node:test';

import React from 'react';
import { act, create, type ReactTestInstance, type ReactTestRenderer } from 'react-test-renderer';

import { ChatContentProvider } from '@bk-lite/chat-content/ui';
import { WikiMaterialWriteCards } from '../packages/webchat-ui/src/components/WikiMaterialWriteCards';

const fullIncoming = `${'新'.repeat(4001)}TAIL`;
const queuedPolls: Array<() => void> = [];

if (typeof globalThis.window === 'undefined') {
  Object.defineProperty(globalThis, 'window', {
    configurable: true,
    writable: true,
    value: {
      setTimeout(fn: TimerHandler) {
        if (typeof fn === 'function') queuedPolls.push(fn);
        return queuedPolls.length;
      },
      clearTimeout() {
        return undefined;
      },
    },
  });
}

interface TransportCall {
  via: 'post' | 'fetch';
  path: string;
  body?: unknown;
}

interface Outcome {
  material_id: number;
  phase: string;
  summary: string;
  checks?: Array<Record<string, unknown>>;
}

const decisionOutcome: Outcome = {
  material_id: 7,
  phase: 'needs_decision',
  summary: '这条知识与已有内容冲突，请在对话里确认',
  checks: [
    {
      id: 3,
      page_title: '告警规则',
      current_body: '当前规则',
      incoming_body: '新的规则',
      actions: ['keep_current', 'use_new', 'edit_accept'],
      status: 'open',
    },
  ],
};

function installTransport(handle: (path: string, body: unknown) => unknown) {
  const calls: TransportCall[] = [];
  const post = async (path: string, body?: unknown) => {
    calls.push({ via: 'post', path, body });
    return handle(path, body);
  };
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input);
    const body = init?.body ? JSON.parse(String(init.body)) as unknown : undefined;
    calls.push({ via: 'fetch', path, body });
    try {
      const data = await handle(path, body);
      return { ok: true, status: 200, json: async () => ({ result: true, data }) };
    } catch (error) {
      const message = error instanceof Error && error.message ? error.message : '请求失败';
      return { ok: false, status: 400, json: async () => ({ result: false, message }) };
    }
  }) as typeof fetch;
  return { calls, post };
}

function visibleText(node: ReactTestInstance): string {
  return node.children.map((child) => (typeof child === 'string' ? child : visibleText(child))).join('');
}

function alertText(renderer: ReactTestRenderer): string {
  return renderer.root
    .findAll((node) => node.props?.role === 'alert')
    .map((node) => visibleText(node))
    .join('\n');
}

function buttonByName(renderer: ReactTestRenderer, name: string) {
  const found = renderer.root.findAll((node) => node.type === 'button' && visibleText(node) === name);
  assert.equal(found.length, 1, name);
  return found[0];
}

async function flush() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

async function mount(post?: (path: string, body?: unknown) => Promise<unknown>, writes = [{
  material_id: 7,
  phase: 'writing',
  summary: '正在写入，请在此等待结果',
}]) {
  let renderer: ReactTestRenderer | undefined;
  await act(async () => {
    renderer = create(
      <ChatContentProvider value={{ post }}>
        <WikiMaterialWriteCards writes={writes} />
      </ChatContentProvider>,
    );
  });
  await flush();
  assert.ok(renderer);
  return renderer;
}

test('shows the server message when confirming a wiki write fails', async () => {
  const { calls, post } = installTransport((path) => {
    if (path.includes('/decide/')) throw new Error('无法确认这条知识');
    return decisionOutcome;
  });
  const renderer = await mount(post);

  assert.equal(alertText(renderer), '');
  await act(async () => {
    buttonByName(renderer, '使用新知识').props.onClick();
  });
  await flush();

  assert.match(alertText(renderer), /无法确认这条知识/);
  assert.equal(buttonByName(renderer, '使用新知识').props.disabled, false);
  const decide = calls.find((call) => call.path.includes('/decide/'));
  assert.equal(decide?.via, 'post');
  assert.equal(decide?.path, '/opspilot/chat_wiki_material/7/decide/');
  assert.deepEqual(decide?.body, { check_id: 3, action: 'use_new' });
  await act(async () => {
    renderer.unmount();
  });
});

test('marks a shortened preview and submits the full incoming body', async () => {
  const { calls, post } = installTransport((path) => {
    if (path.includes('/decide/')) {
      return {
        material_id: 7,
        phase: 'published',
        summary: '已按编辑后的内容写入',
        checks: [],
      };
    }
    return {
      ...decisionOutcome,
      checks: [
        {
          ...decisionOutcome.checks?.[0],
          incoming_body: fullIncoming,
          actions: ['edit_accept'],
        },
      ],
    };
  });
  const renderer = await mount(post);

  const incoming = renderer.root.findAll((node) => node.type === 'section' && visibleText(node).includes('待确认内容'))[0];
  assert.ok(incoming, '待确认内容');
  assert.match(visibleText(incoming), /还有未展示的全文/);
  assert.equal(visibleText(incoming).includes('TAIL'), false);

  await act(async () => {
    buttonByName(renderer, '编辑后采用').props.onClick();
  });
  const draft = renderer.root.findByType('textarea');
  assert.equal(draft.props.value, fullIncoming);
  assert.equal(String(draft.props.value).endsWith('TAIL'), true);

  await act(async () => {
    buttonByName(renderer, '提交').props.onClick();
  });
  await flush();

  const decide = calls.find((call) => call.path.includes('/decide/'));
  assert.equal(decide?.via, 'post');
  assert.equal(decide?.path, '/opspilot/chat_wiki_material/7/decide/');
  assert.deepEqual(decide?.body, { check_id: 3, action: 'edit_accept', body: fullIncoming });
  await act(async () => {
    renderer.unmount();
  });
});

test('stacks the knowledge comparison below two 16rem tracks', async () => {
  const { post } = installTransport(() => decisionOutcome);
  const renderer = await mount(post, [{
    material_id: 7,
    phase: 'needs_decision',
    summary: '请确认',
  }]);

  const grids = renderer.root.findAll((node) => typeof node.props?.className === 'string' && node.props.className.includes('grid'));
  assert.equal(grids.some((node) => /(^|\s)grid-cols-2(\s|$)/.test(node.props.className)), false);
  const compare = grids.find((node) => node.props.className.includes('auto-fit'));
  assert.ok(compare);
  assert.match(compare.props.className, /minmax\(min\(100%,16rem\),1fr\)/);
  await act(async () => {
    renderer.unmount();
  });
});

test('shows a distinct status for each wiki write phase', async () => {
  const phases: Array<[string, string, string]> = [
    ['writing', '写入中', '请稍候'],
    ['needs_decision', '待确认', '请选择'],
    ['published', '已发布', '已经写入'],
    ['failed', '写入失败', '没有写上'],
  ];
  for (const [phase, label, summary] of phases) {
    const { post } = installTransport(() => ({
      material_id: 7,
      phase,
      summary,
      checks: [],
    }));
    const renderer = await mount(post, [{ material_id: 7, phase, summary }]);
    const text = visibleText(renderer.root);
    assert.match(text, new RegExp(label));
    assert.match(text, new RegExp(summary));
    await act(async () => {
      renderer.unmount();
    });
  }
});

test('shows a failed outcome read and keeps polling while the write is running', async () => {
  queuedPolls.length = 0;
  let reads = 0;
  const { post } = installTransport((path) => {
    if (!path.includes('/outcome/')) throw new Error('意外的请求');
    reads += 1;
    if (reads === 1) throw new Error('没有这条写入结果');
    return decisionOutcome;
  });
  const renderer = await mount(post);

  assert.match(alertText(renderer), /没有这条写入结果/);
  assert.match(visibleText(renderer.root), /正在写入，请在此等待结果/);
  assert.equal(queuedPolls.length, 1);

  await act(async () => {
    queuedPolls.shift()?.();
  });
  await flush();

  assert.equal(reads, 2);
  assert.equal(alertText(renderer), '');
  assert.match(visibleText(renderer.root), /待确认/);
  assert.equal(buttonByName(renderer, '使用新知识').props.disabled, false);
  await act(async () => {
    renderer.unmount();
  });
});

test('shows an error when the conversation cannot send the wiki request', async () => {
  installTransport(() => decisionOutcome);
  const renderer = await mount(undefined);
  assert.match(alertText(renderer), /当前对话不能执行此操作/);
  assert.equal(renderer.root.findAllByType('button').length, 0);
  await act(async () => {
    renderer.unmount();
  });
});
