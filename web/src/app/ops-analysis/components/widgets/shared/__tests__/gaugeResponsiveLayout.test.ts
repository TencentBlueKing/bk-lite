import { describe, expect, it } from 'vitest';
import {
  estimateGaugeEffectiveRadius,
  gaugeLabelInsetFromOuterEdge,
  getGaugeResponsiveLayout,
  resolveGaugeLayoutTier,
} from '../gaugeResponsiveLayout';

describe('gaugeResponsiveLayout', () => {
  it('estimates effective radius from min(width, height), not width alone', () => {
    expect(estimateGaugeEffectiveRadius(320, 100, false)).toBeCloseTo(54, 0);
    expect(estimateGaugeEffectiveRadius(320, 100, true)).toBeCloseTo(45, 0);
    expect(estimateGaugeEffectiveRadius(180, 180, false)).toBeCloseTo(97.2, 1);
  });

  it('maps small / medium / large tiers to splitNumber density', () => {
    expect(getGaugeResponsiveLayout({ width: 120, height: 120 })).toMatchObject({
      tier: 'small',
      splitNumber: 2,
    });
    expect(getGaugeResponsiveLayout({ width: 180, height: 180 })).toMatchObject({
      tier: 'medium',
      splitNumber: 5,
    });
    expect(getGaugeResponsiveLayout({ width: 320, height: 320 })).toMatchObject({
      tier: 'large',
      splitNumber: 10,
    });
  });

  it('keeps axisLabel.distance in the safe 25~27 band', () => {
    expect(getGaugeResponsiveLayout({ width: 120, height: 120 }).axisLabelDistance).toBe(27);
    expect(getGaugeResponsiveLayout({ width: 180, height: 180 }).axisLabelDistance).toBe(26);
    expect(getGaugeResponsiveLayout({ width: 320, height: 320 }).axisLabelDistance).toBe(25);
  });

  it('pushes detail lower on small semicircle gauges', () => {
    const small = getGaugeResponsiveLayout({ width: 120, height: 120, gaugeShape: 'semicircle' });
    const large = getGaugeResponsiveLayout({ width: 320, height: 320, gaugeShape: 'semicircle' });

    expect(small.detailOffsetCenterY).toBe('50%');
    expect(large.detailOffsetCenterY).toBe('38%');
    expect(small.detailFontSize).toBeLessThan(large.detailFontSize);
  });

  it('applies hysteresis around tier boundaries', () => {
    expect(resolveGaugeLayoutTier(68, 'medium')).toBe('small');
    expect(resolveGaugeLayoutTier(72, 'small')).toBe('small');
    expect(resolveGaugeLayoutTier(80, 'small')).toBe('medium');

    expect(resolveGaugeLayoutTier(112, 'large')).toBe('medium');
    expect(resolveGaugeLayoutTier(118, 'medium')).toBe('medium');
    expect(resolveGaugeLayoutTier(128, 'medium')).toBe('large');
  });

  it('caps detail offset on very short semicircle containers', () => {
    const layout = getGaugeResponsiveLayout({
      width: 320,
      height: 100,
      gaugeShape: 'semicircle',
    });
    expect(layout.tier).toBe('small');
    expect(layout.detailOffsetCenterY).toBe('35%');
    expect(layout.detailFontSize).toBe(20);
  });

  it('does not depend on fixed 0/100 min/max semantics', () => {
    const layout = getGaugeResponsiveLayout({ width: 180, height: 180 });
    expect(layout.splitNumber).toBe(5);
    expect(layout.axisLabelDistance).toBe(26);
  });

  it('does not overwrite tier hysteresis state on transient zero size', () => {
    const large = getGaugeResponsiveLayout({ width: 320, height: 320 });
    expect(large.tier).toBe('large');

    const transientZero = getGaugeResponsiveLayout({
      width: 0,
      height: 0,
      previousTier: 'large',
    });
    expect(transientZero.tier).toBe('medium');

    const restored = getGaugeResponsiveLayout({
      width: 320,
      height: 320,
      previousTier: 'large',
    });
    expect(restored.tier).toBe('large');
  });

  it('keeps labels inside the arc with ~5-8px clearance', () => {
    const arcWidth = 14;
    [27, 26, 25].forEach((distance) => {
      const inset = gaugeLabelInsetFromOuterEdge(distance);
      expect(inset).toBeGreaterThanOrEqual(arcWidth + 5);
      expect(inset).toBeLessThanOrEqual(arcWidth + 8);
    });
  });
});
