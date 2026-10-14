import { describe, expect, it } from 'vitest';

import { rumBrowserEndpoints } from '@/app/rum/lib/public-endpoints';

describe('rum browser endpoints', () => {
  it('uses the console origin and fixed paths', () => {
    expect(rumBrowserEndpoints('https://bklite.example.com')).toEqual({
      collectUrl: 'https://bklite.example.com/rum/v1/collect',
      replayUrl: 'https://bklite.example.com/rum/v1/replay',
      sdkCdnUrl: 'https://bklite.example.com/rum/bklite-rum-sdk.js',
    });
  });

  it('prefers a configured public origin over the console origin', () => {
    expect(
      rumBrowserEndpoints('http://127.0.0.1:3000', 'https://rum.example.com/'),
    ).toEqual({
      collectUrl: 'https://rum.example.com/rum/v1/collect',
      replayUrl: 'https://rum.example.com/rum/v1/replay',
      sdkCdnUrl: 'https://rum.example.com/rum/bklite-rum-sdk.js',
    });
  });

  it('ignores an override that is not an origin', () => {
    expect(
      rumBrowserEndpoints('https://bklite.example.com', 'https://evil.example/collect'),
    ).toEqual({
      collectUrl: 'https://bklite.example.com/rum/v1/collect',
      replayUrl: 'https://bklite.example.com/rum/v1/replay',
      sdkCdnUrl: 'https://bklite.example.com/rum/bklite-rum-sdk.js',
    });
  });
});
