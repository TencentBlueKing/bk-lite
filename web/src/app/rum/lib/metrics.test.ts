import { describe, expect, it } from 'vitest';

import { countText, maxKnown, metricOrZero, sumKnown } from '@/app/rum/lib/metrics';

describe('rum aggregate display numbers', () => {
  it('keeps null distinct from zero and sums only known values', () => {
    expect(metricOrZero(null)).toBeNull();
    expect(metricOrZero('3')).toBe(3);
    expect(metricOrZero(undefined)).toBe(0);
    expect(countText(null)).toBe('—');
    expect(countText(0)).toBe('0');
    expect(sumKnown([120, null, 0])).toBe(120);
    expect(sumKnown([null, null])).toBeNull();
    expect(maxKnown([null, 2400, 1800])).toBe(2400);
    expect(maxKnown([null])).toBeNull();
  });
});
