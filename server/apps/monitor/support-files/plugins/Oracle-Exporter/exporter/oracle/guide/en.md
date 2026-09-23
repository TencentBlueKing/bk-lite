# Oracle Monitoring Guide

This capability runs Oracle-Exporter on the selected node, and Telegraf scrapes its local `/metrics` endpoint.

## Prerequisites

- The collector node can reach the Oracle database host and actual listener port.
- Prepare a dedicated monitoring account that can log in to the specified `service_name` and read the default-metric views plus the RAC, ASM, archive, and Data Guard queries. Grant the underlying `V_$` / `DBA_` objects. Do not grant `DBA` or `SELECT ANY DICTIONARY`.
- The page requires an Oracle `service_name`, not a SID.
- Reserve an unused exporter listen port on the collector node. It is separate from the Oracle database port.
- The current page has no fields for a SID, TCPS, Wallet, or a custom connection string.

## Setup Steps

1. Have the DBA create a dedicated account in the container the collector actually connects to. Grant `V_$` / `DBA_` objects, not the `V$` synonyms. Replace `<monitor_user>` and `<password>` with site values. Do not grant `DBA` or `SELECT ANY DICTIONARY`:

```sql
CREATE USER <monitor_user> IDENTIFIED BY "<password>";
GRANT CREATE SESSION TO <monitor_user>;

-- default metrics
GRANT SELECT ON V_$INSTANCE TO <monitor_user>;
GRANT SELECT ON V_$SESSION TO <monitor_user>;
GRANT SELECT ON V_$RESOURCE_LIMIT TO <monitor_user>;
GRANT SELECT ON V_$SYSSTAT TO <monitor_user>;
GRANT SELECT ON V_$PROCESS TO <monitor_user>;
GRANT SELECT ON V_$SYSMETRIC TO <monitor_user>;
GRANT SELECT ON V_$WAITCLASSMETRIC TO <monitor_user>;
GRANT SELECT ON V_$SYSTEM_WAIT_CLASS TO <monitor_user>;
GRANT SELECT ON V_$SGA TO <monitor_user>;
GRANT SELECT ON V_$SGASTAT TO <monitor_user>;
GRANT SELECT ON V_$PGASTAT TO <monitor_user>;
GRANT SELECT ON V_$PARAMETER TO <monitor_user>;
GRANT SELECT ON V_$DATAFILE TO <monitor_user>;
GRANT SELECT ON V_$LOG_HISTORY TO <monitor_user>;
GRANT SELECT ON V_$EVENTMETRIC TO <monitor_user>;
GRANT SELECT ON V_$EVENT_NAME TO <monitor_user>;
GRANT SELECT ON V_$LOCKED_OBJECT TO <monitor_user>;
GRANT SELECT ON V_$ASM_DISKGROUP_STAT TO <monitor_user>;
GRANT SELECT ON DBA_TABLESPACE_USAGE_METRICS TO <monitor_user>;
GRANT SELECT ON DBA_TABLESPACES TO <monitor_user>;
GRANT SELECT ON DBA_INDEXES TO <monitor_user>;
GRANT SELECT ON DBA_OBJECTS TO <monitor_user>;
GRANT SELECT ON DBA_USERS TO <monitor_user>;

-- the packaged collector always starts with --isRAC --isASM --isArchiveLog --isDataGuard
GRANT SELECT ON GV_$INSTANCE TO <monitor_user>;
GRANT SELECT ON V_$ASM_DISK_STAT TO <monitor_user>;
GRANT SELECT ON V_$ASM_ALIAS TO <monitor_user>;
GRANT SELECT ON V_$ASM_DISKGROUP TO <monitor_user>;
GRANT SELECT ON V_$ASM_FILE TO <monitor_user>;
GRANT SELECT ON V_$DATAGUARD_STATS TO <monitor_user>;
GRANT SELECT ON V_$DATABASE TO <monitor_user>;
GRANT SELECT ON V_$ARCHIVE_DEST TO <monitor_user>;
```

These objects match the exporter `default_metrics.toml`, `rac_metrics.toml`, `asm_metrics.toml`, `dg_metrics.toml`, and archive queries. Use a local user for a non-CDB or a single PDB. Use a `C##` common user only when monitoring multiple containers from the CDB root.

2. From the actual collector node, validate the database host, port, `service_name`, and monitoring account.
3. Enter the username, password, service name, database host, and database port.
4. Enter an unused exporter listen port and the interval (default `60` seconds).
5. In the monitored objects table, select the node and enter the listen port, host, port, instance name, and optional group.
6. Save the configuration and wait for at least one collection interval.

## Pre-checks

Use `sqlplus` to connect to the service. The command prompts for the password, so no password is placed on the command line:

```bash
sqlplus monitor@//db.example.com:1521/ORCLPDB1
```

After login, confirm that the account can query the required dynamic performance views. You can also check the TCP port first:

```bash
nc -vz db.example.com 1521
```

## Field Reference

| Field | Required | Description |
| --- | --- | --- |
| Username | Yes | Oracle monitoring account. |
| Password | Yes | Password for the account. |
| Service Name | Yes | Oracle `service_name`, not a SID. |
| Listen Port | Yes | Local port where Oracle-Exporter exposes `/metrics`. |
| Host | Yes | Oracle database host. |
| Port | Yes | Actual Oracle database listener port. |
| Interval | Yes | Collection interval in seconds; default `60`. |
| Node | Yes | Collector node that runs Oracle-Exporter. |
| Instance Name | Yes | Display name in the platform. |
| Group | No | Optional instance group. |

## Post-setup Verification

After saving and waiting for one interval, check the local endpoint with the configured listen port, for example:

```bash
curl --fail --silent --show-error "http://127.0.0.1:9161/metrics"
```

Then confirm that these metrics are queryable in the platform:

- `oracledb_up_gauge`
- `oracledb_uptime_seconds_gauge`
- `oracledb_sessions_value_gauge`
- `oracledb_tablespace_used_percent_gauge`

## Troubleshooting

### Login fails

- Distinguish `service_name` from SID, and check the host, database port, and account state.
- Validate through the interactive password prompt to avoid a false result caused by shell escaping.

### The exporter's local endpoint is unavailable

- Do not enter the database port in the Listen Port field.
- Check for a local port conflict and inspect the Oracle-Exporter process arguments and logs.

### Only some metrics are present

- A successful login does not prove access to every dynamic performance view. Use the actual query error in the exporter log to grant the minimum required read access.
- Tablespace, session, and resource metrics depend on different views; verify both privileges and whether the target instance provides the data.
