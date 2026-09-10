### Overview
Discovers Redis instances on the target host via a script (JOB), collects version, port, and key configuration (including master/slave and topology identification), and syncs them to CMDB in a standardized form. Collection is read-only and does not modify any target configuration.

### Execution Mode
This plugin is a **JOB (script)** type. The execution method is selected automatically based on the target IP:

| Target | Execution method | SSH credential required |
| :--- | :--- | :--- |
| Target host **has Agent installed** (in the Node Management node list) | **Local execution**: The Agent runs the collection script directly on that host | No |
| Target host **does not have Agent installed** (not in the node list) | **SSH remote fallback**: The access point node SSHs into the target and runs the script | Yes |

> In short: hosts with Agent can be collected with zero credentials; hosts without Agent depend on the SSH account you provide for remote collection.

### Version Compatibility
- Compatible with common mainstream Redis versions. `username` (ACL account) requires Redis 6+; use the actually deployed version as the reference.

### Prerequisites
1. **Network and connectivity**
   - SSH target: the SSH port from the access point to the target is reachable (default `22`, customizable).
   - Local-execution target: the host's Agent/Executor is online in Node Management.
2. **Target dependencies**
   - Redis is started on the host, the install directory is readable, and `redis-cli` exists on the target host.
   - Multiple instances must listen on separate ports.
3. **Collection permissions**
   - The script runs read-only commands such as `PING` / `INFO` / `CONFIG GET` / `CLUSTER` / `SENTINEL` via `redis-cli`.
   - If Redis has `requirepass` or ACL enabled, provide the corresponding password (injected via the `REDISCLI_AUTH` environment variable, not written in plaintext on the command line).

### Procedure
#### Step 0: Entry Point
1. Go to "CMDB → Management → Auto Discovery → Collection → Professional Collection".
2. Select the **Redis** plugin and click "Add Task".

> The task actually runs on the "access point" you select; the self-check commands below should be run on the access point host.

#### Step 1: Network connectivity self-check (run on the access point, SSH targets only)
- Linux：`nc -vz <host_ip> 22`
- Windows PowerShell：`Test-NetConnection <host_ip> -Port 22`

Pass criterion: the port is reachable.

#### Step 2: Fill in the task
- **Collection target**: enter the target IP.
- **Credential**: prepare an SSH credential for targets "without Agent"; if Redis has access control, fill in the Redis port and password (and ACL username).
- Set timeout and collection interval, then save and run.

#### Step 3: Verify results
- In the task details, check the `Added / Updated / Deleted` summary and raw data. You should be able to query the corresponding instance under the Redis model in CMDB.

### Credential Fields
- `username`: Redis ACL login username (optional, Redis 6+).
- `password`: Redis access password. Encrypted at rest and injected as an environment variable (`REDISCLI_AUTH`) when dispatched; not written to plaintext config files or the command line.
- `port`: Redis listen port, default `6379`.

### Collected Data
**Redis (redis)**

| Key | Description |
| :--- | :--- |
| inst_name | Instance display name (`{ip}-redis-{port}`) |
| ip_addr | Host private IP |
| port | Redis listen port |
| version | Redis version |
| install_path | Install path (parent directory of the process executable) |
| max_conn | Max connections (`CONFIG GET maxclients`) |
| max_mem | Max memory limit (`CONFIG GET maxmemory`; 0 means unlimited) |
| database_role | Instance role (master / slave, from `INFO replication`) |
| topo_mode | Topology mode: standalone / replication / sentinel / cluster |
| cluster_uuid | Cluster identifier |
| slaves | Slave node list (when master) |
| master | Master node address (when slave) |

> Note: `slaves` has a value only when the instance is master; `master` has a value only when the instance is slave. Topology fields depend on `CLUSTER` / `SENTINEL` command output. For standalone deployments `topo_mode` is `standalone`, and cluster-related fields may be empty.
