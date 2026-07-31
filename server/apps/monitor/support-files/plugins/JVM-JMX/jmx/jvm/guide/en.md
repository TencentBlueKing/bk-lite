# JVM-JMX Monitoring Guide

This capability connects a JVM-JMX collector to a standard JMX/RMI service, and Telegraf then scrapes the collector's local `/metrics` endpoint.

## Prerequisites

- Remote JMX/RMI is enabled on the target Java application. Both the JMX Registry and RMI Server ports are fixed and reachable from the collector node.
- `java.rmi.server.hostname` resolves to a target address reachable from the collector node.
- If JMX authentication is enabled, prepare an account that can read standard MBeans such as `java.lang` and `java.nio`. Leave both credential fields empty when authentication is disabled.
- Reserve an unused local port on the collector node. It exposes the collector's `/metrics` endpoint and is not the target JMX port.
- The current rules collect only standard JVM MBeans in the template whitelist; application-specific MBeans are not collected automatically.

## Setup Steps

1. From the actual collector node, validate the target JMX/RMI address, fixed ports, and credentials.
2. Enter the optional username and password, the standard JMX Service URL, and the interval (default `60` seconds).
3. In the monitored objects table, select the node and enter an unused listen port, JMX URL, instance name, and optional group.
4. Save the configuration and wait for at least one collection interval.

## Pre-checks

First verify that the target port is reachable:

```bash
nc -vz app.example.com 9010
```

The corresponding standard JMX/RMI URL can be:

```text
service:jmx:rmi:///jndi/rmi://app.example.com:9010/jmxrmi
```

Then use `jconsole`, `jmc`, or another JMX client from the same collector node to connect and read standard MBeans. A Jolokia HTTP URL is not supported by this capability.

## Field Reference

| Field | Required | Description |
| --- | --- | --- |
| Username | No | Enter when JMX authentication is enabled; otherwise leave empty. |
| Password | No | Used with the JMX username; otherwise leave empty. |
| JMX URL | Yes | Standard JMX Service URL. |
| Listen Port | Yes | Local port where the collector exposes `/metrics`; it must not conflict with another instance on the same node. |
| Interval | Yes | Collection interval in seconds; default `60`. |
| Node | Yes | Node that runs the collector and can reach the target JMX/RMI service. |
| Instance Name | Yes | Display name in the platform. |
| Group | No | Optional instance group. |

## Post-setup Verification

After saving and waiting for one interval, check the local endpoint with the configured listen port, for example:

```bash
curl --fail --silent --show-error "http://127.0.0.1:9404/metrics"
```

Then confirm that these metrics are queryable in the platform:

- `jmx_scrape_error_gauge`
- `jvm_memory_usage_used_value`
- `jvm_threads_count_value`
- `jvm_gc_collectiontime_seconds_value`

## Troubleshooting

### The JMX port is reachable but collection fails

- Check that `java.rmi.server.hostname` can be resolved and reached from the collector node.
- Fix `com.sun.management.jmxremote.rmi.port` so that the RMI callback does not use an unreachable random port.
- Retry the same JMX URL from the collector node, not only from the target host.

### Authentication fails or only some metrics are present

- Leave both username and password empty when authentication is disabled.
- When authentication is enabled, confirm that the account can read the standard MBeans referenced by the whitelist.
- Application-specific MBeans are outside the current rules and require another capability or an explicit rule extension.

### The local endpoint is unavailable

- Check whether another process or monitoring instance already uses the listen port.
- Inspect the collector process arguments, generated configuration, and logs for the actual error.
