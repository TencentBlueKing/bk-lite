import { describe, expect, it } from 'vitest';
import {
  countRenderableLinePoints,
  resolveLineSeriesPointMark,
} from '../lineSeriesSymbol';

describe('line series single point mark', () => {
  it('counts numeric samples and ignores empty gaps', () => {
    expect(countRenderableLinePoints([1.75, null, '', undefined])).toBe(1);
    expect(countRenderableLinePoints([['2026-09-28', 20.96]])).toBe(1);
    expect(countRenderableLinePoints([1.75, 3.06])).toBe(2);
    expect(countRenderableLinePoints(null)).toBe(0);
  });

  it('draws a circle when a line cannot be formed', () => {
    expect(resolveLineSeriesPointMark(1)).toEqual({
      showSymbol: true,
      showAllSymbol: true,
      symbol: 'circle',
      symbolSize: 8,
    });
  });

  it('keeps dense trends as unmarked lines', () => {
    expect(resolveLineSeriesPointMark(2)).toMatchObject({
      showSymbol: false,
      showAllSymbol: false,
      symbol: 'none',
      symbolSize: 0,
    });
    expect(resolveLineSeriesPointMark(0).showSymbol).toBe(false);
  });
});