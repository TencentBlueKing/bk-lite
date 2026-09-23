import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { formatRelativeTime, pickEntityTimestamp } from '@/utils/relativeTime';

describe('relativeTime', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-09-21T12:00:00.000Z'));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('prefers updated_at and falls back to created_at', () => {
    expect(pickEntityTimestamp({
      updated_at: '2026-09-21T11:00:00.000Z',
      created_at: '2026-09-20T11:00:00.000Z',
    })).toBe('2026-09-21T11:00:00.000Z');
    expect(pickEntityTimestamp({ created_at: '2026-09-20T11:00:00.000Z' }))
      .toBe('2026-09-20T11:00:00.000Z');
    expect(pickEntityTimestamp({})).toBeUndefined();
  });

  it('formats buckets and falls back to calendar date after 30 days', () => {
    expect(formatRelativeTime('2026-09-21T11:59:58.000Z')).toBe('刚刚');
    expect(formatRelativeTime('2026-09-21T11:59:20.000Z')).toBe('40秒前');
    expect(formatRelativeTime('2026-09-21T11:10:00.000Z')).toBe('50分钟前');
    expect(formatRelativeTime('2026-09-21T09:00:00.000Z')).toBe('3小时前');
    expect(formatRelativeTime('2026-09-18T12:00:00.000Z')).toBe('3天前');
    expect(formatRelativeTime('2026-08-01T12:00:00.000Z')).toBe('2026-08-01');
    expect(formatRelativeTime('not-a-date')).toBe('');
    expect(formatRelativeTime(null)).toBe('');
  });

  it('uses translation templates without interpolating the whole object', () => {
    const t = vi.fn((id: string, fallback?: string, values?: Record<string, string | number>) => {
      if (id === 'common.hoursAgo') return `${values?.count}h`;
      return fallback || id;
    });

    expect(formatRelativeTime('2026-09-21T09:00:00.000Z', t)).toBe('3h');
    expect(t).toHaveBeenCalledWith('common.hoursAgo', '{count}小时前', { count: 3 });
  });
});
