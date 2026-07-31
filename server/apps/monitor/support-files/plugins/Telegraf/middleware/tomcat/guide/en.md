# Tomcat Monitoring Guide

This capability uses Telegraf `inputs.tomcat` to scrape the Tomcat Manager XML status endpoint.

## Prerequisites

- The target Tomcat enables Manager status and provides a full URL such as `http://tomcat.example.com:8080/manager/status/all?XML=true`.
- Prepare a monitoring account with only the `manager-status` role. Do not grant extra management or scripting roles for collection.
- The collector node can reach the Manager port, and RemoteAddrValve allows the actual collector source IP.
- The current page requires URL, username, and password. The URL must return XML status content.

Example four-octet regular expression that allows one collector IP:

```xml
<Valve className="org.apache.catalina.valves.RemoteAddrValve"
       allow="10\.0\.0\.25"/>
```

## Setup Steps

1. From the actual collector node, validate the XML status URL, `manager-status` account, and source-IP allow-list.
2. Enter the full URL, username, password, and interval (default `60` seconds).
3. In the monitored objects table, select the node and enter the URL, instance name, and optional group.
4. Save the configuration and wait for at least one collection interval.

## Pre-checks

This command prompts for the password:

```bash
curl --fail --silent --show-error --user monitor "http://tomcat.example.com:8080/manager/status/all?XML=true"
```

The request must return `200` and XML; `--fail` preserves `4xx/5xx` failures.

## Field Reference

| Field | Required | Description |
| --- | --- | --- |
| URL | Yes | Full Tomcat Manager XML status URL including `?XML=true`. |
| Username | Yes | Account with the `manager-status` role. |
| Password | Yes | Password for the account. |
| Interval | Yes | Collection interval in seconds; default `60`. |
| Node | Yes | Collector node that can reach Manager status. |
| Instance Name | Yes | Display name in the platform. |
| Group | No | Optional instance group. |

## Post-setup Verification

After saving and waiting for one interval, confirm that these metrics are queryable in the platform:

- `tomcat_jvm_memory_free`
- `tomcat_jvm_memorypool_used`
- `tomcat_connector_request_count_rate`
- `tomcat_connector_current_thread_utilization`

## Troubleshooting

### The endpoint returns `401` or `403`

- Confirm that the account role is consistently `manager-status`.
- Check that the RemoteAddrValve expression has four IP octets and includes the actual collector source address.

### The endpoint returns HTML or parsing fails

- Confirm that the URL contains `?XML=true` and that a reverse proxy preserves the query string.
- Reproduce with the pre-check command from the actual collector node.

### Only some data is present

- Connector and memory-pool dimensions depend on the target Tomcat and JVM configuration. Objects that do not exist produce no series.
