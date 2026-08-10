import { describe, expect, it } from 'vitest';

import { formatMetricValue } from '../format';

describe('formatMetricValue', () => {
  it('normalizes the legacy Bps alias as bytes per second', () => {
    expect(formatMetricValue(2048, 'Bps')).toEqual({
      value: '2',
      unit: 'KiB/s',
    });
  });
});
