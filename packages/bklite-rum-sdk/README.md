# bklite-rum-sdk

`bklite-rum-sdk` is a browser transport for Grafana Faro `2.8.2`. It adds bounded
queues, deterministic retries, one atomic Faro collect batch, and isolated
segmented Session Replay. It does not wrap or re-export Faro instrumentation and
does not require a Grafana backend.

## Install

```sh
bun add --exact bklite-rum-sdk@0.1.0 @grafana/faro-web-sdk@2.8.2
```

Faro's published manifest uses a compatible range for `@grafana/faro-core`.
Pin the approved runtime line in the consuming application's `package.json`:

```json
{
  "overrides": {
    "@grafana/faro-core": "2.8.2",
    "@grafana/faro-web-sdk": "2.8.2"
  }
}
```

## Initialize Faro

```ts
import { getWebInstrumentations, initializeFaro } from "@grafana/faro-web-sdk";
import { CoreRumTransport } from "bklite-rum-sdk";

const faro = initializeFaro({
  app: {
    name: "my-app",
    environment: "production",
    release: "0.1.0",
  },
  instrumentations: getWebInstrumentations(),
  sessionTracking: { enabled: true, samplingRate: 1 },
  transports: [
    new CoreRumTransport({
      apiKey: "<browser-public-key>",
      collectUrl: "https://telemetry.example.com/rum/v1/collect",
      replayUrl: "https://telemetry.example.com/rum/v1/replay",
    }),
  ],
});
```

Replay is disabled unless `replay: { enabled: true }` is supplied. Configure
Grafana's Replay instrumentation separately and pass `sanitizeReplayEvent` as
its `beforeSend` hook.

## Fixed browser protocol

The default protocol sends `X-API-Key`, `X-RUM-Application`,
`X-RUM-Batch-Id`, and, for Replay, `X-Faro-Session-Id`. Header names and status
sets are not configurable. Only `202` means accepted; `408`, `429`, `502`,
`503`, and `504` are retried. `Retry-After` is honored.

## Delivery limits

- Ordinary events and browser traces share one Faro body, Batch ID, and bounded
  2 MiB queue. The body is retried unchanged until the Gateway has durably
  accepted every signal present in the batch.
- Replay: a separate serial 8 MiB queue with snapshot-rooted segments.
- A single collect body never exceeds 1 MiB.
- Network failures and the fixed retryable statuses use jittered exponential
  backoff while preserving the request body and batch identifier.
- `pagehide` and `visibilitychange: hidden` flush active Replay work using the
  browser keepalive budget when available.
