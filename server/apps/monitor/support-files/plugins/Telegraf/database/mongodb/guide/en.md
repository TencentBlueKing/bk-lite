# MongoDB Monitoring Guide

## Prerequisites

- The target MongoDB service is up and reachable on the default port `27017`.
- The collector node can reach the MongoDB endpoint (security groups / firewalls opened).
- Confirm whether authentication is enabled: when auth is disabled, username and password may be empty; when auth is enabled, an account with read access to `serverStatus` and `dbStats` is required.
- Telegraf `inputs.mongodb` connects directly via `mongodb://user:pass@host:port/?connect=direct`. No external exporter needs to be deployed.

## Recommended Permissions

When authentication is enabled, create a dedicated read-only monitoring account with at least:

- `clusterMonitor`: read access to `serverStatus`, `replSetGetStatus`, and other cluster-level metrics.
- `read` (on target databases) or equivalent privileges to read `dbStats` / `collStats`.

Example creation (run in mongosh; extend as needed for sharded or multi-tenant clusters):

```javascript
db.getSiblingDB("admin").createUser({
  user: "monitor",
  pwd: "<password>",
  roles: [
    { role: "clusterMonitor", db: "admin" }
  ]
})
```

When auth is disabled, leave username and password empty and the template will use a credential-less connection string.

## Setup Steps

1. From the collector node, verify connectivity to the target MongoDB (use the pre-check commands below).
2. On the configuration page, fill in host, port (default `27017`), and collection interval (default `60s`).
3. If authentication is enabled, fill in the corresponding username and password; otherwise leave them empty.
4. Add rows in the monitored objects table for node, host, port, instance name, and group.
5. Click Confirm and wait for at least one collection interval.
6. Check the asset or metrics page to confirm data is reporting.

## Pre-check Commands

Without authentication:

```bash
mongosh "mongodb://<host>:<port>" --eval "db.serverStatus().ok"
```

With authentication:

```bash
mongosh "mongodb://<user>:<password>@<host>:<port>" --eval "db.serverStatus().ok"
```

If mongosh is not available, confirm port reachability with:

```bash
nc -vz <host> 27017
```

The endpoint is basically healthy when:

- `db.serverStatus().ok` returns `1`.
- Port `27017` is reachable from the collector node.

## Field Reference

| Field | Required | Description |
| --- | --- | --- |
| Username | No | Required only when authentication is enabled; leave empty otherwise |
| Password | No | Password for the username; leave empty when authentication is disabled |
| Host | Yes | MongoDB service address, e.g. `10.0.0.10` |
| Port | Yes | MongoDB port, default `27017` |
| Interval | Yes | Collection interval in seconds, default `60` |
| Node | Yes | Collector node used for this instance |
| Instance Name | Yes | Display name in the platform |
| Group | No | Organization group for ownership/permission |

## Troubleshooting

### 1. No data after saving

- Re-run the `mongosh` / `nc -vz` checks from the collector node, not only from your laptop.
- Wait for at least one collection interval.
- Confirm Telegraf / collection tasks are healthy on the node.
- Make sure the firewall or security group allows the collector node IP on port `27017`.

### 2. Authentication failures

- Check username/password for accidental spaces or character escaping issues.
- Confirm the account has the `clusterMonitor` role and can read `serverStatus`.
- If MongoDB uses SCRAM / x.509 or other auth mechanisms, verify the collector supports the configured mechanism.
- When authentication is enabled but credentials are left blank, the collector falls back to an anonymous connection — always fill in both fields.

### 3. Partial missing metrics or insufficient permissions

- The `mongodb` metrics (connections, replica set status, etc.) depend on `serverStatus`; without `clusterMonitor` this group may be empty.
- Database-level metrics (`dbStats`) require `read` privileges on the target databases — grant them as needed.
- When business database names vary widely, filter the metrics page by the `database_name` tag to confirm which databases are actually being collected.