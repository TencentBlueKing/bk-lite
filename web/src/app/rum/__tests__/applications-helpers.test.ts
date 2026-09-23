import { describe, expect, it } from 'vitest';

import { normalizeApplication } from '@/app/rum/api';
import { appExperienceTone, cwvTone, errorRateTone, formatPct } from '@/app/rum/lib/cwv';

describe('rum applications helpers', () => {
  it('normalizes null slices on application views', () => {
    const view = normalizeApplication({
      application: 'storefront',
      enabled: true,
      origins: undefined,
      browserKeys: undefined,
      browserKeyDigests: undefined,
    });
    expect(view.origins).toEqual([]);
    expect(view.browserKeys).toEqual([]);
    expect(view.browserKeyDigests).toEqual([]);
  });

  it('preserves ingest evidence timestamps used by the setup list', () => {
    const view = normalizeApplication({
      application: 'checkout',
      enabled: true,
      lastAcceptedAt: 1_700_000_000,
      lastStoredAt: 1_700_000_030,
    });
    expect(view.lastAcceptedAt).toBe(1_700_000_000);
    expect(view.lastStoredAt).toBe(1_700_000_030);
  });

  it('classifies CWV and experience tones', () => {
    expect(cwvTone('lcp', 1200)).toBe('success');
    expect(cwvTone('lcp', 3000)).toBe('warning');
    expect(cwvTone('inp', 600)).toBe('danger');
    expect(appExperienceTone(1200, 100, 0)).toBe('success');
    expect(appExperienceTone(1200, 100, 0.02)).toBe('warning');
    expect(appExperienceTone(5000, 100, 0)).toBe('danger');
    expect(errorRateTone(0.06)).toBe('danger');
    expect(formatPct(0.1234)).toBe('12.34%');
  });
});
