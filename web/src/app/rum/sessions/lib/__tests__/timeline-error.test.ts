import { describe, expect, it } from 'vitest';

import { rumTraceHref } from '@/app/rum/sessions/lib/timeline-error';

describe('rumTraceHref', () => {
  it('links a normal trace id to APM without a locale or query', () => {
    expect(rumTraceHref('abc')).toBe('/apm/explore/traces/abc');
  });

  it('encodes slash and space in the trace id', () => {
    expect(rumTraceHref('abc/def')).toBe('/apm/explore/traces/abc%2Fdef');
    expect(rumTraceHref('a b')).toBe('/apm/explore/traces/a%20b');
  });

  it('trims a non-empty id before encoding', () => {
    expect(rumTraceHref('  abc/def  ')).toBe('/apm/explore/traces/abc%2Fdef');
  });

  it('returns null for blank, null, and undefined', () => {
    expect(rumTraceHref('')).toBeNull();
    expect(rumTraceHref('   ')).toBeNull();
    expect(rumTraceHref(null)).toBeNull();
    expect(rumTraceHref(undefined)).toBeNull();
  });
});
