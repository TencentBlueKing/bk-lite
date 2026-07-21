# ActiveMQ Monitoring Guide

This plugin uses Telegraf `inputs.activemq` to periodically call the ActiveMQ WebConsole's Console API and collect queue / topic / subscriber metrics over HTTP Basic Auth. Make sure the ActiveMQ WebConsole is enabled (default `http://<host>:8161`) and a read-only monitoring account is ready.

## Prerequisites

- The target ActiveMQ service is running; the WebConsole default port is `8161`.
- The collector node can reach the ActiveMQ host (security groups / firewalls opened).
- A monitoring account with WebConsole login privilege is ready (the default admin is `admin/admin`; switch to a read-only account in production).
- The WebConsole exposes the `admin` webadmin root path (the plugin default).

> Telegraf collects three measurements: `activemq_queues`, `activemq_topics`, and `activemq_subscribers`, tagged with `name`, `source`, `port`, `client_id`, etc.

## Recommended Permissions

The WebConsole itself uses basic authentication via the `users`/`groups`/`login.config` files. The monitoring account only needs to be able to log in; it does not need the admin role:

```text
# $ACTIVEMQ_HOME/conf/credentials.properties or users.properties
monitor=monitor_pwd
```

```text
# $ACTIVEMQ_HOME/conf/groups.properties
monitor=readonly
```

The `readonly` role is enough for the Console API; do not grant the `admin` role to a monitoring account.

## Setup Steps

1. Verify the WebConsole is reachable from the collector node:

   ```bash
   curl -u monitor:monitor_pwd http://<host>:8161/admin/
   ```

2. On the configure page, fill in the URL (default `http://<host>:8161`), username, password, and interval (default `60s`).
3. Add rows in the monitored objects table for node, URL, instance name, and group.
4. Click Confirm and wait for at least one collection interval.
5. Check the asset or metrics page to confirm data is reporting.

## Pre-check Commands

WebConsole HTTP reachability:

```bash
curl -u <user>:<pwd> http://<host>:8161/admin/xml/queues.jsp
```

HTTP 200 with ActiveMQ XML response means the endpoint is healthy.

## Field Reference

| Field | Required | Description |
| --- | --- | --- |
| URL | Yes | ActiveMQ WebConsole address, e.g. `http://10.0.0.5:8161` |
| Username | Yes | WebConsole login account |
| Password | Yes | Password for that account; no leading/trailing spaces |
| Interval | Yes | Collection interval in seconds, default `60` |
| Node | Yes | Collector node used for this instance |
| Instance Name | Yes | Display name in the platform; defaults to the URL |
| Group | No | Organization group for ownership/permission |

## Troubleshooting

### 1. No data after saving

- Confirm ActiveMQ and the WebConsole are up; port `8161` is reachable.
- Run `curl` with the configured account directly against `/admin/` from the collector node.
- Wait for at least one collection interval.
- Confirm Telegraf / collection tasks are healthy on the node.

### 2. Authentication failures

- Check the username / password for accidental spaces; remember ActiveMQ caches the user config and a restart is required after editing `credentials.properties`.
- Make sure the account is authorized in `groups.properties` to log in to `admin`.
- If JAAS is enabled, the account must also be registered in `login.config`.

### 3. Partial missing metrics

- `activemq_subscribers` depends on `client_id`; clients that connect anonymously will not be reported.
- `activemq_queues` is tagged with `name` matching the queue; once a queue is deleted its label disappears — that is normal.
- If the WebConsole's `webadmin` root path is not the default `admin`, override the Telegraf `webadmin` option accordingly.