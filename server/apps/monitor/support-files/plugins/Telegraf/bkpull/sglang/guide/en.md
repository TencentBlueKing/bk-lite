# SGLang Monitoring Integration Guide

This plugin uses Telegraf to scrape the Prometheus metrics endpoint exposed by SGLang. Enter the full metrics URL including scheme, host, port, and path.

## Prerequisites

- Launch SGLang with `--enable-metrics`; otherwise `/metrics` is not exposed.
- Official docs use port `30000` as an example: `http://<host>:30000/metrics`.
- Optional: `--enable-mfu-metrics` for MFU counters (not included in the first metric set of this plugin).
- The collector node must reach the full URL.
- Current official examples use the `sglang:` colon prefix; older `sglang_*` names may appear depending on version/pipeline—adjust after a live scrape if needed.
- For HTTPS, place readable CA/client cert/key files on the collector node.

## Integration Steps

1. Confirm the process was started with `--enable-metrics`.
2. Run the pre-check and confirm `sglang:` series in the response.
3. Fill URL, optional TLS, interval, and certificate verification on the SGLang page.
4. Select a node, enter the same URL, instance name, and optional group.
5. Save and wait at least one scrape interval (default `60` seconds).

## Pre-check

```bash
SGLANG_METRICS_URL=http://127.0.0.1:30000/metrics
curl --fail-with-body --silent --show-error "$SGLANG_METRICS_URL" --output /tmp/sglang-metrics.txt
grep -E -m 8 '^# (HELP|TYPE) sglang:' /tmp/sglang-metrics.txt
grep -E -m 8 '^sglang:' /tmp/sglang-metrics.txt
```

Example launch (from official docs):

```bash
python -m sglang.launch_server \
  --model-path <your_model_path> \
  --port 30000 \
  --enable-metrics
```

`curl` must exit `0` and the body must contain `sglang:` metrics. If empty or non-metrics, check `--enable-metrics` first.

## Form Fields

| Field | Required | Default | Description |
| --- | --- | --- | --- |
| URL | Yes | none | Full metrics URL, e.g. `http://127.0.0.1:30000/metrics`. |
| CA Certificate Path | No | none | CA file on the collector node. |
| Client Certificate Path | No | none | Client cert for mTLS. |
| Client Key Path | No | none | Client key for mTLS. |
| Interval | Yes | `60` s | Telegraf scrape interval. |
| Skip Certificate Verification | No | off | Keep off in production. |
| Node | Yes | none | Collector node. |
| URL (instance) | Yes | none | Full metrics URL; must be unique. |
| Instance Name | Yes | none | Display name. |
| Group | No | none | Optional group. |

Request/response timeouts are fixed at `30` seconds in the template.

## Naming After Ingest

Telegraf `inputs.prometheus` (default `metric_version=1`) names follow `{upstream_name}_{type}`. Verified with Telegraf 1.32.3:

| Upstream name | Type | Platform query name |
| --- | --- | --- |
| `sglang:num_running_reqs` | gauge | `sglang:num_running_reqs_gauge` |
| `sglang:num_queue_reqs` | gauge | `sglang:num_queue_reqs_gauge` |
| `sglang:prompt_tokens_total` | counter | `sglang:prompt_tokens_total_counter` |
| `sglang:time_to_first_token_seconds` | histogram | `sglang:time_to_first_token_seconds_count` / `_sum` / `_<le>` |
| `sglang:e2e_request_latency_seconds` | histogram | `sglang:e2e_request_latency_seconds_count` / `_sum` / `_<le>` |

The colon prefix is preserved.

## Post-integration Checks

1. Wait one scrape interval and confirm instance status.
2. Verify registered series such as:
   - `sglang:num_running_reqs_gauge`
   - `sglang:num_queue_reqs_gauge`
   - `sglang:cache_hit_rate_gauge`
   - `sglang:gen_throughput_gauge`
   - `sglang:time_to_first_token_seconds_p99`
   - `sglang:time_to_first_token_seconds_p90`
   - `sglang:e2e_request_latency_seconds_p90`
3. If empty, re-check the URL and `--enable-metrics`.

## FAQ

### `/metrics` 404 or non-metrics body

Ensure `--enable-metrics` and that the URL hits the service port `/metrics`.

### Prefix is `sglang_` instead of `sglang:`

Some versions/pipelines rewrite colons. Use live scrape + Telegraf naming as source of truth.

### HTTPS / timeouts

Fix certificates and network first; template HTTP timeout is `30` seconds.
