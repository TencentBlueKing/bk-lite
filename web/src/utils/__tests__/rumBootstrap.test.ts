import { describe, expect, it } from 'vitest';

import { readRumBootstrapConfig } from '../rumBootstrap';

describe('readRumBootstrapConfig', () => {
  it('stays off until the application, endpoint, and browser key are all set', () => {
    expect(readRumBootstrapConfig({})).toBeNull();
    expect(readRumBootstrapConfig({ NEXT_PUBLIC_RUM_APP: 'bklite-web' })).toBeNull();
  });

  it('reads a local collector endpoint', () => {
    expect(
      readRumBootstrapConfig({
        NEXT_PUBLIC_RUM_APP: 'bklite-web',
        NEXT_PUBLIC_RUM_ENDPOINT: 'http://127.0.0.1:4319/rum/v1/',
        NEXT_PUBLIC_RUM_API_KEY: 'browser-key-value',
      }),
    ).toEqual({
      app: 'bklite-web',
      endpoint: 'http://127.0.0.1:4319/rum/v1',
      apiKey: 'browser-key-value',
      environment: 'development',
    });
  });
});
