### Overview
Collects etcd basic configuration inventory (version, client port, peer port, install path, data directory, and configuration file path) and syncs it to CMDB in a standardized form. This plugin is a **JOB (SSH script)** type: it logs in, parses process parameters and `etcd --version`, then exits. It does not modify any configuration.

### Execution Mode
This plugin is a **JOB (script)** type. The execution method is selected automatically based on the target IP:

| Target | Execution method | SSH credential required |
| :--- | :--- | :--- |
| Target host **has Agent installed** (in the Node Management node list) | **Local execution**: The Agent runs the collection script directly on that host | No |
| Target host **does not have Agent installed** (not in the node list) | **SSH remote fallback**: The access point node SSHs into the target and runs the script | Yes |

> In short: hosts with Agent can be collected with zero credentials; hosts without Agent depend on the SSH account you provide for remote collection.

### Version Compatibility
- Compatible with official etcd v3.0.x+ (including v3.4.x, v3.5.x, v3.6.x, v3.7.x, etc.).

### Prerequisites
1. **Network and connectivity**
   - SSH target: the SSH port from the access point to the target is reachable (default `22`, customizable).
   - Local-execution target: the host's Agent/Executor is online in Node Management.
2. **Collection account and permissions**
   - Can run `ps` to view etcd processes and `readlink` to resolve the executable path.
   - Can run `etcd --version`.
3. **Target dependencies**
   - etcd is started.

### Procedure
#### Step 0: Entry Point
1. Go to "CMDB → Management → Auto Discovery → Collection → Professional Collection".
2. Select the **etcd** plugin and click "Add Task".

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
- In the task details, check the `Added / Updated / Deleted` summary and raw data. You should be able to query the corresponding instance under the etcd model in CMDB.

### Credential Fields
- `username`: SSH login username (required only for SSH targets).
- `password`: Password for the account above. Encrypted at rest and injected as an environment variable when dispatched; not written to plaintext config files.
- `port`: SSH port, default `22`.

### Collected Data
**etcd (etcd)**

| Key | Description |
| :--- | :--- |
| inst_name | Instance display name |
| ip_addr | Host IP |
| port | Client port |
| peer_port | Peer communication port |
| install_path | Directory of the etcd executable |
| version | etcd version |
| data_dir | Data directory |
| conf_file_path | Configuration file path in use |

> Note: `conf_file_path` is empty when etcd is not started with a configuration file. Fields such as `data_dir` and `peer_port` depend on process startup parameters and may be empty when not specified explicitly.
