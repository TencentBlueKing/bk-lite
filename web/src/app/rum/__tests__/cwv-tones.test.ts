import { describe, expect, it } from 'vitest';

import {
  cwvTone,
  formatMs,
  toneBarClass,
  toneColor,
  toneDotClass,
  toneSemanticPalette,
  toneSoftBgClass,
  toneTextClass,
} from '@/app/rum/lib/cwv';

describe('rum cwv tone helpers', () => {
  it('rates core and diagnostic vitals without throwing on unknown names', () => {
    expect(cwvTone('lcp', 1200)).toBe('success');
    expect(cwvTone('fcp', 1200)).toBe('success');
    expect(cwvTone('ttfb', 2000)).toBe('danger');
    expect(cwvTone('fid', 80)).toBe('success');
    expect(cwvTone('cls', 0.2)).toBe('warning');
    expect(cwvTone('fcp', 0)).toBe('neutral');
    expect(cwvTone('', 1800)).toBe('neutral');
    expect(cwvTone('web-vital-unknown', 9999)).toBe('neutral');
  });

  it('formats milliseconds and empty values', () => {
    expect(formatMs(1234.6)).toBe('1235ms');
    expect(formatMs(0)).toBe('—');
    expect(formatMs(-1)).toBe('—');
  });

  it('maps tones to semantic class tokens', () => {
    expect(toneDotClass('success')).toContain('--color-success');
    expect(toneDotClass('warning')).toContain('status-warning');
    expect(toneDotClass('danger')).toContain('--color-fail');
    expect(toneDotClass('neutral')).toContain('--color-text-4');

    expect(toneTextClass('success')).toContain('--color-success');
    expect(toneTextClass('neutral')).toContain('--color-text-3');

    expect(toneBarClass('danger')).toContain('--color-fail');
    expect(toneSoftBgClass('success')).toContain('color-mix');
    expect(toneSoftBgClass('neutral')).toContain('--color-fill-2');
  });

  it('builds badge palettes and raw tone colors', () => {
    expect(toneSemanticPalette('info').textColor).toBe('var(--color-primary)');
    expect(toneSemanticPalette('warning').backgroundColor).toContain('status-warning');
    expect(toneSemanticPalette('neutral').textColor).toBe('var(--color-text-3)');
    expect(toneColor('success')).toBe('var(--color-success)');
    expect(toneColor('danger')).toBe('var(--color-fail)');
    expect(toneColor('neutral')).toBe('var(--color-text-3)');
  });
});
