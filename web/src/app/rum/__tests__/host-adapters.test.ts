import { describe, expect, it } from 'vitest';

import { rumPath } from '@/app/rum/api/client';
import { degradationReason, withDegradation } from '@/app/rum/lib/degradation';
import { parseRumRange, parseRumTraffic } from '@/app/rum/lib/search-params';

describe('rum host adapters', () => {
  it('prefixes API paths under /rum without a trailing slash', () => {
    expect(rumPath('/applications/')).toBe('/rum/applications');
    expect(rumPath('meta/')).toBe('/rum/meta');
    expect(rumPath('/applications/store/')).toBe('/rum/applications/store');
    expect(rumPath('/sessions/trend/')).toBe('/rum/sessions/trend');
  });

  it('parses range and traffic query values', () => {
    expect(parseRumRange('1h')).toBe('1h');
    expect(parseRumRange('nope')).toBe('24h');
    expect(parseRumTraffic('all')).toBe('all');
    expect(parseRumTraffic('')).toBe('visitors');
  });

  it('maps exclusive pipeline degradation reasons', () => {
    expect(degradationReason({ controlUnavailable: true })).toBe('control');
    expect(degradationReason({ analyticsUnavailable: true })).toBe('analytics');
    expect(degradationReason({})).toBeNull();
    const page = withDegradation({
      sessions: [],
      controlUnavailable: 1 as unknown as boolean,
      analyticsUnavailable: 0 as unknown as boolean,
    });
    expect(page.controlUnavailable).toBe(true);
    expect(page.analyticsUnavailable).toBe(false);
  });
});
