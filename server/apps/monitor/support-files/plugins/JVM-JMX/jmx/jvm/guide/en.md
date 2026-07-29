# JVM-JMX Monitoring Guide

## Prerequisites

- Remote JMX/RMI is enabled on the target Java application.
- The JVM-JMX collector is installed on the collector node, and that node can reach the target JMX port.
- The JMX Registry port and RMI Server port are fixed and allowed through firewalls or security groups.
- `java.rmi.server.hostname` is set to a target address reachable from the collector node, not an address available only on the target host.
- If JMX authentication is enabled, a read-only monitoring username and password are available.
- An unused port is reserved on the collector node for the JVM-JMX collector to expose the local Prometheus `/metrics` endpoint.

Example JVM options:

```text
-Dcom.sun.management.jmxremote
-Dcom.sun.management.jmxremote.port=9010
-Dcom.sun.management.jmxremote.rmi.port=9010
-Djava.rmi.server.hostname=<reachable-target-address>
-Dcom.sun.management.jmxremote.authenticate=false
-Dcom.sun.management.jmxremote.ssl=false
```

This example disables authentication and SSL and is suitable only for a controlled test environment. In production, enable authentication according to the Java JMX security mechanism and restrict access to the JMX port.

## Setup Steps

1. From the collector node, confirm that the target JMX port is reachable and validate the connection URL with a JMX client.
2. Select the `JVM` plugin on the monitoring integration page.
3. If JMX authentication is enabled on the target Java application, enter the username and password; otherwise leave them empty.
4. Set the collection interval. The default is `60` seconds.
5. In the monitored objects table, select the collector node, enter the listen port and JMX URL, and set the instance name and optional group.
6. Save the configuration, wait for at least one collection interval, and then check the instance or metrics page.

## Pre-checks

Check the target JMX port from the actual collector node:

```bash
nc -vz <target-host> 9010
```

Example standard JMX/RMI URL:

```text
service:jmx:rmi:///jndi/rmi://<target-host>:9010/jmxrmi
```

Also connect to the same URL with `jconsole`, `jmc`, or another JMX client. The address, RMI callback, authentication, and network configuration are basically valid only when the client can connect and read MBeans in the `java.lang` and `java.nio` domains.

> This plugin connects through standard JMX/RMI. It does not accept a Jolokia HTTP URL such as `http://<host>:<port>/jolokia`.

## Field Reference

| Field | Required | Description |
| --- | --- | --- |
| Username | No | Enter when JMX authentication is enabled; otherwise leave it empty. |
| Password | No | Password for the JMX monitoring account; used together with the username. |
| JMX URL | Yes | Standard JMX Service URL, for example `service:jmx:rmi:///jndi/rmi://10.0.0.12:9010/jmxrmi`. |
| Listen Port | Yes | Local port where the JVM-JMX collector exposes `/metrics` on the selected collector node. It is not the target application's JMX port. Different instances on the same node must use different ports. |
| Interval | Yes | Collection interval in seconds. The default is `60`. |
| Node | Yes | Node that runs the JVM-JMX collector. It must be able to reach the target JMX/RMI address. |
| Instance Name | Yes | Display name of the instance in the platform. |
| Group | No | Optional group for the instance. |

For a new integration, enter the listen port and JMX URL in the monitored objects table. When editing an existing configuration, the page displays the corresponding collection fields.

## Post-setup Verification

After saving the configuration and waiting for at least one collection interval:

1. Confirm that the JVM-JMX collector process is running on the selected node and that its listen port has no conflict.
2. From the collector node, open `http://127.0.0.1:<listen-port>/metrics` and confirm that `jmx_` or `jvm_` metrics are present.
3. Confirm that `jmx_scrape_error_gauge` is `0` in the platform.
4. Confirm that at least the following JVM metrics are queryable:
   - `jvm_memory_usage_used_value`
   - `jvm_threads_count_value`
   - `jvm_gc_collectiontime_seconds_value`

The current rules cover standard MBeans for JVM memory, threads, operating system, buffer pools, garbage collection, and memory pools. Application-specific MBeans outside the whitelist are not collected automatically.

## Troubleshooting

### 1. The JMX port is reachable, but collection still fails

- Check that `java.rmi.server.hostname` resolves to an IP address or hostname reachable from the collector node.
- JMX/RMI can connect to the Registry port and then call back through a different random port. Set `com.sun.management.jmxremote.rmi.port` to a fixed port and allow it through the network boundary.
- Retry the same URL with a JMX client from the collector node, not only from the target host.

### 2. Authentication fails

- Confirm whether `com.sun.management.jmxremote.authenticate` is enabled on the target JVM.
- Check the username, password, and permissions of the JMX password and access files.
- When authentication is disabled, leave both username and password empty.

### 3. The JVM-JMX collector does not start or its local `/metrics` endpoint is unavailable

- Check whether another process or JVM monitoring instance already uses the configured listen port.
- Confirm that the selected node has the JVM-JMX collector and a Java runtime installed.
- Inspect the collector process arguments and logs to confirm that the generated configuration was loaded.

### 4. `jmx_scrape_error_gauge` is non-zero or only some metrics are available

- Check whether the target JVM version provides the standard MBeans used by the current rules.
- Confirm that the monitoring account can read the `java.lang` and `java.nio` domains.
- Application-specific MBeans and Tomcat thread-pool metrics are outside the generic JVM scope and require the corresponding monitoring capability or additional collection rules.
