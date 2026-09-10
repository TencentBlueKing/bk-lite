import { describe, expect, test } from 'vitest';
import { buildGaugeAxisLineColor } from '@/app/ops-analysis/utils/thresholdUtils';

describe('buildGaugeAxisLineColor', () => {
  test('maps ≥ thresholds to ECharts segments ending at the next threshold', () => {
    // 当值 ≥70 红 / ≥30 橙 / ≥0 蓝 → 弧线 0–30 蓝、30–70 橙、70–100 红
    expect(
      buildGaugeAxisLineColor(0, 100, [
        { value: '70', color: '#DC2626' },
        { value: '30', color: '#D97706' },
        { value: '0', color: '#2563EB' },
      ]),
    ).toEqual([
      [0.3, '#2563EB'],
      [0.7, '#D97706'],
      [1, '#DC2626'],
    ]);
  });

  test('does not emit a zero-width segment at min', () => {
    const segments = buildGaugeAxisLineColor(0, 100, [
      { value: '0', color: '#2563EB' },
      { value: '50', color: '#D97706' },
    ]);
    expect(segments[0]?.[0]).toBeGreaterThan(0);
    expect(segments).toEqual([
      [0.5, '#2563EB'],
      [1, '#D97706'],
    ]);
  });

  test('extends the last threshold color to max', () => {
    expect(
      buildGaugeAxisLineColor(0, 100, [{ value: '80', color: '#DC2626' }]),
    ).toEqual([[1, '#DC2626']]);
  });

  test('returns default color when thresholds are empty', () => {
    expect(buildGaugeAxisLineColor(0, 100, [])).toEqual([[1, '#366CE4']]);
  });
});
