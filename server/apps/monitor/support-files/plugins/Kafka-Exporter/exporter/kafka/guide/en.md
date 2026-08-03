# Kafka Monitoring Guide

This capability uses kafka_exporter to access brokers through the Kafka client protocol, and Telegraf then scrapes the exporter's local `/metrics` endpoint. It does not use JMX.

## Prerequisites

- The collector node can reach the configured broker `host:port` and every broker address returned through `advertised.listeners`.
- The page accepts one broker address only. It is used for cluster discovery; multiple broker entries cannot be entered on the page.
- The current page supports plaintext and SASL over plaintext. It has no TLS switch or certificate fields.
- When SASL is enabled, prepare the username, password, and mechanism that match the broker, and grant access to topic, partition, and consumer-group metadata.
- Reserve an unused exporter listen port on the collector node. It is separate from the Kafka broker port.
- The current exporter requires Kafka **0.10.2.0** or newer; older versions fail to start.

## Setup Steps

1. From the actual collector node, verify both the initial broker and its advertised addresses.
2. Enter a Kafka protocol version (at least `0.10.2.0`). Enable authentication and enter the SASL username, password, and mechanism when required.
3. Enter an unused listen port, one Kafka server address, topic/group include and exclude expressions, and the interval (default `60` seconds).
4. For large topic or consumer-group fleets, tune concurrency, batch size, and consumer-group collection timeout as needed.
5. In the monitored objects table, select the node and enter the listen port, server address, instance name, and optional group.
6. Save the configuration and wait for at least one collection interval.

## Pre-checks

Check the configured broker port from the collector node, for example:

```bash
nc -vz broker.example.com 9092
```

Also run a Kafka client metadata query with the same authentication mode. Confirm that every broker address returned by the cluster is reachable from the collector node. Reachability of the initial port alone does not validate the full discovery path.

## Field Reference

| Field | Required | Description |
| --- | --- | --- |
| Version | Yes | Kafka client protocol version, such as `2.0.0`; it must be compatible with the broker. **Minimum: `0.10.2.0`**. |
| Enable Authentication | No | SASL switch; disabled by default. |
| Username, Password | Conditional | Required when authentication is enabled. |
| Operation Mode | No | SASL mechanism: `plain`, `sha256`, `sha512`, or `gssapi`; empty uses PLAIN as the current exporter default. |
| Listen Port | Yes | Local port where the exporter exposes `/metrics`. |
| Server Address | Yes | One broker `host:port`. |
| Topic Include / Exclude | No | Regular expressions default to `.*` and `^$`. |
| Consumer Group Include / Exclude | No | Regular expressions default to `.*` and `^$`. |
| Topic Collection Workers | Yes | Concurrency for topic metadata and offset requests; default `20`. |
| Consumer Group Collection Workers | Yes | Concurrency for consumer-group OffsetFetch requests; default `20`. |
| Consumer Group Batch Size | Yes | Maximum consumer groups per DescribeGroups request; default `50`. |
| Offset Batch Size | Yes | Maximum partitions per ListOffsets request; default `1000`. |
| Consumer Group Collection Timeout | Yes | Timeout in seconds for one consumer-group metric collection; default `45`. **Must be less than the collection interval.** |
| Collect All Committed Partitions | Yes | Enabled by default; when disabled, only partitions assigned to active members are collected. |
| Allow Concurrent Scrapes | Yes | Disabled by default; keep disabled for 10,000-topic clusters so concurrent scrapes share one result. |
| Interval | Yes | Collection interval in seconds; default `60`. |
| Node | Yes | Collector node that runs the exporter. |
| Instance Name | Yes | Display name in the platform. |
| Group | No | Optional instance group. |

## Recommended Timeout Values

Keep this timeout relationship so Telegraf does not finish before the exporter and leave the instance without data:

`GROUP_METRICS_TIMEOUT` < collection `interval`

Telegraf `timeout` and `response_timeout` are **always equal to `interval`** (issued together by the child template). Do not set them shorter or longer than the interval on their own.

| Parameter | Recommended value |
| --- | --- |
| Collection interval (`interval`) | `60` seconds |
| Telegraf `timeout` / `response_timeout` | Same as `interval` (for example `60` seconds) |
| Consumer-group collection timeout (`GROUP_METRICS_TIMEOUT`) | `45` seconds (must be less than `interval`) |

If you lower the interval to `30` seconds, also lower the consumer-group collection timeout below `30` seconds (for example `20` seconds). The platform validates this order on save.

## Upgrade and Redeploy

Existing instances do not automatically pick up child-template timeout changes. After upgrading BK-Lite or kafka_exporter, re-save and redeploy the instance collection config on the integration page if you need the new `timeout` / `response_timeout` behavior (aligned with the interval).

## Lag Semantics

- `kafka_consumergroup_lag = LEO - committed offset`, both from the same scrape.
- When the committed offset is `-1`, lag is `-1` and no anomaly series is emitted; the partition has no commit record.
- When the committed offset is greater than the same-scrape LEO, the exporter keeps the computed negative lag (which may be `-1`) and emits `kafka_consumergroup_lag_anomaly=1`.
- Therefore a lag of `-1` must be read with the anomaly metric: no anomaly series means no commit record; anomaly `1` means the committed offset exceeds LEO.

## Post-setup Verification

After saving and waiting for one interval, check the local endpoint with the configured listen port, for example:

```bash
curl --fail --silent --show-error "http://127.0.0.1:9308/metrics"
```

Then confirm that these metrics are queryable in the platform:

- `kafka_up_gauge`
- `kafka_brokers_gauge`
- `kafka_exporter_scrape_success`
- `kafka_topic_partition_count`
- `kafka_consumergroup_lag`

## Troubleshooting

### The initial broker is reachable but no data appears

- Inspect the exporter log for the broker addresses it actually uses. Collection fails when `advertised.listeners` returns addresses unreachable from the collector node.
- Confirm that the configured protocol version is at least `0.10.2.0` and compatible with the broker.
- TLS cannot be configured on the current page, so a TLS-only cluster cannot be integrated directly.
- Confirm that the consumer-group collection timeout is less than the collection interval so Telegraf does not time out before the exporter finishes.

### SASL authentication fails

- Check that the authentication switch, username, password, and mechanism match the broker.
- Enter the password only in the password field; do not embed it in the server address or another field.

### Topic or consumer-group data is missing

- Check the include and exclude expressions. The default exclude expression `^$` excludes nothing.
- Confirm that the account can read topic, partition, and consumer-group metadata.
