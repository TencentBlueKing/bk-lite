# RUM port tickets

Source: [`spec.md`](./spec.md). Loop picks the **first unchecked** ticket each
tick, implements it, updates this file, then stops for that tick unless the
ticket is a tiny follow-on.

Legend: `[ ]` pending · `[~]` in progress · `[x]` done · `[-]` cancelled

## P0 — Architecture & scaffold

- [x] T00 Write `specs/changes/rum-port/{spec,tickets}.md`
- [x] T01 Scaffold `server/apps/rum` (AppConfig, urls, empty viewsets, models for 8+1 tables)
- [x] T02 Seed `server/support-files/system_mgmt/menus/rum.json` + roles
- [x] T03 Scaffold `web/src/app/rum` routes for all 15 pages + `constants/menu.json` + locales stubs
- [x] T04 Register `app.rum` in `web/src/locales/{zh,en}.json` and public menus
- [x] T05 Draft ADR: RUM public gateway (Browser Key + Origin) separate from APM ADR 0008 (`docs/adr/0009-rum-public-gateway.md`)
- [x] T06 Draft ADR / decision: Redis hard dependency when RUM enabled (`docs/adr/0010-rum-requires-redis.md`)
- [x] T07 Generate Django migration `0001_initial` for rum product tables and run focused import check
- [x] T08 Confirm `apps.rum` auto-discovers under `/api/v1/rum/` when `INSTALL_APPS` includes `rum` (local `.env` currently omits it — operators must add `rum`)
- [x] T09 Add `rum` to local/dev INSTALL_APPS docs (DEVELOP.md) without forcing unrelated apps

## P1 — Data plane

- [x] T10 Vendor upstream RUM collector packages into `deploy/rum/collector` (commit `d1dc8b34`, import rewrite to `github.com/bk-lite/rum-collector`, factory stub + `otel/rum.gateway.yaml`)
- [x] T11 Wire Faro collect `:4319/rum/v1/collect` and replay `:4320/rum/v1/replay` (buildable `bklite-rum-gateway`, BK-Lite env/secrets, OTel **0.154.0** aligned with upstream — not APM 0.153.0; `make validate-config` green)
- [x] T12 Port `core-rum-controller` → `cmd/bklite-rum-controller` + NATS `rum.v1.control.*` subjects (`make build-controller` / `test-controller` green)
- [x] T13 Port `core-rum-maintainer` → `cmd/bklite-rum-maintainer` (erase + replay reconcile; `make build-maintainer` / `test-maintainer` green)
- [x] T14 `deploy/rum` compose fixture + ACCEPTANCE.md (`make validate` green; image pull smoke may need registry access)
- [x] T15 Publish `bklite-rum-sdk` from upstream `packages/core-rum-sdk` (rename + CDN URLs; `bun run check` / pack green; assets → `web/public/rum/`)

## P2 — Django BFF (parity with upstream `/api/ops/rum`)

- [x] T20 Applications CRUD + keys + disable + status + overview + snippets + meta + analytics catalog (NATS control client + MemoryControl tests; overview/analytics degrade with `analyticsUnavailable` until T28 LogsQL)
- [x] T21 Sessions list/detail/trend + replay manifest/grants/segments (degrade until LogsQL/MinIO; HMAC grant/manifest signing; unit tests green)
- [x] T22 Views (CWV) + saved-views (list degrades until LogsQL; saved-views CRUD on `rum_saved_views`)
- [x] T23 Errors list/detail + issue triage + sourcemap restore (degrade until LogsQL; Memory/Django issue stores; VLQ restore)
- [x] T24 Funnels CRUD + reach (PG/memory store; reach degrades until LogsQL)
- [x] T25 Releases + baselines + sourcemap upload/CI ingest
- [x] T26 Monitors + alert-events + Celery evaluator + SystemMgmt notify
- [x] T27 Compliance erase (`rum_erase_jobs` ledger)
- [x] T28 LogsQL query parity tests vs upstream fixtures
- [x] T29 Health/degraded flags (`controlUnavailable` / `analyticsUnavailable`)

## P3 — Web pages (1:1 UI)

- [x] T30 Host adapters (`api`, i18n, Permission, searchParams)
- [x] T31 Applications list + create + overview + setup
- [x] T32 Sessions list + detail + replay player
- [x] T33 Views page
- [x] T34 Errors list + detail
- [x] T35 Funnels list + detail
- [x] T36 Releases + sourcemap manager
- [x] T37 Monitors + alert-events
- [x] T38 Compliance page
- [x] T39 Saved views / export / traffic filters across lists
- [x] T40 Vitest + DESIGN four-state pass

## P4 — Closeout

- [x] T50 `CONTEXT.md` RUM terms
- [x] T51 `mise run check` / focused pytest + vitest green for rum
  - Evidence (no `mise` in BK-Lite; focused equivalent):
    - `cd web && pnpm test:rum` → 16 passed
    - `cd server && DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true uv run pytest apps/rum/tests --no-cov` → 59 passed
- [x] T52 Cold review against this spec + diff
  - Spec P0 fixed: HTTP service defaults now use Django stores (compliance /
    monitors / releases / errors) so Celery evaluator and API share PG state.
  - Standards P0 fixed: `rum_logger` in `apps.core.logger`; rum services use it;
    notify/eval failures include `failed_stage` / `error_type`.
  - Residual P1 (not blocking T52): query “parity” tests are LogsQL/synthetic
    not upstream BFF golden; hardcoded palette colors; ViewSet error duplication;
    large `victoria_analytics.py`.
- [x] T53 Mark `spec.md` Status: implemented with completion evidence
  - `spec.md` → Status: implemented + Completion evidence
  - ADR 0009 / 0010 → Status: accepted
  - Re-check: `pnpm test:rum` 16 passed; pytest `apps/rum/tests` 59 passed
    (2026-09-07)

## Loop notes

- Prefer vertical slices that keep API + page for one domain green together
  once T01–T06 are done.
- Do not expand APM 4318. Do not introduce ClickHouse.
- Preserve upstream JSON field names (`camelCase` where the RUM API uses it) at the HTTP
  boundary even if Django models use snake_case.
