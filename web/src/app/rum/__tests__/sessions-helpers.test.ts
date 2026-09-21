import { describe, expect, it } from 'vitest';

import {
  displayRoute,
  formatDurationMs,
  parseBrowser,
  parseDevice,
  rewriteRumSegmentUrl,
  truncateMiddle,
} from '@/app/rum/lib/format';
import { presentTimelineError } from '@/app/rum/sessions/lib/timeline-error';

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

describe('session timeline error presentation', () => {
  it('does not invent a body when the journey only has a hashed or empty message', () => {
    expect(
      presentTimelineError({
        message: 'message:29c5196b11f3265a',
        errorType: 'CheckoutError',
        route: '/cart',
        fingerprint: 'fp1',
      }),
    ).toEqual({
      title: 'CheckoutError',
      hint: '/cart',
      protectedMessage: true,
      traceId: null,
      fingerprint: 'fp1',
      route: '/cart',
    });
    expect(presentTimelineError({ message: 'message:1017c61a6f8dca6e' })).toEqual({
      title: '异常错误',
      hint: null,
      protectedMessage: true,
      traceId: null,
      fingerprint: null,
      route: null,
    });
    expect(presentTimelineError({ message: '   ' })).toEqual({
      title: '异常错误',
      hint: null,
      protectedMessage: false,
      traceId: null,
      fingerprint: null,
      route: null,
    });
  });

  it('keeps a real message as the title and only adds type/trace when they add information', () => {
    expect(
      presentTimelineError({
        message: 'Failed to fetch /api/checkout',
        errorType: 'TypeError',
        traceId: 'abc',
      }),
    ).toEqual({
      title: 'Failed to fetch /api/checkout',
      hint: 'TypeError',
      protectedMessage: false,
      traceId: 'abc',
      fingerprint: null,
      route: null,
    });
    expect(presentTimelineError({ errorMessage: 'boom' })).toEqual({
      title: 'boom',
      hint: null,
      protectedMessage: false,
      traceId: null,
      fingerprint: null,
      route: null,
    });
    expect(
      presentTimelineError({
        message: 'CheckoutError: payment declined for order :id',
        errorType: 'CheckoutError',
      }),
    ).toEqual({
      title: 'CheckoutError: payment declined for order :id',
      hint: null,
      protectedMessage: false,
      traceId: null,
      fingerprint: null,
      route: null,
    });
  });
});
