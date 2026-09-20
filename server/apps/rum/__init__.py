"""RUM product domain — Real User Monitoring control plane.

Ported from core-admin `plugins/ops/server/rum`. Telemetry stays in
VictoriaLogs / VictoriaTraces / MinIO; this app owns Postgres product assets,
NATS control calls, LogsQL query orchestration, and domain alerts.
"""
