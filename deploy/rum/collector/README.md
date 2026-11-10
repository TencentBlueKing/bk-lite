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
| `otel/rum.gateway.yaml` | Production gateway config, including the aggregate branch |
| `otel/rum.gateway.ingest.yaml` | Same ingest config without the aggregate branch |
| `otel/rum.gateway.auth.yaml` | Optional basic-auth overlay for the aggregate remote write |
| `otel/rum.gateway.dev.yaml` | Local/dev gateway config (BK-Lite env names) |
| `cmd/bklite-rum-gateway` | Faro `:4319` + replay `:4320` binary |
| `cmd/bklite-rum-controller` | NATS `rum.v1.control.*` queue consumer |
| `cmd/bklite-rum-maintainer` | Erase jobs + Replay reconcile / orphan scan + session end records |
| `internal/rum/maintainer` | Maintainer Redis / Victoria / MinIO workers |
| `env/*.env.example` | Dev env templates (Redis password required; ACL username optional) |
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
make image          # bklite/rum-collector:0.1.0-bklite.3 (override RUM_COLLECTOR_IMAGE)
```

The image ships all three binaries under `/usr/local/bin/` and
`/etc/bklite-rum/rum.gateway.yaml`, `rum.gateway.ingest.yaml`, and `rum.gateway.auth.yaml`.
Select the process via entrypoint. Runtime wiring is in `../OPS-DEPLOY.md`.

`rum.gateway.yaml` requires `AGG_VICTORIAMETRICS_WRITE_URL` and `RUM_AGG_SHARD`.
An empty write URL fails validation and stops VictoriaLogs ingest with it. Collector
cannot disable one pipeline from an empty variable. Keep detail ingest by loading
`rum.gateway.ingest.yaml` instead. Do not fall back to `VICTORIAMETRICS_HOST`.
Load `rum.gateway.auth.yaml` as a second `--config` only when both
`AGG_VICTORIAMETRICS_USER` and `AGG_VICTORIAMETRICS_PASSWORD` are set. An empty
basicauth extension still sends `Authorization`.

Do not point APM OTLP 4318 at this gateway. See `docs/adr/0009-rum-public-gateway.md`.
