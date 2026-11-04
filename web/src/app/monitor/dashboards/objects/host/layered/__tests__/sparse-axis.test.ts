import { describe, expect, it } from 'vitest';

import { readableAxisBounds, sparseAxisBounds } from '../thin-time-series';

const awayFromZero = [129, 180, 217];

describe('sparseAxisBounds rate floor', () => {
  it('pins rate units to 0 even when samples sit far above the baseline', () => {
    (['cps', 'msps', 'byteps', 'bitps', 'pps'] as const).forEach((unit) => {
      const bounds = sparseAxisBounds(awayFromZero, unit);
      expect(bounds?.min).toBe(0);
      expect(bounds?.max).toBeGreaterThanOrEqual(217);
    });
    const drawn = readableAxisBounds(awayFromZero, 'cps');
    expect(drawn?.min).toBe(0);
    expect(drawn?.max).toBeGreaterThanOrEqual(217);
  });

  it('keeps a non-rate series off 0 when the data is far from the baseline', () => {
    const counts = sparseAxisBounds(awayFromZero, 'counts');
    const bytes = sparseAxisBounds(awayFromZero, 'bytes');
    expect(counts?.min).toBeGreaterThan(0);
    expect(bytes?.min).toBeGreaterThan(0);
  });

  it('does not pad an all-zero rate below 0', () => {
    const bounds = readableAxisBounds([0, 0, 0], 'cps');
    expect(bounds?.min).toBe(0);
    expect(bounds?.max).toBeGreaterThan(0);
  });
});
