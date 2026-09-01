import { describe, expect, it } from 'vitest';
import {
  buildTrendYTicks,
  formatAlarmDurationSeconds,
  formatAlarmOccurredAt,
  projectTrendX,
  resolveDetailStatus,
} from '../application3DDetailChrome';

describe('application3D detail chrome helpers', () => {
  it('formats duration and empty occurredAt', () => {
    expect(formatAlarmDurationSeconds(60)).toBe('1m 0s');
    expect(formatAlarmDurationSeconds(3661)).toBe('1h 1m');
    expect(formatAlarmOccurredAt(null)).toBe('-');
    expect(formatAlarmOccurredAt('not-a-date')).toBe('-');
  });

  it('strips trailing alarm count from detail status label', () => {
    const status = resolveDetailStatus(
      {
        name: 'demo',
        health: {
          state: 'alarming',
          reason: 'alarm',
          activeAlarmCount: 2,
          highestSeverity: { id: 'warning', label: '警告', color: 'warning' },
        },
      },
      (key, fallback) => (key.endsWith('_warning') ? '警告' : (fallback ?? key)),
    );
    expect(status.statusLabel).toBe('警告');
    expect(status.statusLabel).not.toMatch(/\d/);
  });

  it('builds y ticks spanning thresholds', () => {
    const ticks = buildTrendYTicks(40, 120);
    expect(ticks[0]).toBeLessThanOrEqual(40);
    expect(ticks[ticks.length - 1]).toBeGreaterThanOrEqual(120);
  });

  it('projects marker x by timestamp domain', () => {
    const early = projectTrendX(0, 0, 100, 36, 200);
    const mid = projectTrendX(50, 0, 100, 36, 200);
    const late = projectTrendX(100, 0, 100, 36, 200);
    expect(early).toBe(36);
    expect(mid).toBe(136);
    expect(late).toBe(236);
  });
});
