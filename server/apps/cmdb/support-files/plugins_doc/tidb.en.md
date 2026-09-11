### Overview
[BETA] Discovers TiDB instances on the target host via a script (JOB), reads the `tidb-server` process and related configuration, collects version, port, and basic configuration, and syncs them to CMDB in a standardized form. Collection is read-only and does not modify any target configuration.

### Execution Mode
This plugin is a **JOB (script)** type. The execution method is selected automatically based on the target IP:

| Target | Execution method | SSH credential required |
| :--- | :--- | :--- |
| Target host **has Agent installed** (in the Node Management node list) | **Local execution**: The Agent runs the collection script directly on that host | No |
| Target host **does not have Agent installed** (not in the node list) | **SSH remote fallback**: The access point node SSHs into the target and runs the script | Yes |

> In short: hosts with Agent can be collected with zero credentials; hosts without Agent depend on the SSH account you provide for remote collection.

### Version Compatibility
- Compatible with common mainstream TiDB versions; use the actually deployed version as the reference.

### Prerequisites
1. **Network and connectivity**
   - SSH target: the SSH port from the access point to the target is reachable (default `22`, customizable).
   - Local-execution target: the host's Agent/Executor is online in Node Management.
2. **Target dependencies**
   - A `tidb-server` process is running on the host.
3. **Collection permissions**
   - Can run `ps` and `ss`, and can read `tidb.toml` / `tikv.toml`. Cluster-mode detection optionally depends on `pd-ctl`.

### Procedure
#### Step 0: Entry Point
1. Go to "CMDB → Management → Auto Discovery → Collection → Professional Collection".
2. Select the **TiDB** plugin and click "Add Task".

> The task actually runs on the "access point" you select; the self-check commands below should be run on the access point host.

#### Step 1: Network connectivity self-check (run on the access point, SSH targets only)
- Linux：`nc -vz <host_ip> 22`
- Windows PowerShell：`Test-NetConnection <host_ip> -Port 22`

Pass criterion: the port is reachable.

#### Step 2: Fill in the task
- **Collection target**: enter the target IP.
- **Credential**: prepare an SSH credential for targets "without Agent".
- Set timeout and collection interval, then save and run.

#### Step 3: Verify results
- In the task details, check the `Added / Updated / Deleted` summary and raw data. You should be able to query the corresponding instance under the TiDB model in CMDB.

### Credential Fields
- `username`: SSH login username (required only for SSH targets).
- `password`: Password for the account above. Encrypted at rest and injected as an environment variable when dispatched; not written to plaintext config files.
- `port`: SSH port, default `22`.

### Collected Data
**TiDB (tidb)**

| Key | Description |
| :--- | :--- |
| inst_name | Instance display name (`{ip}-tidb-{port}`) |
| ip_addr | Host private IP |
| port | TiDB listen port (default `4000`) |
| version | TiDB version (`tidb-server -V`) |
| install_path | Install path |
| home_bash | Home directory of the startup user |
| db_max_sessions | Max sessions (`max-server-connections`) |
| redo_log | TiKV WAL directory (`wal-dir`) |
| datafile | TiKV data directory (`data-dir`) |
| mode | Deployment mode (single / cluster) |

> Note: the `mode` field's cluster/standalone detection depends on the optional tool `pd-ctl` (confirm with `pd-ctl -V`). If `pd-ctl` is not present, cluster mode may not be detected accurately and standalone is used by default. `tikv.toml` exists only in distributed deployments; standalone has only `tidb.toml`. TiKV-related fields such as `redo_log` / `datafile` may be empty when the corresponding items are not configured in the target `tikv.toml`.
