import { describe, expect, it } from 'vitest';

import {
  DashboardRuntimeScheduler,
  RuntimeRequestCancelledError,
} from '@/app/ops-analysis/utils/dashboardRuntimeScheduler';

const deferred = <T,>() => {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
};

describe('DashboardRuntimeScheduler', () => {
  it('limits physical requests to six and drains the queue', async () => {
    const scheduler = new DashboardRuntimeScheduler({ concurrency: 6 });
    const requests = Array.from({ length: 100 }, () => deferred<number>());
    let running = 0;
    let peak = 0;

    const promises = requests.map((request, index) =>
      scheduler.schedule({
        consumerId: `widget-${index}`,
        ownerId: `widget-${index}`,
        physicalKey: `request-${index}`,
        priority: { cause: 1, visibility: 0, distance: 0, order: index },
        start: async () => {
          running += 1;
          peak = Math.max(peak, running);
          try {
            return await request.promise;
          } finally {
            running -= 1;
          }
        },
      }),
    );

    await Promise.resolve();
    expect(scheduler.snapshot()).toMatchObject({ running: 6, queued: 94 });
    expect(peak).toBe(6);

    for (let start = 0; start < requests.length; start += 6) {
      const end = Math.min(start + 6, requests.length);
      requests.slice(start, end).forEach((request, offset) => request.resolve(start + offset));
      await Promise.all(promises.slice(start, end));
      expect(peak).toBe(6);
    }

    await expect(Promise.all(promises)).resolves.toEqual(
      Array.from({ length: 100 }, (_, index) => index),
    );
    expect(scheduler.snapshot()).toMatchObject({ running: 0, queued: 0 });
  });

  it('orders queued work by cause, visibility, distance, then canvas order', async () => {
    const scheduler = new DashboardRuntimeScheduler({ concurrency: 1 });
    const blocker = deferred<void>();
    const order: string[] = [];
    const running = scheduler.schedule({
      consumerId: 'running', ownerId: 'running', physicalKey: 'running',
      priority: { cause: 0, visibility: 0, distance: 0, order: 0 },
      start: () => blocker.promise,
    });
    const cases = [
      ['periodic-visible', { cause: 2, visibility: 0, distance: 0, order: 0 }],
      ['initial-near', { cause: 1, visibility: 1, distance: 10, order: 3 }],
      ['manual-far', { cause: 0, visibility: 1, distance: 900, order: 9 }],
      ['initial-visible-later', { cause: 1, visibility: 0, distance: 0, order: 4 }],
      ['initial-visible-earlier', { cause: 1, visibility: 0, distance: 0, order: 2 }],
    ] as const;
    const queued = cases.map(([name, priority]) => scheduler.schedule({
      consumerId: name,
      ownerId: name,
      physicalKey: name,
      priority,
      start: async () => {
        order.push(name);
        return name;
      },
    }));

    blocker.resolve();
    await running;
    await Promise.all(queued);
    expect(order).toEqual([
      'manual-far',
      'initial-visible-earlier',
      'initial-visible-later',
      'initial-near',
      'periodic-visible',
    ]);
  });

  it('releases a slot after physical failure', async () => {
    const scheduler = new DashboardRuntimeScheduler({ concurrency: 1 });
    const failed = deferred<string>();
    let nextStarted = false;
    const first = scheduler.schedule({
      consumerId: 'failed', ownerId: 'failed', physicalKey: 'failed',
      priority: { cause: 0, visibility: 0, distance: 0, order: 0 },
      start: () => failed.promise,
    });
    const next = scheduler.schedule({
      consumerId: 'next', ownerId: 'next', physicalKey: 'next',
      priority: { cause: 0, visibility: 0, distance: 0, order: 1 },
      start: async () => {
        nextStarted = true;
        return 'next';
      },
    });

    failed.reject(new Error('timeout'));
    await expect(first).rejects.toThrow('timeout');
    await expect(next).resolves.toBe('next');
    expect(nextStarted).toBe(true);
    expect(scheduler.snapshot().running).toBe(0);
  });

  it('releases a slot when start throws synchronously', async () => {
    const scheduler = new DashboardRuntimeScheduler({ concurrency: 1 });
    const first = scheduler.schedule({
      consumerId: 'throw', ownerId: 'throw', physicalKey: 'throw',
      priority: { cause: 0, visibility: 0, distance: 0, order: 0 },
      start: () => { throw new Error('sync failure'); },
    });
    const next = scheduler.schedule({
      consumerId: 'next-sync', ownerId: 'next-sync', physicalKey: 'next-sync',
      priority: { cause: 0, visibility: 0, distance: 0, order: 1 },
      start: async () => 'next',
    });

    await expect(first).rejects.toThrow('sync failure');
    await expect(next).resolves.toBe('next');
    expect(scheduler.snapshot()).toMatchObject({ running: 0, queued: 0 });
  });

  it('allows an immediate same-key reschedule from a settled consumer', async () => {
    const scheduler = new DashboardRuntimeScheduler({ concurrency: 1 });
    const first = scheduler.schedule({
      consumerId: 'first-key', ownerId: 'first-key', physicalKey: 'shared-key',
      priority: { cause: 0, visibility: 0, distance: 0, order: 0 },
      start: async () => 'first',
    });

    await expect(first).resolves.toBe('first');
    await expect(scheduler.schedule({
      consumerId: 'second-key', ownerId: 'second-key', physicalKey: 'shared-key',
      priority: { cause: 0, visibility: 0, distance: 0, order: 0 },
      start: async () => 'second',
    })).resolves.toBe('second');
  });

  it('updates owner position without overwriting the request cause', async () => {
    const scheduler = new DashboardRuntimeScheduler({ concurrency: 1 });
    const blocker = deferred<void>();
    const order: string[] = [];
    const running = scheduler.schedule({
      consumerId: 'running', ownerId: 'running', physicalKey: 'running',
      priority: { cause: 0, visibility: 0, distance: 0, order: 0 },
      start: () => blocker.promise,
    });
    const manual = scheduler.schedule({
      consumerId: 'manual', ownerId: 'manual-owner', physicalKey: 'manual',
      priority: { cause: 0, visibility: 1, distance: 100, order: 2 },
      start: async () => { order.push('manual'); },
    });
    const initial = scheduler.schedule({
      consumerId: 'initial', ownerId: 'initial-owner', physicalKey: 'initial',
      priority: { cause: 1, visibility: 0, distance: 0, order: 1 },
      start: async () => { order.push('initial'); },
    });

    scheduler.updateOwnerPriority('manual-owner', {
      cause: 1,
      visibility: 1,
      distance: 500,
      order: 9,
    });
    blocker.resolve();
    await running;
    await Promise.all([manual, initial]);
    expect(order).toEqual(['manual', 'initial']);
  });

  it('accepts B and C into physical scheduling without waiting for A to settle', async () => {
    const scheduler = new DashboardRuntimeScheduler({ concurrency: 2 });
    const a = deferred<string>();
    const b = deferred<string>();
    const c = deferred<string>();
    const started: string[] = [];
    const schedule = (name: string, request: ReturnType<typeof deferred<string>>) =>
      scheduler.schedule({
        consumerId: name,
        ownerId: 'same-widget',
        physicalKey: name,
        priority: { cause: 0, visibility: 0, distance: 0, order: 0 },
        start: () => {
          started.push(name);
          return request.promise;
        },
      });

    const aPromise = schedule('A', a);
    const bPromise = schedule('B', b);
    const cPromise = schedule('C', c);
    await Promise.resolve();
    expect(started).toEqual(['A', 'B']);
    expect(scheduler.snapshot()).toMatchObject({ running: 2, queued: 1 });

    b.resolve('B');
    await bPromise;
    await Promise.resolve();
    expect(started).toEqual(['A', 'B', 'C']);
    c.resolve('C');
    a.resolve('A');
    await expect(Promise.all([aPromise, cPromise])).resolves.toEqual(['A', 'C']);
  });

  it('dedupes before acquiring a slot and promotes a queued duplicate', async () => {
    const scheduler = new DashboardRuntimeScheduler({ concurrency: 1 });
    const blocker = deferred<string>();
    const shared = deferred<string>();
    const order: string[] = [];

    const blockerPromise = scheduler.schedule({
      consumerId: 'blocker', ownerId: 'blocker', physicalKey: 'blocker',
      priority: { cause: 0, visibility: 0, distance: 0, order: 0 },
      start: () => blocker.promise,
    });
    const prefetchPromise = scheduler.schedule({
      consumerId: 'prefetch', ownerId: 'prefetch', physicalKey: 'shared',
      priority: { cause: 2, visibility: 1, distance: 900, order: 2 },
      start: () => {
        order.push('shared');
        return shared.promise;
      },
    });
    const otherPromise = scheduler.schedule({
      consumerId: 'other', ownerId: 'other', physicalKey: 'other',
      priority: { cause: 1, visibility: 1, distance: 100, order: 1 },
      start: async () => {
        order.push('other');
        return 'other';
      },
    });
    const visibleDuplicatePromise = scheduler.schedule({
      consumerId: 'visible', ownerId: 'visible', physicalKey: 'shared',
      priority: { cause: 0, visibility: 0, distance: 0, order: 3 },
      start: () => {
        throw new Error('duplicate must not create another physical request');
      },
    });

    expect(scheduler.snapshot()).toMatchObject({ running: 1, queued: 2 });
    blocker.resolve('blocker');
    await blockerPromise;
    await Promise.resolve();
    expect(order).toEqual(['shared']);
    shared.resolve('shared');

    await expect(prefetchPromise).resolves.toBe('shared');
    await expect(visibleDuplicatePromise).resolves.toBe('shared');
    await expect(otherPromise).resolves.toBe('other');
  });

  it('cancels only queued consumers and never starts work after destroy', async () => {
    const scheduler = new DashboardRuntimeScheduler({ concurrency: 1 });
    const blocker = deferred<string>();
    const blockerPromise = scheduler.schedule({
      consumerId: 'started', ownerId: 'started', physicalKey: 'started',
      priority: { cause: 0, visibility: 0, distance: 0, order: 0 },
      start: () => blocker.promise,
    });
    const queuedPromise = scheduler.schedule({
      consumerId: 'queued', ownerId: 'queued-owner', physicalKey: 'queued',
      priority: { cause: 0, visibility: 0, distance: 0, order: 1 },
      start: async () => 'must-not-start',
    });

    scheduler.cancelQueuedForOwner('queued-owner');
    await expect(queuedPromise).rejects.toBeInstanceOf(RuntimeRequestCancelledError);
    scheduler.destroy();
    blocker.resolve('started-result');
    await expect(blockerPromise).resolves.toBe('started-result');
    expect(scheduler.snapshot()).toMatchObject({ destroyed: true, queued: 0 });
    await expect(scheduler.schedule({
      consumerId: 'late', ownerId: 'late', physicalKey: 'late',
      priority: { cause: 0, visibility: 0, distance: 0, order: 0 },
      start: async () => 'late',
    })).rejects.toBeInstanceOf(RuntimeRequestCancelledError);
  });
});
