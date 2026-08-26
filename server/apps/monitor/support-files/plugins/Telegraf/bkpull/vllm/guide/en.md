# vLLM Monitoring Integration Guide

This plugin uses Telegraf to scrape the Prometheus metrics endpoint exposed by the vLLM OpenAI-compatible API server. Enter the full metrics URL including scheme, host, port, and path.

## Prerequisites

- A running vLLM API server that exposes `/metrics` (usually on the same port as the OpenAI-compatible API, for example `8000`).
- Official docs do not require an extra enable flag; if a reverse proxy blocks `/metrics`, allow it first.
- The collector node must reach the full URL—do not rely on host/port reachability alone.
- Metric names follow the vLLM V1 `vllm:` prefix (for example `vllm:kv_cache_usage_perc`). Deprecated `gpu_cache_*` names are not covered by this plugin.
- For HTTPS, CA/client certificate/key files must exist on the collector node and be readable by the collector process.
- Prefer a trusted CA. Enable “Skip Certificate Verification” only for temporary troubleshooting.

## Integration Steps

1. Run the pre-check on the collector node and confirm the metrics URL returns `vllm:` series.
2. On the vLLM config page, fill in the URL, optional TLS paths, interval, and certificate verification setting.
3. In the instance table, select a node, enter the same full URL, instance name, and optional group.
4. Save and wait at least one scrape interval (default `60` seconds).

## Pre-check

HTTP example:

```bash
VLLM_METRICS_URL=http://127.0.0.1:8000/metrics
curl --fail-with-body --silent --show-error "$VLLM_METRICS_URL" --output /tmp/vllm-metrics.txt
grep -E -m 8 '^# (HELP|TYPE) vllm:' /tmp/vllm-metrics.txt
grep -E -m 8 '^vllm:' /tmp/vllm-metrics.txt
```

HTTPS mutual TLS example:

```bash
VLLM_METRICS_URL=https://vllm.example.com:8000/metrics
curl --fail-with-body --silent --show-error \
  --cacert /etc/ssl/vllm/ca.pem \
  --cert /etc/ssl/vllm/client.pem \
  --key /etc/ssl/vllm/client-key.pem \
  "$VLLM_METRICS_URL" --output /tmp/vllm-metrics.txt
grep -E -m 8 '^vllm:' /tmp/vllm-metrics.txt
```

`curl` must exit `0` and the body must contain Prometheus metrics with the `vllm:` prefix.

Record the version for later comparison against upstream metric renames:

```bash
vllm --version
```

## Form Fields

| Field | Required | Default | Description |
| --- | --- | --- | --- |
| URL | Yes | none | Full `http://` or `https://` metrics URL, e.g. `http://127.0.0.1:8000/metrics`. |
| CA Certificate Path | No | none | CA file path on the collector node for HTTPS. |
| Client Certificate Path | No | none | Client certificate for mTLS; pair with the client key. |
| Client Key Path | No | none | Client private key for mTLS. |
| Interval | Yes | `60` s | Telegraf scrape interval; minimum `1`. |
| Skip Certificate Verification | No | off | Disables HTTPS server cert verification; keep off in production. |
| Node | Yes | none | Collector node that performs the scrape. |
| URL (instance) | Yes | none | Full metrics URL for this instance; must be unique in the config. |
| Instance Name | Yes | none | Display name in the platform. |
| Group | No | none | Optional instance group. |

Request and response timeouts are fixed at `30` seconds in the template. There are no separate scheme/host/port/path fields on the page.

## Naming After Ingest (VictoriaMetrics)

Telegraf `inputs.prometheus` (default `metric_version=1`, same as the etcd bkpull template) stores the Prometheus type as a field. After Influx line protocol ingest, query names follow `{upstream_name}_{type}`. Verified with Telegraf 1.32.3:

| Upstream Prometheus name | Type | Platform query name |
| --- | --- | --- |
| `vllm:num_requests_running` | gauge | `vllm:num_requests_running_gauge` |
| `vllm:num_requests_waiting` | gauge | `vllm:num_requests_waiting_gauge` |
| `vllm:kv_cache_usage_perc` | gauge | `vllm:kv_cache_usage_perc_gauge` |
| `vllm:prompt_tokens_total` | counter | `vllm:prompt_tokens_total_counter` |
| `vllm:generation_tokens_total` | counter | `vllm:generation_tokens_total_counter` |
| `vllm:time_to_first_token_seconds` | histogram | `vllm:time_to_first_token_seconds_count` / `_sum` / `_<le>` |
| `vllm:inter_token_latency_seconds` | histogram | `vllm:inter_token_latency_seconds_count` / `_sum` / `_<le>` |
| `vllm:request_prompt_tokens` | histogram | `vllm:request_prompt_tokens_count` / `_sum` / `_<le>` |
| `vllm:request_generation_tokens` | histogram | `vllm:request_generation_tokens_count` / `_sum` / `_<le>` |
| `vllm:iteration_tokens_total` | histogram | `vllm:iteration_tokens_total_count` / `_sum` / `_<le>` |

The colon prefix is preserved (not rewritten to underscores).

## Post-integration Checks

1. Wait at least one scrape interval and confirm the instance status updates.
2. On the metrics page, verify data for registered series such as:
   - `vllm:num_requests_running_gauge`
   - `vllm:num_requests_waiting_gauge`
   - `vllm:kv_cache_usage_perc_gauge`
   - `vllm:generation_tokens_total_counter_rate`
   - `vllm:time_to_first_token_seconds_p99`
   - `vllm:inter_token_latency_seconds_p99`
   - `vllm:request_prompt_tokens_p99`
   - `vllm:request_generation_tokens_p99`
   - `vllm:request_success_total_counter_rate`
3. If the instance exists but has no metrics, re-run the full URL check and confirm `vllm:` lines in the response.

## FAQ

### URL returns 404

The page does not append `/metrics` automatically. Ensure the URL includes the real metrics path and that proxies do not block it.

### API works but no `vllm:` metrics

Confirm you are scraping the vLLM API server metrics endpoint. Use `grep '^vllm:'` on the response body.

### HTTPS handshake / certificate errors

Fix CA chain, validity, hostname, and mTLS material. Do not leave skip-verify enabled permanently.

### Timeouts

Verify network reachability from the collector node. Increase the page interval if needed; template HTTP timeouts remain `30` seconds.

### Metric names differ from docs

If the target still exposes deprecated names such as `vllm:gpu_cache_usage_perc`, this plugin queries the V1 name `vllm:kv_cache_usage_perc_gauge`. Upgrade vLLM or adjust the metric table after a live scrape.
