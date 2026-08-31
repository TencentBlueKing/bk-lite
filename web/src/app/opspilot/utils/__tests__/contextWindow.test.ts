import { describe, expect, it } from 'vitest';

import {
  isContextWindowTokensInRange,
  tokensFromWindowInput,
  windowInputFromTokens,
} from '../contextWindow';

describe('context window form conversion', () => {
  it('converts 200 K and 2 M to tokens', () => {
    expect(tokensFromWindowInput(200, 'K')).toBe(200_000);
    expect(tokensFromWindowInput(2, 'M')).toBe(2_000_000);
    expect(tokensFromWindowInput(8, 'K')).toBe(8_000);
  });

  it('round-trips stored tokens back to integer plus unit', () => {
    expect(windowInputFromTokens(200_000)).toEqual({ value: 200, unit: 'K' });
    expect(windowInputFromTokens(2_000_000)).toEqual({ value: 2, unit: 'M' });
    expect(windowInputFromTokens(32_000)).toEqual({ value: 32, unit: 'K' });
    expect(windowInputFromTokens(1_500_000)).toEqual({ value: 1500, unit: 'K' });
  });

  it('rejects values outside 8K to 2M', () => {
    expect(isContextWindowTokensInRange(7_999)).toBe(false);
    expect(isContextWindowTokensInRange(8_000)).toBe(true);
    expect(isContextWindowTokensInRange(2_000_000)).toBe(true);
    expect(isContextWindowTokensInRange(2_000_001)).toBe(false);
  });
});
