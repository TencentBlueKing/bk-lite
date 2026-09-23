// CDN Replay asset: optional separate bundle loaded only when the CDN snippet
// has Replay enabled. Registers the Replay instrumentation + full snapshot
// helper on a global the onboarding facade picks up at initCoreRum time.
import { ReplayInstrumentation } from '@grafana/faro-instrumentation-replay';
import { takeFullSnapshot } from '@grafana/rrweb';

declare global {
  interface Window {
    __coreRumReplay: {
      ReplayInstrumentation: typeof ReplayInstrumentation;
      takeFullSnapshot: typeof takeFullSnapshot;
    };
  }
}

window.__coreRumReplay = { ReplayInstrumentation, takeFullSnapshot };
