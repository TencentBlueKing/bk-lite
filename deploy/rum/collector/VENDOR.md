# Vendored from alphamind-dev/core-admin

- Source commit: `d1dc8b3465d4a5cbda457b4d4836145fc5743485`
- Copied paths:
  - `apps/collector/internal/rum` → `internal/rum`
  - `apps/collector/pkg/rum` → `pkg/rum`
  - `platform/server/rumprivacy` → `internal/rumprivacy`
  - `deploy/collector/rum.yaml` → `otel/rum.gateway.yaml` (wiring land in T11)
- Module rewrite: upstream collector module path → `github.com/bk-lite/rum-collector`
- Module rewrite: upstream `platform/server/rumprivacy` → `internal/rumprivacy`
- Test-only LogsQL store import rewritten to `internal/victorialogscontract` (compile isolation; full analytics client stays in Django `apps.rum`).

Re-vendor by re-running the T10 sync and re-applying import rewrites. Do not edit the upstream tree from here.
