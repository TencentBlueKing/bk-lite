# Kafka Monitoring Guide

This capability uses kafka_exporter to access brokers through the Kafka client protocol, and Telegraf then scrapes the exporter's local `/metrics` endpoint. It does not use JMX.

## Prerequisites

- The collector node can reach the configured broker `host:port` and every broker address returned through `advertised.listeners`.
- The page accepts one broker address only. It is used for cluster discovery; multiple broker entries cannot be entered on the page.
- The current page supports plaintext and SASL over plaintext. It has no TLS switch or certificate fields.
- When SASL is enabled, prepare the username, password, and mechanism that match the broker, and grant access to topic, partition, and consumer-group metadata.
- Reserve an unused exporter listen port on the collector node. It is separate from the Kafka broker port.

## Setup Steps

1. From the actual collector node, verify both the initial broker and its advertised addresses.
2. Enter a Kafka protocol version. Enable authentication and enter the SASL username, password, and mechanism when required.
3. Enter an unused listen port, one Kafka server address, topic/group include and exclude expressions, and the interval (default `60` seconds).
4. In the monitored objects table, select the node and enter the listen port, server address, instance name, and optional group.
5. Save the configuration and wait for at least one collection interval.

## Pre-checks

Check the configured broker port from the collector node, for example:

```bash
nc -vz broker.example.com 9092
```

Also run a Kafka client metadata query with the same authentication mode. Confirm that every broker address returned by the cluster is reachable from the collector node. Reachability of the initial port alone does not validate the full discovery path.

## Field Reference

| Field | Required | Description |
| --- | --- | --- |
| Version | Yes | Kafka client protocol version, such as `2.0.0`; it must be compatible with the broker. |
| Enable Authentication | No | SASL switch; disabled by default. |
| Username, Password | Conditional | Required when authentication is enabled. |
| Operation Mode | No | SASL mechanism: `plain`, `sha256`, `sha512`, or `gssapi`; empty uses PLAIN as the current exporter default. |
| Listen Port | Yes | Local port where the exporter exposes `/metrics`. |
| Server Address | Yes | One broker `host:port`. |
| Topic Include / Exclude | No | Regular expressions default to `.*` and `^$`. |
| Consumer Group Include / Exclude | No | Regular expressions default to `.*` and `^$`. |
| Interval | Yes | Collection interval in seconds; default `60`. |
| Node | Yes | Collector node that runs the exporter. |
| Instance Name | Yes | Display name in the platform. |
| Group | No | Optional instance group. |

## Post-setup Verification

After saving and waiting for one interval, check the local endpoint with the configured listen port, for example:

```bash
curl --fail --silent --show-error "http://127.0.0.1:9308/metrics"
```

Then confirm that these metrics are queryable in the platform:

- `kafka_up_gauge`
- `kafka_brokers_gauge`
- `kafka_topic_partition_count`
- `kafka_consumergroup_lag`

## Troubleshooting

### The initial broker is reachable but no data appears

- Inspect the exporter log for the broker addresses it actually uses. Collection fails when `advertised.listeners` returns addresses unreachable from the collector node.
- Confirm that the configured protocol version is compatible with the broker.
- TLS cannot be configured on the current page, so a TLS-only cluster cannot be integrated directly.

### SASL authentication fails

- Check that the authentication switch, username, password, and mechanism match the broker.
- Enter the password only in the password field; do not embed it in the server address or another field.

### Topic or consumer-group data is missing

- Check the include and exclude expressions. The default exclude expression `^$` excludes nothing.
- Confirm that the account can read topic, partition, and consumer-group metadata.
