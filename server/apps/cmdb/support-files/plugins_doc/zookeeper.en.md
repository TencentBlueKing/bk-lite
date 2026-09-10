### Overview
Collects ZooKeeper basic configuration inventory (version, client port, install/config/log/data directories, Java environment, and core cluster parameters) and syncs it to CMDB in a standardized form. This plugin is a **JOB (SSH script)** type: it logs in, parses the process and `zoo.cfg`, then exits. It does not modify any configuration.

### Execution Mode
This plugin is a **JOB (script)** type. The execution method is selected automatically based on the target IP:

| Target | Execution method | SSH credential required |
| :--- | :--- | :--- |
| Target host **has Agent installed** (in the Node Management node list) | **Local execution**: The Agent runs the collection script directly on that host | No |
| Target host **does not have Agent installed** (not in the node list) | **SSH remote fallback**: The access point node SSHs into the target and runs the script | Yes |

> In short: hosts with Agent can be collected with zero credentials; hosts without Agent depend on the SSH account you provide for remote collection.

### Version Compatibility
- Supports official ZooKeeper 3.4.x+ (including 3.6.x, 3.7.x, 3.8.x, 3.9.x, etc.).

### Prerequisites
1. **Network and connectivity**
   - SSH target: the SSH port from the access point to the target is reachable (default `22`, customizable).
   - Local-execution target: the host's Agent/Executor is online in Node Management.
2. **Collection account and permissions**
   - Can run `ps` to view ZooKeeper processes.
   - Can run `lsof` or read `/proc/<pid>/fd` to locate ports and files.
   - Can read the configuration file `zoo.cfg`.
3. **Target dependencies**
   - Java is installed on the target (required to run ZooKeeper) and `lsof` is available.
   - ZooKeeper is started.

### Procedure
#### Step 0: Entry Point
1. Go to "CMDB → Management → Auto Discovery → Collection → Professional Collection".
2. Select the **ZooKeeper** plugin and click "Add Task".

> The task actually runs on the "access point" you select; the self-check commands below should be run on the access point host.

#### Step 1: Network connectivity self-check (run on the access point, SSH targets only)
- Linux：`nc -vz <host_ip> 22`
- Windows PowerShell：`Test-NetConnection <host_ip> -Port 22`

Pass criterion: the port is reachable.

#### Step 2: Fill in the task
- **Collection target**: enter the target IP.
- **Credential**: prepare an SSH credential for targets "without Agent".
- Set timeout (default 60s) and collection interval, then save and run.

#### Step 3: Verify results
- In the task details, check the `Added / Updated / Deleted` summary and raw data. You should be able to query the corresponding instance under the ZooKeeper model in CMDB.

### Credential Fields
- `username`: SSH login username (required only for SSH targets).
- `password`: Password for the account above. Encrypted at rest and injected as an environment variable when dispatched; not written to plaintext config files.
- `port`: SSH port, default `22`.

### Collected Data
**ZooKeeper (zookeeper)**

| Key | Description |
| :--- | :--- |
| inst_name | Instance display name |
| ip_addr | Host IP |
| port | Client port (`clientPort`) |
| version | ZooKeeper version |
| install_path | Install path |
| log_path | Log directory |
| conf_path | Configuration file path |
| java_path | Java executable path |
| java_version | Java version |
| data_dir | Data directory |
| tick_time | Heartbeat interval (`tickTime`) |
| init_limit | Initial sync limit (`initLimit`) |
| sync_limit | Normal sync limit (`syncLimit`) |
| server | Cluster member list |

> Note: when `zoo.cfg` is missing corresponding items (such as `dataDir`, `tickTime`, `server.X`) or the script cannot parse them, related fields may be empty.
