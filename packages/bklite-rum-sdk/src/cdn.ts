import {
  getWebInstrumentations,
  initializeFaro,
  type Faro,
  type Instrumentation,
} from '@grafana/faro-web-sdk';

import { sanitizeReplayEvent } from './replay-privacy';
import { CoreRumTransport } from './transport';

/**
 * CDN onboarding facade. `initCoreRum` wires the platform-owned defaults for
 * the no-build CDN path: ordinary telemetry at 100%, default view = pathname
 * with route synchronization, bounded CoreRumTransport, and (optionally) a
 * privacy-baselined Session Replay.
 *
 * It returns the native Faro instance — it is not a private SDK and does not
 * replace Faro instrumentation.
 */

export interface InitCoreRumConfig {
  app: {
    name: string;
    environment?: string;
    release?: string;
  };
  /** Shared /rum/v1 base; collect and replay endpoints are derived from it. */
  endpoint: string;
  apiKey: string;
  replay?: false | { samplingRate?: number };
  /** Browser origins that may receive W3C trace context (optional). */
  propagateTraceHeaderCorsUrls?: string[];
}

export interface CoreRumReplayGlobals {
  ReplayInstrumentation: new (options: Record<string, unknown>) => unknown;
  takeFullSnapshot: (fullSnapshot?: boolean) => void;
}

declare global {
  interface Window {
    initCoreRum?: (config: InitCoreRumConfig) => Faro;
    __coreRumReplay?: CoreRumReplayGlobals;
  }
}

const REPLAY_MASK_TEXT = '.faro-mask, [data-faro-mask], [contenteditable]';
const REPLAY_BLOCK =
  "input[type='password'], [autocomplete='current-password'], [autocomplete='new-password'], [autocomplete='one-time-code'], form[action*='login' i], form[action*='signin' i], form[action*='checkout' i], form[action*='payment' i]";

export function initCoreRum(config: InitCoreRumConfig): Faro {
  const endpoint = config.endpoint.replace(/\/+$/, '');
  const replayEnabled = Boolean(config.replay);
  const samplingRate = replayEnabled
    ? (config.replay && config.replay.samplingRate) || 0.1
    : 0;

  const instrumentations: Instrumentation[] = [...getWebInstrumentations()];

  if (replayEnabled && window.__coreRumReplay) {
    const replay = window.__coreRumReplay;
    instrumentations.push(
      new replay.ReplayInstrumentation({
        samplingRate,
        beforeSend: sanitizeReplayEvent,
        maskAllInputs: true,
        maskTextSelector: REPLAY_MASK_TEXT,
        blockSelector: REPLAY_BLOCK,
        recordCanvas: false,
        collectFonts: false,
        // Required for replay fidelity: collector turns link[_cssText] into <style>,
        // and the console player CSP blocks external stylesheets.
        inlineStylesheet: true,
        inlineImages: false,
        recordCrossOriginIframes: false,
      }) as unknown as Instrumentation,
    );
  }

  const faro = initializeFaro({
    app: {
      name: config.app.name,
      environment: config.app.environment,
      release: config.app.release,
    },
    sessionTracking: { enabled: true, samplingRate: 1 },
    pageTracking: { generatePageId: () => crypto.randomUUID() },
    transports: [
      new CoreRumTransport({
        apiKey: config.apiKey,
        collectUrl: `${endpoint}/collect`,
        replayUrl: `${endpoint}/replay`,
        replay: { enabled: replayEnabled },
      }),
    ],
    instrumentations,
  });

  // Default view = pathname; pages produce page views out of the box.
  function syncViewFromLocation() {
    faro.api.setView({ name: window.location.pathname || '/' });
  }
  syncViewFromLocation();
  for (const method of ['pushState', 'replaceState'] as const) {
    const original = history[method].bind(history) as (...args: unknown[]) => unknown;
    history[method] = ((...args: unknown[]) => {
      const result = original(...args);
      syncViewFromLocation();
      return result;
    }) as typeof history[typeof method];
  }
  window.addEventListener('popstate', syncViewFromLocation);

  if (replayEnabled && window.__coreRumReplay) {
    const takeFullSnapshot = window.__coreRumReplay.takeFullSnapshot;
    let replayScope = '';
    faro.metas.addListener((meta) => {
      const nextScope = `${meta.session?.id ?? ''}\u0000${meta.user?.id ?? ''}`;
      if (nextScope === replayScope) return;
      replayScope = nextScope;
      try {
        takeFullSnapshot(true);
      } catch {
        // Replay may be paused; its next start supplies a bootstrap snapshot.
      }
    });
  }

  return faro;
}
