import { describe, expect, it } from 'vitest';

import { focusPaddedAxisBounds, formatAxisTick, formatPlainTick, readableAxisBounds } from '../thin-time-series';

const fractionLength = (text: string) => {
  const match = text.match(/\.(\d+)/);
  return match ? match[1].length : 0;
};

describe('formatPlainTick', () => {
  it('keeps non-count ticks to one decimal and drops irregular floats', () => {
    expect(formatPlainTick(208.815)).not.toBe('208.815');
    expect(formatPlainTick(208.18708333333334)).not.toContain('208.18708333333334');
    [208.815, 208.18708333333334, 12.25, 30080.4, 0, 10].forEach((value) => {
      expect(fractionLength(formatPlainTick(value))).toBeLessThanOrEqual(1);
    });
    expect(formatAxisTick(208.815, 'byteps')).not.toMatch(/208\.815/);
    expect(formatAxisTick(208.18708333333334, 'ms')).not.toMatch(/208\.18708333333334/);
    expect(fractionLength(formatAxisTick(208.815, 'byteps').replace(/[^\d.]/g, ''))).toBeLessThanOrEqual(1);
  });

  it('nice-steps a traffic-like series instead of printing 208.815', () => {
    const bounds = readableAxisBounds([0, 120.4, 208.18708333333334], 'byteps');
    expect(bounds).toBeTruthy();
    const steps = Math.round((bounds!.max - bounds!.min) / bounds!.interval);
    for (let index = 0; index <= steps; index += 1) {
      const label = formatAxisTick(bounds!.min + bounds!.interval * index, 'byteps', bounds!.max);
      expect(label).not.toMatch(/208\.815/);
      expect(label).not.toMatch(/\d+\.\d{2,}/);
    }
  });
});

describe('focusPaddedAxisBounds', () => {
  it('lifts an all-zero focus series off the 0-1 floor', () => {
    const bounds = focusPaddedAxisBounds([0, 0, 0]);
    expect(bounds).toBeTruthy();
    expect(bounds!.min).toBeLessThan(0);
    expect(bounds!.max).toBeGreaterThan(0);
    expect(bounds!.min === 0 && bounds!.max === 1).toBe(false);
  });

  it('does not pin a near-zero series to a 0-1 axis', () => {
    const bounds = focusPaddedAxisBounds([0, 0.002, 0.001]);
    expect(bounds).toBeTruthy();
    expect(bounds!.max).toBeLessThan(1);
    expect(bounds!.min === 0 && bounds!.max === 1).toBe(false);
    const span = bounds!.max - bounds!.min;
    const used = 0.002 - bounds!.min;
    expect(used / span).toBeGreaterThan(0.2);
    expect(used / span).toBeLessThan(0.95);
  });

  it('pads a moving series instead of forcing the baseline to 0', () => {
    const bounds = focusPaddedAxisBounds([10, 12, 11]);
    expect(bounds).toBeTruthy();
    expect(bounds!.min).toBeGreaterThan(0);
    expect(bounds!.min).toBeLessThan(10);
    expect(bounds!.max).toBeGreaterThan(12);
  });
});
