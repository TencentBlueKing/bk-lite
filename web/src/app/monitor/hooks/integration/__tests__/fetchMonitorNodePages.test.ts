import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  MONITOR_NODE_SEARCH_DELAY_MS,
  createMonitorNodeQueryCache,
  scheduleMonitorNodeSearch,
  shouldLoadNextMonitorNodePage,
} from '../fetchMonitorNodePages';

describe('scheduleMonitorNodeSearch', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('waits until typing pauses, then searches once with the latest text', () => {
    vi.useFakeTimers();
    const timer: { id?: number } = {};
    const run = vi.fn();

    scheduleMonitorNodeSearch(timer, MONITOR_NODE_SEARCH_DELAY_MS, () => run('l'));
    scheduleMonitorNodeSearch(timer, MONITOR_NODE_SEARCH_DELAY_MS, () => run('lo'));
    scheduleMonitorNodeSearch(timer, MONITOR_NODE_SEARCH_DELAY_MS, () => run('loadtest'));

    vi.advanceTimersByTime(MONITOR_NODE_SEARCH_DELAY_MS - 1);
    expect(run).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(run).toHaveBeenCalledTimes(1);
    expect(run).toHaveBeenCalledWith('loadtest');
  });
});

describe('createMonitorNodeQueryCache', () => {
  it('reuses the first page and shares one request across concurrent callers', async () => {
    const cache = createMonitorNodeQueryCache<{ id: string }>();
    const fetchPage = vi.fn(async () => ({ count: 3, nodes: [{ id: 'a' }] }));
    const first = cache.load({
      keyword: '',
      page: 1,
      append: false,
      nodeId: (node) => node.id,
      fetchPage,
    });
    const second = cache.load({
      keyword: '',
      page: 1,
      append: false,
      nodeId: (node) => node.id,
      fetchPage,
    });

    await Promise.all([first, second]);
    const cached = await cache.load({
      keyword: '',
      page: 1,
      append: false,
      nodeId: (node) => node.id,
      fetchPage,
    });

    expect(fetchPage).toHaveBeenCalledTimes(1);
    expect(cached.nodes.map((node) => node.id)).toEqual(['a']);
  });

  it('keeps the default page after a search so clearing the keyword does not refetch', async () => {
    const cache = createMonitorNodeQueryCache<{ id: string }>();
    const fetchPage = vi.fn(async () => ({ count: 1, nodes: [{ id: 'default' }] }));
    await cache.load({
      keyword: '',
      page: 1,
      append: false,
      nodeId: (node) => node.id,
      fetchPage,
    });
    await cache.load({
      keyword: 'loadtest',
      page: 1,
      append: false,
      nodeId: (node) => node.id,
      fetchPage: async () => ({ count: 1, nodes: [{ id: 'loadtest-001' }] }),
    });

    expect(cache.read('')?.nodes.map((node) => node.id)).toEqual(['default']);
    expect(cache.read('loadtest')?.nodes.map((node) => node.id)).toEqual(['loadtest-001']);
  });
});

describe('shouldLoadNextMonitorNodePage', () => {
  it('loads the next page only when the list is scrolled near the bottom', () => {
    expect(shouldLoadNextMonitorNodePage(0, 256, 800)).toBe(false);
    expect(shouldLoadNextMonitorNodePage(520, 256, 800)).toBe(true);
  });
});
