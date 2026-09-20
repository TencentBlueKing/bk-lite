# BK-Lite RUM Collector / Gateway

Vendored RUM data-plane packages from `alphamind-dev/core-admin` for the public Faro
collect + Session Replay gateway and control-plane controller.

## Layout

| Path | Role |
| --- | --- |
| `internal/rum/components/*` | OTel receiver/processor/exporter factories |
| `internal/rum/ingress` | Browser Key + Origin Redis Lua admission |
| `internal/rum/controller` | NATS control handlers → Redis `ops:rum:v2:*` |
| `pkg/rum/wire` | NATS `rum.v1.control.*` contract |
| `pkg/rum/replayindex` | Replay Redis index helpers |
| `otel/rum.gateway.yaml` | Production-shaped gateway config |
| `otel/rum.gateway.dev.yaml` | Local/dev gateway config (BK-Lite env names) |
| `cmd/bklite-rum-gateway` | Faro `:4319` + replay `:4320` binary |
| `cmd/bklite-rum-controller` | NATS `rum.v1.control.*` queue consumer |
| `cmd/bklite-rum-maintainer` | Erase jobs + Replay reconcile / orphan scan |
| `internal/rum/maintainer` | Maintainer Redis / Victoria / MinIO workers |
| `env/*.env.example` | Dev env templates (ACL Redis usernames required) |
| `VENDOR.md` | Source commit + rewrite rules |

## Status

- **T10–T15:** data-plane binaries + compose fixture + `packages/bklite-rum-sdk`.
- **P2:** Django BFF parity (`apps.rum`).

## Build

```bash
make tidy
make test-controller test-maintainer
make build          # gateway + controller + maintainer
make validate-config
```

Do not point APM OTLP 4318 at this gateway. See `docs/adr/0009-rum-public-gateway.md`.
