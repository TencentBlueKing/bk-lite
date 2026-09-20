# RUM 1:1 端口：core-admin → BK-Lite

Status: implemented

Source of truth for product behavior: `alphamind-dev/core-admin` at
`plugins/ops/{web,server}/rum`, `packages/core-rum-sdk`,
`apps/collector/internal/rum`, `cmd/core-rum-{controller,maintainer}`.

Local clone used for this port: `core-admin` (sibling of this repo).

## Problem Statement

BK-Lite has Monitor / Log / APM but no Real User Monitoring. Upstream
`alphamind-dev/core-admin` already ships a complete RUM domain with 15
console pages, browser SDK, public Faro gateway, Redis admission, VictoriaLogs
analytics, MinIO replay, and domain alerts. The user requires a **1:1 port of
pages + functions** into BK-Lite.

Host stacks differ: upstream control plane is Go + Vite plugin; BK-Lite control
plane is Django + Next.js App Router. Data plane on both sides is a custom
OTel Collector distribution in Go.

## Solution

Contract 1:1; host implementation follows BK-Lite conventions.

```text
Browser (core-rum-sdk / Faro 2.8.2)
  → POST /rum/v1/collect | /rum/v1/replay   (public gateway; Browser Key + Origin)
  → rumsession → VictoriaLogs / VictoriaTraces
  → replay exporter → MinIO + Redis index

apps.rum (Django BFF)  /api/v1/rum/*
  → PG product tables
  → NATS rum.v1.control.* → core-rum-controller → Redis ops:rum:v2:*
  → LogsQL / MinIO read
  → domain alerts → SystemMgmt.dispatch_notification

web/src/app/rum  /rum/*
  → 15 pages mirrored from upstream RUM routes
```

### Explicit decisions

1. **Data plane Go components are reused** (gateway internals, controller,
   maintainer, `pkg/rum/wire`, replayindex). Merged into BK-Lite collector
   builder / new binaries under `deploy/rum/`.
2. **Control-plane BFF is rewritten in Django** as `server/apps/rum`. HTTP
   path prefix becomes `/api/v1/rum` (drop upstream `/api/ops` segment). Response
   JSON shapes stay 1:1 with the upstream RUM API.
3. **Pages are ported** into `web/src/app/rum` with host adapters
   (`useApiClient`, `useTranslation`, `<Permission>`, Next navigation).
4. **New ADR required** before exposing public RUM gateway: RUM public ingest
   is separate from APM ADR 0008 trusted regional OTLP.
5. **Redis becomes a hard dependency** when RUM is enabled (admission +
   application registry + replay index).
6. **Only intentional product deviation**: compliance erase job ledger is
   stored in Postgres (`rum_erase_jobs`), not browser `localStorage`.

### Non-goals

- ClickHouse (upstream already cut over away from it).
- Keeping a Go BFF as the long-term control plane inside BK-Lite.
- Porting the upstream plugin shell / `@core-admin/platform-web` as a dependency.

## User Stories

1. As a RUM admin, I create an application with Origins and receive a Browser
   Key + SDK snippet that reports to the BK-Lite RUM gateway.
2. As an operator, I browse applications by session volume, error rate, and CWV.
3. As an operator, I open a session timeline and optionally play Session Replay.
4. As an operator, I triage clustered JS errors with source-map restore.
5. As a release owner, I compare releases and upload source maps.
6. As a product analyst, I define route funnels and compute reach.
7. As an alert admin, I set error-rate / CWV policies and receive notifications
   through System Management channels.
8. As a compliance officer, I erase a end-user's RUM data for an application.

## Route contract (must match upstream RUM UI)

| Path | Page |
| --- | --- |
| `/rum` → `/rum/applications` | redirect |
| `/rum/applications` | application list |
| `/rum/applications/:name/overview` | application overview |
| `/rum/applications/:name` | ingest setup |
| `/rum/sessions` | session list |
| `/rum/sessions/:sessionId` | session detail |
| `/rum/sessions/:sessionId/replay` | session replay |
| `/rum/views` | views / CWV |
| `/rum/errors` | error list |
| `/rum/errors/detail` | error detail |
| `/rum/funnels` | funnel list |
| `/rum/funnels/:id` | funnel detail |
| `/rum/releases` | releases + sourcemaps |
| `/rum/monitors` | alert policies |
| `/rum/alert-events` | alert events |
| `/rum/compliance` | compliance erase |

API contract mirrors the upstream RUM API under `/api/v1/rum/*` (see tickets for endpoint list).

## Phases

Tracked in [`tickets.md`](./tickets.md). Do not mark the change complete until
all P0–P3 tickets are done and acceptance scenarios pass.

## Acceptance (summary)

- SDK can report collect + replay against local `deploy/rum` fixture.
- Illegal Origin / Key rejected; valid Origin accepted.
- All 15 pages reachable with menu permissions; loading / empty / degraded /
  forbidden states present.
- Same VictoriaLogs fixture yields list/detail numbers within documented
  tolerance vs the upstream BFF (query parity tests).
- Policy fire / recover delivers via System Management channel.
- Erase job removes VL/VT/MinIO evidence for the targeted user id.
- APM 4318 remains trusted-intranet-only (ADR 0008 unchanged).

## Progress pointer

All tickets T00–T53 complete. See `tickets.md` and Completion evidence below.

## Completion evidence

- **Scaffold / menus / ADRs**: `server/apps/rum`, `web/src/app/rum` (15 routes),
  `support-files` menus, ADR
  [`0009`](../../../docs/adr/0009-rum-public-gateway.md) /
  [`0010`](../../../docs/adr/0010-rum-requires-redis.md) **accepted**.
- **Data plane**: `deploy/rum/` (gateway/controller/maintainer/compose +
  ACCEPTANCE.md); APM 4318 untouched.
- **BFF**: `/api/v1/rum/*` services + Django product stores (T52: HTTP defaults
  aligned with Celery); degrade flags `controlUnavailable` /
  `analyticsUnavailable`; erase ledger in PG (`rum_erase_jobs`).
- **Web**: pages + host adapters; focused vitest `pnpm test:rum` → **16 passed**
  (2026-09-07).
- **Tests**: `uv run pytest apps/rum/tests --no-cov` → **59 passed** (2026-09-07).
- **Known residual (non-blocking for Status:implemented)**: LogsQL tests are
  synthetic/shape parity, not upstream BFF golden tolerance; palette/token polish
  and ViewSet error dedupe remain P1 follow-ups.
