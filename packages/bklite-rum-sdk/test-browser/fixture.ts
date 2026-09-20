import { initializeFaro } from '@grafana/faro-web-sdk';

import { CoreRumTransport } from '../dist/index.js';

export function sendBrowserSmokeEvent(
  collectUrl: string,
  replayUrl: string,
): void {
  const transport = new CoreRumTransport({
    apiKey: 'core-rum-browser-e2e',
    collectUrl,
    replayUrl,
    replay: { enabled: false },
  });
  const faro = initializeFaro({
    app: {
      name: 'bklite-rum-sdk-browser',
      environment: 'test',
      release: '0.1.0',
    },
    batching: {
      enabled: true,
      itemLimit: 1,
      sendTimeout: 10,
    },
    instrumentations: [],
    isolate: true,
    sessionTracking: { enabled: false },
    transports: [transport],
  });
  faro.api.pushEvent('core-rum.browser-smoke', { source: 'playwright' });
}
