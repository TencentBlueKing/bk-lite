import { describe, expect, it, vi } from 'vitest';

import {
  recentPublicWidgetWindow,
  resolvePublicWidgetQueryWindow,
} from '../resolvePublicWidgetQueryWindow';

describe('resolvePublicWidgetQueryWindow', () => {
  const now = new Date('2026-09-17T12:00:00.000Z');

  it('uses the provided ISO window when valid', () => {
    expect(
      resolvePublicWidgetQueryWindow(
        '2026-09-16T09:30:00.000Z',
        '2026-09-16T10:30:00.000Z',
        now,
      ),
    ).toEqual({
      startedAt: '2026-09-16T09:30:00.000Z',
      endedAt: '2026-09-16T10:30:00.000Z',
    });
  });

  it('falls back to now−1h when missing or invalid', () => {
    const fallback = recentPublicWidgetWindow(now);
    expect(resolvePublicWidgetQueryWindow(undefined, undefined, now)).toEqual(
      fallback,
    );
    expect(
      resolvePublicWidgetQueryWindow(
        '2026-09-16T10:30:00.000Z',
        '2026-09-16T09:30:00.000Z',
        now,
      ),
    ).toEqual(fallback);
    expect(
      resolvePublicWidgetQueryWindow('bad', '2026-09-16T10:30:00.000Z', now),
    ).toEqual(fallback);
  });
});

describe('recentPublicWidgetWindow', () => {
  it('is a one-hour lookback ending at now', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-09-17T12:00:00.000Z'));
    expect(recentPublicWidgetWindow()).toEqual({
      startedAt: '2026-09-17T11:00:00.000Z',
      endedAt: '2026-09-17T12:00:00.000Z',
    });
    vi.useRealTimers();
  });
});
