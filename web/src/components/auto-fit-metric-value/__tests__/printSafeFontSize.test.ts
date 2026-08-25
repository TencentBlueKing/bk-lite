import { describe, expect, it } from 'vitest';

import {
  buildPrintSafeFontSize,
  evaluatePrintSafeFontSize,
} from '@/components/auto-fit-metric-value/printSafeFontSize';

describe('print-safe metric font size', () => {
  it('keeps the fitted size when the container is unchanged', () => {
    expect(evaluatePrintSafeFontSize(80, 348, 348)).toBe(80);
  });

  it('caps a height-driven font when print layout narrows the card', () => {
    const fittedPx = 80;
    const textWidthPx = 348;
    const printWidthPx = 300;
    const result = evaluatePrintSafeFontSize(
      fittedPx,
      textWidthPx,
      printWidthPx,
    );

    expect(result).toBeCloseTo((80 * 300) / 348, 5);
    expect((textWidthPx / fittedPx) * result).toBeLessThanOrEqual(printWidthPx);
  });

  it('does not grow past the height-fitted size when the container is wider', () => {
    expect(evaluatePrintSafeFontSize(80, 348, 500)).toBe(80);
  });

  it('emits a CSS min() that print layout can recompute via cqi', () => {
    expect(buildPrintSafeFontSize(80, 348)).toBe('min(80px, 22.9885cqi)');
  });
});
