import { describe, expect, it } from 'vitest';

import { degradationBanners, listEmptyUsesAnalyticsCopy } from '@/app/rum/lib/degradation';

describe('rum list degradation flags', () => {
  it('shows one banner per flag and keeps both', () => {
    expect(degradationBanners({ controlUnavailable: true, analyticsUnavailable: true })).toEqual([
      'control',
      'analytics',
    ]);
    expect(degradationBanners({ controlUnavailable: true })).toEqual(['control']);
    expect(degradationBanners({ analyticsUnavailable: true })).toEqual(['analytics']);
    expect(degradationBanners({})).toEqual([]);
    expect(degradationBanners(null)).toEqual([]);
  });

  it('uses the analytics empty copy only when analytics is down', () => {
    expect(listEmptyUsesAnalyticsCopy({ analyticsUnavailable: true })).toBe(true);
    expect(
      listEmptyUsesAnalyticsCopy({ controlUnavailable: true, analyticsUnavailable: true }),
    ).toBe(true);
    expect(listEmptyUsesAnalyticsCopy({ controlUnavailable: true })).toBe(false);
    expect(listEmptyUsesAnalyticsCopy({})).toBe(false);
    expect(listEmptyUsesAnalyticsCopy(null)).toBe(false);
  });
});
