import {afterEach, describe, expect, it, vi} from 'vitest';
import {NextRequest} from 'next/server';

import {buildProxyRequestHeaders} from '../proxyForwarding';
import {POST} from '../route';

afterEach(() => {
  vi.unstubAllGlobals();
  delete process.env.OTP_WEB_XFF_MODE;
});

describe('buildProxyRequestHeaders', () => {
  it('strips an attacker-controlled XFF by default', () => {
    const result = buildProxyRequestHeaders(
      new Headers({'x-forwarded-for': '198.51.100.9'}),
      'console.example.com',
      'https:',
    );

    expect(result.has('x-forwarded-for')).toBe(false);
  });

  it('preserves an upstream-sanitized chain only when explicitly enabled', () => {
    const result = buildProxyRequestHeaders(
      new Headers({'x-forwarded-for': '203.0.113.7, 10.0.0.2'}),
      'console.example.com',
      'https:',
      'trusted_upstream',
    );

    expect(result.get('x-forwarded-for')).toBe('203.0.113.7, 10.0.0.2');
  });

  it('keeps the old forwarding behavior as an explicit rollback', () => {
    const result = buildProxyRequestHeaders(
      new Headers({'x-forwarded-for': '198.51.100.9'}),
      'console.example.com',
      'https:',
      'legacy',
    );

    expect(result.get('x-forwarded-for')).toBe('198.51.100.9');
  });

  it('strips a forged XFF on the real Web-to-Server proxy path', async () => {
    let forwardedHeaders: Headers | undefined;
    vi.stubGlobal('fetch', vi.fn(async (_url: string, options: RequestInit) => {
      forwardedHeaders = new Headers(options.headers);
      return new Response('{}', {status: 200, headers: {'content-type': 'application/json'}});
    }));
    const request = new NextRequest(
      'http://console.example.com/api/proxy/core/api/verify_otp_login/',
      {
        method: 'POST',
        headers: {'content-type': 'application/json', 'x-forwarded-for': '198.51.100.9'},
        body: '{}',
      },
    );

    await POST(request);

    expect(forwardedHeaders?.has('x-forwarded-for')).toBe(false);
  });
});
