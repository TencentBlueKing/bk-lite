# Vendored / ported from alphamind-dev/core-admin

- Source path: `packages/core-rum-sdk`
- Package rename: `core-rum-sdk` → `bklite-rum-sdk`
- CDN artifacts: `bklite-rum-sdk.js`, `bklite-rum-replay.js` → copied to `web/public/rum/` on build
- Collect/replay URL contract unchanged: `/rum/v1/collect`, `/rum/v1/replay`
- Public class/facade names (`CoreRumTransport`, `initCoreRum`) kept for snippet 1:1 parity; package import path is `bklite-rum-sdk`

Re-sync by copying from `alphamind-dev/core-admin` and re-applying renames above. Do not edit the upstream tree from here.
