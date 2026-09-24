import {
  BoundedConcurrentQueue,
  TransportQueueDroppedError,
  TransportQueueFullError,
} from './queue';
import { describe, expect, it } from 'vitest';

describe('BoundedConcurrentQueue', () => {
  it('allows the configured concurrency and bounds waiting items and bytes', async () => {
    const releases: Array<() => void> = [];
    const queue = new BoundedConcurrentQueue({
      maxInFlight: 2,
      maxQueuedItems: 1,
      maxQueuedBytes: 10,
    });
    const block = () =>
      new Promise<void>((resolve) => {
        releases.push(resolve);
      });

    const first = queue.enqueue(block, { bytes: 10, items: 1 });
    const second = queue.enqueue(block, { bytes: 10, items: 1 });
    const waiting = queue.enqueue(async () => {}, { bytes: 10, items: 1 });

    expect(queue.snapshot()).toEqual({
      inFlight: 2,
      queuedBytes: 10,
      queuedItems: 1,
    });
    await expect(
      queue.enqueue(async () => {}, { bytes: 1, items: 1 }),
    ).rejects.toBeInstanceOf(TransportQueueFullError);

    for (const release of releases.splice(0)) release();
    await Promise.all([first, second, waiting]);
    expect(queue.snapshot()).toEqual({
      inFlight: 0,
      queuedBytes: 0,
      queuedItems: 0,
    });
  });

  it('keeps a recording queue strictly serial', async () => {
    const order: string[] = [];
    let release: (() => void) | undefined;
    const queue = new BoundedConcurrentQueue({
      maxInFlight: 1,
      maxQueuedItems: 2,
      maxQueuedBytes: 8 * 1024 * 1024,
    });

    const first = queue.enqueue(
      () =>
        new Promise<void>((resolve) => {
          order.push('first:start');
          release = () => {
            order.push('first:end');
            resolve();
          };
        }),
      { bytes: 1, items: 1 },
    );
    const second = queue.enqueue(
      async () => {
        order.push('second');
      },
      { bytes: 1, items: 1 },
    );

    expect(order).toEqual(['first:start']);
    release?.();
    await Promise.all([first, second]);
    expect(order).toEqual(['first:start', 'first:end', 'second']);
  });

  it('drops the oldest replaceable work to preserve a protected task', async () => {
    let release: (() => void) | undefined;
    const dropped: string[] = [];
    const queue = new BoundedConcurrentQueue(
      { maxInFlight: 1, maxQueuedItems: 1, maxQueuedBytes: 10 },
      () => dropped.push('oldest'),
    );
    const running = queue.enqueue(
      () =>
        new Promise<void>((resolve) => {
          release = resolve;
        }),
      { bytes: 1, items: 1 },
    );
    const replaceable = queue.enqueue(async () => {}, {
      bytes: 10,
      droppable: true,
      items: 1,
    });
    const replaceableExpectation = expect(replaceable).rejects.toBeInstanceOf(
      TransportQueueDroppedError,
    );
    const protectedTask = queue.enqueue(async () => {}, {
      bytes: 10,
      droppable: false,
      items: 1,
    });

    await replaceableExpectation;
    expect(dropped).toEqual(['oldest']);
    release?.();
    await Promise.all([running, protectedTask]);
  });
});
