import { afterEach, describe, expect, it, vi } from 'vitest';

import { captionFromOption } from '@/components/chart-snapshot';
import { matchPilots } from '../pilots';
import { createPageContextRegistry, mergePageContexts } from '../registry';
import { PAGE_CONTEXT_PROVIDER_TIMEOUT_MS, type AiPageContextPilot } from '../types';

describe('ai-page-context registry', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('registers, collects, and unregisters providers', async () => {
    const registry = createPageContextRegistry({ getPathname: () => '/cmdb', pilots: [] });
    expect(registry.hasAvailable()).toBe(false);
    const unregister = registry.register(() => ({
      title: '告警',
      sections: [{ id: 'a', label: '筛选', content: 'level=critical', priority: 3 }],
    }));
    expect(registry.hasAvailable()).toBe(true);
    const snapshot = await registry.collect();
    expect(snapshot?.title).toBe('告警');
    expect(snapshot?.sections?.[0].content).toContain('critical');
    unregister();
    expect(registry.hasAvailable()).toBe(false);
    await expect(registry.collect()).resolves.toBeNull();
  });

  it('matches pilots by pathname without loading until collect', async () => {
    const load = vi.fn(async () => ({
      getMessage: () => ({ title: 'pilot-cache', currentTime: '1' }),
      getContext: async () => ({
        title: 'pilot',
        sections: [{ id: 'p', label: '仪表盘', content: 'host', priority: 1 }],
      }),
    }));
    const pilots: AiPageContextPilot[] = [
      { test: (pathname) => pathname.includes('/monitor/view/dashboard/'), load },
    ];
    const registry = createPageContextRegistry({
      getPathname: () => '/monitor/view/dashboard/host',
      pilots,
    });
    expect(registry.hasAvailable()).toBe(true);
    expect(load).not.toHaveBeenCalled();
    const snapshot = await registry.collect();
    expect(load).toHaveBeenCalledTimes(1);
    expect(snapshot?.title).toBe('pilot');
  });

  it('reuses getContext when title and currentTime are unchanged', async () => {
    const getContext = vi.fn(async () => ({
      title: 'cached-title',
      sections: [{ id: 's', label: 'S', content: 'payload', priority: 1 }],
    }));
    const registry = createPageContextRegistry({
      getPathname: () => '/monitor/view/dashboard/host',
      pilots: [
        {
          test: () => true,
          load: async () => ({
            getMessage: () => ({ title: 'cache-key', currentTime: 't1' }),
            getContext,
          }),
        },
      ],
    });
    await registry.collect();
    await registry.collect();
    expect(getContext).toHaveBeenCalledTimes(1);
  });

  it('recollects when currentTime changes or is missing', async () => {
    let tick = 't1';
    const getContext = vi.fn(async () => ({
      sections: [{ id: 's', label: 'S', content: tick, priority: 1 }],
    }));
    const registry = createPageContextRegistry({
      getPathname: () => '/x',
      pilots: [
        {
          test: () => true,
          load: async () => ({
            getMessage: () => ({ title: 'k', currentTime: tick }),
            getContext,
          }),
        },
      ],
    });
    await registry.collect();
    tick = 't2';
    await registry.collect();
    expect(getContext).toHaveBeenCalledTimes(2);

    const alwaysFresh = vi.fn(async () => ({
      sections: [{ id: 's', label: 'S', content: 'fresh', priority: 1 }],
    }));
    const noTime = createPageContextRegistry({
      getPathname: () => '/y',
      pilots: [
        {
          test: () => true,
          load: async () => ({
            getMessage: () => ({ title: 'no-time' }),
            getContext: alwaysFresh,
          }),
        },
      ],
    });
    await noTime.collect();
    await noTime.collect();
    expect(alwaysFresh).toHaveBeenCalledTimes(2);
  });

  it('does not match unrelated routes', () => {
    expect(matchPilots('/cmdb/resource', [
      {
        test: (pathname) => pathname.includes('/monitor/view/dashboard/'),
        load: async () => ({
          getMessage: () => ({ title: 'x' }),
          getContext: async () => ({}),
        }),
      },
    ])).toHaveLength(0);
  });

  it('merges sources and drops low-priority overflow', () => {
    const merged = mergePageContexts([
      {
        sections: [
          { id: 'low', label: '低', content: 'L'.repeat(5000), priority: 1 },
          { id: 'high', label: '高', content: 'H'.repeat(5000), priority: 9 },
        ],
        images: [
          { caption: 'a', dataUrl: 'data:1' },
          { caption: 'b', dataUrl: 'data:2' },
          { caption: 'c', dataUrl: 'data:3' },
          { caption: 'd', dataUrl: 'data:4' },
          { caption: 'e', dataUrl: 'data:5' },
          { caption: 'f', dataUrl: 'data:6' },
          { caption: 'g', dataUrl: 'data:7' },
        ],
      },
    ]);
    expect(merged.sections?.some((section) => section.id === 'high')).toBe(true);
    expect(merged.sections?.some((section) => section.id === 'low')).toBe(false);
    expect(merged.images).toHaveLength(6);
  });

  it('keeps a 2s global deadline instead of the dashboard screenshot budget', () => {
    expect(PAGE_CONTEXT_PROVIDER_TIMEOUT_MS).toBe(2000);
  });

  it('falls back to getTextContext when screenshots time out', async () => {
    vi.useFakeTimers();
    const registry = createPageContextRegistry({
      getPathname: () => '/x',
      timeoutMs: 20,
      pilots: [
        {
          test: () => true,
          load: async () => ({
            getMessage: () => ({ title: 'k', currentTime: 't1' }),
            getContext: () => new Promise(() => undefined),
            getTextContext: () => ({
              sections: [{ id: 'kpi', label: '时间筛选', content: '磁盘使用率: 82.9%', priority: 9 }],
            }),
          }),
        },
      ],
    });
    const pending = registry.collect();
    await vi.advanceTimersByTimeAsync(30);
    const snapshot = await pending;
    expect(snapshot?.sections?.[0].content).toContain('磁盘使用率: 82.9%');
  });

  it('times out empty-message getContext with the shared deadline', async () => {
    vi.useFakeTimers();
    const registry = createPageContextRegistry({
      getPathname: () => '/x',
      timeoutMs: 20,
      pilots: [
        {
          test: () => true,
          load: async () => ({
            getMessage: () => ({ title: '' }),
            getContext: () => new Promise(() => undefined),
          }),
        },
      ],
    });
    const pending = registry.collect();
    await vi.advanceTimersByTimeAsync(30);
    await expect(pending).resolves.toBeNull();
  });

  it('times out hanging pilot.load with the shared deadline', async () => {
    vi.useFakeTimers();
    const registry = createPageContextRegistry({
      getPathname: () => '/x',
      timeoutMs: 20,
      pilots: [
        {
          test: () => true,
          load: () => new Promise(() => undefined),
        },
      ],
    });
    const pending = registry.collect();
    await vi.advanceTimersByTimeAsync(30);
    await expect(pending).resolves.toBeNull();
  });

  it('does not wait past the deadline when a pilot has no getTextContext', async () => {
    vi.useFakeTimers();
    const registry = createPageContextRegistry({
      getPathname: () => '/x',
      timeoutMs: 20,
      pilots: [
        {
          test: () => true,
          load: async () => ({
            getMessage: () => ({ title: 'k', currentTime: 't1' }),
            getContext: () => new Promise(() => undefined),
          }),
        },
      ],
    });
    const pending = registry.collect();
    await vi.advanceTimersByTimeAsync(30);
    await expect(pending).resolves.toBeNull();
  });

  it('skips timed-out providers and still returns other sources', async () => {
    vi.useFakeTimers();
    const registry = createPageContextRegistry({
      getPathname: () => '/x',
      pilots: [],
      timeoutMs: 20,
    });
    registry.register(() => new Promise(() => undefined));
    registry.register(() => ({
      sections: [{ id: 'ok', label: 'ok', content: 'alive', priority: 1 }],
    }));
    const pending = registry.collect();
    await vi.advanceTimersByTimeAsync(30);
    const snapshot = await pending;
    expect(snapshot?.sections?.[0].content).toBe('alive');
  });
});

