# llama-server Monitoring Integration Guide

This plugin uses Telegraf to scrape the Prometheus metrics endpoint from llama.cpp `llama-server`. Enter the full metrics URL including scheme, host, port, and path.

## Prerequisites

- Start `llama-server` with `--metrics` (or `LLAMA_ARG_ENDPOINT_METRICS`); otherwise `/metrics` is unavailable.
- Common default port is `8080`, e.g. `http://<host>:8080/metrics`.
- The collector node must reach the full URL.
- In router mode, the master and per-model processes may expose separate metrics endpoints and may require a `?model=` query parameter—confirm the correct scrape URL first.
- For HTTPS, place readable certificate material on the collector node.

## Integration Steps

1. Confirm the process was started with `--metrics`.
2. Run the pre-check and confirm `llamacpp:` series.
3. Fill URL, optional TLS, interval, and certificate verification.
4. Select a node, enter the same URL, instance name, and optional group.
5. Save and wait at least one scrape interval (default `60` seconds).

## Pre-check

```bash
LLAMA_METRICS_URL=http://127.0.0.1:8080/metrics
curl --fail-with-body --silent --show-error "$LLAMA_METRICS_URL" --output /tmp/llamaserver-metrics.txt
grep -E -m 8 '^# (HELP|TYPE) llamacpp:' /tmp/llamaserver-metrics.txt
grep -E -m 8 '^llamacpp:' /tmp/llamaserver-metrics.txt
```

If metrics are disabled, the server typically reports that the endpoint is unsupported. Enable `--metrics` and retry.

Record version information when possible:

```bash
llama-server --version 2>/dev/null || true
```

## Form Fields

| Field | Required | Default | Description |
| --- | --- | --- | --- |
| URL | Yes | none | Full metrics URL, e.g. `http://127.0.0.1:8080/metrics`. |
| CA Certificate Path | No | none | CA file on the collector node. |
| Client Certificate Path | No | none | Client cert for mTLS. |
| Client Key Path | No | none | Client key for mTLS. |
| Interval | Yes | `60` s | Telegraf scrape interval. |
| Skip Certificate Verification | No | off | Keep off in production. |
| Node | Yes | none | Collector node. |
| URL (instance) | Yes | none | Full metrics URL; must be unique. |
| Instance Name | Yes | none | Display name. |
| Group | No | none | Optional group. |

Template HTTP timeouts are fixed at `30` seconds.

## Naming After Ingest

Telegraf `inputs.prometheus` (default `metric_version=1`) names follow `{upstream_name}_{type}`. Verified with Telegraf 1.32.3:

| Upstream name | Type | Platform query name |
| --- | --- | --- |
| `llamacpp:requests_processing` | gauge | `llamacpp:requests_processing_gauge` |
| `llamacpp:kv_cache_usage_ratio` | gauge | `llamacpp:kv_cache_usage_ratio_gauge` |
| `llamacpp:prompt_tokens_total` | counter | `llamacpp:prompt_tokens_total_counter` |
| `llamacpp:tokens_predicted_total` | counter | `llamacpp:tokens_predicted_total_counter` |
| `llamacpp:n_decode_total` | counter | `llamacpp:n_decode_total_counter` |
| `llamacpp:n_busy_slots_per_decode` | counter | `llamacpp:n_busy_slots_per_decode_counter` |

The colon prefix is preserved.

> **Note:** Newer llama.cpp builds may remove `llamacpp:kv_cache_usage_ratio`. If absent on the target, KV panels/alerts may stay empty—use a live `/metrics` scrape as source of truth.

## Post-integration Checks

1. Wait one scrape interval and confirm instance status.
2. Verify registered series such as:
   - `llamacpp:requests_processing_gauge`
   - `llamacpp:requests_deferred_gauge`
   - `llamacpp:predicted_tokens_seconds_gauge`
   - `llamacpp:n_decode_total_counter_rate`
   - `llamacpp:n_busy_slots_per_decode_gauge`
   - `llamacpp:tokens_per_decode_gauge`
3. If empty, confirm `--metrics` and the router-mode scrape target.

## FAQ

### `/metrics` unsupported

`--metrics` was not enabled. Start with the flag and retry.

### Incomplete metrics in router mode

Master and worker processes may expose different endpoints. Scrape the URL that matches your operations need (optionally with `model`).

### HTTPS / timeouts

Fix certificates and network first; template timeout is `30` seconds.
