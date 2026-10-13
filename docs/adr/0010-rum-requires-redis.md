# ADR 0010: Redis is the RUM hot path, not the config authority

Status: accepted

## Context

The Faro gateway admission path is a Redis Lua script. Session assignment,
replay indexes, and short-lived erasure fences also live in Redis under
`ops:rum:v2:*`. Without Redis the public gateway cannot safely accept browser
traffic.

Application configuration and erase jobs are durable product data. They used to
exist only in Redis, with `WAITAOF` after every write and a different ACL
username for each process.

## Decision

1. When RUM is enabled, Redis remains a hard runtime dependency for the gateway,
   controller, and maintainer. It stores only rebuildable projections and
   short-lived hot-path state.
2. The business database, accessed through Django ORM, is the authority for
   application configuration and erase jobs. Django publishes projections over
   NATS `rum.v1.control.projection.*` and does not write Redis keys itself.
3. Redis 5 with a single password is enough. AOF and Redis ACL usernames are
   optional hardening (`redis_require_acl_identity` / `--redis-require-acl-identity`),
   not startup requirements.
4. Product tables (applications, origins, keys, projection outbox, issues,
   funnels, monitors, sourcemaps, erase jobs) stay in the business database.
   The schema does not use PostgreSQL-only types.

## Consequences

- Local/dev and production install docs must provision Redis before RUM smoke.
- Operators disabling Redis must also disable RUM; the control plane should
  surface `controlUnavailable` rather than silently accepting traffic.
- A failed projection publish leaves the saved business row and
  `projectionPending`; the gateway must not be described as ready to ingest.
