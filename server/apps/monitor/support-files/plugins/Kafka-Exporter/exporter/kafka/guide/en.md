# Kafka Monitoring Guide

This plugin uses WeOps's kafka_exporter (forked from danielqsj/kafka_exporter) to connect to Kafka brokers via the **Kafka client protocol** and collect broker / topic / consumer-group metrics. Telegraf `inputs.prometheus` scrapes the exporter's local listen port at `/metrics`. Be sure to distinguish the **exporter listen port** from the **Kafka broker port** (default Kafka `9092`, exporter `9308`).

## Prerequisites

- The target Kafka broker(s) are running and listening on `9092` (default).
- The exporter connects to the broker via the Kafka client protocol — JMX access on the broker is NOT required.
- Kafka must have `advertised.listeners=PLAINTEXT://<reachable_ip>:9092`; the broker must be reachable via the address it advertises.
- When SASL is enabled, create the monitor account on the broker side (`bin/kafka-configs.sh` or the KRaft controller).
- When TLS is enabled, exporter needs `tls.ca-file` / `tls.cert-file` / `tls.key-file`. The current UI does not expose TLS, so only plaintext or SASL/plaintext is supported.
- The collector node can reach Kafka broker (default `9092`).
- The exporter process starts and the collector can access `http://127.0.0.1:9308/metrics`.

> The `kafka.server` field is broker `host:port`. **Use multiple `--kafka.server` flags for multiple brokers**; the current UI exposes only one. Multi-broker support needs UI extension.

## Recommended Permissions

Grant the monitor account minimum read-only permissions:

```text
# SASL/SCRAM (Kafka 7.0+) — create creds via bin/kafka-configs.sh first
# The monitor account needs Describe only; no pub/sub needed.
kafka-acls.sh --authorizer-properties zookeeper.connect=<zk:2181> \
  --add --allow-principal User:'<monitor>' --operation Describe --topic '*'
kafka-acls.sh --add --allow-principal User:'<monitor>' --operation Describe --group '*'
kafka-acls.sh --add --allow-principal User:'<monitor>' --operation ClusterAction --cluster '*'
```

`Describe Topic` and `Describe Group` are required to capture lag/offset; `Cluster Action` is required for `kafka_consumergroup_*`.

## Setup Steps

1. Verify the broker port is reachable from the collector:

   ```bash
   nc -zv <broker_host> 9092
   ```

2. On the configure page, fill in:
   - Kafka version (default `2.0.0`)
   - Enable authentication (as needed)
   - SASL username / password / mechanism (as needed; SCRAM-SHA-256 / SCRAM-SHA-512 / GSSAPI)
   - Exporter listen port (default `9308`)
   - Kafka server address (`host:port`, e.g. `broker-1:9092`)
   - Topic include / exclude (as needed; regex `.*` / `^$`)
   - Consumer group include / exclude (as needed)
   - Interval (default `60s`)
3. Add rows in the monitored objects table for node, listen port, Kafka server address, instance name, and group.
4. Click Confirm and wait for at least one collection interval.
5. Check the asset or metrics page to confirm data is reporting.

## Pre-check Commands

Broker reachability:

```bash
nc -zv <broker_host> 9092
```

Exporter reachability:

```bash
curl -sS http://127.0.0.1:9308/metrics | head
```

HTTP 200 with `kafka_broker_info`, `kafka_topic_partition_*`, `kafka_consumergroup_*`, `kafka_exporter_build_info` metrics indicates the chain is healthy.

## Field Reference

| Field | Required | Description |
| --- | --- | --- |
| Version | Yes | Kafka broker protocol version, default `2.0.0`; idempotent / transactional semantics differ across versions |
| Enable Auth | No | Switch; if enabled emits `sasl.enabled`, otherwise empty string |
| Username | Conditionally required | SASL username; required when auth is enabled |
| Password | Conditionally required | SASL password; required when auth is enabled |
| Mechanism | No | SASL mechanism, e.g. `plain` / `sha256` / `sha512` / `gssapi`; blank falls back to PLAIN |
| Listen Port | Yes | The port the exporter exposes `/metrics` on, default `9308`, NOT the Kafka broker port 9092 |
| Server Address | Yes | Broker `host:port`, e.g. `kafka:9092`; broker must be reachable via `advertised.listeners` |
| Topic Include | No | Regex for topics to scrape, default `.*` |
| Topic Exclude | No | Regex for topics to skip, default `^$` |
| Group Include | No | Regex for consumer groups to scrape, default `.*` |
| Group Exclude | No | Regex for consumer groups to skip, default `^$` |
| Interval | Yes | Collection interval in seconds, default `60` |
| Node | Yes | Collector node used for this instance |
| Instance Name | Yes | Display name in the platform; defaults to the Kafka server address |
| Group | No | Organization group for ownership/permission |

## Troubleshooting

### 1. No data after saving

- Run `curl http://127.0.0.1:9308/metrics` from the collector node and confirm the exporter exposes metrics.
- Check exporter logs for `connection refused` or `no advertised brokers`; usually caused by `advertised.listeners` pointing to an internal IP the collector cannot reach.
- When TLS is enabled, verify CA / chain matches; the certificate CN/SAN must match `tls.server-name`.
- Wait for at least one collection interval.

### 2. Authentication failures

- SASL credentials (username / password / mechanism) must match those configured on the broker via `bin/kafka-configs.sh`.
- Keep special characters in the password field; do not embed them in the broker address or other flags.
- On managed Kafka (AKS/Strimzi), the `KafkaUser` resource must declare an `authentication.type` that matches the SASL mechanism.

### 3. Partial missing metrics

- `kafka_consumergroup_*` requires `Describe Group` permission; missing means the broker rejects the request.
- `kafka_topic_partition_*` is filtered by `topic.filter/exclude`; mismatches yield no data.
- Brokers older than 0.10.1 do not support `kafka_consumergroup`; upgrade the broker.