import { describe, expect, it } from 'vitest';
import { formatSuppressionTime, shieldRuntimeLabelKey } from '../shieldDisplay';

describe('formatSuppressionTime', () => {
  it('prefixes one-time windows and sorts month and week days', () => {
    expect(formatSuppressionTime({
      type: 'month',
      week_month: [1, 3, 6, 5, 2, 28, 30, 31, 26, 24],
      start_time: '02:00:00',
      end_time: '23:59:59',
    })).toBe('每月 1日,2日,3日,5日,6日,24日,26日,28日,30日,31日 02:00:00 - 23:59:59');

    expect(formatSuppressionTime({
      type: 'week',
      week_month: [5, 3],
      start_time: '03:00:02',
      end_time: '23:59:59',
    })).toBe('每周 星期三,星期五 03:00:02 - 23:59:59');

    expect(formatSuppressionTime({
      type: 'one',
      start_time: '2026-10-21 00:00:00',
      end_time: '2026-11-21 23:59:59',
    })).toBe('单次 2026-10-21 00:00:00-2026-11-21 23:59:59');

    expect(formatSuppressionTime({
      type: 'day',
      start_time: '00:00:00',
      end_time: '23:57:59',
    })).toBe('每天 00:00:00 - 23:57:59');
  });

  it('returns a dash when the window is missing', () => {
    expect(formatSuppressionTime(null)).toBe('--');
    expect(formatSuppressionTime({})).toBe('--');
  });
});

describe('shieldRuntimeLabelKey', () => {
  it('maps backend runtime codes to copy keys', () => {
    expect(shieldRuntimeLabelKey('shielding')).toBe('settings.shieldDisplay.runtimeShielding');
    expect(shieldRuntimeLabelKey('not_started')).toBe('settings.shieldDisplay.runtimeNotStarted');
    expect(shieldRuntimeLabelKey('unknown')).toBe('');
  });
});
