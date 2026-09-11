### Overview
[BETA] Discovers MongoDB instances on the target host via a script (JOB), reads the `mongod` process and configuration file, collects version, port, and basic configuration, and syncs them to CMDB in a standardized form. Collection is read-only and does not modify any target configuration.

### Execution Mode
This plugin is a **JOB (script)** type. The execution method is selected automatically based on the target IP:

| Target | Execution method | SSH credential required |
| :--- | :--- | :--- |
| Target host **has Agent installed** (in the Node Management node list) | **Local execution**: The Agent runs the collection script directly on that host | No |
| Target host **does not have Agent installed** (not in the node list) | **SSH remote fallback**: The access point node SSHs into the target and runs the script | Yes |

> In short: hosts with Agent can be collected with zero credentials; hosts without Agent depend on the SSH account you provide for remote collection.

### Version Compatibility
- Compatible with common mainstream MongoDB versions; use the actually deployed version as the reference.

### Prerequisites
1. **Network and connectivity**
   - SSH target: the SSH port from the access point to the target is reachable (default `22`, customizable).
   - Local-execution target: the host's Agent/Executor is online in Node Management.
2. **Target dependencies**
   - A `mongod` process is running on the host, and the configuration file (default `/etc/mongod.conf`) is readable.
   - The `mongo` shell is optional: basic information can still be collected without it. Only `database_role` (primary/secondary role, depending on `rs.status()`) may be empty, which does not affect task success.
3. **Collection permissions**
   - Being able to read `mongod` process information and the configuration file is enough. The `mongo` shell is only used to collect replica-set role and is optional.

### Procedure
#### Step 0: Entry Point
1. Go to "CMDB → Management → Auto Discovery → Collection → Professional Collection".
2. Select the **MongoDB** plugin and click "Add Task".

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
- In the task details, check the `Added / Updated / Deleted` summary and raw data. You should be able to query the corresponding instance under the MongoDB model in CMDB.

### Credential Fields
- `username`: SSH login username (required only for SSH targets).
- `password`: Password for the account above. Encrypted at rest and injected as an environment variable when dispatched; not written to plaintext config files.
- `port`: SSH port, default `22`.

### Collected Data
**MongoDB (mongodb)**

| Key | Description |
| :--- | :--- |
| inst_name | Instance display name (`{ip}-mongodb-{port}`) |
| ip_addr | Host private IP |
| port | MongoDB listen port |
| version | MongoDB version (`mongod --version`) |
| bin_path | Executable path |
| mongo_path | mongo path |
| config | Configuration file path (default `/etc/mongod.conf`) |
| fork | Whether started as a background process |
| system_log | System log configuration |
| db_path | Data directory |
| max_incoming_conn | Max incoming connections |
| database_role | Instance role (`rs.status()`) |

> Note: `database_role` depends on the mongo shell running `rs.status()`, and may be empty when the shell is unavailable or the deployment is not a replica set. Configuration fields may be empty when the corresponding items are not configured in the target configuration file.
