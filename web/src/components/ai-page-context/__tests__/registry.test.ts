import { afterEach, describe, expect, it, vi } from 'vitest';

import { captionFromOption } from '../chart-capture';
import { matchPilots } from '../pilots';
import { createPageContextRegistry, mergePageContexts } from '../registry';
import type { AiPageContextPilot } from '../types';

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
      collect: async () => ({
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

  it('does not match unrelated routes', () => {
    expect(matchPilots('/cmdb/resource', [
      { test: (pathname) => pathname.includes('/monitor/view/dashboard/'), load: async () => ({ collect: async () => ({}) }) },
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
});
