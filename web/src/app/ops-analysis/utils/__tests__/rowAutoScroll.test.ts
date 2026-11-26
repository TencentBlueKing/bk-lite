import assert from 'node:assert/strict';
import test from 'node:test';
import { findScrollViewport, startRowAutoScroll, type RowScrollRead } from '../rowAutoScroll';

type Listener = () => void;

const fakeViewport = () => {
  const listeners = new Map<string, Set<Listener>>();
  const rows = [
    { offsetTop: 0, offsetHeight: 20 },
    { offsetTop: 20, offsetHeight: 20 },
  ];
  return {
    scrollTop: 0,
    scrollHeight: 100,
    clientHeight: 40,
    addEventListener(type: string, listener: Listener) {
      const set = listeners.get(type) ?? new Set<Listener>();
      set.add(listener);
      listeners.set(type, set);
    },
    removeEventListener(type: string, listener: Listener) {
      listeners.get(type)?.delete(listener);
    },
    querySelectorAll() {
      return rows;
    },
    enter() {
      listeners.get('pointerenter')?.forEach((listener) => listener());
    },
    leave() {
      listeners.get('pointerleave')?.forEach((listener) => listener());
    },
  };
};

const installFrames = () => {
  const queue: Array<{ id: number; callback: FrameRequestCallback }> = [];
  let nextId = 1;
  const originalFrame = globalThis.requestAnimationFrame;
  const originalCancel = globalThis.cancelAnimationFrame;
  globalThis.requestAnimationFrame = (callback: FrameRequestCallback) => {
    const id = nextId;
    nextId += 1;
    queue.push({ id, callback });
    return id;
  };
  globalThis.cancelAnimationFrame = (id: number) => {
    const index = queue.findIndex((item) => item.id === id);
    if (index >= 0) queue.splice(index, 1);
  };
  return {
    pending() {
      return queue.length;
    },
    flush(time: number) {
      const batch = queue.splice(0, queue.length);
      batch.forEach((item) => item.callback(time));
    },
    restore() {
      globalThis.requestAnimationFrame = originalFrame;
      globalThis.cancelAnimationFrame = originalCancel;
    },
  };
};

test('off does not schedule a frame or change scrollTop', () => {
  const frames = installFrames();
  try {
    const viewport = fakeViewport();
    const reads: RowScrollRead[] = [
      { autoScroll: undefined, screenEnabled: false },
      { autoScroll: true, screenEnabled: false },
      { autoScroll: undefined, screenEnabled: true },
    ];
    reads.forEach((read) => {
      viewport.scrollTop = 12;
      const stop = startRowAutoScroll(
        viewport as unknown as HTMLElement,
        () => read,
        '[data-auto-scroll-row]',
      );
      frames.flush(1000);
      assert.equal(viewport.scrollTop, 12);
      stop();
    });
  } finally {
    frames.restore();
  }
});

test('motion travels part of a row and hover holds the offset', () => {
  const frames = installFrames();
  try {
    const viewport = fakeViewport();
    const stop = startRowAutoScroll(
      viewport as unknown as HTMLElement,
      () => ({ autoScroll: true, screenEnabled: true }),
      '.ant-table-row',
    );
    frames.flush(0);
    assert.equal(viewport.scrollTop, 0);
    frames.flush(1000);
    assert.equal(viewport.scrollTop, 10);
    viewport.enter();
    frames.flush(2000);
    assert.equal(viewport.scrollTop, 10);
    viewport.leave();
    frames.flush(3000);
    assert.equal(viewport.scrollTop, 20);
    stop();
    frames.flush(3000);
    assert.equal(viewport.scrollTop, 20);
  } finally {
    frames.restore();
  }
});

test('passing the end returns to the top', () => {
  const frames = installFrames();
  try {
    const viewport = fakeViewport();
    viewport.scrollTop = 50;
    startRowAutoScroll(
      viewport as unknown as HTMLElement,
      () => ({ autoScroll: true, screenEnabled: true }),
      '[data-auto-scroll-row]',
    );
    frames.flush(0);
    frames.flush(1000);
    assert.equal(viewport.scrollTop, 0);
  } finally {
    frames.restore();
  }
});

test('no overflow does not move', () => {
  const frames = installFrames();
  try {
    const viewport = fakeViewport();
    viewport.scrollHeight = 40;
    viewport.clientHeight = 40;
    viewport.scrollTop = 0;
    startRowAutoScroll(
      viewport as unknown as HTMLElement,
      () => ({ autoScroll: true, screenEnabled: true }),
      '[data-auto-scroll-row]',
    );
    assert.equal(frames.pending(), 0);
    frames.flush(0);
    frames.flush(1000);
    assert.equal(frames.pending(), 0);
    assert.equal(viewport.scrollTop, 0);
  } finally {
    frames.restore();
  }
});

test('saved seconds per row replace the two second default', () => {
  const frames = installFrames();
  try {
    const viewport = fakeViewport();
    startRowAutoScroll(
      viewport as unknown as HTMLElement,
      () => ({ autoScroll: true, screenEnabled: true, scrollSeconds: 1 }),
      '[data-auto-scroll-row]',
    );
    frames.flush(0);
    frames.flush(1000);
    assert.equal(viewport.scrollTop, 20);
  } finally {
    frames.restore();
  }
});

test('hover on the pause target holds the offset', () => {
  const frames = installFrames();
  try {
    const viewport = fakeViewport();
    const pause = fakeViewport();
    startRowAutoScroll(
      viewport as unknown as HTMLElement,
      () => ({ autoScroll: true, screenEnabled: true }),
      '[data-auto-scroll-row]',
      pause as unknown as HTMLElement,
    );
    frames.flush(0);
    frames.flush(1000);
    assert.equal(viewport.scrollTop, 10);
    pause.enter();
    frames.flush(2000);
    assert.equal(viewport.scrollTop, 10);
  } finally {
    frames.restore();
  }
});

test('whole-pixel scrollTop still advances across subpixel frames', () => {
  const frames = installFrames();
  try {
    const viewport = fakeViewport();
    const content = { style: { transform: '' } };
    (viewport as { firstElementChild?: unknown }).firstElementChild = content;
    let stored = 0;
    Object.defineProperty(viewport, 'scrollTop', {
      configurable: true,
      get() {
        return stored;
      },
      set(value: number) {
        stored = Math.trunc(value);
      },
    });
    startRowAutoScroll(
      viewport as unknown as HTMLElement,
      () => ({ autoScroll: true, screenEnabled: true }),
      '[data-auto-scroll-row]',
    );
    frames.flush(0);
    frames.flush(16);
    assert.equal(viewport.scrollTop, 0);
    frames.flush(216);
    assert.equal(viewport.scrollTop, 2);
    assert.equal(content.style.transform, '');
  } finally {
    frames.restore();
  }
});

test('findScrollViewport prefers the element that already overflows', () => {
  const body = { scrollHeight: 40, clientHeight: 40 };
  const content = { scrollHeight: 80, clientHeight: 40 };
  const root = {
    querySelector(selector: string) {
      if (selector === '.ant-table-body') return body;
      if (selector === '.ant-table-content') return content;
      return null;
    },
  };
  assert.equal(
    findScrollViewport(root as unknown as ParentNode, ['.ant-table-body', '.ant-table-content']),
    content,
  );
  assert.equal(findScrollViewport(null, ['.ant-table-body']), null);
});
