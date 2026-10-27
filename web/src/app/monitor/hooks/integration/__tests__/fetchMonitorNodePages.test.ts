import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  MONITOR_NODE_SEARCH_DELAY_MS,
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

describe('shouldLoadNextMonitorNodePage', () => {
  it('loads the next page only when the list is scrolled near the bottom', () => {
    expect(shouldLoadNextMonitorNodePage(0, 256, 800)).toBe(false);
    expect(shouldLoadNextMonitorNodePage(520, 256, 800)).toBe(true);
  });
});
