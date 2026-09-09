### Overview
[BETA] Discovers HBase Master processes on the target host via a script (JOB), parses startup parameters and `hbase-site.xml`, collects version, port, install path, log path, Java information, and key runtime parameters, and syncs them to CMDB in a standardized form. Collection is read-only and does not modify any target configuration.

> Currently only discovers and collects **running HBase Master instances** on the target host. It does not collect RegionServer / Backup Master / cluster topology.

### Execution Mode
This plugin is a **JOB (script)** type. The execution method is selected automatically based on the target IP:

| Target | Execution method | SSH credential required |
| :--- | :--- | :--- |
| Target host **has Agent installed** (in the Node Management node list) | **Local execution**: The Agent runs the collection script directly on that host | No |
| Target host **does not have Agent installed** (not in the node list) | **SSH remote fallback**: The access point node SSHs into the target and runs the script | Yes |

> In short: hosts with Agent can be collected with zero credentials; hosts without Agent depend on the SSH account you provide for remote collection.

### Version Compatibility
- Aimed at discovering HBase Master instances on Linux. Compatible with common mainstream HBase versions; use the actually deployed version as the reference.

### Prerequisites
1. **Network and connectivity**
   - SSH target: the SSH port from the access point to the target is reachable (default `22`, customizable).
   - Local-execution target: the host's Agent/Executor is online in Node Management.
2. **Target dependencies**
   - An HBase Master process is running on the host; Java is correctly installed and `JAVA_HOME` is configured. Confirm with `echo $JAVA_HOME` and `java -version`.
3. **Collection permissions**
   - Can read `hbase-site.xml` and run `hbase version` (depends on `JAVA_HOME`).

### Procedure
#### Step 0: Entry Point
1. Go to "CMDB → Management → Auto Discovery → Collection → Professional Collection".
2. Select the **HBase** plugin and click "Add Task".

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
- In the task details, check the `Added / Updated / Deleted` summary and raw data. You should be able to query the corresponding instance under the HBase model in CMDB.

### Credential Fields
- `username`: SSH login username (required only for SSH targets).
- `password`: Password for the account above. Encrypted at rest and injected as an environment variable when dispatched; not written to plaintext config files.
- `port`: SSH port, default `22`.

### Collected Data
**HBase (hbase)**

| Key | Description |
| :--- | :--- |
| inst_name | Instance display name (`{ip}-hbase-{port}`) |
| ip_addr | Host private IP |
| port | HBase Master service port (`hbase.master.port`, default `16000`) |
| version | HBase version (`hbase version`) |
| install_path | Install path |
| log_path | Log directory |
| config_file | Absolute path of `hbase-site.xml` |
| tmp_dir | Temporary directory |
| cluster_distributed | Whether deployed as distributed |
| java_path | Java executable path |
| java_version | Java version |

> Note: the current script only discovers running HBase Master instances on the local host. It does not collect RegionServer, Backup Master, ZooKeeper topology, or HDFS relationships. If the `hbase` executable is not found, this collection returns empty results.
