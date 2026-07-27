# Tomcat Monitoring Guide

This plugin uses Telegraf `inputs.tomcat` to periodically scrape the Tomcat Manager status page (`/manager/status/all?XML=true`) and collect JVM memory / memory pool / connector metrics. The endpoint requires a Manager-role account (`manager-gui` or `manager-jmx`); use a dedicated read-only account in production.

## Prerequisites

- The target Tomcat is running with the Manager enabled:

  ```xml
  <!-- conf/tomcat-users.xml -->
  <role rolename="manager-gui"/>
  <user username="monitor" password="monitor-pwd" roles="manager-gui"/>
  ```

- The status servlet is loaded in the Host (the default).
- The collector node can reach the Manager port (security groups / firewalls opened).

> Telegraf emits three measurements — `tomcat_jvm_memory`, `tomcat_jvm_memorypool`, `tomcat_connector` — tagged with `source`, `name`, `type`.

## Recommended Permissions

Tomcat Manager is controlled by `conf/tomcat-users.xml`. Grant only the read-only role (`manager-gui` or the stricter `manager-status`); avoid `manager-script`, `manager-jmx`, or `admin-gui`:

```xml
<role rolename="manager-gui"/>
<role rolename="manager-status"/>
<user username="monitor" password="monitor-pwd" roles="manager-status"/>
```

Tomcat 7+ provides RemoteAddrValve to restrict remote access. Whitelist only the collector node IP:

```xml
<Context antiResourceLocking="false" privileged="true">
    <Valve className="org.apache.catalina.valves.RemoteAddrValve"
           allow="10\.0\.0\.\d+\.\d+"/>
</Context>
```

## Setup Steps

1. Verify the Manager status endpoint from the collector node:

   ```bash
   curl -u monitor:monitor-pwd "http://<host>:8080/manager/status/all?XML=true"
   ```

2. On the configure page, fill in the URL (default `http://<host>:8080/manager/status/all?XML=true`, must include `?XML=true`), username, password, and interval (default `60s`).
3. Add rows in the monitored objects table for node, URL, instance name, and group.
4. Click Confirm and wait for at least one collection interval.
5. Check the asset or metrics page to confirm data is reporting.

## Pre-check Commands

Manager status reachability:

```bash
curl -u <user>:<pwd> "http://<host>:8080/manager/status/all?XML=true"
```

HTTP 200 with an XML response indicates the endpoint is healthy.

## Field Reference

| Field | Required | Description |
| --- | --- | --- |
| URL | Yes | Tomcat Manager status URL, must include `?XML=true`, e.g. `http://10.0.0.5:8080/manager/status/all?XML=true` |
| Username | Yes | Manager login account; prefer `manager-status` |
| Password | Yes | Password for that account |
| Interval | Yes | Collection interval in seconds, default `60` |
| Node | Yes | Collector node used for this instance |
| Instance Name | Yes | Display name in the platform; defaults to the URL |
| Group | No | Organization group for ownership/permission |

## Troubleshooting

### 1. No data after saving

- Confirm the URL ends with `?XML=true`; otherwise Telegraf fails to parse the HTML.
- Confirm the Manager is enabled in `tomcat-users.xml` and that RemoteAddrValve has not blocked the collector node IP.
- Run `curl /manager/status/all?XML=true` from the collector node and verify HTTP 200 + XML.
- Wait for at least one collection interval.

### 2. Authentication failures / 403

- Tomcat 9+ restricts Manager to `127.0.0.1` / `::1` by default; edit `webapps/manager/META-INF/context.xml` to remove or widen RemoteAddrValve.
- The account must have `manager-gui` or `manager-status`; `admin-gui` alone is not enough.

### 3. Partial missing metrics

- `tomcat_connector` only lists connectors configured in `server.xml`; new connectors require a Tomcat restart.
- `tomcat_jvm_memorypool` pool names (`CodeCache`, `Metaspace`, ...) depend on the JVM (HotSpot / OpenJ9); non-HotSpot JVMs may have different dimensions.
- AJP / HTTPS connectors also appear under `tomcat_connector` and can be distinguished via the `name` tag.