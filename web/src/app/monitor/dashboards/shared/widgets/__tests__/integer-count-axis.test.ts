import { describe, expect, it } from 'vitest';

import { formatIntegerTick, integerCountAxis, integerCountTicks } from '../integer-count-axis';

describe('integer count axis', () => {
  it('emits only integer ticks and keeps the max at least 1', () => {
    const bounds = integerCountAxis([0, 3]);
    const ticks = integerCountTicks(bounds);
    expect(bounds.min).toBe(0);
    expect(bounds.max).toBeGreaterThanOrEqual(1);
    expect(bounds.max).toBeGreaterThanOrEqual(3);
    expect(Number.isInteger(bounds.max)).toBe(true);
    expect(Number.isInteger(bounds.interval)).toBe(true);
    expect(bounds.max % bounds.interval).toBe(0);
    expect(ticks.every((tick) => /^\d+$/.test(tick))).toBe(true);
    expect(ticks.join(' ')).not.toContain('3.3000000000000003');
  });

  it('lifts an all-zero series to a max of 1', () => {
    const bounds = integerCountAxis([0, 0]);
    expect(integerCountTicks(bounds)).toEqual(['0', '1']);
  });

  it('drops float glitches that are not integers', () => {
    expect(formatIntegerTick(3)).toBe('3');
    expect(formatIntegerTick(1.0000000000000002)).toBe('1');
    expect(formatIntegerTick(3.3000000000000003)).toBe('');
  });
});
