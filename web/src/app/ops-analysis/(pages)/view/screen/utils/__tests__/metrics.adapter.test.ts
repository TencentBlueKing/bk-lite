import { describe, expect, it } from 'vitest';
import { calculateScreenFitMetrics } from '../metrics';

describe('calculateScreenFitMetrics adapters', () => {
  it('fill stretches each axis to the window and does not scroll', () => {
    const fit = calculateScreenFitMetrics({
      contentWidth: 1920,
      contentHeight: 1200,
      designWidth: 1920,
      designHeight: 1080,
      adapter: 'fill',
    });

    expect(fit.scaleX).toBe(1);
    expect(fit.scaleY).toBeCloseTo(1200 / 1080);
    expect(fit.renderedWidth).toBe(1920);
    expect(fit.renderedHeight).toBe(1200);
    expect(fit.overflowX).toBe(false);
    expect(fit.overflowY).toBe(false);
  });

  it('contain letterboxes a taller screen without scrolling', () => {
    const fit = calculateScreenFitMetrics({
      contentWidth: 1920,
      contentHeight: 1200,
      designWidth: 1920,
      designHeight: 1080,
      adapter: 'contain',
    });

    expect(fit.scaleX).toBe(1);
    expect(fit.scaleY).toBe(1);
    expect(fit.renderedWidth).toBe(1920);
    expect(fit.renderedHeight).toBe(1080);
    expect(fit.overflowX).toBe(false);
    expect(fit.overflowY).toBe(false);
  });

  it('fitWidth on a taller screen matches the width and leaves vertical space', () => {
    const fit = calculateScreenFitMetrics({
      contentWidth: 1920,
      contentHeight: 1200,
      designWidth: 1920,
      designHeight: 1080,
      adapter: 'fitWidth',
    });

    expect(fit.scaleX).toBe(1);
    expect(fit.scaleY).toBe(1);
    expect(fit.overflowX).toBe(false);
    expect(fit.overflowY).toBe(false);
  });

  it('fitHeight on a taller screen scales uniformly and scrolls sideways', () => {
    const fit = calculateScreenFitMetrics({
      contentWidth: 1920,
      contentHeight: 1200,
      designWidth: 1920,
      designHeight: 1080,
      adapter: 'fitHeight',
    });

    expect(fit.scaleX).toBeCloseTo(1200 / 1080);
    expect(fit.scaleY).toBeCloseTo(1200 / 1080);
    expect(fit.renderedHeight).toBe(1200);
    expect(fit.renderedWidth).toBe(Math.round(1920 * (1200 / 1080)));
    expect(fit.overflowX).toBe(true);
    expect(fit.overflowY).toBe(false);
  });

  it('fitWidth on an ultrawide screen scales uniformly and scrolls vertically', () => {
    const fit = calculateScreenFitMetrics({
      contentWidth: 2560,
      contentHeight: 1080,
      designWidth: 1920,
      designHeight: 1080,
      adapter: 'fitWidth',
    });

    expect(fit.scaleX).toBeCloseTo(2560 / 1920);
    expect(fit.scaleY).toBeCloseTo(2560 / 1920);
    expect(fit.renderedWidth).toBe(2560);
    expect(fit.overflowX).toBe(false);
    expect(fit.overflowY).toBe(true);
  });

  it('defaults missing adapter to fill', () => {
    const withDefault = calculateScreenFitMetrics({
      contentWidth: 1920,
      contentHeight: 1200,
      designWidth: 1920,
      designHeight: 1080,
    });
    const fill = calculateScreenFitMetrics({
      contentWidth: 1920,
      contentHeight: 1200,
      designWidth: 1920,
      designHeight: 1080,
      adapter: 'fill',
    });

    expect(withDefault).toEqual(fill);
  });
});