describe('captionFromOption', () => {
  it('rounds pie slice values to one decimal like the dashboard', () => {
    const caption = captionFromOption({
      series: [
        {
          type: 'pie',
          data: [
            { name: '用户态', value: 21.759 },
            { name: 'I/O Wait 占比', value: 3.165 },
          ],
        },
      ],
    });
    expect(caption).toContain('21.8');
    expect(caption).toContain('3.2');
    expect(caption).not.toContain('21.759');
  });

  it('extracts pie slice names and values', () => {
    const caption = captionFromOption({
      series: [
        {
          type: 'pie',
          data: [
            { name: '用户态', value: 12.3 },
            { name: '内核态', value: 8.1 },
          ],
        },
      ],
    });
    expect(caption).toContain('用户态');
    expect(caption).toContain('内核态');
    expect(caption).toContain('12.3');
    expect(caption).toContain('8.1');
  });

  it('extracts title, series and latest value', () => {
    const caption = captionFromOption({
      title: { text: 'CPU' },
      series: [{ name: 'usage', data: [1, 2, 91] }],
      yAxis: { min: 0, max: 100 },
    });
    expect(caption).toContain('CPU');
    expect(caption).toContain('usage');
    expect(caption).toContain('91');
    expect(caption).toContain('0~100');
  });

  it('includes x-axis clock span for unix-second series', () => {
    const caption = captionFromOption({
      title: { text: '系统负载趋势' },
      series: [
        {
          name: '1 分钟负载',
          data: [
            [1_777_000_000, 1.2],
            [1_777_021_600, 4.3],
          ],
        },
      ],
    });
    expect(caption).toContain('横轴:');
    expect(caption).toMatch(/\d{2}:\d{2}~\d{2}:\d{2}/);
  });
});
