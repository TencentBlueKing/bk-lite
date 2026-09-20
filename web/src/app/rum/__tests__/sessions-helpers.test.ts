import { describe, expect, it } from 'vitest';

import {
  displayRoute,
  formatDurationMs,
  parseBrowser,
  parseDevice,
  rewriteRumSegmentUrl,
  truncateMiddle,
} from '@/app/rum/lib/format';

describe('rum sessions helpers', () => {
  it('parses device and browser from UA', () => {
    expect(parseDevice('Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)')).toBe('mobile');
    expect(parseDevice('Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X)')).toBe('tablet');
    expect(parseBrowser('Mozilla/5.0 Chrome/120.0.0.0 Safari/537.36')).toBe('Chrome');
  });

  it('formats routes, durations, and truncations', () => {
    expect(displayRoute('https://example.com/checkout')).toBe('/checkout');
    expect(formatDurationMs(90_000)).toBe('1m 30s');
    expect(truncateMiddle('abcdefghijklmnopqrstuvwxyz', 10)).toContain('…');
  });

  it('rewrites grant segment URLs onto the BK-Lite proxy', () => {
    expect(rewriteRumSegmentUrl('/api/v1/rum/replay/segments/abc')).toBe(
      '/api/proxy/rum/replay/segments/abc',
    );
    expect(rewriteRumSegmentUrl('/rum/replay/segments/abc')).toBe('/api/proxy/rum/replay/segments/abc');
    expect(rewriteRumSegmentUrl('https://cdn.example/seg')).toBe('https://cdn.example/seg');
  });
});
