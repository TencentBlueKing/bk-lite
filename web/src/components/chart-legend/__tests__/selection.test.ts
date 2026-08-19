import { describe, expect, it } from 'vitest';
import {
  isSameChartLegendSelection,
  shouldEmitLegendReset,
} from '@/components/chart-legend/selection';

describe('chart legend selection helpers', () => {
  it('does not emit a reset on the first legend key', () => {
    expect(shouldEmitLegendReset(null, '未分派\x00待响应')).toBe(false);
  });

  it('emits a reset only when the legend key actually changes', () => {
    expect(shouldEmitLegendReset('未分派', '待响应')).toBe(true);
    expect(shouldEmitLegendReset('未分派', '未分派')).toBe(false);
  });

  it('treats empty selection maps as equal', () => {
    expect(isSameChartLegendSelection({}, {})).toBe(true);
    expect(isSameChartLegendSelection({ a: true }, {})).toBe(false);
  });
});
