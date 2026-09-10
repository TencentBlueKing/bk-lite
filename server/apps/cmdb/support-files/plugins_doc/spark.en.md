### Overview
Collects Spark instance version and key configuration via a script (listen port, install path, Web UI port, Java environment, log path, etc.) and syncs them to CMDB in a standardized form. Collection is read-only and does not modify any target configuration.

> **[BETA / Untested]** This plugin has not been fully tested. Try it in a non-production environment first and confirm the collection results match expectations before rolling it out.

### Execution Mode
This plugin is a **JOB (SSH script)** type. The execution method is selected automatically based on the target IP:

| Target | Execution method | SSH credential required |
| :--- | :--- | :--- |
| Target host **has Agent installed** (in the Node Management node list) | **Local execution**: The Agent runs the collection script directly on that host | No |
| Target host **does not have Agent installed** (not in the node list) | **SSH remote fallback**: The access point node SSHs into the target and runs the script | Yes |

> In short: hosts with Agent can be collected with zero credentials; hosts without Agent depend on the SSH account you provide for remote collection.

### Version Compatibility
- Compatible with mainstream Spark versions; verify on the target instance first.

### Prerequisites
1. **Network and connectivity**
   - SSH target: the SSH port from the access point to the target is reachable (default `22`, customizable).
   - Local-execution target: the host's Agent/Executor is online in Node Management.
2. **Collection account and permissions (required only for SSH remote)**
   - Need to be able to run `spark-shell` and have permission to read the log directory.
3. **Target dependencies**
   - Java runtime is installed on the target host.
   - A running Spark process exists on the target host.

### Procedure
#### Step 0: Entry Point
1. Go to "CMDB → Management → Auto Discovery → Collection → Professional Collection".
2. Select the **Spark** plugin and click "Add Task".

> The task actually runs on the "access point" you select; the self-check commands below should be run on the access point host.

#### Step 1: Network connectivity self-check (run on the access point, SSH targets only)
- Linux：`nc -vz <host_ip> 22`
- Windows PowerShell：`Test-NetConnection <host_ip> -Port 22`

Pass criterion: the port is reachable.

#### Step 2: Fill in the task
- **Collection target**: enter the target IP range (supports CIDR, comma-separated, and ranges).
- **Credential**: prepare an SSH credential for targets "without Agent".
- Set timeout and collection interval, then save and run.

#### Step 3: Verify results
- In the task details, check the `Added / Updated / Deleted` summary and raw data. You should be able to query the instance under the corresponding CMDB model.

### Credential Fields
- `username`: SSH login username (required only for SSH targets).
- `password`: Password for the account above. Encrypted at rest and injected as an environment variable when dispatched; not written to plaintext config files.
- `port`: SSH port, default `22`.

### Collected Data
| Key | Description |
| :--- | :--- |
| bk_inst_name | Instance display name |
| ip_addr | Host private IP |
| port | Master listen port (`--port`) |
| install_path | Install path |
| version | Spark version (`spark-shell --version`) |
| webui_port | Web UI port (`--webui-port`) |
| java_path | Java path |
| java_version | Java version |
| log_path | Log path (`-Dspark.log.dir`, or `install_path/logs`) |

> Note: `log_path` prefers the directory specified by `-Dspark.log.dir`, and falls back to `install_path/logs` when not specified. `port` and `webui_port` are parsed from process startup parameters and may be empty when not explicitly configured.
