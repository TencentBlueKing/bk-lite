# ADR 0010: Redis is required when RUM is enabled

Status: accepted

## Context

Upstream RUM stores application registry, Browser Keys, Origins, budgets,
last-accepted / last-stored evidence, and Session Replay indexes in Redis under
`ops:rum:v2:*`. The Faro gateway admission path is a Redis Lua script; without
Redis the public gateway cannot safely accept browser traffic.

BK-Lite currently treats Redis as an optional cache (`REDIS_CACHE_URL`).

## Decision

1. When the RUM product is installed/enabled, Redis is a hard runtime dependency
   for the RUM gateway, controller, and maintainer.
2. Django `apps.rum` talks to that state through NATS `rum.v1.control.*`
   (controller), not by writing Redis keys directly from Python.
3. Product tables (issues, funnels, monitors, sourcemaps, erase jobs, …) remain
   in PostgreSQL.

## Consequences

- Local/dev and production install docs must provision Redis before RUM smoke.
- Operators disabling Redis must also disable RUM; the control plane should
  surface `controlUnavailable` rather than silently accepting traffic.
